"""Declarative rule evaluators (whitelist only)."""

from __future__ import annotations

from typing import Any

EVALUATOR_WHITELIST = frozenset(
    {
        "LEQ",
        "BOOTABLE_IMAGE_EXISTS",
        "RECOVERY_MODE_ACCEPTABLE",
        "NO_CLASSICAL_ONLY_CRITICAL_AUTH_PATH",
        "NON_ATOMIC_WINDOW_HANDLED",
    }
)

_NOT_EXECUTED = "NOT_EXECUTED"


def run_evaluator(
    evaluator_id: str,
    *,
    context: dict[str, Any],
) -> dict[str, Any]:
    """Run a whitelisted evaluator and return a structured result.

    A missing target-specific input means the evaluator did not run.
    An explicit UNKNOWN value means the evaluator ran and the fact is unknown.
    """
    if evaluator_id not in EVALUATOR_WHITELIST:
        return {"status": _NOT_EXECUTED, "reason": f"Evaluator non in whitelist: {evaluator_id}"}

    if evaluator_id == "RECOVERY_MODE_ACCEPTABLE":
        return _recovery(context)
    if evaluator_id == "NO_CLASSICAL_ONLY_CRITICAL_AUTH_PATH":
        return _classical_path(context)
    if evaluator_id == "BOOTABLE_IMAGE_EXISTS":
        return _bootable(context)
    if evaluator_id == "NON_ATOMIC_WINDOW_HANDLED":
        return _non_atomic(context)
    if evaluator_id == "LEQ":
        return _leq(context)
    return {"status": _NOT_EXECUTED, "reason": "Evaluator non eseguito"}


def _recovery(context: dict[str, Any]) -> dict[str, Any]:
    if "observed_recovery_mode" not in context:
        return {"status": _NOT_EXECUTED, "reason": "Input recovery assente"}
    observed = context.get("observed_recovery_mode")
    acceptable = {
        mode for mode in (context.get("acceptable_recovery_modes") or []) if mode != "NONE"
    }
    if observed in (None, "UNKNOWN"):
        return {"status": "UNKNOWN", "reason": "Modalità recovery non osservata"}
    if observed == "NONE" or observed not in acceptable:
        return {
            "status": "VIOLATED",
            "reason": "Recovery osservata non accettabile per il profilo",
        }
    return {"status": "SATISFIED"}


def _classical_path(context: dict[str, Any]) -> dict[str, Any]:
    if "policy" not in context:
        return {"status": _NOT_EXECUTED, "reason": "Input policy assente"}
    policy = context.get("policy")
    if policy in (None, "UNKNOWN"):
        return {"status": "UNKNOWN", "reason": "Policy di autorizzazione UNKNOWN"}
    if policy == "CLASSICAL_ONLY":
        return {
            "status": "VIOLATED",
            "reason": "Path critico solo classico dopo attivazione policy",
        }
    return {"status": "SATISFIED"}


def _bootable(context: dict[str, Any]) -> dict[str, Any]:
    if "bootable" not in context:
        return {"status": _NOT_EXECUTED, "reason": "Input bootability assente"}
    value = context.get("bootable")
    if value in (None, "UNKNOWN"):
        return {"status": "UNKNOWN", "reason": "Bootability UNKNOWN"}
    if value is True:
        return {"status": "SATISFIED"}
    return {"status": "VIOLATED", "reason": "Nessuna immagine avviabile"}


def _non_atomic(context: dict[str, Any]) -> dict[str, Any]:
    if "non_atomic_handled" not in context:
        return {"status": _NOT_EXECUTED, "reason": "Input finestra non atomica assente"}
    value = context.get("non_atomic_handled")
    if value in (None, "UNKNOWN"):
        return {"status": "UNKNOWN", "reason": "Finestra non atomica UNKNOWN"}
    if value is True:
        return {"status": "SATISFIED"}
    return {"status": "VIOLATED", "reason": "Finestra non atomica non gestita"}


def _leq(context: dict[str, Any]) -> dict[str, Any]:
    pair = _leq_operands(context)
    if pair is None:
        return {"status": _NOT_EXECUTED, "reason": "Input capacità assente"}
    used, bound, reason = pair
    if used in (None, "UNKNOWN") or bound in (None, "UNKNOWN"):
        return {"status": "UNKNOWN", "reason": "Capacità UNKNOWN"}
    if used <= bound:
        return {"status": "SATISFIED"}
    return {"status": "VIOLATED", "reason": reason}


def _leq_operands(context: dict[str, Any]) -> tuple[Any, Any, str] | None:
    """Pick one operand pair. The signer pair is not a signed-file size."""
    if "requested_image_size" in context and "max_signable_image_size" in context:
        return (
            context.get("requested_image_size"),
            context.get("max_signable_image_size"),
            "Immagine richiesta oltre il massimo accettato dal signer",
        )
    if "signed_artifact_size" in context and "boot_slot_capacity" in context:
        return (
            context.get("signed_artifact_size"),
            context.get("boot_slot_capacity"),
            "Artefatto oltre la capacità dello slot",
        )
    return None


__all__ = ["EVALUATOR_WHITELIST", "run_evaluator"]
