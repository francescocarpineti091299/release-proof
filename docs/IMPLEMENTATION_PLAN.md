# ReleaseProof — Implementation Plan (living document)

> Owner: tech lead · Started: 2026-10-17 13:50 CEST · Update this file at the end of every phase.
> Source brief: `../ReleaseProof_AMD_ACT_III_Engineering_Brief.md` · POC: `../../firmware-migration-assurance` (HEAD `ef408b8`).

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

### Phase 0 — Foundations (13:50 → 15:30)
- ☐ Scaffold repo, LICENSE (MIT), CODE_PROVENANCE, THIRD_PARTY_NOTICES
- ☐ Port `src/` → `backend/releaseproof/core`, contract pack → `contract/`; all ported tests + golden hashes green
- ☐ D05 additive patch + regression test
- ☐ Shared contracts: RunnerEvent/Observation schema, profile schema, test catalog, AI schemas (TestPlanProposal, NarrativeReport, ChangeProposal), API models
- DoD: `pytest` green, golden baseline/signer-bound hashes unchanged.

### Phase 1 — Parallel workstreams (15:30 → 19:00)
- ☐ WS-A wolfBoot runner (Docker, isolated workdir, G1/G2/E03/X01/T1/layout)
- ☐ WS-B MCUboot spike → runner (**go/no-go 18:00**)
- ☐ WS-C API + orchestrator (jobs, SSE, artifacts, idempotency, queue)
- ☐ WS-D AI gateway (planner, explainer, alternatives, analyst; stub only in tests)
- ☐ WS-E adapters A/B → V1.2 assessments
- ☐ WS-F web UI (wizard, live job, result, evidence, alternatives, AMD panel, reference run)

### Phase 2 — Integration (19:00 → 01:00)
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
