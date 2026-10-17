# ReleaseProof â€” Implementation Plan (living document)

> Owner: tech lead Â· Started: 2026-10-17 13:50 CEST Â· Update this file at the end of every phase.
> Source brief: `../general_docs/ReleaseProof_AMD_ACT_III_Engineering_Brief.md (private, git-ignored)` Â· POC: `../../firmware-migration-assurance` (HEAD `ef408b8`).

## 0. Deadlines

| Item | Time (CEST) | Note |
|---|---|---|
| lablab `endAt` | **2026-10-18 12:00** | event JSON `2026-10-18T10:00Z`; Luma Rome says 16:00 â€” treat 12:00 as hard |
| Internal feature freeze | 2026-10-18 09:00 | after this: only fixes, video, docs |
| Submission target | 2026-10-18 11:00 | confirm deadline on Discord |

## 1. Decisions

| ID | Decision | Status |
|---|---|---|
| D01â€“D04 | From brief (two E2E configs, supported-only UX, AMD-only LLM, Evolus out) | Decided |
| D05 | **Additive engine patch**: requirement evaluators also select evidence by `test_id` (E03 auth-negative, A4 signer-bound, E05 layout) besides legacy hardcoded IDs. Golden hashes MUST stay identical (regression test). | Decided |
| D06 | **Profile B change = PQC migration (ECDSA P-256 â†’ ML-DSA)** on MCUboot; PQC support is *measured live* (sign attempt). Classical key-rotation would need a separate ruleset â†’ stretch only. | Decided |
| D07 | **Deploy on AWS**: one EC2 `c7a.2xlarge` (AMD EPYC Genoa) + Elastic IP, Docker Compose, Caddy auto-TLS. LLM inference on AMD (Token Factory / AMD Developer Cloud vLLM). | Decided |
| D08 | ReleaseProof code licensed MIT; wolfBoot (GPL-3.0) never vendored â€” fetched at pinned commit inside the runner image only. | Decided |
| D09 | Profile B board: nRF52840 (Zephyr + MCUboot, Renode with NVMC model). Fallbacks: `direct-xip` mode â†’ STM32F4 disco. | Decided, spike gate |

## 2. Architecture (summary)

```
web (Next.js) â”€â”€REST/SSEâ”€â”€â–º api (FastAPI, SQLite, artifacts)
                               â”œâ”€ orchestrator (state machine, queue, per-runner semaphore)
                               â”œâ”€ ai gateway (OpenAI-compatible, AMD only, traced)  â”€â”€â–º AMD endpoint
                               â”œâ”€ adapters (observations â†’ V1.2 assessment) â”€â”€â–º core.evaluate()
                               â””â”€ HTTP/NDJSON â”€â”€â–º runner-wolfboot | runner-mcuboot  (internal network, no egress)
```

Runners **measure** (build, sign, Renode, discovery). Backend **projects + evaluates**. LLM **proposes/explains** only.

## 3. Repository layout

```
releaseproof/
  contract/PQC_Engineering_Pack_V1_2/   verbatim copy (normative)
  backend/releaseproof/{core,adapters,orchestrator,api,store,profiles,ai}
  backend/tests/{unit,contract,integration}
  runners/{common,wolfboot,mcuboot}
  profiles/*.yaml, profiles/test_catalog.yaml
  web/  scripts/  docs/  deploy/aws/
```

## 4. Phases & status

Legend: â˜ todo Â· â— in progress Â· â˜‘ done Â· âœ– blocked

### Phase 0 â€” Foundations (13:50 â†’ 15:30) â€” â˜‘ DONE 15:10
- â˜‘ Scaffold repo (git, LF), LICENSE (MIT), CODE_PROVENANCE, THIRD_PARTY_NOTICES
- â˜‘ Port `src/` â†’ `backend/releaseproof/core` (paths centralised in `core/paths.py`), contract pack â†’ `contract/`, freeze run records â†’ `reference/wp0-freeze-20261001/`; 55 ported tests + golden hashes green
- â˜‘ D05 additive patch (`test_id` E03/A4 fallback) + regression tests (golden unchanged)
- â˜‘ Shared contracts: `contracts/{runner,ai,profile,api,services}.py`, JSON Schemas in `schemas/`, registry loader, `profiles/*.yaml`, `test_catalog.yaml`
- â˜‘ Runner framework `runners/common/rp_runner` (events, proc w/ process-group kill, template engine, HTTP NDJSON server) + protocol test
- â˜‘ `docs/WORKSTREAMS.md`: ownership, fact vocabulary, orchestration rules
- Result: 64 tests green.
- As-is notes: POC tests excluded from port (demo/export/catalog/wp0-harness: replaced by new modules); engine Italian finding strings kept (part of golden hash).
- Plan delta: AI_PLAN runs before DISCOVERY (single runner call); profiles start `EXPERIMENTAL` and are promoted to `SUPPORTED` only by the acceptance gate.

### Phase 1 â€” Parallel workstreams (15:10 â†’ 19:00) â€” â— launched 15:15 (6 agents)
- â˜‘ WS-D AI gateway (111 tests at merge) â€” note: `AMD_LLM_ALLOWED_HOSTS` must be set explicitly to the real AMD endpoint host
- â˜‘ WS-A wolfBoot runner â€” image 3.4 GB, full run â‰ˆ64 s; all 8 templates reproduce frozen facts (840 / 12876 B, E11 UNSUPPORTED, O05 BUILD_FAILED); X01 REJECTED and P01 REJECT observed live
- â˜‘ WS-E adapters â€” 66 tests; coverage-gated requirements so missing facts â‡’ UNKNOWN; live verdict expectation A: candidate COMPATIBLE (with P01) / transition INCOMPATIBLE; field_service_reflash â‡’ transition INDETERMINATE (I4 unknown)
- Tech-lead decisions on WS-E open questions:
  - REQ-AUTH-NEGATIVE as TRANSITION + critical: **accepted** (deployed verifier must reject tampered images).
  - No HYBRID_OR derivation from P01 ACCEPT: **accepted**.
  - X01/E08 informational (shown as evidence, not requirements): **accepted** for V1.2.
  - S1 (ML-DSA bootloader + ECDSA firmware) is not bootable per P01 â€” real hazard, invisible to I1. **Open**: surface as a finding in the UI/AI explanation; engine change deferred (would be V1.3).
- â˜‘ WS-B MCUboot runner â€” Zephyr v4.2.0 + MCUboot 4eba8087, own MIT NVMC model, swap-using-move works first try (no fallback); full run â‰ˆ66 s; offline (`--network none`) verified; E02 imgtool 2.2.0 refuses ml-dsa (measured)
- â˜‘ **Real-stream integration check (17:30)**: recorded NDJSON from both live containers â†’ adapters â†’ `evaluate()`:

| Profile / plan | Candidate | Transition | Migration |
|---|---|---|---|
| wolfBoot / bootloader_self_update | COMPATIBLE | INCOMPATIBLE (REQ-BOOT-S0S1) | INCOMPATIBLE |
| wolfBoot / field_service_reflash | COMPATIBLE | INDETERMINATE (I4, maintenance condition) | INDETERMINATE |
| wolfBoot / staged_hybrid | COMPATIBLE | INCOMPATIBLE (O05 build failed) | INCOMPATIBLE |
| MCUboot / mcuboot_field_update | INCOMPATIBLE (REQ-PQC-VERIFIER) | INCOMPATIBLE (REQ-BL-FIELD-UPDATE) | INCOMPATIBLE |
| MCUboot / depot_reflash | INCOMPATIBLE | INDETERMINATE | INCOMPATIBLE |

  Frozen as regression fixtures `backend/tests/fixtures/runner_streams/` (249 tests green).
- â˜ WS-A wolfBoot runner (Docker, isolated workdir, G1/G2/E03/X01/T1/layout)
- â˜ WS-B MCUboot spike â†’ runner (**go/no-go 18:00**)
- â˜ WS-C API + orchestrator (jobs, SSE, artifacts, idempotency, queue)
- â˜ WS-D AI gateway (planner, explainer, alternatives, analyst; stub only in tests)
- â˜ WS-E adapters A/B â†’ V1.2 assessments
- â˜ WS-F web UI (wizard, live job, result, evidence, alternatives, AMD panel, reference run)

### Phase 2 â€” Integration (started 14:40, ahead of schedule)
- â˜‘ Full stack in Docker (api + both real runners, `docker-compose.dev.yml`): `scripts/acceptance.py` **PASSED for both profiles** (reports in `docs/acceptance/`)
- â˜‘ Bug found by acceptance: stock Renode `nrf52840.repl` downloads its SVD at load â†’ fails on the no-egress runner network â†’ E01 update INCONCLUSIVE (correctly not faked). Fix: SVD baked + sha256-pinned in runner-wolfboot image.
- â˜‘ Gates verified live: REEVALUATION of `field_service_reflash` â‡’ new run INDETERMINATE, parent unchanged (hash identical); REQUIRES_EXTERNAL_VALIDATION alternative â‡’ 422; runner killed mid-run â‡’ run FAILED (TOOL_FAILURE), no verdict, `/result` 409; `/reference` returns golden hash.
- â— WS-F UI finishing against the real API
- âœ– AWS deploy blocked: IAM user `programmatic-ettore-caputo` lacks EC2/SSM permissions. Minimal policy in `deploy/aws/iam-policy.json`. Scripts patched (AMI fallback, tar sync without rsync).
- â˜ AMD endpoint (key pending)

### Phase 2 â€” Integration (19:00 â†’ 01:00) [original targets]
- â˜ A end-to-end from UI (target 22:00)
- â˜ AMD planner wired into the job
- â˜ B end-to-end (target 01:00)

### Phase 3 â€” Agentic loop + deploy (01:00 â†’ 06:00)
- â˜ Alternatives â†’ re-evaluation as new run (parent ref)
- â˜ Assistant chat on AMD
- â˜ AWS deploy (EC2 c7a + compose + Caddy)
- â˜ `scripts/acceptance.py` incl. negative tests (Renode crash, AI down, unregistered test, prompt injection, bad citation)

### Phase 4 â€” Hardening & submission (06:00 â†’ 11:00)
- â˜ AMD benchmark + `docs/AMD_EVIDENCE.md`
- â˜ README, LIMITATIONS, architecture diagram
- â˜ Video (authentic runs), slides, cover; submission

## 5. Test catalog (bootloader-agnostic semantics)

| Test | Meaning | A (wolfBoot) | B (MCUboot) |
|---|---|---|---|
| E01 | Current state boots | ECC256 build + Renode boot | MCUboot ECDSA + app v1 boot |
| E02 | Candidate state boots | ML-DSA-87 build + boot | PQC sign attempt (tool refusal measured) |
| E03 | Auth negative | tampered image rejected | tampered image rejected |
| X01 | Cross-transition | deployed BL + ML-DSA update | deployed BL + image signed by other key |
| E05 | Layout fits | signed size vs partition | partitions from `zephyr.dts`/imgtool |
| T1 | Bootloader field-update capability | static scan (self-update absent) | single-stage MCUboot, no BL slot |

## 6. Risk register (live)

| Risk | Status | Mitigation |
|---|---|---|
| MCUboot in Renode (no NVMC model) | open | custom NVMC model; fallback direct-xip / STM32F4 |
| AMD access pending | open | code with stub (tests only); smoke 10 calls on key arrival |
| Public deploy uptime after event | open | AWS EC2, not a laptop tunnel |
| Zephyr image build time | open | workspace baked in image; only app build per job |

## 7. Change log

- 2026-10-17 13:50 â€” Plan created from validated brief; D05â€“D09 decided.
