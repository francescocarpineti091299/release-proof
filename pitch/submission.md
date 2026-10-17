# ReleaseProof: submission kit (AMD Developer Hackathon ACT III · lablab.ai)

> Yellow-tag placeholders (`[[...]]`) **must** be filled with measured values before submitting. Do not
> replace them with estimates. If a value cannot be measured in time, delete the sentence instead.
> Facts here come from `docs/IMPLEMENTATION_PLAN.md`, `docs/ARCHITECTURE.md`,
> `docs/acceptance/*.json`, `profiles/*.yaml` and the runner READMEs (17 Oct 2026).

---

## Title

**ReleaseProof: a firmware can boot and still be impossible to upgrade safely**

(Short form if the field is limited: **ReleaseProof: Firmware Migration Assurance**)

## Track

**Intelligent Industry**

## Short description (≤ 255 characters)

> ReleaseProof checks whether deployed devices can actually migrate to post-quantum firmware
> signatures. It uses real builds, Renode emulation and a deterministic verdict. AMD-hosted AI plans
> and explains but never decides.

(221 characters including spaces. The count was checked with PowerShell `.Length` on the
single-line version.)

## Long description

Industrial and IoT fleets stay in the field for 10–20 years, and their secure bootloaders verify
firmware with keys and algorithms chosen long before post-quantum cryptography. The deadlines are now
concrete:

- NSA CNSA 2.0 requires software and firmware signing to use CNSA 2.0 algorithms exclusively by 2030.
- NIST IR 8547 (draft) disallows ECDSA and RSA signatures after 2035.
- The EU Cyber Resilience Act fully applies on 11 December 2027, and products must remain
  maintainable with security updates.

Teams usually check one thing: "does the new ML-DSA image boot?" That check is necessary but not
sufficient. **A firmware can boot and still be impossible to upgrade safely**, because the
bootloader already deployed in the field may reject the new image and may have no way to replace
itself.

**ReleaseProof verifies the migration path, not just the new image.** An engineer picks a verified
configuration (device + bootloader, all versions pinned) and a change (for example ECDSA P-256 →
ML-DSA-87), then clicks *Run assessment*. A LIVE run then:

1. builds the deployed and candidate bootloaders and images with pinned toolchains and signs them
   with ephemeral keys;
2. boots and updates them in **Renode** on an emulated **Nordic nRF52840**;
3. runs **positive and negative tests**: tampered image, cross-generation update (deployed
   bootloader vs. candidate image), wrong key, and candidate rejects classical;
4. hashes every artifact with sha256 and projects the observations into the deterministic
   **V1.2 semantic engine**. The engine issues three separate verdicts (candidate, transition,
   migration) with an explanation graph, a canonical result hash and a manifest.

A run takes about a minute (42–75 s measured today). Two configurations run end to end and pass our
acceptance gate:

- **wolfBoot @4c79eee (ECDSA P-256 → ML-DSA-87):** the candidate is **COMPATIBLE** (the ML-DSA-87
  bootloader and image build and boot), but the transition is **INCOMPATIBLE**. wolfBoot has no
  bootloader self-update on nRF52840, and the deployed ECDSA bootloader rejects the ML-DSA update
  (`Update type invalid 0xB01!=0x200`, v1 keeps running). In short, it boots but it does not migrate.
- **MCUboot @4eba8087 / Zephyr v4.2.0 (ECDSA P-256 → ML-DSA):** the result is **INCOMPATIBLE**. The
  pinned imgtool 2.2.0 refuses `ml-dsa-44/65/87` (measured, not assumed), and single-stage MCUboot
  cannot be replaced in the field.

**The agentic loop.** The AMD-hosted LLM plans which registered optional tests to run. Required tests
always run, and unknown templates are blocked. After the verdict, the LLM explains it with citations
to real evidence IDs and proposes alternative plans from the profile's allowed set. When a human
picks an alternative, ReleaseProof creates a **new** run. For wolfBoot, *re-flash the bootloader in
a field-service window* is re-evaluated as **INDETERMINATE**: the blocker is removed, but recovery
from an interrupted update was never observed, so the result is an honest unknown and not a pass.
The parent run is never modified.

**The AI never decides.** The safeguards are schema-validated outputs, citation checks, a
verdict-echo check, an allow-listed AMD host with no fallback provider, tool output wrapped as
untrusted data, and no shell access. If a runner dies mid-run, the run is FAILED and no verdict is
issued. A tool failure is never turned into a result.

ReleaseProof is complementary to CBOM/SBOM scanners (they tell you *what* to migrate) and to OTA
platforms (they *deliver* the update). It answers the question in between: **can this fleet actually
get there?**

## Tags

`post-quantum cryptography` · `PQC` · `ML-DSA` · `firmware` · `secure boot` · `embedded` · `IoT` ·
`industrial IoT` · `Cyber Resilience Act` · `CNSA 2.0` · `wolfBoot` · `MCUboot` · `Zephyr` ·
`Renode` · `emulation` · `agentic AI` · `AMD Instinct` · `AMD EPYC` · `AMD Developer Cloud` ·
`vLLM` · `ROCm` · `FastAPI` · `Next.js`

(Keep `vLLM` / `ROCm` only if the final AMD serving stack is self-hosted vLLM on ROCm. Check this
against `[[AMD_SERVING_STACK]]`.)

## Tech stack

| Layer | Technology |
|---|---|
| UI | Next.js (React), Tailwind, Server-Sent Events for live progress |
| API / orchestration | Python 3.12, FastAPI, SQLite, state-machine orchestrator with queue and per-runner semaphore |
| Runners (Docker, internal network, no egress) | **runner-wolfboot**: wolfBoot `4c79eee`, wolfSSL `4aa1ad7`, Arm GNU Toolchain 14.2.rel1, Renode 1.16.1 · **runner-mcuboot**: Zephyr v4.2.0 sysbuild, MCUboot `4eba8087`, imgtool 2.2.0, Zephyr SDK 0.17.4, Renode 1.16.1 + ReleaseProof NVMC flash model (MIT) |
| Decision engine | ReleaseProof V1.2 semantic engine (validate · evaluate · explanation graph · canonical hash), golden-hash regression tests |
| AI gateway | OpenAI-compatible client, AMD-hosted endpoint only (host allow-list), JSON-schema structured outputs, citation and verdict-echo guardrails, traces |
| AMD | AMD Instinct-hosted LLM on AMD Developer Cloud (`[[AMD_MODEL]]` on `[[AMD_HARDWARE]]`, `[[AMD_SERVING_STACK]]`) · deployment target AWS EC2 **c7a.2xlarge (AMD EPYC 4th gen)** |
| Edge / deploy | Docker Compose, Caddy (auto-TLS) |

## How we use AMD

ReleaseProof sends every AI step (test planning, cited explanations, alternative plans and the
"Ask about this run" assistant) to **one OpenAI-compatible endpoint running on AMD Instinct
hardware on AMD Developer Cloud**: `[[AMD_MODEL]]` served with `[[AMD_SERVING_STACK]]` on
`[[AMD_HARDWARE]]`. The endpoint host is allow-listed and there is **no fallback to any other
provider**. If the AMD endpoint is unavailable, the steps are recorded as `AI_UNAVAILABLE` and the
deterministic pipeline continues on its own. Our benchmark (`scripts/amd_benchmark.py`, real calls
only) measured a p50 latency of `[[AMD_LATENCY_P50]]` and a schema-valid response rate of
`[[AMD_SCHEMA_VALID_RATE]]`. It also measures citation fidelity, verdict-echo fidelity and
prompt-injection leaks. The compute-heavy part of the product consists of cross-compiling
bootloaders, signing images and running Renode emulations for every assessment. It is designed for
an **AMD EPYC** host (AWS EC2 c7a.2xlarge, Docker Compose) reachable at `[[DEMO_URL]]`.

> Honesty note (delete once filled): when this kit was written, the AMD API key was still pending
> and the AWS deployment was blocked on IAM permissions. All runs in the screenshots executed on
> the developer laptop (Docker Desktop) with `AI_UNAVAILABLE` and the deterministic fallback plan.
> Do not claim "ran on AMD" for any number that was not measured on AMD.

## AMD evidence checklist (lablab hidden checklist)

| Item | Value |
|---|---|
| Hardware | LLM: `[[AMD_HARDWARE]]` (AMD Developer Cloud) · Host: AWS EC2 c7a.2xlarge, AMD EPYC 4th gen (Genoa), 8 vCPU / 16 GiB |
| Model | `[[AMD_MODEL]]` |
| Serving stack | `[[AMD_SERVING_STACK]]` (Plan A: AMD Token Factory managed API · Plan B: vLLM `vllm/vllm-openai-rocm` on MI300X, see `deploy/amd/README.md`) |
| Benchmark | p50 latency `[[AMD_LATENCY_P50]]` · schema-valid rate `[[AMD_SCHEMA_VALID_RATE]]` · report `docs/AMD_BENCHMARK.json` (generated by `scripts/amd_benchmark.py -n 5`) |
| What ran on AMD | Every LLM call (planner, explainer, alternatives, assistant) on AMD Instinct. The whole stack (builds, Renode, engine, UI) on the EPYC host once deployed at `[[DEMO_URL]]` |

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
  API -->|OpenAI-compatible, allow-listed host| AMD[(LLM on AMD Instinct<br/>AMD Developer Cloud)]
  UI --> C
```

Run lifecycle: `PREPARING → AI_PLAN → DISCOVERY → BUILD_SIGN → EMULATION_TESTS → EVALUATION → NEXT_STEPS`.
Runners **measure**, adapters **project** (a missing observation becomes `UNKNOWN`), the engine
**decides**, and the LLM **proposes and explains**. Also shown on slide 6 of `pitch/slides.pdf`.

## Setup instructions

```bash
git clone [[GITHUB_URL]] && cd releaseproof
cp .env.example .env            # optional: fill AMD_LLM_BASE_URL / _API_KEY / _MODEL / _ALLOWED_HOSTS
# Local: full stack (web, api, both runners, Caddy) on http://localhost:8080
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
# Acceptance gate: one fresh LIVE run per profile, writes docs/acceptance/<ts>.json
python scripts/acceptance.py --base http://localhost:8080
# AMD benchmark (real calls only, needs AMD_LLM_* exported)
python scripts/amd_benchmark.py -n 5 --out docs/AMD_BENCHMARK.json
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
| AI gateway with schema, citation and verdict-echo guardrails, AMD-only host allow-list, no fallback provider, prompt-injection wrapping (unit-tested with a stub) | **Live AMD endpoint and benchmark numbers** (`[[AMD_MODEL]]`, `[[AMD_LATENCY_P50]]`, `[[AMD_SCHEMA_VALID_RATE]]`) |
| AWS deploy scripts for EC2 c7a (AMD EPYC) | **Public deployment** (`[[DEMO_URL]]`), which was blocked on IAM permissions when this was written |
| Both profiles are still flagged `EXPERIMENTAL` in `profiles/*.yaml` (promotion to `SUPPORTED` is a manual step after the gate) | CI integration (GitHub/GitLab action) and evidence-pack export |

## Evaluation

### One business result (measured)

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
the engine's verdicts exactly, otherwise it is rejected. A **human** chooses whether to evaluate an
alternative, and that creates a new run while the parent stays unchanged. Alternatives that need
external validation are refused (HTTP 422). Every result is marked "Non-official engineering
assessment" and carries the engine version, canonical hash and manifest, so the reviewing engineer
can trace each claim to UART captures and artifacts.

## Links

- Demo: `[[DEMO_URL]]`
- Video: `[[VIDEO_URL]]`
- Code: `[[GITHUB_URL]]` (MIT; third-party tools fetched at pinned commits, see `THIRD_PARTY_NOTICES.md`)
- Slides: `pitch/slides.pdf` · Cover: `pitch/cover.png`
- Team: `[[TEAM]]`

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
- IoT Analytics, connected IoT devices, Oct 2025: https://iot-analytics.com/number-connected-iot-devices/
- MarketsandMarkets, PQC market, Oct 2025: https://www.marketsandmarkets.com/Market-Reports/post-quantum-cryptography-market-126986626.html
- Mordor Intelligence, secure boot & firmware security market, Jul 2025: https://www.mordorintelligence.com/industry-reports/secure-boot-and-firmware-security-market
- ABI Research, PQC press release, 29 Apr 2025: https://www.abiresearch.com/press/new-algorithmic-standards-and-migration-policy-timelines-propel-post-quantum-cryptography-toward-billion-dollar-market-by-2030
- ONEKEY, *PQC for connected devices*, Jul 2026: https://www.onekey.com/resource/post-quantum-cryptography-connected-devices
- Binarly docs, CBOM / PQC report: https://docs.binarly.io/user-guides/export/pqc
- wolfBoot upstream CI: https://github.com/wolfSSL/wolfBoot/blob/master/.github/workflows/test-renode-nrf52.yml
