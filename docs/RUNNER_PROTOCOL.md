# Runner protocol and observation vocabulary

Runners **measure**; they never decide. This page describes the contract between the
orchestrator, the runners and the assessment adapters.

## Contracts (source of truth)

- **Runner protocol:** `backend/releaseproof/contracts/runner.py`, with schema
  `schemas/runner_event.schema.json`. The runner-side helper (stdlib only) is
  `runners/common/rp_runner/`: `events.py`, `proc.py`, `engine.py` and `server.py`. Runner
  phases run in this order: PREPARING → DISCOVERY → BUILD_SIGN → EMULATION_TESTS.
- **API view models:** `backend/releaseproof/contracts/api.py`.
- **AI structured outputs:** `backend/releaseproof/contracts/ai.py`.
- **Service seams:** `backend/releaseproof/contracts/services.py` (`AssessmentAdapter`,
  `AIServiceProtocol`).
- **Registry:** `profiles/*.yaml` and `profiles/test_catalog.yaml`, loaded by
  `backend/releaseproof/profiles/registry.py`.
- **Semantic engine:** `releaseproof.core.assurance.service.evaluate(assessment)` and
  `releaseproof.core.validation.service.validate_assessment`. The normative contract is in
  `contract/PQC_Engineering_Pack_V1_2/`.

Run IDs have the form `RP-YYYYMMDDTHHMMSSZ-xxxxxx` (6 hex digits).

## Observation facts (runner → adapter)

Observation IDs are `OBS-<test_id>-<fact>`, unique per run. The `subject` is one of
`deployed_state`, `candidate_state`, `transition`, `platform` or `toolchain`. Values in CAPS are
the only allowed enumerations. Anything not observed has value `"UNKNOWN"`, or the observation is
omitted and the test result says why.

### wolfBoot (`runners/wolfboot`)

| test_id | fact | subject | value | acquisition_mode |
|---|---|---|---|---|
| D01 | `bootloader_commit` | toolchain | str sha | REPOSITORY |
| D01 | `crypto_commit` | toolchain | str sha | REPOSITORY |
| D01 | `partition_layout` | platform | `{boot_partition_address, update_partition_address, swap_address, partition_size_bytes, sector_size_bytes}` (ints, from pinned config) | STATIC_CONFIG |
| E11 | `bootloader_field_update` | platform | SUPPORTED \| UNSUPPORTED \| UNKNOWN | SOURCE_INSPECTION |
| E01 | `boot_outcome` | deployed_state | BOOT_OK \| FAIL \| UNKNOWN | EMULATED |
| E01 | `observed_version` | deployed_state | int | EMULATED |
| E08 | `update_outcome` | deployed_state | APPLIED \| NOT_APPLIED \| UNKNOWN (same-scheme v1→v2) | EMULATED |
| E01 | `signed_image_size_bytes` / `bootloader_size_bytes` | deployed_state | int | STATIC_ARTIFACT |
| E01 | `public_key_sha256` | deployed_state | hex | STATIC_ARTIFACT |
| E02 | `boot_outcome`, `observed_version`, `signed_image_size_bytes`, `bootloader_size_bytes`, `public_key_sha256` | candidate_state | as above | as above |
| E04 | `image_header` | candidate_state | `{image_header_size_bytes, header_span_bytes}` | STATIC_ARTIFACT |
| E05 | `layout_fit` | candidate_state | `{signed_artifact_size, boot_slot_capacity}` | STATIC_ARTIFACT |
| E03 | `auth_negative` | deployed_state | REJECT \| ACCEPT \| UNKNOWN | EMULATED |
| X01 | `cross_update_outcome` | transition | REJECTED \| APPLIED \| UNKNOWN | EMULATED |
| P01 | `classical_image_on_candidate` | candidate_state | REJECT \| ACCEPT \| UNKNOWN | EMULATED |
| O05 | `dual_signature_build` | candidate_state | BUILD_FAILED \| BUILT_NOT_BOOTED \| BOOT_OK | BUILD |

### MCUboot (`runners/mcuboot`)

| test_id | fact | subject | value | acquisition_mode |
|---|---|---|---|---|
| D01 | `bootloader_commit`, `zephyr_commit` | toolchain | str sha | REPOSITORY |
| D01 | `partition_layout` | platform | `{boot_partition_size, slot0_address, slot0_size, slot1_address, slot1_size}` (from build `zephyr.dts`) | STATIC_CONFIG |
| D01 | `imgtool_key_types` | toolchain | list[str] (from `imgtool keygen --help`) | STATIC_ANALYSIS |
| E11 | `bootloader_field_update` | platform | SUPPORTED \| UNSUPPORTED \| UNKNOWN | STATIC_CONFIG |
| E01 | `boot_outcome`, `observed_version`, `signed_image_size_bytes`, `bootloader_size_bytes`, `public_key_sha256` | deployed_state | as wolfBoot | as wolfBoot |
| E05 | `layout_fit` | deployed_state | `{signed_artifact_size, boot_slot_capacity}` | STATIC_ARTIFACT |
| E08 | `update_outcome` | deployed_state | APPLIED \| NOT_APPLIED \| UNKNOWN | EMULATED |
| E03 | `auth_negative` | deployed_state | REJECT \| ACCEPT \| UNKNOWN | EMULATED |
| E02 | `pqc_signing` | candidate_state | `{signing_result: OK\|REJECTED, algorithm, tool, message}` | SIGN_TOOL |
| X01 | `cross_update_outcome` | transition | REJECTED \| APPLIED \| UNKNOWN | EMULATED |

### Test outcome semantics

| Outcome | Meaning |
|---|---|
| `PASS` | The test observed what it was designed to check. A negative test that observes the rejection is a PASS. |
| `FAIL` | The opposite was observed. |
| `INCONCLUSIVE` | The test ran but the observation is not decisive, e.g. a UART timeout with no marker. |
| `ERROR` | The test could not run, e.g. a build or tool failure. |

**A UART timeout is never a REJECT.** A rejection must be positively identified, either by an
explicit marker or by explicit evidence that the old version kept running after the staged
update.

## Orchestrated run

The stages shown to users, in order: PREPARING → AI_PLAN → DISCOVERY → BUILD_SIGN →
EMULATION_TESTS → EVALUATION → NEXT_STEPS.

1. **AI_PLAN.** The final plan is computed deterministically: required ∪ (AI-selected ∩
   optional), ordered by AI priority.
   - Templates the AI proposes that are not in the profile are recorded as `blocked_templates`.
   - If the AI is unavailable, the plan is required + all optional
     (`planned_by=PROFILE_OPTIONAL`), and the stage is INCONCLUSIVE with `AI_UNAVAILABLE`.
2. **Runner execution.** The runner's `/execute` NDJSON stream is persisted event by event and
   relayed over SSE.
3. **Runner failure.** If the runner reports `FAILED` or the transport breaks, the run is
   `FAILED`. There is **no evaluation and no verdict**.
4. **EVALUATION.** The adapter output goes through `evaluate()`, the gap plan, the dossier and
   finally `manifest.json`. The manifest records inputs, pins, artifact hashes and the result's
   canonical hash.
5. **NEXT_STEPS.** The AI writes the cited explanation and the alternatives. Alternatives are
   skipped when the migration is COMPATIBLE.
6. **REEVALUATION.** An alternative `plan_id` is evaluated on the parent LIVE run's observations,
   with no runner call. If the alternative declares `requires_rerun_tests`, a new LIVE run starts
   instead.
