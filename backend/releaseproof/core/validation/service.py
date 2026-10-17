"""Cross-object and schema validation for assessments."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

from releaseproof.core.domain.enums import (
    DERIVATION_RULE_REFS,
    DERIVED_EFFECT_TYPES,
    AssessmentLifecycle,
    EvaluationPhase,
    EvaluationSubjectType,
)
from releaseproof.core.domain.schemas import ValidationResult
from releaseproof.core.paths import CONTRACT_PACK

_SCHEMA_PATH = (
    CONTRACT_PACK
    / "schemas"
    / "pqc_assessment_v1_2.schema.json"
)

_ALLOWED_SCOPE: dict[str, frozenset[str]] = {
    EvaluationPhase.CURRENT.value: frozenset({EvaluationSubjectType.STATE.value}),
    EvaluationPhase.TARGET.value: frozenset({EvaluationSubjectType.STATE.value}),
    EvaluationPhase.TRANSITION.value: frozenset(
        {
            EvaluationSubjectType.STATE.value,
            EvaluationSubjectType.TRANSITION_STEP.value,
            EvaluationSubjectType.PLAN.value,
        }
    ),
}


def validate_assessment(assessment: dict[str, Any]) -> ValidationResult:
    """Validate assessment payload; return READY or BLOCKED with errors."""
    errors: list[str] = []

    if _SCHEMA_PATH.is_file():
        schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        for err in sorted(validator.iter_errors(assessment), key=lambda e: list(e.path)):
            errors.append(f"Schema: {err.message}")

    errors.extend(_validate_cross_object(assessment))

    if errors:
        return ValidationResult(
            lifecycle=AssessmentLifecycle.BLOCKED,
            errors=errors,
            ready=False,
        )
    return ValidationResult(
        lifecycle=AssessmentLifecycle.READY,
        errors=[],
        ready=True,
    )


def _validate_cross_object(assessment: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    platform = assessment.get("platform_model") or {}
    component_ids = {c["component_id"] for c in platform.get("components") or []}
    declared_surfaces = set(platform.get("declared_surface_ids") or [])
    for path in platform.get("authorization_paths") or []:
        if path.get("path_id"):
            declared_surfaces.add(path["path_id"])

    candidate = assessment.get("candidate_state") or {}
    plan = assessment.get("transition_plan") or {}
    states = plan.get("states") or []
    if states:
        final = states[-1]
        if final.get("snapshot_hash") != candidate.get("snapshot_hash"):
            errors.append("Stato finale del piano non coerente con candidate_state")

    allowed = assessment.get("allowed_change_set") or {}
    modifiable = set(allowed.get("modifiable_components") or [])

    for mode in (assessment.get("profile") or {}).get("acceptable_recovery_modes") or []:
        if mode == "NONE":
            errors.append("NONE non è una recovery accettabile per il profilo")

    derived_effects = {d["effect_id"]: d for d in assessment.get("derived_effects") or []}
    for effect in derived_effects.values():
        if effect.get("effect_type") not in DERIVED_EFFECT_TYPES:
            errors.append(f"DerivedEffect tipo non ammesso: {effect.get('effect_type')}")
        if effect.get("derivation_rule_ref") not in DERIVATION_RULE_REFS:
            errors.append("derivation_rule_ref non risolvibile")

    for step in plan.get("steps") or []:
        for action in step.get("actions") or []:
            cid = action.get("component_ref")
            if cid not in component_ids:
                errors.append(f"Action riferisce component_id inesistente: {cid}")
            elif cid not in modifiable and action.get("action_type"):
                pass
            for ref in action.get("derived_effect_refs") or []:
                if ref not in derived_effects:
                    errors.append(f"derived_effect_refs orfano: {ref}")

        for pre in step.get("preconditions") or []:
            if "allowed_by_profile" in pre:
                errors.append("allowed_by_profile non è un input: lo calcola il motore")

    for state in states:
        for path_id in state.get("authorization_path_states") or {}:
            if path_id not in declared_surfaces and path_id not in {
                p.get("path_id") for p in platform.get("authorization_paths") or []
            }:
                errors.append(f"authorization_path_states path sconosciuto: {path_id}")

    for assertion in assessment.get("coverage_assertions") or []:
        for item in assertion.get("claimed_items") or []:
            if item not in declared_surfaces:
                errors.append(f"CoverageAssertion item non nel PlatformModel: {item}")

    errors.extend(_validate_transition_delta(plan, derived_effects))

    for inv in assessment.get("invariants") or []:
        phases = inv.get("applicable_phase") or []
        if isinstance(phases, str):
            phases = [phases]
        subject_type = inv.get("subject_type")
        for phase in phases:
            if not subject_type:
                continue
            allowed_subjects = _ALLOWED_SCOPE.get(str(phase))
            if allowed_subjects and subject_type not in allowed_subjects:
                errors.append(f"Scope invariante non ammesso: {phase}/{subject_type}")

    return errors


def _accountable_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    components = {
        c["component_id"]: c.get("configuration") or {} for c in state.get("components") or []
    }
    return {
        "components": components,
        "authorization_path_states": state.get("authorization_path_states") or {},
    }


def _validate_transition_delta(
    plan: dict[str, Any],
    derived_effects: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    states_by_id = {s["state_id"]: s for s in plan.get("states") or []}
    effect_index = {e["effect_id"]: e for e in derived_effects.values()}

    for step in plan.get("steps") or []:
        from_state = states_by_id.get(step.get("from") or "")
        to_state = states_by_id.get(step.get("to") or "")
        if not from_state or not to_state:
            continue
        before = _accountable_snapshot(from_state)
        after = _accountable_snapshot(to_state)
        explained = _explained_fields(step, effect_index)
        for key in _delta_keys(before, after):
            if key not in explained:
                errors.append(
                    f"Delta non spiegato tra {step.get('from')} e {step.get('to')}: {key}"
                )
    return errors


def _delta_keys(before: dict[str, Any], after: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for comp_id in set(before["components"]) | set(after["components"]):
        if before["components"].get(comp_id) != after["components"].get(comp_id):
            keys.add(f"component:{comp_id}")
    if before["authorization_path_states"] != after["authorization_path_states"]:
        keys.add("authorization_path_states")
    return keys


def _explained_fields(step: dict[str, Any], effects: dict[str, Any]) -> set[str]:
    explained: set[str] = set()
    for action in step.get("actions") or []:
        explained.add(f"component:{action.get('component_ref')}")
        for ref in action.get("derived_effect_refs") or []:
            effect = effects.get(ref)
            if not effect:
                continue
            target = effect.get("target_ref")
            field = effect.get("affected_field") or ""
            if effect.get("effect_type") == "AUTHORIZATION_POLICY_UPDATE":
                explained.add("authorization_path_states")
            if field.startswith("configuration."):
                explained.add(f"component:{target}")
            if "authorization" in field:
                explained.add("authorization_path_states")
    return explained


__all__ = ["validate_assessment"]
