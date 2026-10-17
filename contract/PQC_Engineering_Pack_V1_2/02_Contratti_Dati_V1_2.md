# 02 — Contratti dati V1.2

## Schemi

- `schemas/pqc_assessment_v1_2.schema.json` — input
- `schemas/ruleset_v1_2.schema.json` — catalogo, incluso `required_invariants`
- `schemas/semantic_result_v1_2.schema.json` — output del motore

## Oggetti chiave

- `EvaluationScope`, `RequirementEvaluationResult`, `InvariantEvaluationResult`
- `DerivedEffect`, `TransitionAction.derived_effect_refs`
- `required_evidence_groups` su requirement
- `authorization_path_states` su `systemState`
- `SemanticAssessmentResult` (output motore, `official: false`)

## Lifecycle esteso

Aggiunto `INCOMPLETE` rispetto a V1.1.

## Explanation graph

Nodi tipizzati: `VERDICT`, `REQUIREMENT`, `INVARIANT`, `RULE`, `EVIDENCE`, `EVIDENCE_GAP`, `EVIDENCE_REQUIREMENT`, `TEST`, `RUN`, `ARTIFACT`, `SOURCE`.

`TransitionAction.component_ref` è il riferimento al componente. `allowed_by_profile` nell'input è rifiutato dallo schema (`BLOCKED`). Il motore lo emette solo dentro `conditions[]`.

## Canonical hash

Vedi `01_Specifica_Semantica_V1_2.md` §13 e `examples/canonical_hash_vectors_v1_2.json`. Ogni vector fissa `expected_canonical_json` e `expected_sha256`.
