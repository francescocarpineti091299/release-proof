"""Assurance evaluation and verdict aggregation."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema

from releaseproof.core.canonical.service import compute_canonical_hash
from releaseproof.core.domain.enums import (
    AssessmentLifecycle,
    EvaluationPhase,
    EvaluationSubjectType,
    RequirementResultState,
    Verdict,
)
from releaseproof.core.domain.schemas import SemanticAssessmentResult
from releaseproof.core.explanation.service import (
    build_explanation_graph,
    merge_trust_chain,
    provenance_errors,
    sanitize_explanation_graph,
)
from releaseproof.core.rules.service import run_evaluator
from releaseproof.core.validation.service import validate_assessment
from releaseproof.core.paths import CONTRACT_PACK

_PACK = CONTRACT_PACK
_MISSING = object()

_VERDICT_RANK = {
    Verdict.INCOMPATIBLE: 4,
    Verdict.INDETERMINATE: 3,
    Verdict.CONDITIONAL: 2,
    Verdict.COMPATIBLE: 1,
}


def evaluate(assessment: dict[str, Any]) -> SemanticAssessmentResult:
    """Evaluate a validated assessment and derive scoped verdicts."""
    validation = validate_assessment(assessment)
    assessment_id = str(assessment.get("assessment_id", ""))

    if not validation.ready:
        return _emit(
            assessment,
            SemanticAssessmentResult(
                assessment_id=assessment_id,
                lifecycle=AssessmentLifecycle.BLOCKED,
                errors=validation.errors,
            ),
        )

    req_results = _evaluate_requirements(assessment)
    if _has_change_set_violation(assessment):
        plan_id = (assessment.get("transition_plan") or {}).get("plan_id", "PLAN")
        req_results.append(
            {
                "requirement_id": "REQ-CHANGE-SET",
                "phase": EvaluationPhase.TRANSITION,
                "subject_type": EvaluationSubjectType.PLAN,
                "subject_ref": plan_id,
                "state": RequirementResultState.VIOLATED,
                "critical_for_verdict": True,
                "evidence_refs": [],
                "gap_refs": [],
                "rule_refs": ["RULE-CHANGE-SET"],
                "provenance": "CONSTRAINT",
                "findings": [
                    {
                        "requirement_id": "REQ-CHANGE-SET",
                        "observation": "Azione fuori dall'AllowedChangeSet",
                    }
                ],
            }
        )
    inv_results, incomplete_reasons = _evaluate_invariants(assessment)

    if incomplete_reasons:
        return _emit(
            assessment,
            SemanticAssessmentResult(
                assessment_id=assessment_id,
                lifecycle=AssessmentLifecycle.INCOMPLETE,
                errors=incomplete_reasons,
                requirement_evaluation_results=req_results,
                invariant_evaluation_results=inv_results,
            ),
        )

    candidate_verdict = _aggregate_verdict_for_phase(
        req_results,
        inv_results,
        phase=EvaluationPhase.TARGET,
    )
    transition_verdict = _aggregate_verdict_for_phase(
        req_results,
        inv_results,
        phase=EvaluationPhase.TRANSITION,
    )
    migration_verdict = _combine_verdicts(candidate_verdict, transition_verdict)

    evidence_by_id = {e["id"]: e for e in assessment.get("evidence") or [] if e.get("id")}
    findings = [item for result in req_results for item in result.get("findings") or []]
    graph = build_explanation_graph(
        migration_verdict=migration_verdict.value,
        requirement_results=req_results,
        invariant_results=inv_results,
        evidence_by_id=evidence_by_id,
        gaps=assessment.get("evidence_gaps") or [],
        global_findings=findings,
    )
    graph = merge_trust_chain(
        graph,
        evidence=list(assessment.get("evidence") or []),
    )
    path_errors = provenance_errors(
        graph,
        requirement_results=req_results,
        invariant_results=inv_results,
        evidence_by_id=evidence_by_id,
    )
    if path_errors:
        return _emit(
            assessment,
            SemanticAssessmentResult(
                assessment_id=assessment_id,
                lifecycle=AssessmentLifecycle.INCOMPLETE,
                errors=path_errors,
                requirement_evaluation_results=req_results,
                invariant_evaluation_results=inv_results,
                explanation_graph=graph,
                findings=findings,
            ),
        )

    return _emit(
        assessment,
        SemanticAssessmentResult(
            assessment_id=assessment_id,
            lifecycle=AssessmentLifecycle.COMPLETED,
            official=False,
            migration_verdict=migration_verdict,
            candidate_verdict=candidate_verdict,
            transition_verdict=transition_verdict,
            requirement_evaluation_results=req_results,
            invariant_evaluation_results=inv_results,
            explanation_graph=graph,
            findings=findings,
        ),
    )


def _has_change_set_violation(assessment: dict[str, Any]) -> bool:
    allowed = assessment.get("allowed_change_set") or {}
    modifiable = set(allowed.get("modifiable_components") or [])
    for step in (assessment.get("transition_plan") or {}).get("steps") or []:
        for action in step.get("actions") or []:
            if action.get("component_ref") not in modifiable:
                return True
    return False


def _evaluate_requirements(assessment: dict[str, Any]) -> list[dict[str, Any]]:
    profile = assessment.get("profile") or {}
    requirements = profile.get("requirements") or []
    evidence = assessment.get("evidence") or []
    gaps = {g["gap_id"]: g for g in assessment.get("evidence_gaps") or []}
    coverage = assessment.get("coverage_assertions") or []
    results: list[dict[str, Any]] = []

    for req in requirements:
        if req.get("scope_status") != "IN_SCOPE":
            continue
        req_id = req["id"]
        wanted = set(req.get("applicable_subject_types") or [])
        critical = bool(req.get("critical_for_verdict"))
        for phase in req.get("applicable_phase") or []:
            scopes = _subject_refs_for_phase(phase, assessment)
            if wanted:
                scopes = [scope for scope in scopes if scope[0] in wanted]
            for subject_type, subject_ref in scopes:
                state, ev_refs, gap_refs = _requirement_state_for_scope(
                    req,
                    phase=phase,
                    assessment=assessment,
                    evidence=evidence,
                    coverage=coverage,
                    gaps=gaps,
                )
                findings: list[dict[str, Any]] = []
                if state == RequirementResultState.VIOLATED and not critical:
                    findings.append(
                        {
                            "requirement_id": req_id,
                            "observation": "Violazione non critica: non modifica il verdict",
                        }
                    )
                results.append(
                    {
                        "requirement_id": req_id,
                        "phase": phase,
                        "subject_type": subject_type,
                        "subject_ref": subject_ref,
                        "state": state,
                        "critical_for_verdict": critical,
                        "evidence_refs": ev_refs,
                        "gap_refs": gap_refs,
                        "rule_refs": list(req.get("rule_refs") or []),
                        "provenance": _provenance_for(ev_refs, gap_refs, evidence),
                        "findings": findings,
                    }
                )
    return results


def _subject_refs_for_phase(phase: str, assessment: dict[str, Any]) -> list[tuple[str, str]]:
    if phase == EvaluationPhase.CURRENT:
        sid = (assessment.get("deployed_state") or {}).get("state_id", "S0")
        return [(EvaluationSubjectType.STATE, sid)]
    if phase == EvaluationPhase.TARGET:
        sid = (assessment.get("candidate_state") or {}).get("state_id", "S2")
        return [(EvaluationSubjectType.STATE, sid)]
    plan_id = (assessment.get("transition_plan") or {}).get("plan_id", "PLAN")
    refs: list[tuple[str, str]] = [(EvaluationSubjectType.PLAN, plan_id)]
    for step in (assessment.get("transition_plan") or {}).get("steps") or []:
        step_id = step.get("step_id") or f"{step.get('from')}-{step.get('to')}"
        refs.append((EvaluationSubjectType.TRANSITION_STEP, step_id))
    for state in (assessment.get("transition_plan") or {}).get("states") or []:
        refs.append((EvaluationSubjectType.STATE, state.get("state_id", "")))
    return refs


def _requirement_state_for_scope(
    req: dict[str, Any],
    *,
    phase: str,
    assessment: dict[str, Any],
    evidence: list[dict[str, Any]],
    coverage: list[dict[str, Any]],
    gaps: dict[str, Any],
) -> tuple[str, list[str], list[str]]:
    policy = req.get("acceptable_evidence_policy") or {}
    groups = policy.get("required_evidence_groups") or []
    if not groups and policy.get("accepted_combinations"):
        groups = [
            {
                "role": "PRIMARY",
                "min_satisfied": 1,
                "accepted_combinations": policy["accepted_combinations"],
            }
        ]

    explicit_gap_ids = _gap_ids_for(req["id"], gaps)
    required_surfaces = set(req.get("required_surface_ids") or [])
    if required_surfaces:
        claimed: set[str] = set()
        for assertion in coverage:
            claimed.update(assertion.get("claimed_items") or [])
        if not required_surfaces.issubset(claimed):
            gap_ids = explicit_gap_ids or [f"GAP-{req['id']}-COV"]
            return RequirementResultState.UNKNOWN, [], gap_ids

    failing_hazard = _failing_hazard_ids(evidence, groups)
    admitted = _precondition_admitted(req, assessment)
    matched_evidence: list[str] = []
    for group in groups:
        min_sat = int(group.get("min_satisfied", 1))
        group_matches = [
            e["id"]
            for e in evidence
            if e.get("id") and _evidence_matches_group(e, group.get("accepted_combinations") or [])
        ]
        if len(set(group_matches)) < min_sat:
            if failing_hazard and not admitted:
                return RequirementResultState.VIOLATED, failing_hazard, []
            if admitted and policy.get("operational_precondition_allowed"):
                gap_ids = explicit_gap_ids or [f"GAP-{req['id']}-OPEN"]
                return RequirementResultState.OPEN_CONDITION, [], gap_ids
            gap_ids = explicit_gap_ids or [f"GAP-{req['id']}-UNKNOWN"]
            return RequirementResultState.UNKNOWN, [], gap_ids

    for group in groups:
        for item in evidence:
            if _evidence_matches_group(item, group.get("accepted_combinations") or []):
                matched_evidence.append(item["id"])

    # Specialized criteria outrank a generic FAIL/UNSUPPORTED match.
    # A scenario hazard must not flip an unrelated requirement such as E03.
    layout_state = _layout_requirement_state(req, evidence=evidence)
    if layout_state is not None:
        state, ev_refs = layout_state
        return state, ev_refs, []

    bound_state = _signer_bound_requirement_state(req, evidence=evidence)
    if bound_state is not None:
        state, ev_refs = bound_state
        return state, ev_refs, []

    auth_negative = _auth_negative_requirement_state(req, evidence=evidence)
    if auth_negative is not None:
        state, ev_refs = auth_negative
        return state, ev_refs, []

    primary_failures = _primary_failure_ids(evidence, groups)
    if primary_failures:
        return RequirementResultState.VIOLATED, primary_failures, []

    if matched_evidence:
        return RequirementResultState.SATISFIED, list(dict.fromkeys(matched_evidence)), []

    if explicit_gap_ids:
        return RequirementResultState.UNKNOWN, [], explicit_gap_ids
    return RequirementResultState.UNKNOWN, [], [f"GAP-{req['id']}-UNKNOWN"]


def _gap_ids_for(requirement_id: str, gaps: dict[str, Any]) -> list[str]:
    return [gap["gap_id"] for gap in gaps.values() if gap.get("requirement_id") == requirement_id]


def _precondition_admitted(req: dict[str, Any], assessment: dict[str, Any]) -> bool:
    allowed = set((assessment.get("profile") or {}).get("allowed_operational_preconditions") or [])
    for step in (assessment.get("transition_plan") or {}).get("steps") or []:
        for pre in step.get("preconditions") or []:
            if pre.get("requirement_id") == req.get("id") and pre.get("condition_id") in allowed:
                return True
    return False


def _primary_failure_ids(evidence: list[dict[str, Any]], groups: list[dict[str, Any]]) -> list[str]:
    primary = [group for group in groups if group.get("role") == "PRIMARY"]
    failing: list[str] = []
    for item in evidence:
        value = item.get("value")
        if not isinstance(value, str) or value not in {"FAIL", "UNSUPPORTED", "OVERFLOW"}:
            continue
        if not item.get("id"):
            continue
        if any(
            _evidence_matches_group(item, group.get("accepted_combinations") or [])
            for group in primary
        ):
            failing.append(item["id"])
    return failing


def _failing_hazard_ids(evidence: list[dict[str, Any]], groups: list[dict[str, Any]]) -> list[str]:
    hazard_groups = [group for group in groups if group.get("role") == "HAZARD_OBSERVATION"]
    failing: list[str] = []
    for item in evidence:
        if not item.get("id"):
            continue
        if not any(
            _evidence_matches_group(item, group.get("accepted_combinations") or [])
            for group in hazard_groups
        ):
            continue
        value = item.get("value")
        if value in {"FAIL", "OVERFLOW", "VIOLATED"} or (
            isinstance(value, str) and "FAIL" in value
        ):
            failing.append(item["id"])
    return failing


def _evidence_matches_group(evidence: dict[str, Any], combinations: list[dict[str, Any]]) -> bool:
    for combo in combinations:
        if (
            combo.get("evidence_kind")
            and evidence.get("evidence_kind") not in combo["evidence_kind"]
        ):
            continue
        if combo.get("source_role") and evidence.get("source_role") not in combo["source_role"]:
            continue
        if (
            combo.get("authority_context")
            and evidence.get("authority_context") not in combo["authority_context"]
        ):
            continue
        if (
            combo.get("acquisition_mode")
            and evidence.get("acquisition_mode") not in combo["acquisition_mode"]
        ):
            continue
        if (
            combo.get("review_status")
            and evidence.get("review_status") not in combo["review_status"]
        ):
            continue
        return True
    return False


def _evaluate_invariants(
    assessment: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Evaluate the frozen catalog. Client omissions do not remove I1–I4."""
    results: list[dict[str, Any]] = []
    incomplete: list[str] = []
    plan = assessment.get("transition_plan") or {}
    steps = plan.get("steps") or [{}]
    first_step = str(steps[0].get("step_id") or "STEP")
    state_ids = [
        state.get("state_id") if isinstance(state, dict) else str(state)
        for state in (plan.get("states") or ["S1"])
    ]
    subject_for = {
        "STATE": state_ids[1] if len(state_ids) > 1 else state_ids[0],
        "TRANSITION_STEP": first_step,
        "PLAN": str(plan.get("plan_id") or "PLAN"),
    }

    gap_catalog = assessment.get("evidence_gaps") or []
    for inv in _catalog_invariants():
        inv_id = inv["invariant_id"]
        outcome = run_evaluator(
            inv["evaluator_id"],
            context=_invariant_context(assessment, inv["evaluator_id"]),
        )
        status = outcome.get("status")
        if status == "NOT_EXECUTED":
            incomplete.append(f"Invariante {inv_id} senza result finalizzato")
            continue
        mapped = (
            RequirementResultState.UNKNOWN
            if status == "UNKNOWN"
            else RequirementResultState.VIOLATED
            if status == "VIOLATED"
            else RequirementResultState.SATISFIED
        )
        phase = inv["applicable_phase"]
        subject_ref = subject_for.get(inv["subject_type"], first_step)
        if inv["subject_type"] == "STATE" and phase == EvaluationPhase.TARGET:
            subject_ref = (assessment.get("candidate_state") or {}).get("state_id", subject_ref)
        gap_refs = [
            str(gap["gap_id"])
            for gap in gap_catalog
            if gap.get("requirement_id") == inv_id and gap.get("gap_id")
        ]
        evidence_refs = _invariant_evidence_refs(assessment, inv["evaluator_id"], mapped)
        results.append(
            {
                "invariant_id": inv_id,
                "phase": phase,
                "subject_type": inv["subject_type"],
                "subject_ref": subject_ref,
                "state": mapped,
                "critical_for_verdict": inv["critical_for_verdict"],
                "evidence_refs": evidence_refs,
                "gap_refs": gap_refs if mapped == RequirementResultState.UNKNOWN else [],
                "rule_refs": list(inv["rule_refs"]),
                "provenance": "CONSTRAINT",
                "findings": [],
            }
        )
    return results, incomplete


def _invariant_evidence_refs(
    assessment: dict[str, Any],
    evaluator_id: str,
    mapped: RequirementResultState,
) -> list[str]:
    if mapped != RequirementResultState.SATISFIED:
        return []
    if evaluator_id == "BOOTABLE_IMAGE_EXISTS":
        refs: list[str] = []
        for item in assessment.get("evidence") or []:
            if item.get("test_id") in {"E01", "E02"} and item.get("value") == "BOOT_OK":
                refs.append(str(item["id"]))
        return refs
    if evaluator_id == "NON_ATOMIC_WINDOW_HANDLED":
        for item in assessment.get("evidence") or []:
            if item.get("test_id") == "E12" and item.get("value") == "PASS":
                return [str(item["id"])]
    return []


def _invariant_context(assessment: dict[str, Any], evaluator_id: str) -> dict[str, Any]:
    context: dict[str, Any] = {
        "acceptable_recovery_modes": (assessment.get("profile") or {}).get(
            "acceptable_recovery_modes"
        ),
    }
    if evaluator_id == "RECOVERY_MODE_ACCEPTABLE" and "observed_recovery_mode" in assessment:
        context["observed_recovery_mode"] = assessment.get("observed_recovery_mode")
    if evaluator_id == "NO_CLASSICAL_ONLY_CRITICAL_AUTH_PATH":
        path_states = (assessment.get("candidate_state") or {}).get(
            "authorization_path_states"
        ) or {}
        if path_states:
            context["policy"] = next(iter(path_states.values())).get("policy")
    if evaluator_id == "BOOTABLE_IMAGE_EXISTS":
        fact = _evidence_fact(assessment, {"E01", "E02"}, {"BOOT_OK"}, {"FAIL", "NOT_BOOTABLE"})
        if fact is not _MISSING:
            context["bootable"] = fact
    if evaluator_id == "NON_ATOMIC_WINDOW_HANDLED":
        fact = _evidence_fact(assessment, {"E12"}, {"PASS"}, {"FAIL"})
        if fact is not _MISSING:
            context["non_atomic_handled"] = fact
    return context


def _evidence_fact(
    assessment: dict[str, Any],
    test_ids: set[str],
    truthy: set[str],
    falsy: set[str],
) -> Any:
    for item in assessment.get("evidence") or []:
        if item.get("test_id") not in test_ids:
            continue
        value = item.get("value")
        if value in truthy:
            return True
        if value in falsy:
            return False
        if value == "UNKNOWN":
            return "UNKNOWN"
    return _MISSING


def _aggregate_phase_verdict(
    scoped: list[dict[str, Any]],
) -> Verdict:
    if not scoped:
        return Verdict.COMPATIBLE

    for r in scoped:
        if r.get("critical_for_verdict") and r.get("state") == RequirementResultState.VIOLATED:
            return Verdict.INCOMPATIBLE
    for r in scoped:
        if r.get("critical_for_verdict") and r.get("state") == RequirementResultState.UNKNOWN:
            return Verdict.INDETERMINATE
    for r in scoped:
        if r.get("state") == RequirementResultState.OPEN_CONDITION:
            return Verdict.CONDITIONAL
    return Verdict.COMPATIBLE


def _aggregate_verdict_for_phase(
    req_results: list[dict[str, Any]],
    inv_results: list[dict[str, Any]],
    *,
    phase: str,
) -> Verdict:
    req_scoped = [r for r in req_results if r.get("phase") == phase]
    inv_scoped = [r for r in inv_results if r.get("phase") == phase]
    return _combine_verdicts(
        _aggregate_phase_verdict(req_scoped),
        _aggregate_phase_verdict(inv_scoped),
    )


def _combine_verdicts(a: Verdict, b: Verdict) -> Verdict:
    return a if _VERDICT_RANK[a] >= _VERDICT_RANK[b] else b


def _layout_sizes_from_evidence(
    evidence: list[dict[str, Any]],
) -> dict[str, int] | None:
    signed: int | None = None
    capacity: int | None = None
    for item in evidence:
        if item.get("test_id") != "E05" and "LAYOUT" not in str(item.get("id", "")):
            continue
        value = item.get("value")
        if isinstance(value, dict):
            if value.get("signed_artifact_size") is not None:
                signed = int(value["signed_artifact_size"])
            if value.get("boot_slot_capacity") is not None:
                capacity = int(value["boot_slot_capacity"])
        elif isinstance(value, int | float) and item.get("test_id") == "E05":
            signed = int(value)
    if signed is None or capacity is None:
        return None
    return {"signed_artifact_size": signed, "boot_slot_capacity": capacity}


def _layout_requirement_state(
    req: dict[str, Any],
    *,
    evidence: list[dict[str, Any]],
) -> tuple[str, list[str]] | None:
    if "RULE-LAYOUT" not in (req.get("rule_refs") or []):
        return None
    sizes = _layout_sizes_from_evidence(evidence)
    if sizes is None:
        legacy = [
            item
            for item in evidence
            if item.get("id") == "EV-LAYOUT" or "LAYOUT" in str(item.get("id", ""))
        ]
        if not legacy:
            return None
        if any(item.get("value") == "FAIL" for item in legacy):
            return RequirementResultState.VIOLATED, [legacy[0]["id"]]
        if any(item.get("value") == "PASS" for item in legacy):
            return RequirementResultState.SATISFIED, [legacy[0]["id"]]
        return None
    outcome = run_evaluator("LEQ", context=sizes)
    status = outcome.get("status")
    refs = [
        item["id"]
        for item in evidence
        if item.get("id") and item.get("test_id") == "E05"
    ]
    if status == "VIOLATED":
        return RequirementResultState.VIOLATED, refs or ["EV-LAYOUT"]
    if status == "UNKNOWN":
        return RequirementResultState.UNKNOWN, refs
    return RequirementResultState.SATISFIED, refs or ["EV-LAYOUT"]


def _auth_negative_requirement_state(
    req: dict[str, Any],
    *,
    evidence: list[dict[str, Any]],
) -> tuple[str, list[str]] | None:
    """Key-mismatch boot must reject (E03 PANIC), not accept a bad image."""
    if "RULE-AUTH-NEGATIVE" not in (req.get("rule_refs") or []):
        return None
    found = next((item for item in evidence if item.get("id") == "EV-E03-PANIC"), None)
    if found is None:
        # D05 (additive): live runners emit E03 evidence under run-scoped IDs.
        found = next((item for item in evidence if item.get("test_id") == "E03"), None)
    if found is None:
        return RequirementResultState.UNKNOWN, []
    value = found.get("value")
    if value == "REJECT":
        return RequirementResultState.SATISFIED, [found["id"]]
    if value in {"ACCEPT", "PASS", "BOOT_OK"}:
        return RequirementResultState.VIOLATED, [found["id"]]
    return RequirementResultState.UNKNOWN, [found["id"]]


def _signer_bound_requirement_state(
    req: dict[str, Any],
    *,
    evidence: list[dict[str, Any]],
) -> tuple[str, list[str]] | None:
    """LEQ on the signer's stated image size and its stated maximum.

    The operands are the tool's refusal line. There is no signed file size.
    """
    if "RULE-SIGN-BOUND" not in (req.get("rule_refs") or []):
        return None
    found = next(
        (item for item in evidence if item.get("id") == "EV-A4-SIGNER-BOUND"),
        None,
    )
    if found is None:
        # D05 (additive): live runners emit signer-bound evidence under run-scoped IDs.
        found = next((item for item in evidence if item.get("test_id") == "A4"), None)
    if found is None:
        return None
    value = found.get("value")
    if not isinstance(value, dict) or value.get("signing_result") != "REJECTED":
        return RequirementResultState.UNKNOWN, [found["id"]]
    outcome = run_evaluator(
        "LEQ",
        context={
            "requested_image_size": value.get("requested_image_size"),
            "max_signable_image_size": value.get("max_signable_image_size"),
        },
    )
    status = outcome.get("status")
    if status == "VIOLATED":
        return RequirementResultState.VIOLATED, [found["id"]]
    if status == "UNKNOWN":
        return RequirementResultState.UNKNOWN, [found["id"]]
    if status == "SATISFIED":
        return RequirementResultState.SATISFIED, [found["id"]]
    return RequirementResultState.UNKNOWN, [found["id"]]


def _provenance_for(
    evidence_refs: list[str],
    gap_refs: list[str],
    evidence: list[dict[str, Any]],
) -> str:
    by_id = {item.get("id"): item for item in evidence}
    if evidence_refs:
        kinds = {by_id.get(ref, {}).get("evidence_kind") for ref in evidence_refs}
        if "MEASUREMENT" in kinds:
            return "MEASUREMENT"
        return "DECLARATION"
    if gap_refs:
        return "GAP"
    return "CONSTRAINT"


def _emit(
    assessment: dict[str, Any],
    result: SemanticAssessmentResult,
) -> SemanticAssessmentResult:
    conditions = _condition_evaluations(assessment)
    graph = result.explanation_graph
    if "nodes" not in graph or "edges" not in graph:
        graph = {"nodes": [], "edges": []}
    graph = sanitize_explanation_graph(graph)
    result = result.model_copy(update={"conditions": conditions, "explanation_graph": graph})
    document = result.model_dump(mode="json")
    document.pop("canonical_hash", None)
    document["candidate_state_assurance"] = (
        {"verdict": document["candidate_verdict"]} if document.get("candidate_verdict") else None
    )
    document["transition_plan_assurance"] = (
        {"verdict": document["transition_verdict"]} if document.get("transition_verdict") else None
    )
    digest = compute_canonical_hash(document)
    document["canonical_hash"] = digest
    errors = list(jsonschema.Draft202012Validator(_result_schema()).iter_errors(document))
    if errors:
        raise RuntimeError(errors[0].message)
    return result.model_copy(update={"canonical_hash": digest})


def _condition_evaluations(assessment: dict[str, Any]) -> list[dict[str, Any]]:
    allowed = set((assessment.get("profile") or {}).get("allowed_operational_preconditions") or [])
    evaluations: list[dict[str, Any]] = []
    for step in (assessment.get("transition_plan") or {}).get("steps") or []:
        for pre in step.get("preconditions") or []:
            condition_id = pre.get("condition_id")
            if not condition_id:
                continue
            evaluations.append(
                {
                    "condition_id": condition_id,
                    "step_id": str(step.get("step_id") or ""),
                    "requirement_id": str(pre.get("requirement_id") or ""),
                    "allowed_by_profile": condition_id in allowed,
                }
            )
    return evaluations


@lru_cache(maxsize=1)
def _catalog_invariants() -> tuple[dict[str, Any], ...]:
    ruleset = json.loads((_PACK / "examples" / "ruleset_v1_2.json").read_text(encoding="utf-8"))
    by_id = {rule["rule_id"]: rule for rule in ruleset["rules"]}
    catalog: list[dict[str, Any]] = []
    for invariant_id in ruleset["required_invariants"]:
        rule = by_id[invariant_id]
        for phase in rule["applicable_phase"]:
            catalog.append(
                {
                    "invariant_id": invariant_id,
                    "evaluator_id": rule["evaluator_id"],
                    "critical_for_verdict": rule["critical_for_verdict"],
                    "applicable_phase": phase,
                    "subject_type": rule["subject_type"],
                    "rule_refs": rule["invariant_refs"],
                }
            )
    return tuple(catalog)


@lru_cache(maxsize=1)
def _result_schema() -> dict[str, Any]:
    path = _PACK / "schemas" / "semantic_result_v1_2.schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = ["evaluate"]
