# ReleaseProof — Implementation Plan (living document)

> Owner: tech lead · Started: 2026-10-17 13:50 CEST · Update this file at the end of every phase.
> Source brief: `../general_docs/ReleaseProof_AMD_ACT_III_Engineering_Brief.md` (private, git-ignored) · POC: `../../firmware-migration-assurance` (HEAD `ef408b8`).

## 0. Deadlines

| Item | Time (CEST) | Note |
|---|---|---|
| lablab `endAt` | **2026-10-18 12:00** | event JSON `2026-10-18T10:00Z`; Luma Rome says 16:00 — treat 12:00 as hard |
| Internal feature freeze | 2026-10-18 09:00 | after this: only fixes, video, docs |
| Submission target | 2026-10-18 11:00 | confirm deadline on Discord |

## 1. Decisions

| ID | Decision | Status |
|---|---|---|
| D01–D04 | From brief (two E2E configs, supported-only UX, AMD-only LLM, Evolus out) | Decided |
| D05 | **Additive engine patch**: requirement evaluators also select evidence by `test_id` (E03 auth-negative, A4 signer-bound, E05 layout) besides legacy hardcoded IDs. Golden hashes MUST stay identical (regression test). | Decided |
| D06 | **Profile B change = PQC migration (ECDSA P-256 → ML-DSA)** on MCUboot; PQC support is *measured live* (sign attempt). Classical key-rotation would need a separate ruleset → stretch only. | Decided |
| D07 | **Deploy on AWS**: one EC2 `c7a.2xlarge` (AMD EPYC Genoa) + Elastic IP, Docker Compose, Caddy auto-TLS. LLM inference on AMD (Token Factory / AMD Developer Cloud vLLM). | Decided |
| D08 | ReleaseProof code licensed MIT; wolfBoot (GPL-3.0) never vendored — fetched at pinned commit inside the runner image only. | Decided |
| D09 | Profile B board: nRF52840 (Zephyr + MCUboot, Renode with NVMC model). Fallbacks: `direct-xip` mode → STM32F4 disco. | Decided, spike gate |

## 2. Architecture (summary)

```
web (Next.js) ──REST/SSE──► api (FastAPI, SQLite, artifacts)
                               ├─ orchestrator (state machine, queue, per-runner semaphore)
                               ├─ ai gateway (OpenAI-compatible, AMD only, traced)  ──► AMD endpoint
                               ├─ adapters (observations → V1.2 assessment) ──► core.evaluate()
                               └─ HTTP/NDJSON ──► runner-wolfboot | runner-mcuboot  (internal network, no egress)
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

Legend: ☐ todo · ◐ in progress · ☑ done · ✖ blocked

### Phase 0 — Foundations (13:50 → 15:30) — ☑ DONE 15:10
- ☑ Scaffold repo (git, LF), LICENSE (MIT), CODE_PROVENANCE, THIRD_PARTY_NOTICES
- ☑ Port `src/` → `backend/releaseproof/core` (paths centralised in `core/paths.py`), contract pack → `contract/`, freeze run records → `reference/wp0-freeze-20261001/`; 55 ported tests + golden hashes green
- ☑ D05 additive patch (`test_id` E03/A4 fallback) + regression tests (golden unchanged)
- ☑ Shared contracts: `contracts/{runner,ai,profile,api,services}.py`, JSON Schemas in `schemas/`, registry loader, `profiles/*.yaml`, `test_catalog.yaml`
- ☑ Runner framework `runners/common/rp_runner` (events, proc w/ process-group kill, template engine, HTTP NDJSON server) + protocol test
- ☑ `docs/WORKSTREAMS.md`: ownership, fact vocabulary, orchestration rules
- Result: 64 tests green.
- As-is notes: POC tests excluded from port (demo/export/catalog/wp0-harness: replaced by new modules); engine Italian finding strings kept (part of golden hash).
- Plan delta: AI_PLAN runs before DISCOVERY (single runner call); profiles start `EXPERIMENTAL` and are promoted to `SUPPORTED` only by the acceptance gate.

### Phase 1 — Parallel workstreams (15:10 → 19:00) — ◐ launched 15:15 (6 agents)
- ☑ WS-D AI gateway (111 tests at merge) — note: `AMD_LLM_ALLOWED_HOSTS` must be set explicitly to the real AMD endpoint host
- ☑ WS-A wolfBoot runner — image 3.4 GB, full run ≈64 s; all 8 templates reproduce frozen facts (840 / 12876 B, E11 UNSUPPORTED, O05 BUILD_FAILED); X01 REJECTED and P01 REJECT observed live
- ☑ WS-E adapters — 66 tests; coverage-gated requirements so missing facts ⇒ UNKNOWN; live verdict expectation A: candidate COMPATIBLE (with P01) / transition INCOMPATIBLE; field_service_reflash ⇒ transition INDETERMINATE (I4 unknown)
- Tech-lead decisions on WS-E open questions:
  - REQ-AUTH-NEGATIVE as TRANSITION + critical: **accepted** (deployed verifier must reject tampered images).
  - No HYBRID_OR derivation from P01 ACCEPT: **accepted**.
  - X01/E08 informational (shown as evidence, not requirements): **accepted** for V1.2.
  - S1 (ML-DSA bootloader + ECDSA firmware) is not bootable per P01 — real hazard, invisible to I1. **Open**: surface as a finding in the UI/AI explanation; engine change deferred (would be V1.3).
- ☑ WS-B MCUboot runner — Zephyr v4.2.0 + MCUboot 4eba8087, own MIT NVMC model, swap-using-move works first try (no fallback); full run ≈66 s; offline (`--network none`) verified; E02 imgtool 2.2.0 refuses ml-dsa (measured)
- ☑ **Real-stream integration check (17:30)**: recorded NDJSON from both live containers → adapters → `evaluate()`:

| Profile / plan | Candidate | Transition | Migration |
|---|---|---|---|
| wolfBoot / bootloader_self_update | COMPATIBLE | INCOMPATIBLE (REQ-BOOT-S0S1) | INCOMPATIBLE |
| wolfBoot / field_service_reflash | COMPATIBLE | INDETERMINATE (I4, maintenance condition) | INDETERMINATE |
| wolfBoot / staged_hybrid | COMPATIBLE | INCOMPATIBLE (O05 build failed) | INCOMPATIBLE |
| MCUboot / mcuboot_field_update | INCOMPATIBLE (REQ-PQC-VERIFIER) | INCOMPATIBLE (REQ-BL-FIELD-UPDATE) | INCOMPATIBLE |
| MCUboot / depot_reflash | INCOMPATIBLE | INDETERMINATE | INCOMPATIBLE |

  Frozen as regression fixtures `backend/tests/fixtures/runner_streams/` (249 tests green).
- ☐ WS-A wolfBoot runner (Docker, isolated workdir, G1/G2/E03/X01/T1/layout)
- ☐ WS-B MCUboot spike → runner (**go/no-go 18:00**)
- ☐ WS-C API + orchestrator (jobs, SSE, artifacts, idempotency, queue)
- ☐ WS-D AI gateway (planner, explainer, alternatives, analyst; stub only in tests)
- ☐ WS-E adapters A/B → V1.2 assessments
- ☐ WS-F web UI (wizard, live job, result, evidence, alternatives, AMD panel, reference run)

### Phase 2 — Integration (started 14:40, ahead of schedule)
- ☑ Full stack in Docker (api + both real runners, `docker-compose.dev.yml`): `scripts/acceptance.py` **PASSED for both profiles** (reports in `docs/acceptance/`)
- ☑ Bug found by acceptance: stock Renode `nrf52840.repl` downloads its SVD at load → fails on the no-egress runner network → E01 update INCONCLUSIVE (correctly not faked). Fix: SVD baked + sha256-pinned in runner-wolfboot image.
- ☑ Gates verified live: REEVALUATION of `field_service_reflash` ⇒ new run INDETERMINATE, parent unchanged (hash identical); REQUIRES_EXTERNAL_VALIDATION alternative ⇒ 422; runner killed mid-run ⇒ run FAILED (TOOL_FAILURE), no verdict, `/result` 409; `/reference` returns golden hash.
- ☑ WS-F UI merged; verified visually (home wizard, run decision page, evidence, alternatives, pipeline) through Caddy on :8080; SSE streams live via proxy (194 events in first 25 s)
- ☑ Dossier now English + generic target metadata (no wolfBoot-specific keys)
- ☑ README (quickstart, live results, AMD usage placeholders, limitations, licenses)
- ◐ Pitch kit agent (slides/cover/submission/video+pitch scripts) → `pitch/`
- ✖ AWS deploy blocked: IAM user `programmatic-ettore-caputo` lacks EC2/SSM permissions. Minimal policy in `deploy/aws/iam-policy.json`. Scripts patched (AMI fallback, tar sync without rsync).
- ☐ AMD endpoint (key pending) → then `amd_smoke.py`, `amd_benchmark.py`, `acceptance.py --require-ai`, promote profiles to SUPPORTED
- ☐ Before publishing: history scan — Phase-0 commit contains the private brief (moved to git-ignored `general_docs/`); publish from a clean squashed history.

### Phase 2 — Integration (19:00 → 01:00) [original targets]
- ☐ A end-to-end from UI (target 22:00)
- ☐ AMD planner wired into the job
- ☐ B end-to-end (target 01:00)

### Phase 3 — Agentic loop + deploy (01:00 → 06:00)
- ☐ Alternatives → re-evaluation as new run (parent ref)
- ☐ Assistant chat on AMD
- ☐ AWS deploy (EC2 c7a + compose + Caddy)
- ☐ `scripts/acceptance.py` incl. negative tests (Renode crash, AI down, unregistered test, prompt injection, bad citation)

### Phase 4 — Hardening & submission (06:00 → 11:00)
- ☐ AMD benchmark + `docs/AMD_EVIDENCE.md`
- ☐ README, LIMITATIONS, architecture diagram
- ☐ Video (authentic runs), slides, cover; submission

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

- 2026-10-17 13:50 — Plan created from validated brief; D05–D09 decided.
