"""Project live runner facts into V1.2 evidence, requirements and plans.

Coverage assertions require decisive observations; absent facts become UNOBSERVED
rows and explicit gaps. Evidence groups use narrow acquisition modes, and failure
tokens belong only to the requirement's primary measurement.

I1 and I4 inputs are emitted even when missing, so the engine can evaluate them as
UNKNOWN rather than omit them. EMULATED verdict rows use scalar values; structured
measurements remain informational.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterable
from typing import Any

from releaseproof.contracts.profile import ChangeScenario, Profile
from releaseproof.contracts.runner import ArtifactEvent, Observation, Origin, TestResultEvent
from releaseproof.contracts.services import AdapterError
from releaseproof.core.canonical.service import compute_canonical_hash

UNKNOWN = "UNKNOWN"
DEFAULT_PLAN = "__default__"

RULESET_REF = {"id": "RULESET-V1.2", "version": "1.2", "hash": "version-pin:ruleset-v1.2"}
ACCEPTABLE_RECOVERY_MODES = ["FIELD_SERVICE", "DEPOT_PHYSICAL_REFLASH"]
PLATFORM_RECOVERY_MODES = ["FIELD_SERVICE", "DEPOT_PHYSICAL_REFLASH", "UNKNOWN"]

# Coverage surfaces (declared in the PlatformModel, claimed only by decisive observations).
SURFACE_BOOT_SLOT = "boot-slot-capacity"
SURFACE_BL_UPDATE = "bootloader-update-path"
SURFACE_VERIFIER_NEGATIVE = "deployed-verifier-negative"
SURFACE_CANDIDATE_BOOT = "candidate-boot"
SURFACE_CANDIDATE_PQC = "candidate-pqc-verifier"
SURFACE_HYBRID_BUILD = "hybrid-verifier-build"
SURFACE_RAM = "ram-budget"
BASE_SURFACES = ["fw-boot", "fw-update", "recovery"]
ALL_SURFACES = BASE_SURFACES + [
    SURFACE_BOOT_SLOT,
    SURFACE_BL_UPDATE,
    SURFACE_VERIFIER_NEGATIVE,
    SURFACE_CANDIDATE_BOOT,
    SURFACE_CANDIDATE_PQC,
    SURFACE_HYBRID_BUILD,
    SURFACE_RAM,
]

COND_MAINTENANCE = "COND-MAINTENANCE-WINDOW"
REQ_MAINTENANCE = "REQ-MAINTENANCE-WINDOW"

_HEX40 = re.compile(r"^[0-9a-f]{7,40}$")


class Facts:
    """Index of one LIVE run's observations, artifacts and test results.

    Observations with origin ``AI_PROPOSAL`` are not facts and are ignored. Duplicate
    ``(test_id, fact)`` observations must agree, otherwise the run cannot be projected.
    """

    def __init__(
        self,
        observations: Iterable[Observation | dict[str, Any]],
        artifacts: Iterable[ArtifactEvent | dict[str, Any]],
        test_results: Iterable[TestResultEvent | dict[str, Any]],
    ) -> None:
        self._obs: dict[tuple[str, str], Observation] = {}
        for obs in sorted(coerce_observations(observations), key=lambda o: o.observation_id):
            if obs.origin == Origin.AI_PROPOSAL:
                continue
            key = (obs.test_id, obs.fact)
            previous = self._obs.get(key)
            if previous is not None and previous.value != obs.value:
                raise AdapterError(
                    f"conflicting observations for {key[0]}/{key[1]}: "
                    f"{previous.observation_id} vs {obs.observation_id}"
                )
            self._obs.setdefault(key, obs)
        self._artifacts: dict[str, ArtifactEvent] = {}
        for art in coerce_artifacts(artifacts):
            known = self._artifacts.get(art.artifact_id)
            if known is not None and known.sha256 != art.sha256:
                raise AdapterError(f"artifact {art.artifact_id} reported with two digests")
            self._artifacts.setdefault(art.artifact_id, art)
        self._results: dict[str, TestResultEvent] = {}
        for result in sorted(_coerce(test_results, TestResultEvent), key=lambda r: r.seq):
            self._results[result.test_id] = result

    def get(self, test_id: str, fact: str) -> Observation | None:
        return self._obs.get((test_id, fact))

    def value(self, test_id: str, fact: str) -> Any:
        obs = self.get(test_id, fact)
        return None if obs is None else obs.value

    def sources(self, obs: Observation | None) -> list[ArtifactEvent]:
        if obs is None:
            return []
        return [self._artifacts[a] for a in obs.source_artifact_ids if a in self._artifacts]

    def artifact_sha(self, obs: Observation | None) -> str | None:
        arts = self.sources(obs)
        return arts[0].sha256 if arts else None

    def result(self, test_id: str) -> TestResultEvent | None:
        return self._results.get(test_id)

    def why_missing(self, test_id: str, fact: str) -> str:
        """Human-readable reason a decisive fact is absent or UNKNOWN."""
        obs = self.get(test_id, fact)
        result = self.result(test_id)
        parts: list[str] = []
        if obs is None:
            parts.append(f"{test_id} {fact} was not observed in this run")
        else:
            parts.append(f"{test_id} {fact} was reported as {obs.value!r} (not decisive)")
        if result is not None:
            detail = f"test_result {result.outcome.value}"
            if result.failure_class is not None:
                detail += f" ({result.failure_class.value})"
            parts.append(detail)
        else:
            parts.append("no test_result")
        return "; ".join(parts)


def _coerce(items: Iterable[Any], model: type) -> list[Any]:
    return [item if isinstance(item, model) else model.model_validate(item) for item in items]


def coerce_observations(items: Iterable[Observation | dict[str, Any]]) -> list[Observation]:
    return _coerce(items, Observation)


def coerce_artifacts(items: Iterable[ArtifactEvent | dict[str, Any]]) -> list[ArtifactEvent]:
    return _coerce(items, ArtifactEvent)


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class EvidenceSet:
    """Collects evidence rows, coverage assertions and evidence gaps for one assessment."""

    def __init__(self, facts: Facts, evidence_run_id: str) -> None:
        self.facts = facts
        self.run_id = evidence_run_id
        self.leading: list[dict[str, Any]] = []
        self.rows: list[dict[str, Any]] = []
        self.coverage: list[dict[str, Any]] = []
        self.gaps: list[dict[str, Any]] = []

    def observed(
        self,
        evidence_id: str,
        obs: Observation,
        value: Any,
        *,
        test_id: str | None = None,
    ) -> dict[str, Any]:
        """A measurement row linked to its run and source artifacts."""
        declared = obs.origin == Origin.DECLARED
        row: dict[str, Any] = {
            "id": evidence_id,
            "evidence_kind": "DECLARATION" if declared else "MEASUREMENT",
            "source_role": "TOOL",
            "authority_context": "DECLARED" if declared else "OBSERVED",
            "acquisition_mode": obs.acquisition_mode,
            "review_status": "AUTOMATIC",
            "status": "VALID",
            "source_identity": obs.parser,
            "value": value,
            "test_id": test_id or obs.test_id,
            "run_id": self.run_id,
        }
        self._attach_artifacts(row, obs)
        return row

    def not_observed(
        self,
        evidence_id: str,
        test_id: str,
        obs: Observation | None = None,
    ) -> dict[str, Any]:
        """Placeholder for a fact the run did not establish (value UNKNOWN).

        When the runner did report the fact (as UNKNOWN) the row keeps its run and artifact
        linkage for traceability; no requirement group accepts ``NOT_OBSERVED`` rows.
        """
        row: dict[str, Any] = {
            "id": evidence_id,
            "evidence_kind": "MEASUREMENT",
            "source_role": "TOOL",
            "authority_context": "NOT_OBSERVED",
            "acquisition_mode": "UNOBSERVED",
            "review_status": "AUTOMATIC",
            "status": "VALID",
            "test_id": test_id,
            "value": UNKNOWN,
        }
        if obs is not None:
            row["run_id"] = self.run_id
            row["source_identity"] = obs.parser
            self._attach_artifacts(row, obs)
        return row

    def _attach_artifacts(self, row: dict[str, Any], obs: Observation) -> None:
        arts = self.facts.sources(obs)
        if arts:
            row["artifact_refs"] = [a.name for a in arts]
            row["content_hash"] = f"sha256:{arts[0].sha256}"

    def add(self, row: dict[str, Any]) -> dict[str, Any]:
        self.rows.append(row)
        return row

    def add_dict_fact(
        self, evidence_id: str, test_id: str, fact: str, key: str | None = None
    ) -> Any:
        """Informational fact wrapped in a dict (never read as a verdict token). Omitted when
        missing or UNKNOWN: it gates no requirement and must not shadow I1 inputs."""
        obs = self.facts.get(test_id, fact)
        if obs is None or obs.value is None or obs.value == UNKNOWN:
            return None
        self.add(self.observed(evidence_id, obs, {key or fact: obs.value}))
        return obs.value

    def add_scalar_fact(self, evidence_id: str, test_id: str, fact: str) -> int | None:
        """Keep an integer measurement as a scalar; omit absent or non-integer values."""
        obs = self.facts.get(test_id, fact)
        if obs is None or not is_int(obs.value):
            return None
        self.add(self.observed(evidence_id, obs, obs.value))
        return obs.value

    def add_identity_fact(self, evidence_id: str, test_id: str, fact: str) -> str | None:
        """Source pin (commit sha) kept as a raw string value, like the freeze EV-PIN row."""
        obs = self.facts.get(test_id, fact)
        if obs is None or not isinstance(obs.value, str) or obs.value in {"", UNKNOWN}:
            return None
        self.add(self.observed(evidence_id, obs, obs.value))
        return obs.value

    def add_enum_fact(
        self,
        evidence_id: str,
        test_id: str,
        fact: str,
        mapping: dict[str, str],
        *,
        emit_missing: bool = False,
    ) -> str | None:
        """Map a CAPS enumeration fact onto an evidence value.

        Returns the mapped value when decisive, otherwise None (row emitted as
        NOT_OBSERVED when reported, or when ``emit_missing``).
        """
        obs = self.facts.get(test_id, fact)
        raw = None if obs is None else obs.value
        if isinstance(raw, str) and raw in mapping:
            mapped = mapping[raw]
            self.add(self.observed(evidence_id, obs, mapped))  # type: ignore[arg-type]
            return mapped
        if obs is not None or emit_missing:
            self.add(self.not_observed(evidence_id, test_id, obs))
        return None

    def cover(self, surface: str, obs: Observation, *, subject: str, scope: str) -> None:
        assertion: dict[str, Any] = {
            "assertion_id": f"COV-{obs.test_id}-{surface}",
            "claimed_items": [surface],
            "subject": subject,
            "scope": scope,
            "source_role": "TOOL",
            "authority_context": "OBSERVED",
            "source_ref": obs.observation_id,
            "review_status": "AUTOMATIC",
        }
        sha = self.facts.artifact_sha(obs)
        if sha:
            assertion["content_hash"] = f"sha256:{sha}"
        self.coverage.append(assertion)

    def gap(
        self,
        gap_id: str,
        requirement_id: str,
        reason: str,
        *,
        critical: bool,
        requested: str,
        gap_type: str = "UNKNOWN_FACT",
    ) -> None:
        self.gaps.append(
            {
                "gap_id": gap_id,
                "requirement_id": requirement_id,
                "gap_type": gap_type,
                "reason": reason,
                "critical": critical,
                "requested_evidence": requested,
            }
        )

    def missing_gap(
        self,
        gap_id: str,
        requirement_id: str,
        test_id: str,
        fact: str,
        *,
        critical: bool,
        requested: str,
    ) -> None:
        gap_type = "UNKNOWN_FACT" if self.facts.get(test_id, fact) else "NOT_OBSERVED"
        self.gap(
            gap_id,
            requirement_id,
            self.facts.why_missing(test_id, fact),
            critical=critical,
            requested=requested,
            gap_type=gap_type,
        )

    def evidence(self) -> list[dict[str, Any]]:
        return [*self.leading, *self.rows]


_BOOT_RANK = {"FAIL": 0, "NOT_BOOTABLE": 0, UNKNOWN: 1, "BOOT_OK": 2}


def boot_rows(
    ev: EvidenceSet,
    specs: list[tuple[str, str, str]],
) -> dict[str, str]:
    """Emit the I1 input rows ``(evidence_id, test_id, failure_token)``; return test_id → value.

    INV-I1 takes the *first* E01/E02 row with a decisive value. Rows are placed first in the
    evidence list, worst outcome first, so I1 reads as the conjunction "every observed state
    boots" (any failure → VIOLATED, else any unknown → UNKNOWN). The failure token differs by
    role: the candidate boot (E02) is also the primary measurement of REQ-CANDIDATE-BOOT and
    uses ``FAIL``; the deployed boot (E01) uses ``NOT_BOOTABLE`` (I1-falsy, not a generic
    failure token) so a broken deployed image cannot violate candidate requirements.
    """
    produced: list[tuple[int, int, dict[str, Any]]] = []
    values: dict[str, str] = {}
    for order, (evidence_id, test_id, failure_token) in enumerate(specs):
        obs = ev.facts.get(test_id, "boot_outcome")
        raw = None if obs is None else obs.value
        if raw == "BOOT_OK":
            row = ev.observed(evidence_id, obs, "BOOT_OK")  # type: ignore[arg-type]
            value = "BOOT_OK"
        elif raw == "FAIL":
            row = ev.observed(evidence_id, obs, failure_token)  # type: ignore[arg-type]
            value = failure_token
        else:
            row = ev.not_observed(evidence_id, test_id, obs)
            value = UNKNOWN
        values[test_id] = value
        produced.append((_BOOT_RANK[value], order, row))
    ev.leading = [row for _, _, row in sorted(produced, key=lambda item: (item[0], item[1]))]
    return values


def e12_placeholder(ev: EvidenceSet) -> None:
    """INV-I4 input: no catalog test interrupts an update, so the window is never observed."""
    ev.add(ev.not_observed("EV-E12-WINDOW", "E12"))


def combo(
    acquisition: list[str],
    *,
    kinds: tuple[str, ...] = ("MEASUREMENT",),
    roles: tuple[str, ...] = ("TOOL",),
    authority: tuple[str, ...] = ("OBSERVED",),
    review: tuple[str, ...] = ("AUTOMATIC",),
) -> dict[str, Any]:
    return {
        "evidence_kind": list(kinds),
        "source_role": list(roles),
        "authority_context": list(authority),
        "acquisition_mode": list(acquisition),
        "review_status": list(review),
    }


def requirement(
    req_id: str,
    *,
    risk: str,
    phases: list[str],
    critical: bool,
    criterion: str,
    rule: str,
    acquisition: list[str],
    surfaces: list[str] | None = None,
    subject_types: list[str] | None = None,
    scope: str = "IN_SCOPE",
) -> dict[str, Any]:
    req: dict[str, Any] = {
        "id": req_id,
        "risk_category": risk,
        "applicable_phase": phases,
        "critical_for_verdict": critical,
        "criterion": criterion,
        "scope_status": scope,
        "rule_refs": [rule],
        "acceptable_evidence_policy": {
            "required_evidence_groups": [
                {
                    "role": "PRIMARY",
                    "min_satisfied": 1,
                    "accepted_combinations": [combo(acquisition)],
                }
            ]
        },
    }
    if subject_types:
        req["applicable_subject_types"] = subject_types
    if surfaces:
        req["required_surface_ids"] = surfaces
    return req


def layout_requirement() -> dict[str, Any]:
    return requirement(
        "REQ-LAYOUT",
        risk="LAYOUT_STORAGE",
        phases=["TARGET", "TRANSITION"],
        critical=True,
        criterion="Signed candidate image fits the boot slot (E05, LEQ on measured sizes)",
        rule="RULE-LAYOUT",
        acquisition=["STATIC_ARTIFACT", "STATIC_ANALYSIS"],
        surfaces=[SURFACE_BOOT_SLOT],
    )


def auth_negative_requirement() -> dict[str, Any]:
    """E03 measures the *deployed* verifier, which authenticates the migration update until it
    is replaced, so it is scoped to the transition plan (not the candidate state) and critical:
    a verifier that accepts a tampered image cannot carry a signature migration."""
    return requirement(
        "REQ-AUTH-NEGATIVE",
        risk="AUTHENTICITY_SIGNATURE",
        phases=["TRANSITION"],
        subject_types=["PLAN"],
        critical=True,
        criterion="Deployed verifier rejects a tampered signed image (E03)",
        rule="RULE-AUTH-NEGATIVE",
        acquisition=["EMULATED"],
        surfaces=[SURFACE_VERIFIER_NEGATIVE],
    )


def ram_requirement() -> dict[str, Any]:
    return requirement(
        "REQ-RAM",
        risk="RUNTIME_RESOURCES",
        phases=["TARGET"],
        critical=False,
        criterion="RAM/stack within budget (no runtime stack measurement in this run)",
        rule="RULE-RAM",
        acquisition=["STATIC_ANALYSIS"],
        surfaces=[SURFACE_RAM],
    )


def maintenance_requirement(criterion: str) -> dict[str, Any]:
    """Operational precondition admitted by the profile for service-based plans.

    Same shape as the reference SCENARIO-CONDITIONAL: closure needs a confirmed
    system-owner declaration, which a runner can never produce, so the result is
    OPEN_CONDITION while the precondition is admitted.
    """
    return {
        "id": REQ_MAINTENANCE,
        "risk_category": "UPDATE_ROLLBACK_RECOVERY",
        "applicable_phase": ["TRANSITION"],
        "applicable_subject_types": ["PLAN"],
        "critical_for_verdict": True,
        "criterion": criterion,
        "scope_status": "IN_SCOPE",
        "rule_refs": ["RULE-MAINTENANCE-WINDOW"],
        "acceptable_evidence_policy": {
            "required_evidence_groups": [
                {
                    "role": "HAZARD_OBSERVATION",
                    "min_satisfied": 1,
                    "accepted_combinations": [combo(["EMULATED"])],
                },
                {
                    "role": "CONDITION_CLOSURE",
                    "min_satisfied": 1,
                    "accepted_combinations": [
                        combo(
                            ["DOCUMENTARY"],
                            kinds=("DECLARATION",),
                            roles=("SYSTEM_OWNER",),
                            authority=("SIMULATED",),
                            review=("CONFIRMED",),
                        )
                    ],
                },
            ],
            "operational_precondition_allowed": True,
        },
    }


def maintenance_precondition(closure_action: str) -> dict[str, Any]:
    return {
        "condition_id": COND_MAINTENANCE,
        "condition_type": "OPERATIONAL_PRECONDITION",
        "requirement_id": REQ_MAINTENANCE,
        "closure_action": closure_action,
        "acceptance_criterion": "No uncontrolled power loss or interruption during the re-flash",
        "responsible_role": "SYSTEM_OWNER",
    }


def recovery_declaration(
    *, profile: Profile, change: ChangeScenario, plan_id: str, mode: str
) -> dict[str, Any]:
    """The plan *declares* its recovery mode; it is not measured. Reuses the reference id
    ``EV-SCENARIO-RECOVERY`` so the trust chain shows recovery as DECLARED. It does not match
    the maintenance closure group (not a confirmed system-owner statement)."""
    return {
        "id": "EV-SCENARIO-RECOVERY",
        "evidence_kind": "DECLARATION",
        "source_role": "PROFILE_PLAN",
        "authority_context": "DECLARED",
        "acquisition_mode": "DOCUMENTARY",
        "review_status": "UNREVIEWED",
        "status": "VALID",
        "source_identity": f"{profile.id}@{profile.version}:{change.change_id}:{plan_id}",
        "value": mode,
    }


def maintenance_gap(ev: EvidenceSet) -> None:
    ev.gap(
        "GAP-MAINTENANCE-WINDOW-CLOSURE",
        REQ_MAINTENANCE,
        "Service window admitted by the profile; no confirmed system-owner closure evidence",
        critical=True,
        requested="Confirmed system-owner record of the controlled service window",
        gap_type="OPEN_CONDITION",
    )


def standard_gaps(ev: EvidenceSet, *, include_e10: bool) -> None:
    ev.gap(
        "GAP-E07-RAM",
        "REQ-RAM",
        "No runtime RAM/stack measurement in the test catalog",
        critical=False,
        requested="E07 RAM/stack method beyond static linker region",
        gap_type="NOT_EXECUTABLE",
    )
    if include_e10:
        ev.gap(
            "GAP-E10-INTERRUPT",
            "INV-I4",
            "No interrupted firmware update is executed by this runner",
            critical=True,
            requested="E10 event-based interruption with stable UART",
            gap_type="NOT_EXECUTABLE",
        )
    ev.gap(
        "GAP-E12-NON-ATOMIC",
        "INV-I4",
        "Non-atomic update window not observed; I4 remains UNKNOWN",
        critical=True,
        requested="E12 interrupted update with observed recovery",
        gap_type="NOT_EXECUTABLE",
    )


def sealed(state: dict[str, Any]) -> dict[str, Any]:
    """Attach a content-derived snapshot hash (components carry live artifact digests)."""
    body = {
        "state_id": state["state_id"],
        "components": state["components"],
        "authorization_path_states": state.get("authorization_path_states") or {},
    }
    out = copy.deepcopy(state)
    out["snapshot_hash"] = compute_canonical_hash(body)
    return out


def system_state(
    state_id: str,
    *,
    bootloader: dict[str, Any],
    firmware: dict[str, Any],
    path_state: dict[str, Any],
) -> dict[str, Any]:
    return sealed(
        {
            "state_id": state_id,
            "components": [
                {"component_id": "bootloader", "configuration": copy.deepcopy(bootloader)},
                {"component_id": "firmware", "configuration": copy.deepcopy(firmware)},
            ],
            "authorization_path_states": {"fw-boot": copy.deepcopy(path_state)},
        }
    )


def action(
    action_id: str,
    action_type: str,
    component: str,
    *,
    effects: list[str],
    **parameters: Any,
) -> dict[str, Any]:
    return {
        "action_id": action_id,
        "action_type": action_type,
        "component_ref": component,
        "parameters": parameters,
        "derived_effect_refs": effects,
    }


def auth_effects() -> list[dict[str, Any]]:
    return [
        {
            "effect_id": effect_id,
            "effect_type": "AUTHORIZATION_POLICY_UPDATE",
            "target_ref": "fw-boot",
            "affected_field": "authorization_path_states",
            "derivation_rule_ref": "RULE-AUTH-TRANSITION",
        }
        for effect_id in ("DE-AUTH-S1", "DE-AUTH-S2")
    ]


def platform_model(
    *,
    platform_id: str,
    version: str,
    pin: str,
    bootloader_mutability: str,
) -> dict[str, Any]:
    return {
        "id": platform_id,
        "version": version,
        "hash": pin,
        "declared_surface_ids": list(ALL_SURFACES),
        "components": [
            {
                "component_id": "bootloader",
                "component_type": "SECURE_BOOTLOADER",
                "mutability": bootloader_mutability,
            },
            {
                "component_id": "firmware",
                "component_type": "APPLICATION_FIRMWARE",
                "mutability": "UPDATABLE",
            },
        ],
        "authorization_paths": [
            {
                "path_id": "fw-boot",
                "purpose": "FIRMWARE_BOOT",
                "authorization_mode": "UNKNOWN",
                "component_refs": ["bootloader"],
            }
        ],
        "recovery_modes": list(PLATFORM_RECOVERY_MODES),
    }


def mutability_from_field_update(value: str | None) -> str:
    if value == "PASS":
        return "UPDATABLE"
    if value == "UNSUPPORTED":
        return "NOT_FIELD_UPDATABLE"
    return "UNKNOWN"


def check_inputs(
    *,
    profile: Profile,
    change: ChangeScenario,
    family: str,
    run_id: str,
    evidence_run_id: str,
    created_at: str,
) -> None:
    if profile.bootloader.family != family:
        raise AdapterError(
            f"profile {profile.id} is a {profile.bootloader.family} profile, not {family}"
        )
    if change.change_id not in {c.change_id for c in profile.changes}:
        raise AdapterError(f"change {change.change_id} is not declared by profile {profile.id}")
    for name, value in (
        ("run_id", run_id),
        ("evidence_run_id", evidence_run_id),
        ("created_at", created_at),
    ):
        if not isinstance(value, str) or not value:
            raise AdapterError(f"{name} must be a non-empty string")


def resolve_mechanism(change: ChangeScenario, plan_id: str, supported: set[str]) -> str:
    """Return ``DEFAULT_PLAN`` or the alternative's mechanism; refuse non-evaluable plans."""
    if plan_id == change.default_plan_id:
        return DEFAULT_PLAN
    for alt in change.alternatives:
        if alt.plan_id != plan_id:
            continue
        if alt.status != "EXECUTABLE":
            raise AdapterError(
                f"plan {plan_id} is {alt.status}: it cannot be evaluated from this run's evidence"
            )
        if alt.mechanism not in supported:
            raise AdapterError(f"plan {plan_id}: mechanism {alt.mechanism} has no projection")
        return alt.mechanism
    raise AdapterError(f"unknown plan {plan_id} for change {change.change_id}")


def check_pin(observed: Any, pinned: str, what: str) -> None:
    """A run on a different commit than the profile pin is a different platform."""
    if not isinstance(observed, str) or not _HEX40.match(pinned.lower()):
        return
    a, b = observed.lower(), pinned.lower()
    if _HEX40.match(a) and not (a.startswith(b) or b.startswith(a)):
        raise AdapterError(f"{what} commit {observed} does not match the profile pin {pinned}")


def profile_ref(profile: Profile) -> dict[str, Any]:
    return {
        "id": profile.id,
        "version": profile.version,
        "hash": f"version-pin:{profile.id}@{profile.version}",
    }


def plan_ref(profile: Profile, change: ChangeScenario, plan_id: str) -> dict[str, str]:
    return {
        "plan_id": plan_id,
        "version": profile.version,
        "hash": f"version-pin:{profile.id}@{profile.version}/{change.change_id}/{plan_id}",
    }
