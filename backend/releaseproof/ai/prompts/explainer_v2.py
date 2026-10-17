"""Explainer version 2: explicit phase labels match the stronger prose guardrail."""

from releaseproof.ai.prompts import explainer_v1

TEMPLATE_ID = "explainer@2"
ROLE = explainer_v1.ROLE
RULES = (
    explainer_v1.RULES
    + """\
- Whenever a verdict label appears in prose, precede it in the same clause with its explicit \
phase: migration, candidate or transition. Match that phase's engine verdict, including lowercase \
labels. Example: "Candidate is COMPATIBLE; migration is INCOMPATIBLE." Never infer migration \
success from candidate success or write an unscoped label like "COMPATIBLE: ready".
- Do not describe deployment as safe, certified, guaranteed or universally supported. Citation \
ID validation does not prove every sentence; emulation and missing observations remain limits.
"""
)
