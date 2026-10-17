# ReleaseProof: submission kit (AMD Developer Hackathon ACT III · lablab.ai)

> Yellow-tag placeholders (`[[...]]`) **must** be filled with measured values before submitting. Do not
> replace them with estimates. If a value cannot be measured in time, delete the sentence instead.
> Facts here come from `docs/IMPLEMENTATION_PLAN.md`, `docs/ARCHITECTURE.md`,
> `docs/acceptance/*.json`, `profiles/*.yaml` and the runner READMEs (17 Oct 2026).

> Historical evidence: both profiles were promoted after `docs/acceptance/20261017T135337Z.json`.
> That older gate required only one successful AI call. The final submission must reference the
> fresh strengthened `--require-ai` gate and `docs/RELEASE_EVIDENCE.json`, not infer full AI success
> from historical promotion. Managed GPU identity is not attested. Public AWS infrastructure
> and transport are independently verified in `docs/INFRA_AUDIT_2026-10-17.md`; this does not
> attest current-source equivalence or repository security controls on the older AWS images.
> The deck is now eight slides focused on industrial sensor OEMs. Existing screenshots describe
> historical runs and must be retaken or labelled before submission. Unfilled publication/benchmark
> placeholders remain intentional.

---

## Title

**ReleaseProof: Firmware Migration Assurance**

42 characters. The longer "a firmware can boot..." sentence is the pitch hook, not the form title.

## Track

**Intelligent Industry**

## Short description (≤ 255 characters)

> ReleaseProof helps industrial IoT teams verify firmware migration paths before rollout. Real
> builds, Renode emulation and separate candidate/transition verdicts expose update blockers.
> AMD-hosted AI plans and explains; the engine decides.

Use the single-line version in the form; standard limit 50–255 characters.

## Long description

Industrial sensor OEMs need to know whether deployed devices can reach a new
security configuration, not merely whether a new image boots. Changing signature algorithms
can leave a working candidate that the deployed bootloader cannot accept.

ReleaseProof connects AMD-hosted AI, real firmware builds and Renode emulation to a
deterministic migration-assurance engine. Engineers choose a pinned device/bootloader profile
and a guided change. The AMD Token Factory planner selects registered tests; mandatory
checks cannot be removed. Isolated runners build, sign with ephemeral keys and execute
positive and negative tests. Evidence is linked to logs, source pins and SHA-256 artifacts.
The engine, never the LLM, produces separate candidate, transition and migration verdicts.

Two nRF52840 configurations demonstrate different blockers. With wolfBoot, the ML-DSA-87
candidate boots, but the deployed ECDSA bootloader rejects the update and cannot self-update
on this port. With MCUboot/Zephyr, the pinned imgtool explicitly refuses ML-DSA key types;
tampered and wrong-key updates are rejected in emulation.

AMD AI explains findings with checked citation IDs and proposes allowed alternatives. Human
selection creates a new assessment without rewriting the parent. AI outages are explicit,
with no external-provider fallback; deterministic tests can still run. The submission gate
requires successful AMD planning and reporting, not just any successful AI call.

This is an engineering demo, not certification or proof on silicon. Interrupted-update
recovery remains UNKNOWN. ReleaseProof complements inventory scanners and OTA platforms
by answering the question between them: can this migration proceed as planned?

## Buyer and operational value

First segment: OEMs of wireless condition-monitoring sensors in factories and remote sites.
Buyer: Head of Embedded Engineering, Firmware Lead or Product Security Manager, with OT/operations
as co-sponsor. The operational goal is to keep sensors maintainable without avoidable physical
intervention or gaps in monitoring. Nordic documents nRF52840 in NI MON-10411, Lynxemi and Atomation
products: hardware relevance only, not proprietary firmware support, customers or PQC defects.

Illustrative scenario, **not measured ROI**: 5,000 sensors × hypothetical 5% requiring service ×
hypothetical €250/intervention = €62,500 of exposure, not demonstrated savings. Validate in pilots:
pre-rollout blockers, engineering hours saved, confirmed interventions avoided and cost/profile/run.
Proposed packaging: custom-profile onboarding, then subscription per supported product profile
and assessment volume. No pricing or willingness to pay is validated; no per-device billing claim.

Static inventory and OTA delivery are complementary. Finite State already documents evidence-linked
AI and release gates; ReleaseProof's focus is the deployed-to-candidate bootloader transition and
its separate verdicts. No exclusivity, competitive incapability or head-to-head superiority claim.

Regulatory context: CRA main obligations 11 Dec 2027, reporting 11 Sep 2026, with scope/exclusions
and transitional rules—not a general ML-DSA mandate. CNSA 2.0 applies to US NSS, not all industrial
OEMs. NIST IR 8547 is an initial public draft, not binding law. No certification claim is made.

## Tags

`post-quantum cryptography` · `PQC` · `ML-DSA` · `firmware` · `secure boot` · `embedded` · `IoT` ·
`industrial IoT` · `condition monitoring` · `wolfBoot` · `MCUboot` · `Zephyr` ·
`Renode` · `emulation` · `agentic AI` · `AMD Token Factory` · `FastAPI` · `Next.js`

Do not add AMD Instinct/MI300X, EPYC, vLLM or ROCm deployment tags without evidence of their use.

## Tech stack

| Layer | Technology |
|---|---|
| UI | Next.js (React), Tailwind, Server-Sent Events for live progress |
| API / orchestration | Python 3.12, FastAPI, SQLite, state-machine orchestrator with queue and per-runner semaphore |
| Runners (Docker, internal network, no egress) | **runner-wolfboot**: wolfBoot `4c79eee`, wolfSSL `4aa1ad7`, Arm GNU Toolchain 14.2.rel1, Renode 1.16.1 · **runner-mcuboot**: Zephyr v4.2.0 sysbuild, MCUboot `4eba8087`, imgtool 2.2.0, Zephyr SDK 0.17.4, Renode 1.16.1 + ReleaseProof NVMC flash model (MIT) |
| Decision engine | ReleaseProof V1.2 semantic engine (validate · evaluate · explanation graph · canonical hash), golden-hash regression tests |
| AI gateway | OpenAI-compatible client, configured AMD host allow-list, JSON mode or structured outputs with local schema validation, citation/verdict-echo guardrails, traces |
| AMD | AMD Token Factory managed API, `DeepSeek-V4-Flash`, GPU undisclosed · deployment target AWS EC2 **c7a.2xlarge (AMD EPYC 4th gen)** |
| Edge / deploy | Docker Compose, Caddy (auto-TLS) |

## How we use AMD

ReleaseProof sends every AI step (test planning, cited explanations, alternative plans and the
"Ask about this run" assistant) to **one configured AMD-hosted OpenAI-compatible endpoint**.
The recorded managed configuration is AMD Token Factory with `DeepSeek-V4-Flash`; its specific
GPU is undisclosed. Provider/hardware labels are declarations, not remote attestation.
The endpoint host is allow-listed and there is **no fallback to any other
provider**. If the AMD endpoint is unavailable, the steps are recorded as `AI_UNAVAILABLE` and the
deterministic pipeline continues on its own. The benchmark (`scripts/amd_benchmark.py`, real calls
only) records latency, schema validity, citation/verdict checks and adversarial cases. Quote
only the retained report's actual measurements and sample size. The compute-heavy part consists of cross-compiling
bootloaders, signing images and running Renode emulations for every assessment. It is designed for
 an **AMD EPYC** host (AWS EC2 c7a.2xlarge, Docker Compose); deployment is not attested.

> Honesty note: the retained Token Factory smoke has 9/10 logical calls OK and one outage;
> The small current benchmark retains upstream outages and missing metrics; it is not a
> completed reliability/performance claim. Early screenshots show `AI_UNAVAILABLE`;
> they must not be used as evidence of later AMD-enabled runs. AWS remains a deployment target
> until a completed deployment is independently verified. Do not claim specific GPUs or benchmark
> rates from provider labels or smoke counts.

## AMD evidence checklist (team verification, not an official hidden checklist)

| Item | Value |
|---|---|
| Hardware | Managed LLM GPU undisclosed; self-hosted MI300X is an alternative, not the recorded serving configuration. Host target: AWS EC2 c7a.2xlarge, AMD EPYC 4th gen (Genoa), 8 vCPU / 16 GiB |
| Model | `DeepSeek-V4-Flash` in the retained Token Factory smoke |
| Serving stack | AMD Token Factory managed API; vLLM on MI300X is documented as Plan B in `deploy/amd/README.md` |
| Benchmark | Use the actual sample size, successes and failures in `docs/AMD_BENCHMARK.json`; do not replace missing statistics with smoke counts |
| What ran on AMD | Retained AMD Token Factory inference traces. Existing HTTPS demo: https://d1yxcnwgdgjzt6.cloudfront.net. Verify the frozen hardened release there before the final walkthrough; local acceptance does not attest cloud hardware |

## Architecture

```mermaid
flowchart LR
  subgraph Browser
    UI[Next.js UI<br/>wizard · live run · evidence · alternatives]
  end
  subgraph AWS EC2 c7a (AMD EPYC)
    C[Caddy TLS] --> UI2[web :3000]
    C --> API[FastAPI :8000<br/>orchestrator · SQLite · artifacts]
    API -->|NDJSON /execute| RW[runner-wolfboot<br/>wolfBoot · Arm GCC · Renode]
    API -->|NDJSON /execute| RM[runner-mcuboot<br/>Zephyr · MCUboot · imgtool · Renode]
    API --> AD[Assessment adapters] --> ENG[V1.2 semantic engine<br/>validate · evaluate · canonical hash]
  end
   API -->|OpenAI-compatible, allow-listed host| AMD[(Configured AMD-hosted LLM<br/>managed GPU undisclosed)]
  UI --> C
```

Run lifecycle: `PREPARING → AI_PLAN → DISCOVERY → BUILD_SIGN → EMULATION_TESTS → EVALUATION → NEXT_STEPS`.
Runners **measure**, adapters **project** (a missing observation becomes `UNKNOWN`), the engine
**decides**, and the LLM **proposes and explains**. Also shown on slide 6 of `pitch/slides.pdf`.

## Setup instructions

```bash
git clone https://github.com/francescocarpineti091299/release-proof && cd release-proof
cp .env.example .env            # optional: fill AMD_LLM_BASE_URL / _API_KEY / _MODEL / _ALLOWED_HOSTS
# Local: full stack (web, api, both runners, Caddy) on http://localhost:8080
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
# Acceptance gate: one fresh LIVE run per profile, writes docs/acceptance/<ts>.json
python scripts/acceptance.py --base http://localhost:8080
# AMD benchmark (real calls only, needs AMD_LLM_* exported)
python scripts/amd_benchmark.py --env-file .env -n 5 --out docs/AMD_BENCHMARK.json
# Cloud: AMD EPYC host on AWS (see deploy/aws/README.md)
deploy/aws/provision.sh --region eu-west-1 && deploy/aws/deploy.sh
```

Runner images are about 3.4 GB (wolfBoot) and 3.8 GB (MCUboot). All sources are fetched at
pinned commits at image build time, and a job needs no network. Without `AMD_LLM_*` the app still
works and the AI steps show `AI_UNAVAILABLE`.

## What's real vs roadmap

| Real today (verifiable in the repo and the running app) | Roadmap / not yet done |
|---|---|
| Two LIVE configurations on nRF52840 in Renode 1.16.1 (wolfBoot @4c79eee, MCUboot @4eba8087 / Zephyr v4.2.0), both passing `scripts/acceptance.py` (`docs/acceptance/20261017T124851Z.json`, MCUboot run in `20261017T124626Z.json`) | Real silicon: a hardware-in-the-loop runner on dev kits |
| Real builds, ephemeral keys, Renode boot and update, positive and negative tests, sha256 for every artifact, manifest and canonical hash | Interrupted-update / power-fail test (E12): currently stays `UNKNOWN` |
| Deterministic V1.2 engine with golden-hash regression tests (249 tests green at the integration checkpoint) | Staged hybrid ECDSA + ML-DSA plan (the dual-signature build fails on the pinned wolfBoot commit, as measured) |
| Re-evaluation runs with a parent reference, immutable history, refusal (HTTP 422) of alternatives needing external validation | LMS / hash-based signatures for MCUboot (upstream PR #2707, still in review) |
| Failed-run policy: runner killed ⇒ FAILED, no verdict, `/result` 409 | More boards (STM32, NXP), more bootloader families, key-rotation rulesets |
| AI gateway with schema/citation/verdict guardrails, configured AMD host allow-list, no fallback; real Token Factory smoke and AMD-required acceptance retained | **Completed benchmark numbers** (`[[AMD_LATENCY_P50]]`, `[[AMD_SCHEMA_VALID_RATE]]`) |
| Verified EC2 `c7a.2xlarge` (AMD EPYC) + CloudFront demo: https://d1yxcnwgdgjzt6.cloudfront.net; inventory, TLS and live transport evidence retained | Reviewed deployment of latest application hardening, strict current-source cloud acceptance, off-host backups and operational alarms |
| Both YAML profiles are `SUPPORTED`; historical promotion used `docs/acceptance/20261017T135337Z.json`; current-source strict acceptance must be rerun | Additional supported boards/forks require their own acceptance |
| Evidence pack download; strict preflight CLI with independent integrity checks and engine replay; manual GitHub Actions integration (`docs/RELEASE_GATE.md`) | GitHub-hosted execution and production CI/OTA integration are not attested |

## Evaluation

### One technical result (measured; not measured business savings)

On the wolfBoot configuration, ReleaseProof found in **42 s** a migration blocker that a boot-only
check would pass. The ML-DSA-87 candidate boots, yet deployed devices cannot reach it: there is no
bootloader self-update on nRF52840, and the deployed ECDSA bootloader rejects the ML-DSA update. The
verdict comes with **8/8 tests executed, 21 evidence items and 61 sha256-hashed artifacts**
(LIVE run `RP-20261017T124806Z-a39610`, hash `sha256:a22d6efc…6e54`). The MCUboot run
`RP-20261017T124230Z-7682fc` took 75 s, with 7/7 tests and 50 artifacts. *We do not claim a measured
saving in engineering hours or any ROI. Those would be estimates and are not presented as results.*

### One known limitation

This is **emulation, not silicon**. Renode models nRF52840 flash as plain memory for wolfBoot, and
our MCUboot NVMC model is minimal, so power-loss and timing faults are not reproduced. The
interrupted-update window (E12) is not executed, so INV-I4 stays `UNKNOWN`. That is why the
field-service re-flash alternative is INDETERMINATE and not COMPATIBLE. Only two configurations are
supported, and verdicts are non-official engineering assessments.

### One failure case

**Runner killed mid-run.** In run `RP-20261017T124942Z-23dd8f` (MCUboot), the runner connection
broke (`TOOL_FAILURE`). The run is marked FAILED, **no verdict is issued**, `/result` returns 409,
and nothing falls back to recorded data. A second case was caught by our own acceptance gate: the
stock Renode nRF52840 platform downloads its SVD file at load time. On the no-egress runner network
that failed, and E01 was reported `INCONCLUSIVE` instead of being faked. The gate marked the
wolfBoot run as not passing (`docs/acceptance/20261017T124626Z.json`). The fix bakes in and pins the
SVD.

### Safeguard / human review

The AI **cannot change a verdict**. Its outputs are labelled PROPOSAL and validated against a JSON
schema. Every claim must cite an evidence ID that exists in the run, and the explanation must echo
the engine's verdicts exactly; explicit verdict-phase swaps in report prose are rejected. Chat is
buffered before checking citation IDs and verdict phases. This is not semantic entailment of every
sentence. A **human** chooses whether to evaluate an
alternative, and that creates a new run while the parent stays unchanged. Alternatives that need
external validation are refused (HTTP 422). Every result is marked "Non-official engineering
assessment" and carries the engine version, canonical hash and manifest, so the reviewing engineer
can trace each claim to UART captures and artifacts.

## Links

- Demo: https://d1yxcnwgdgjzt6.cloudfront.net (existing deployment; final hardening must be verified there)
- Video: `[[VIDEO_URL]]`
- Code: https://github.com/francescocarpineti091299/release-proof (public/MIT; publish the reviewed final changes before submission; third-party tools retain their licenses)
- Slides: `pitch/slides.pdf` · Cover: `pitch/cover.png`
- Team: Francesco Carpineti (solo)

## Suggested gallery images (`pitch/assets/`)

1. `cover.png` (cover)
2. `run_wolfboot_incompatible.png`: wolfBoot LIVE run, candidate COMPATIBLE / transition INCOMPATIBLE
3. `run_reeval_indeterminate.png`: re-evaluation of the field-service re-flash, INDETERMINATE
4. `run_mcuboot_incompatible.png`: MCUboot LIVE run, INCOMPATIBLE
5. `mcuboot_pqc_refusal.png`: imgtool 2.2.0 refuses ML-DSA (measured)
6. `wolfboot_negative_tests.png`: E03 / X01 / P01 negative tests with UART evidence
7. `run_failed_killed.png`: runner killed ⇒ FAILED, no verdict
8. `amd.png`: AMD AI panel (**retake after the endpoint is connected**; the current capture shows
   "endpoint not set")

## Sources used in public materials

- NSA, *CNSA 2.0 Algorithms* CSA, May 2025: https://media.defense.gov/2025/May/30/2003728741/-1/-1/0/CSA_CNSA_2.0_ALGORITHMS.PDF
- European Commission, *CRA summary*: https://digital-strategy.ec.europa.eu/en/policies/cra-summary
- Regulation (EU) 2024/2847 (CRA), Art. 64 penalties: https://eur-lex.europa.eu/eli/reg/2024/2847/oj
- NIST IR 8547 ipd, Nov 2024: https://csrc.nist.gov/pubs/ir/8547/ipd
- Nordic / NI MON-10411: https://www.nordicsemi.com/Nordic-news/2019/09/National-Instruments-employs-nRF52840-to-wirelessly-transmit-asset-health-data
- Nordic / Lynxemi: https://www.nordicsemi.com/Nordic-news/2020/04/Lynxemis-Bluetooth-5-2-Bluetooth-LE-sensor-employs-nRF52840
- Nordic / Atomation: https://www.nordicsemi.com/Nordic-news/2023/06/Atomations-Atom-employs-nRF52840-SoC
- ONEKEY, *PQC for connected devices*, Jul 2026: https://www.onekey.com/resource/post-quantum-cryptography-connected-devices
- Binarly docs, CBOM / PQC report: https://docs.binarly.io/user-guides/export/pqc
- Binarly PQC/reachability: https://www.binarly.io/news/binarly-expands-platform-to-enable-post-quantum-compliance-readiness
- Finite State Product Security OS: https://finitestate.io/news/autonomous-product-security-os-launch
- Memfault OTA: https://memfault.com/ota-firmware-updates/
- Mender: https://mender.io/resources/reports-and-guides/ota-updates-best-practices
- Foundries.io security: https://docs.foundries.io/91/reference-manual/security/security.html
- Renode determinism: https://renode.io/news/fully-deterministic-linux-zephyr-micro-ros-testing-in-renode/
- wolfBoot upstream CI: https://github.com/wolfSSL/wolfBoot/blob/master/.github/workflows/test-renode-nrf52.yml
