# Workstreams — shared spec (read before touching code)

Repo root: `C:\Users\carpy\Desktop\ProgettiPersonali\PQC\releaseproof` (Windows host, Docker Desktop
with Linux containers, WSL Ubuntu available). POC (read-only reference for the original workstreams):
`C:\Users\carpy\Desktop\ProgettiPersonali\PQC\firmware-migration-assurance`.

Backend venv: `backend\.venv\Scripts\python.exe` (Python 3.13 on Windows; containers use 3.12).
Run tests: `cd backend; .\.venv\Scripts\python.exe -m pytest`.

## Ground rules

1. **Only write inside the directories you own** (table below). If you need a change elsewhere,
   describe it in your final report instead of editing.
2. **Do not commit to git.** The tech lead reviews and commits.
3. Never weaken the semantic contract: no generated verdicts, no default "PASS" for facts that were
   not observed, no silent fallback to recorded data or non-AMD LLMs.
4. No shell interpolation of user/LLM input. Subprocesses use argv lists.
5. Keep the existing tests green (`backend/tests/unit`, golden hashes).
6. English for code, UI and docs.

## Ownership

| WS | Owner dirs |
|---|---|
| WS-A wolfBoot runner | `runners/wolfboot/` |
| WS-B MCUboot runner | `runners/mcuboot/` |
| WS-C API/orchestrator/store/deploy | `backend/releaseproof/{api,orchestrator,store}/`, `backend/tests/{api,orchestrator}/`, `backend/Dockerfile`, `docker-compose.yml`, `deploy/`, `Caddyfile` |
| WS-D AI gateway | `backend/releaseproof/ai/`, `backend/tests/ai/`, `scripts/amd_*.py`, `deploy/amd/` |
| WS-E Assessment adapters | `backend/releaseproof/adapters/`, `backend/tests/adapters/` |
| WS-F Web UI | `web/` |
| Tech lead | everything else (`contracts/`, `core/`, `profiles/`, `runners/common/`, docs) |

## Contracts (source of truth)

- Runner protocol: `backend/releaseproof/contracts/runner.py` (+ `schemas/runner_event.schema.json`).
  Runner side helper (stdlib only): `runners/common/rp_runner/` (`events.py`, `proc.py`,
  `engine.py`, `server.py`). Engine phases: PREPARING → DISCOVERY → BUILD_SIGN → EMULATION_TESTS.
- API view models: `backend/releaseproof/contracts/api.py`.
- AI structured outputs: `backend/releaseproof/contracts/ai.py`.
- Service seams: `backend/releaseproof/contracts/services.py` (`AssessmentAdapter`, `AIServiceProtocol`).
- Registry: `profiles/*.yaml`, `profiles/test_catalog.yaml`, loader `backend/releaseproof/profiles/registry.py`.
- Semantic engine: `releaseproof.core.assurance.service.evaluate(assessment) -> SemanticAssessmentResult`
  and `releaseproof.core.validation.service.validate_assessment`. Contract docs in
  `contract/PQC_Engineering_Pack_V1_2/` (01 spec, 02 data contracts, schemas/).

Test-only synthetic helpers live in `backend/tests/ai/rp_llm_stub.py` and
`backend/tests/unit/rp_scenarios.py`, not in the shipped `releaseproof` package. Runtime dependency
injection is refused outside `RELEASEPROOF_ENV=test`; there is no browser mock mode.

## Runtime topology

```
caddy :443 ─┬─ /api/*  → api:8000      (FastAPI, SQLite at /data/releaseproof.sqlite)
            └─ /*      → web:3000      (Next.js standalone)
api → http://runner-wolfboot:8080 , http://runner-mcuboot:8080   (internal network only)
shared volume /data ; artifacts of a run in /data/runs/<run_id>/artifacts/
```

Env vars: `RELEASEPROOF_ENV` (`dev|test|demo`), `RELEASEPROOF_DATA_DIR` (/data),
`RELEASEPROOF_EXPOSE_EXPERIMENTAL` (1 in dev), `RUNNER_URL_WOLFBOOT`, `RUNNER_URL_MCUBOOT`,
`AMD_LLM_BASE_URL`, `AMD_LLM_API_KEY`, `AMD_LLM_MODEL`, `AMD_LLM_MODEL_{PLANNER,EXPLAINER,ALTERNATIVES,ASSISTANT}`,
`AMD_LLM_PROVIDER_LABEL`, `AMD_LLM_HARDWARE_LABEL`, `AMD_LLM_ALLOWED_HOSTS`.

Run id format: `RP-YYYYMMDDTHHMMSSZ-xxxxxx` (6 hex).

Both profiles are currently `SUPPORTED` (reviewed promotion after the recorded
`docs/acceptance/20261017T135337Z.json` gate). `scripts/acceptance.py` does not modify their status.
Additional standalone checks: `python -m pytest scripts/tests -q` from the repository root.

## Observation fact vocabulary (runner → adapter)

Observation fields: see `contracts/runner.py::Observation`. Observation IDs: `OBS-<test_id>-<fact>`
(unique per run). `subject` ∈ deployed_state | candidate_state | transition | platform | toolchain.
Values in CAPS are the only allowed enumerations. Anything not observed → value `"UNKNOWN"`
(or the observation is omitted and the test_result says why).

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
`PASS` = the test observed what it was designed to check (a negative test that observes the
rejection is PASS). `FAIL` = opposite observed. `INCONCLUSIVE` = ran but the observation is not
decisive (e.g. UART timeout with no marker). `ERROR` = could not run (build/tool failure).
**A UART timeout is never a REJECT.** A rejection must be positively identified (explicit marker
or explicit evidence that the old version kept running after the staged update).

## Orchestrated run (WS-C)

Stages shown to users, in order: PREPARING → AI_PLAN → DISCOVERY → BUILD_SIGN → EMULATION_TESTS →
EVALUATION → NEXT_STEPS.
1. AI_PLAN: `ai.plan_tests(...)`; deterministic merge: final = required ∪ (AI-selected ∩ optional),
   ordered by AI priority; templates proposed by the AI that are not in the profile are recorded in
   `blocked_templates`; AI unavailable → required + all optional (`planned_by=PROFILE_OPTIONAL`),
   stage INCONCLUSIVE with message `AI_UNAVAILABLE`.
2. Runner `/execute` stream → persist every event → SSE.
3. Runner `done.status == FAILED` or transport error → run FAILED, **no evaluation, no verdict**.
4. EVALUATION: adapter → `evaluate()` → gap plan → dossier → manifest.json (inputs, pins, artifact
   hashes, result canonical hash).
5. NEXT_STEPS: `ai.explain`, `ai.alternatives` (skip alternatives when migration is COMPATIBLE).
6. REEVALUATION runs: alternative `plan_id` evaluated on the parent LIVE run's observations
   (no runner call) unless the alternative has `requires_rerun_tests`, which starts a LIVE run.
