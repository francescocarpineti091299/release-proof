# Semantic Core Release Evidence

Data della run semantica: 2026-09-30. Interprete: Python 3.13.3. pytest 8.3.4. I mutator eseguibili di SV01–SV15 sono i test in `tests/unit/test_sv_conformance.py`. Il file `examples/semantic_validation_cases_v1_2.json` resta la specifica dei casi.

Al 2026-10-01 la suite `python -m pytest tests/unit -q` è 66 passed. Copre SV01–SV15, proiezione WP0, precedenza dei verdict, evidence map, golden `canonical_hash`, catena di trust, scenari demo e catalogo UI. `python -m ruff check src tests`: all checks passed. Gli schema V1.2 non cambiano con il freeze né con il workspace. `RULE-LAYOUT` è nel ruleset esempio con decision log V12-18. Il confronto oversized di A4, nei test, usa un intero in memoria e non è un fatto del freeze. Sul commit pinnato il signer G2 ha rifiutato un payload da 250112 byte (run `a4-20261001T082614Z-047ee1bc`). L'assessment separato confronta 262400 e 249856, i due interi della riga del tool, e non una size di file firmato. Il workspace Next non entra in questa evidenza: legge un catalogo già valutato.

## Esito semantico del 30 settembre 2026

24 passed, solo il nucleo in `src/` e i vector. La suite completa del 1 ottobre 2026, incluso fact pack, golden, scenari e catalogo, è 66 passed.

| Test | Esito |
| --- | --- |
| HV01 key order | PASS |
| HV02 omit top-level canonical_hash | PASS |
| HV03 nested content_hash | PASS |
| HV04 unicode JCS | PASS |
| ruleset I1–I4 | PASS |
| minimal fixture schema | PASS |
| SV01 | PASS |
| SV02 | PASS |
| SV03 | PASS |
| SV04 | PASS |
| SV05 | PASS |
| SV06 | PASS |
| SV07 | PASS |
| SV08 | PASS |
| SV09 | PASS |
| SV10 | PASS |
| omitted I3 still evaluated | PASS |
| SV11 | PASS |
| SV12 | PASS |
| SV13 | PASS |
| SV14 | PASS |
| SV15 | PASS |
| recovery NONE | PASS |
| non-critical finding | PASS |

`python -m ruff check src tests/unit`: All checks passed.

Ogni evaluate completo o bloccato è validato contro `schemas/semantic_result_v1_2.schema.json`. I digest attesi HV01–HV04 sono in `examples/canonical_hash_vectors_v1_2.json`.
