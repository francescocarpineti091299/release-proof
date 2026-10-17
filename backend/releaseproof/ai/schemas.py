"""JSON Schemas sent to the model (response_format + prompt), derived from the contracts."""

from __future__ import annotations

import copy
from functools import lru_cache
from typing import Any

from pydantic import BaseModel

from releaseproof.contracts.ai import AlternativesProposal, NarrativeReport, TestPlanProposal

_VERDICT_VALUE = {"anyOf": [{"type": "string"}, {"type": "null"}]}


def _tighten(node: Any) -> None:
    """Strict-mode friendly: every property required, no extra keys, no defaults/titles."""
    if not isinstance(node, dict):
        return
    node.pop("default", None)
    if isinstance(node.get("title"), str):
        node.pop("title")
    props = node.get("properties")
    if isinstance(props, dict):
        node["required"] = list(props.keys())
        node.setdefault("additionalProperties", False)
        for sub in props.values():
            _tighten(sub)
    for key in ("$defs", "definitions"):
        if isinstance(node.get(key), dict):
            for sub in node[key].values():
                _tighten(sub)
    for key in ("items", "additionalProperties", "not"):
        if isinstance(node.get(key), dict):
            _tighten(node[key])
    for key in ("anyOf", "allOf", "oneOf"):
        if isinstance(node.get(key), list):
            for sub in node[key]:
                _tighten(sub)


def _schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = copy.deepcopy(model.model_json_schema())
    if model is NarrativeReport:
        schema["properties"]["verdict_echo"] = {
            "type": "object",
            "properties": {
                "migration": dict(_VERDICT_VALUE),
                "candidate": dict(_VERDICT_VALUE),
                "transition": dict(_VERDICT_VALUE),
            },
        }
    _tighten(schema)
    return schema


@lru_cache(maxsize=8)
def _cached(name: str) -> dict[str, Any]:
    return _schema(
        {
            "TestPlanProposal": TestPlanProposal,
            "NarrativeReport": NarrativeReport,
            "AlternativesProposal": AlternativesProposal,
        }[name]
    )


def llm_schema(model: type[BaseModel]) -> dict[str, Any]:
    return copy.deepcopy(_cached(model.__name__))


__all__ = ["llm_schema"]
