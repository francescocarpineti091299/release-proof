# 06 — Decision Log V1.2

## Migrazione da V1.1

| ID | Decisione |
| --- | --- |
| V12-01 | V1.2 autosufficiente; V1.1 immutabile |
| V12-02 | `EvaluationScope` con subject_type/ref |
| V12-03 | `INCOMPLETE` distinto da `BLOCKED` e da `INDETERMINATE` |
| V12-04 | I5 delta accountability → BLOCKED |
| V12-05 | `DerivedEffect` tipizzato, whitelist |
| V12-06 | Coverage `claimed_items ⊆ declared_surface_ids` |
| V12-07 | Evidence groups con `min_satisfied` |
| V12-08 | `allowed_by_profile` solo derivato |
| V12-09 | `canonical_hash` top-level, esclusione precisa |
| V12-10 | A1–A4 non golden fino a WP0 + motore |
| V12-11 | Milestone: `SemanticAssessmentResult`, no dossier ufficiale |
| V12-12 | WP0: policy `UNKNOWN` ammessa, no hybrid inventato |
| V12-13 | `allowed_by_profile` assente dallo schema di input |
| V12-14 | Output vincolato da `semantic_result_v1_2.schema.json` |
| V12-15 | I1–I4 obbligatori dal ruleset, non dall'assessment |
| V12-16 | Hash vector con digest JCS attesi |
| V12-17 | `hash` è un pin esterno; `canonical_hash` è calcolato; `content_hash` sono i byte |
| V12-18 | `RULE-LAYOUT` + `REQ-LAYOUT` valutano capacità con `LEQ` su misure E05; A4 usa artefatto oversized misurato |
| V12-19 | Sul pin `4c79eee…` il signer G2 rifiuta header+firmware oltre partition−sector; senza file firmato A4 non entra in `LEQ`. Il frame UART `[1, 2]` ripetuto non chiude O06 |
| V12-20 | A4 del rifiuto è un assessment separato: `LEQ(requested_image_size, max_signable_image_size)` con gli operandi della riga del signer. Il baseline resta `12876 <= 262144`. O05 sul freeze è `UNSUPPORTED_CONFIGURATION_ON_FROZEN_COMMIT`; AND/OR resta ignoto |

## F1–F7

Chiusi nel contratto V1.2 e nel motore `src/`.

## Lettura WP0 al 1 ottobre 2026

La sezione automatica sotto è generata dal harness e viene sostituita a ogni `python -m wp0`. La nota condivisibile è `docs/WP0_STATUS.md`, allineata al freeze `2026-10-01T07:09:31Z`.

O01–O04 e O10 sono chiusi su nRF52840. O03 è la geometria misurata: payload non firmato, span dell'header, partition e settore. O05 resta aperto: la matrice T3 è stata eseguita, il dual non ha fatto boot, AND/OR non è inferito. O06 resta aperto: le due run T2 a 0,2 s non ripetono la stessa coppia UART. O07 e O08 restano parziali. O10 registra che nessun tag di release coincide col commit; `v2.9.0` è il tag semver pubblicato più vicino, non un antenato dimostrato.

Follow-up sullo stesso pin, fuori dal fact pack: A4 `a4-20261001T082614Z-047ee1bc` è un rifiuto del signer (262400 > 249856), non una size. Quell’ineguaglianza sta in un assessment separato (`REQ-SIGN-BOUND`); il baseline tiene `12876 <= 262144` e il candidato `INDETERMINATE`. O05 `o05-20261001T082614Z-20827409` è `UNSUPPORTED_CONFIGURATION_ON_FROZEN_COMMIT`; AND/OR non entra nella evidence chain. O06 `t2-20261001T082614Z-11ae80a6` ripete i frame `[1, 2]` dopo `Verifying signature...done`. La cella `t2-20261001T090819Z-3f080e11` sul primo `Copy sector` è ripetibile e boota la versione 2 a swap già finito. La finestra non è osservata. T1 blocca la transizione, non il candidato.

## Lettura assurance al 1 ottobre 2026

Il reasoning layer sopra il freeze è nel repository, non nel fact pack.

- Golden: la stessa proiezione produce lo stesso `canonical_hash` (`examples/golden/wp0_result_hashes_v1_2.json`).
- `GAP-E10` e `GAP-E12` puntano a `INV-I4`. `REQ-BOOT-S0S1` resta `VIOLATED` da T1.
- Catena lineare: bootloader, verifier, immagine, update. Recovery è un gap. `REQ-AUTH-NEGATIVE` registra il panic T3 e non è critico.
- Quattro esiti dal motore, su assessment diversi: freeze `INCOMPATIBLE` / candidato `INDETERMINATE`; copia firmware-only `INDETERMINATE`; signer-bound `INCOMPATIBLE`; copia con precondizione di manutenzione `CONDITIONAL`; copia a perimetro dichiarato `COMPATIBLE`.
- Il perimetro `COMPATIBLE` chiude I2, I3 e I4 con dichiarazioni e con `EV-SCENARIO-NON-ATOMIC`. Non è un fatto del pin.
- Il workspace in `web/` legge il catalogo esportato. Non calcola verdict. `official` resta `false`.
- Planner deterministico e dossier Markdown non sono in questa lettura.

## WP0 observed (auto)

| ID | Osservazione WP0 | Stato |
| --- | --- | --- |
| O01 | Target candidate nRF52840; Renode platform nrf52840 | CLOSED |
| O02 | G2 status PASS; ML-DSA-87 factory boot observed | CLOSED |
| O03 | Partition size and measured header span are facts | CLOSED |
| O04 | T1 status CONCLUSIVE | CLOSED |
| O05 | T3 status CONCLUSIVE; unsupported configuration on frozen commit 4c79eee999b7; AND/OR not inferred | OPEN |
| O06 | T2 status INCONCLUSIVE | OPEN |
| O07 | RAM method static_linker_ram_region (CONCLUSIVE) | PARTIALLY_CLOSED |
| O08 | Analyzer strings entities ['Component', 'CryptoAsset', 'AuthorizationSurface'] | PARTIALLY_CLOSED |
| O09 | Version matrix at wp0/facts/version_license_matrix.csv | PARTIALLY_CLOSED |
| O10 | wolfBoot pin PINNED commit 4c79eee999b7083743811f37928322fe78b9fdb1 tag none nearest v2.9.0 | CLOSED |
