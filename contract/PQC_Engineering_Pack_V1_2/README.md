# PQC Engineering Pack V1.2

Baseline normativa autosufficiente per il **Semantic Conformance Core**. V1.1 resta archivio di onboarding storico e non va modificato.

## Autorità

| Artefatto | Uso |
| --- | --- |
| `01_Specifica_Semantica_V1_2.md` | Semantica implementativa completa |
| `02_Contratti_Dati_V1_2.md` | Schemi, hash, explanation, lifecycle |
| `06_Decision_Log_V1_2.md` | Migrazione da V1.1 (non necessaria per codificare) |
| `schemas/pqc_assessment_v1_2.schema.json` | Contratto di input |
| `schemas/semantic_result_v1_2.schema.json` | Contratto di output del motore |
| `schemas/ruleset_v1_2.schema.json` | Catalogo regole e invarianti obbligatori |
| `examples/ruleset_v1_2.json` | I1–I4 richiesti dal ruleset |
| `examples/semantic_validation_cases_v1_2.json` | Casi SV01–SV15 |
| `examples/canonical_hash_vectors_v1_2.json` | Vector JCS con digest attesi |
| `examples/minimal_valid_assessment_v1_2.json` | Base per mutazioni conformance |
| `docs/SEMANTIC_CORE_RELEASE_EVIDENCE.md` | Esito SV01–SV15 e hash vector |
| `docs/WP0_BOUNDARY.md` | Confine dello spike: cosa produce e cosa non tocca |
| `docs/WP0_STATUS.md` | Stato condivisibile del freeze WP0 `2026-10-01T07:09:31Z` |
| `examples/golden/wp0_result_hashes_v1_2.json` | `canonical_hash` attesi di baseline e signer-bound. Non è uno schema |
| `examples/gap_planner_mapping_v1.json` | Mapping data-driven per il gap planner (non normativo) |

## Non normativo

- Fixture A1–A4 del pack V1.1: esempi narrativi. La geometria e il self-update nRF52840 sono fatti del freeze 1 ottobre 2026. L'interruzione e la policy dual non lo sono: le fixture non diventano golden finché quei due fatti non sono conclusivi.
- Le copie demo (`SCENARIO-*`) e il catalogo `web/data/catalog.json` sono proiezioni del repository. Non entrano nello snapshot e non modificano gli schemi.
- Nessun dossier ufficiale in questa milestone. `official` resta `false`.

## Implementazione

Codice in `src/` del repository root; test in `tests/unit/`. Lo zip del pack normativo non include l'implementazione: contratto e repository restano due artefatti complementari.

Report as-is del POC (motore, workspace, confine WP0): [`../docs/POC_AS_IS_REPORT.md`](../docs/POC_AS_IS_REPORT.md).
