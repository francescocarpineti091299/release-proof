# ReleaseProof

**Firmware migration assurance for industrial IoT: find out whether devices already in the field
can actually accept a new firmware security configuration, before rollout.**

A new image can boot perfectly and still never reach a single installed device. That happens
when the bootloader already in the field rejects it, and post-quantum signature migrations
(ECDSA P-256 → ML-DSA) are exactly that kind of change. ReleaseProof catches the gap before
rollout:

- it builds the real bootloader and images with pinned toolchains, signs them with ephemeral keys
  and boots and updates them in Renode emulation;
- a deterministic engine issues separate verdicts for the **candidate** firmware and for the
  **transition** from the deployed state;
- AMD-hosted Google Gemma plans the tests and explains the result, citing evidence, but never
  decides the verdict.

| | |
|---|---|
| **Live demo** (anonymous, no login) | https://d1yxcnwgdgjzt6.cloudfront.net |
| **Track** | AMD Developer Hackathon ACT III · Intelligent Industry |
| **AI** | `Gemma-4-31B-IT` on AMD Token Factory, no fallback provider |
| **Compute** | AWS EC2 `c7a.2xlarge`, 4th-gen AMD EPYC |
| **Pitch deck** | [`pitch/slides.pdf`](pitch/slides.pdf) |
| **Evidence** | [`docs/EVIDENCE.md`](docs/EVIDENCE.md) · deployment: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) |

## Key results (measured on the public demo, 17 Oct 2026)

| Configuration | Change | Result | Time | Proof |
|---|---|---|---|---|
| Nordic nRF52840 + wolfBoot `4c79eee` | ECDSA P-256 → ML-DSA-87 | Candidate **COMPATIBLE**, transition **INCOMPATIBLE**: the ML-DSA image boots, but the deployed ECDSA bootloader rejects the update and this port cannot update its own bootloader | 127 s, 7/7 tests, 57 hashed artifacts | `RP-20261017T154715Z-87d365` |
| Nordic nRF52840 + MCUboot `4eba8087` / Zephyr v4.2.0 | ECDSA P-256 → ML-DSA | **INCOMPATIBLE**: the pinned `imgtool` 2.2.0 refuses ML-DSA keys (run, not assumed); single-stage MCUboot cannot be replaced in the field; tampered and wrong-key updates are rejected | 190 s, 6/6 tests, 45 hashed artifacts | `RP-20261017T154354Z-092e99` |
| wolfBoot alternative: *field-service re-flash* | Re-evaluated as a new run on the parent's evidence | **INDETERMINATE**: the blocker is removed, but recovery from an interrupted update was not observed | no new emulation | `RP-20261017T155907Z-42859a` (parent `…87d365`) |

Both runs passed all 27 gates of the strict acceptance check
([`docs/acceptance/20261017T154930Z.json`](docs/acceptance/20261017T154930Z.json)). The gates
include:

- every artifact hash and the canonical result hash recomputed;
- the deployed source matching this repository;
- AMD planning, explanation and alternatives validated for that specific run.

A boot-only check passes the wolfBoot candidate. ReleaseProof reports the blocker that would have
stranded the installed fleet.

## The problem

Industrial sensor OEMs must keep installed devices updatable for years, often in places that are
expensive to reach. Nordic documents the nRF52840 in industrial condition-monitoring sensors such
as [NI MON-10411](https://www.nordicsemi.com/Nordic-news/2019/09/National-Instruments-employs-nRF52840-to-wirelessly-transmit-asset-health-data).
That shows the chip is used in such devices. It does not imply support for NI firmware.

Firmware security requirements are moving:

- **EU Cyber Resilience Act:** vulnerability reporting obligations from 11 Sep 2026, main
  obligations from 11 Dec 2027 ([summary](https://digital-strategy.ec.europa.eu/en/policies/cra-summary)).
- **US NSS (CNSA 2.0):** CNSA 2.0 sets deadlines for moving software and firmware signing to
  quantum-resistant algorithms in US national security systems
  ([NSA CSA, May 2025](https://media.defense.gov/2025/May/30/2003728741/-1/-1/0/CSA_CNSA_2.0_ALGORITHMS.PDF)).
- **NIST:** draft NIST IR 8547 proposes deprecating today's quantum-vulnerable signatures
  ([NIST IR 8547 ipd](https://csrc.nist.gov/pubs/ir/8547/ipd)).

Changing the signature algorithm is a change to the **trust chain**, not just to the image. The
existing tools cover the two ends:

- inventory scanners (for example Binarly, ONEKEY, Finite State) find what must change;
- OTA platforms (for example Memfault, Mender) deliver the update.

ReleaseProof answers the question between them: **can the deployed bootloader get from today's
state to the proposed one?**

**Who uses it:** firmware leads and product-security engineers at industrial IoT OEMs, as a gate
in the release process. The first segment is OEMs of wireless condition-monitoring sensors.

**What it improves:** an incompatible migration is found in two to three minutes per
configuration, in emulation, before any device is touched. The time includes AMD planning and
explanation; the builds and emulation themselves take 45–60 s. Shipping that migration would instead mean
devices that need physical service, or that stop receiving security updates. We do not claim a
measured ROI: savings depend on fleet size and service cost, and would have to be validated in
pilots.

## How it works

1. **Pick a supported configuration and a change.** The configuration is a device plus a
   bootloader, with every commit and toolchain pinned. The change is, for example, *ECDSA P-256 →
   ML-DSA-87*.
2. **AMD Gemma plans the verification.** The planner orders the registered test templates and can
   add optional ones. Required tests are enforced by policy, and unknown templates are blocked and
   shown.
3. **An isolated runner measures.** It builds the bootloader and the images, signs them with
   ephemeral keys, then boots and updates them in **Renode**. It runs positive tests and
   **negative** ones: a tampered image, the wrong key, and the deployed bootloader receiving the
   new-generation image. Every UART capture, log, ELF/BIN and signed image is SHA-256 hashed.
4. **Adapters project the facts.** Runner observations become a V1.2 assessment. A missing
   observation becomes `UNKNOWN` plus a gap, never an invented fact.
5. **A deterministic engine decides.** It issues three verdicts:
   - *Candidate*: is the target state sound?
   - *Transition*: can deployed devices get there?
   - *Migration*: the overall result.

   Each verdict comes with an explanation graph and a canonical hash.
6. **AMD Gemma explains and proposes.** It writes a report in which every claim cites an
   evidence ID, and it proposes alternative plans from an allowed set. An engineer chooses whether
   to evaluate one. Evaluating it creates a **new run**; the parent run is never modified.
7. **Gate the release.** A portable evidence pack (ZIP with a SHA-256 index) and a strict
   preflight CLI/GitHub Action block the release unless all three verdicts are `COMPATIBLE`. See
   [`docs/RELEASE_GATE.md`](docs/RELEASE_GATE.md).

```
Browser ─► CloudFront HTTPS ─► Caddy ─┬─► web (Next.js)
                                     └─► api (FastAPI · orchestrator · SQLite · artifacts)
                                           ├─► runner-wolfboot  ┐ internal network,
                                           ├─► runner-mcuboot   ┘ no internet egress
                                           ├─► adapters ─► V1.2 semantic engine (deterministic)
                                           └─► AMD Token Factory · Gemma (allow-listed host)
```

| Layer | Does | Never does |
|---|---|---|
| Runners | Build, sign, emulate, parse UART, hash artifacts | Decide verdicts, run arbitrary commands, reach the internet |
| Adapters | Project observations into an assessment | Invent facts |
| Engine | Compute verdicts, the explanation graph and the canonical hash | Depend on the LLM |
| AI gateway | Plan, explain with citations, propose alternatives, answer questions about a run | Produce verdicts or measurements, fall back to a non-AMD provider |

More detail, including trust boundaries: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## How AMD is used

- **Every LLM call goes to AMD.** The planner, explainer, alternatives and the "Ask about this
  run" assistant all call Google **Gemma-4-31B-IT** on **AMD Token Factory**, through an
  OpenAI-compatible client restricted to an allow-listed host.
- **No fallback.** If the endpoint is down, the AI steps show `AI_UNAVAILABLE` and the
  deterministic pipeline still produces the same verdict. No other provider is ever called.
- **Every call is traced.** Each trace records the run, model, host, request ID, latency, tokens
  and status. Traces appear in the run's *AMD AI* tab and on `/amd`. Smoke test:
  [10/10 Gemma calls OK](docs/AMD_SMOKE_GEMMA.json).
- **The model output is untrusted input.** It must pass:
  - JSON-schema validation;
  - template allow-lists;
  - a check that every cited evidence ID exists in the run;
  - an exact echo of the engine's verdicts.

  Tool output passed to the model is wrapped as untrusted data, which defends against prompt
  injection through UART logs. Chat answers are buffered and checked before display.
- **Compute runs on AMD EPYC.** Cross-compilation, signing and Renode emulation for every
  assessment run on AWS EC2 `c7a.2xlarge`.
- **Self-hosted option.** vLLM on AMD Instinct MI300X with ROCm is documented in
  [`deploy/amd/`](deploy/amd/README.md).

## Quickstart

Requirements: Docker Engine 26+ with Compose v2.35+, and about 12 GB of disk for the runner
images.

```bash
cp .env.example .env    # set AMD_LLM_API_KEY; Token Factory + Gemma are preconfigured
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
# UI: http://localhost:8080 · API: http://localhost:8000/api
python scripts/acceptance.py --base http://localhost:8080 --require-ai --env-file .env
```

`acceptance.py` starts one fresh LIVE run per profile. Without `AMD_LLM_*` the app still works,
and the AI steps report `AI_UNAVAILABLE`. Per-module model overrides and inference checks are in
[`deploy/amd/README.md`](deploy/amd/README.md).

**Public deployment** (single AMD EPYC host behind CloudFront): see
[`deploy/aws/README.md`](deploy/aws/README.md). The public override,
`docker-compose.public.yml`, keeps the demo anonymous but limits concurrent jobs and POST
requests.

## Tests

```bash
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
pytest                                   # 422 passed: SV01–SV15 conformance, golden hashes, API, AI guardrails
cd .. && PYTHONPATH=runners/common:runners/wolfboot:runners/mcuboot \
  python -m pytest runners scripts/tests  # runner parsing, acceptance/release gates, deploy scripts
python -m ruff check . && python -m ruff format --check .
npm --prefix web run lint && npm --prefix web run typecheck && npm --prefix web test
```

On PowerShell, use `backend\.venv\Scripts\python.exe` and separate `PYTHONPATH` entries with `;`.
Offline tests never start builds or call the AMD endpoint.

## Design decisions

- **The LLM never decides.** Verdicts come from a versioned semantic contract
  ([`contract/PQC_Engineering_Pack_V1_2`](contract/PQC_Engineering_Pack_V1_2/README.md)) with
  golden-hash regression tests. The same evidence always gives the same verdict and hash.
- **Candidate and transition are separate verdicts.** That separation is what exposes "it boots
  but it can't be reached".
- **An unknown is not a pass.** An unobserved property stays `UNKNOWN` and blocks `COMPATIBLE`.
  The verdicts were never adjusted to look better: today every supported migration is correctly
  blocked.
- **History is immutable.** Choosing an alternative creates a new run linked to its parent. A
  failed runner produces `FAILED` and no verdict; nothing falls back to recorded data.
- **Two bootloaders on one chip.** wolfBoot and MCUboot fail for different reasons, and the same
  engine explains both.

## FAQ

**Is any part of the demo mocked?** No. Synthetic AI responses exist only in `backend/tests/` and
are excluded from the runtime image. The recorded proof-of-concept run is shown only as a labelled
*Reference run*.

**Why does nothing reach COMPATIBLE?** Recovery from an interrupted update (power loss mid-swap)
is not exercised in emulation, so invariant I4 stays `UNKNOWN`. Reporting a pass without that
evidence would be wrong.

**Can it check my own firmware?** Not yet. Only the pinned, open-source configurations above are
supported. Each new board or bootloader family needs its own profile and acceptance run.

**Does it replace OTA or SBOM tools?** No. It sits between them, as the release gate for one
question: can the deployed bootloader get from today's state to the proposed one?

## Limitations

- **Renode emulation, not silicon.** There is no power-loss physics and no CryptoCell. MCUboot
  uses a minimal ReleaseProof NVMC flash model.
- **Interrupted-update recovery** and runtime RAM usage are not measured. Both stay `UNKNOWN`.
- **Two supported configurations**, both on nRF52840. Arbitrary firmware upload is out of scope.
- **The demo is anonymous and single-tenant**, with bounded jobs and requests. Production use
  needs identities, per-tenant storage and quotas.
- **Assessments are non-official engineering results** (`official=false`), not certification.
  The managed AMD service does not disclose its GPU model.

## Repository map

| Path | Contents |
|---|---|
| `backend/releaseproof/` | FastAPI API, orchestrator, AI gateway, adapters, semantic engine (`core/`) |
| `runners/` | wolfBoot and MCUboot runner images (build, sign, Renode, UART parsing) |
| `profiles/` | Supported configurations and the registered test catalog |
| `contract/` | V1.2 semantic contract, JSON schemas, golden vectors |
| `web/` | Next.js UI: wizard, live run over SSE, decision, evidence, alternatives, AMD panel |
| `scripts/` | Acceptance gate, release gate CLI, AMD smoke/benchmark, deployment evidence |
| `deploy/` | AWS (EC2 + CloudFront) and self-hosted AMD vLLM scripts |
| `docs/` | Architecture, release gate, verification evidence and acceptance reports |

## Licenses and provenance

ReleaseProof is MIT licensed ([`LICENSE`](LICENSE)). Third-party tools are fetched at pinned
commits inside the runner images and are not vendored: wolfBoot and wolfSSL (GPL-3.0), Zephyr and
MCUboot (Apache-2.0), Renode (MIT), and the toolchains. See
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and [`DEPENDENCIES.md`](DEPENDENCIES.md).
[`CODE_PROVENANCE.md`](CODE_PROVENANCE.md) lists what was built during the hackathon and what
was pre-existing.
