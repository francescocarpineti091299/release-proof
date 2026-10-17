"""Domain enumerations aligned with V1.2 contract wire values."""

from __future__ import annotations

from enum import StrEnum


class AssessmentLifecycle(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    INCOMPLETE = "INCOMPLETE"


class EvaluationPhase(StrEnum):
    CURRENT = "CURRENT"
    TRANSITION = "TRANSITION"
    TARGET = "TARGET"


class EvaluationSubjectType(StrEnum):
    STATE = "STATE"
    TRANSITION_STEP = "TRANSITION_STEP"
    PLAN = "PLAN"


class RequirementResultState(StrEnum):
    SATISFIED = "SATISFIED"
    VIOLATED = "VIOLATED"
    UNKNOWN = "UNKNOWN"
    OPEN_CONDITION = "OPEN_CONDITION"


class Verdict(StrEnum):
    COMPATIBLE = "COMPATIBLE"
    CONDITIONAL = "CONDITIONAL"
    INDETERMINATE = "INDETERMINATE"
    INCOMPATIBLE = "INCOMPATIBLE"


class EvidenceKind(StrEnum):
    MEASUREMENT = "MEASUREMENT"
    DECLARATION = "DECLARATION"
    INFERENCE = "INFERENCE"


DERIVED_EFFECT_TYPES = frozenset(
    {
        "KEYSTORE_PROFILE_UPDATE",
        "AUTHORIZATION_POLICY_UPDATE",
    }
)

DERIVATION_RULE_REFS = frozenset(
    {
        "RULE-KEYSTORE-FROM-BOOTLOADER",
        "RULE-AUTH-TRANSITION",
    }
)

__all__ = [
    "AssessmentLifecycle",
    "DERIVATION_RULE_REFS",
    "DERIVED_EFFECT_TYPES",
    "EvaluationPhase",
    "EvaluationSubjectType",
    "EvidenceKind",
    "RequirementResultState",
    "Verdict",
]
