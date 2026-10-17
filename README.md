# ReleaseProof

**A firmware can boot and still be impossible to upgrade safely.** ReleaseProof checks the
*migration path* — not just whether the new image starts — for supported device/bootloader
configurations, using real builds, real emulation, a deterministic verdict engine and AMD-hosted AI.

> Built for the **AMD Developer Hackathon ACT III** (track: Intelligent Industry).
> Non-official engineering assessments (`official=false`): not a certification.

**Public AWS demo:** https://d1yxcnwgdgjzt6.cloudfront.net

EC2/CloudFront and viewer access were verified on 2026-10-17. See the
[infrastructure audit](docs/INFRA_AUDIT_2026-10-17.md) for scoped cleanup, retained
evidence and the security controls still missing from the older deployed runtime.

## Who it is for

**Industrial IoT manufacturers**, starting with wireless condition-monitoring sensor OEMs.
Firmware leads and product-security teams need to keep installed devices maintainable without
avoidable physical intervention or gaps in monitoring. ReleaseProof verifies a supported
configuration and transition **before rollout**; it neither delivers OTA updates nor manages fleets.

Nordic documents nRF52840 in industrial sensors such as
[NI MON-10411](https://www.nordicsemi.com/Nordic-news/2019/09/National-Instruments-employs-nRF52840-to-wirelessly-transmit-asset-health-data).
That establishes MCU relevance, **not** support for NI's images/bootloaders or a customer relationship.
The first supported scenario is ECDSA P-256 → ML-DSA, not arbitrary industrial firmware changes.

Inventory scanners help identify what changes; OTA platforms deliver updates. Our focus is the
question between them: can the deployed bootloader reach the proposed firmware state? Adjacent
products also offer evidence-backed release gates; no exclusivity or competitor-incapability claim
is made. Commercial packaging and field-service economics remain hypotheses, not measured ROI.

## What it does

1. You pick a **supported configuration** (device + bootloader, pinned versions) and a **change**
   (e.g. *ECDSA P-256 → ML-DSA-87* post-quantum signatures).
2. An **AMD-hosted LLM** proposes the verification plan, restricted to a catalog of registered,
   allow-listed test templates (required tests are enforced by policy).
3. An isolated **runner** builds the bootloader and images with pinned toolchains, signs them with
   ephemeral keys and boots/updates them in **Renode**, running positive and **negative** tests
   (tampered image, wrong key, deployed bootloader receiving the new-generation image, …).
4. Observations (with sha256 of every artifact) are projected into a V1.2 assessment and a
   **deterministic engine** computes three verdicts — *Candidate* (is the target state sound?),
   *Transition* (can deployed devices get there?), *Overall migration* — with an explanation graph
   and a canonical hash.
5. The AI explains the result **citing evidence IDs** and proposes **alternative plans** from an
    allowed set; evaluating one creates a **new** run (history is never mutated).
6. Download a **portable evidence pack** (manifest, assessment/result, dossier, AI traces and
   byte-verified artifacts), and apply a **strict preflight CLI** in CI. `SUCCEEDED` is not a
   deployable verdict: only a complete LIVE assessment with all three verdicts `COMPATIBLE`
   passes. Current configurations correctly block. See [`docs/RELEASE_GATE.md`](docs/RELEASE_GATE.md).

AI checks validate citation IDs and explicit verdict phases before display, including buffered
chat. They do not prove semantic entailment of every sentence; engineering review is still required.

## Supported configurations (live, end-to-end)

| Configuration | Change | Live result (2026-10-17) |
|---|---|---|
| Nordic nRF52840 + **wolfBoot** `4c79eee` (Renode 1.16.1, Arm GCC 14.2) | ECDSA P-256 → ML-DSA-87 | Candidate **COMPATIBLE**, Transition **INCOMPATIBLE**: no bootloader self-update on this port; the deployed ECDSA bootloader rejects the ML-DSA update. Alternative *field-service re-flash* ⇒ **INDETERMINATE** (blocker removed, interrupted-update recovery not observed). |
| Nordic nRF52840 + **MCUboot** `4eba8087` / Zephyr v4.2.0 (Renode 1.16.1, Zephyr SDK 0.17.4) | ECDSA P-256 → ML-DSA | **INCOMPATIBLE**: pinned `imgtool` 2.2.0 refuses ML-DSA (measured); single-stage MCUboot cannot be replaced in the field. Tampered and wrong-key updates are rejected (observed). |

Build/emulation-only runs measured about 42–75 s; AMD planning and explanation add provider
latency, so this is not a full AI-enabled run-time guarantee. Both profiles are `SUPPORTED`,
with historical acceptance in
[`docs/acceptance/20261017T135337Z.json`](docs/acceptance/20261017T135337Z.json).
The strengthened gate now requires AMD planning **and** reporting, complete artifact/result
rehashing and deployed source identity; historical promotion alone does not certify a new build.
The acceptance script writes reports; promotion is a reviewed edit to the profile YAML, not
an automatic side effect.

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

```
Browser ─► CloudFront (public demo) ─► Caddy ─┬─► web (Next.js)
                                            └─► api (FastAPI · orchestrator · SQLite · artifacts)
                                                  ├─► runner-wolfboot  ┐ internal network,
                                                  ├─► runner-mcuboot   ┘ no internet egress
                                                  ├─► adapters ─► V1.2 semantic engine (deterministic)
                                                  └─► AMD-hosted LLM (allow-listed host only)
```

| Layer | Never does |
|---|---|
| Runners (measure) | decide verdicts, run arbitrary commands, reach the internet |
| Adapters (project facts) | invent facts — a missing observation becomes `UNKNOWN` + gap |
| Engine (decide) | depend on the LLM |
| AI (plan, explain, propose) | produce verdicts or measurements, fall back to non-AMD providers |

## AMD usage

- **Inference:** every LLM call (planner, explainer, alternatives, assistant) goes to an endpoint on
  an operator-configured AMD-hosted endpoint. Provider and hardware labels come from `AMD_LLM_*`
  settings; hardware labels are declarations, not remote hardware attestation. Calls are traced
  per run (model, endpoint host, request id, latency, tokens, status) and shown in the UI (`/amd`).
  Recorded smoke (previous default `DeepSeek-V4-Flash`):
  [`docs/AMD_SMOKE_TOKEN_FACTORY.json`](docs/AMD_SMOKE_TOKEN_FACTORY.json)
  (9/10 logical calls OK, one upstream outage). The current default is **`Gemma-4-31B-IT`**
  (Google Gemma on AMD Token Factory); its 2-iteration comparison run is in
  [`docs/AMD_BENCHMARK_PRIOR_20261017T133903Z.json`](docs/AMD_BENCHMARK_PRIOR_20261017T133903Z.json).
  `scripts/amd_benchmark.py` generates
   `docs/AMD_BENCHMARK.json` for schema validity, citation fidelity and injection checks.
   The retained small sample includes upstream outages and unmeasurable metrics; it is not
   a claim of complete reliability or of injection resistance when an adversarial call timed out.
- **Verified demo compute:** AWS EC2 `c7a.2xlarge` (4th-gen **AMD EPYC**) in `eu-west-1`,
  behind CloudFront with validated HTTPS to the origin. Actual resource/health checks are in
  [`docs/INFRA_AUDIT_2026-10-17.md`](docs/INFRA_AUDIT_2026-10-17.md); local acceptance reports
  alone do not attest cloud deployment or current-source equivalence.
- No fallback provider: if the AMD endpoint is unavailable the UI shows `AI_UNAVAILABLE` and the
  deterministic pipeline still runs; verdicts are unaffected.

## Quickstart (local)

Requirements: Docker Engine 26+ with Compose v2.35+, ~12 GB disk for the runner images.
Runners use a volume subpath to keep the database outside their filesystem.

```bash
cp .env.example .env            # set AMD_LLM_* (base URL, key, model, allowed host)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
open http://localhost:8080      # UI; API on http://localhost:8000/api
python scripts/acceptance.py --base http://localhost:8000 --require-ai --env-file .env
```

`.env.example` is preconfigured for **AMD Token Factory**, model `Gemma-4-31B-IT`.
Set only `AMD_LLM_API_KEY` to get started; the key stays server-side. For other available
models, per-module overrides and inference checks, see [`deploy/amd/README.md`](deploy/amd/README.md).
Compose streams structured AMD responses (`AMD_LLM_STRUCTURED_STREAM=1`) to avoid idle
non-streaming connections on long generations, while buffering and validating the complete
JSON before use. Set `0` for an endpoint requiring the legacy non-streaming transport.

Backend tests (Python 3.12+):

```bash
cd backend && python -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"
pytest            # SV01–SV15, golden hashes, adapters, recorded runner streams, API, AI guardrails
```

Additional offline checks, from the repository root (using the backend environment):

```bash
python -m pytest scripts/tests -q
PYTHONPATH=runners/common:runners/wolfboot:runners/mcuboot python -m pytest runners -q
```

On PowerShell use `backend\.venv\Scripts\python.exe` and set `$env:PYTHONPATH` with `;`
instead of `:`. Bash-specific deployment tests skip when Bash is unavailable. Acceptance
starts new live runs and may call the configured AMD endpoint; offline tests do neither.

Code checks, from the repository root (using the backend environment):

```bash
python -m ruff check .
python -m ruff format --check .
npm --prefix web run lint
npm --prefix web run typecheck
npm --prefix web test
```

`ruff.toml` applies the Python checks to the backend, runners and scripts; the frozen
contract and recorded reference artifacts are excluded.

Internet judging demo: add `docker-compose.public.yml` and use HTTPS. **No viewer login or
password is required**, by the owner's explicit submission policy. Do not combine the public
override with `docker-compose.dev.yml`. The API bounds active jobs and POST requests; only
pinned open-source fixtures are accepted. Operator Azure/SSH credentials are never given to judges.

AWS deploy: [`deploy/aws/README.md`](deploy/aws/README.md) (`provision.sh` → `deploy.sh`).
Deployment target: **AWS only**, following the owner's final instruction. The superseded Azure
attempt is retained only as an incident record in [`docs/AZURE_RELEASE_2026-10-17.md`](docs/AZURE_RELEASE_2026-10-17.md).
Public viewer/CloudFront operations: [`deploy/aws/CLOUDFRONT_DEMO.md`](deploy/aws/CLOUDFRONT_DEMO.md).
The live AWS runtime has not yet been rebuilt with all repository hardening changes;
the public override instructions above describe the intended configuration, not its current state.
AMD smoke/benchmark: `scripts/amd_smoke.py`, `scripts/amd_benchmark.py`; self-hosted vLLM on
MI300X: [`deploy/amd/`](deploy/amd/).

## Evidence and reproducibility

Every run stores `manifest.json` with the profile file hash, planned tests, source pins, tool
versions, the sha256 of every artifact (build logs, ELF/BIN, signed images, UART captures, Renode
scripts) and the assessment/result canonical hashes. The recorded proof of concept freeze
(2026-10-01) is available as a clearly-labelled **Reference run**, never as a live run.

The frontend always uses the real API. Synthetic AI responses and assessment scenarios live only
under `backend/tests/`, which is excluded from the runtime package and API Docker image.
Custom orchestrator factories/transports are refused outside `RELEASEPROOF_ENV=test`.
See [`docs/MOCK_AUDIT.md`](docs/MOCK_AUDIT.md) for the audit and retained emulation limitations.

## Known limitations

- Emulation is not hardware: Renode models nRF52840 flash as memory (ReleaseProof adds a minimal
  NVMC model for MCUboot); no power-loss physics, no CryptoCell.
- Interrupted-update recovery (non-atomic window) is **not observed** ⇒ invariant I4 stays
  `UNKNOWN`, so no live migration reaches `COMPATIBLE` today — by design, not by tuning.
- Live RAM usage is not currently measured/projected (including runtime stack); RAM requirements
  stay UNKNOWN. Board capacity and historical linker-region information are not runtime usage.
- Only the configurations above are supported; arbitrary firmware is out of scope.
- The public judging demo is intentionally anonymous. There is no tenant isolation: only open
  fixtures are supported, not customer-data hosting. Active jobs/POST requests are bounded, but
  production use needs stronger identities, per-user quotas and operational controls.

Submission readiness (rules, deliverables and remaining operator steps):
[`docs/HACKATHON_READINESS.md`](docs/HACKATHON_READINESS.md).
Remediation scope and verification: [`docs/COMPLIANCE_REMEDIATION_2026-10-17.md`](docs/COMPLIANCE_REMEDIATION_2026-10-17.md).

Review findings and verification scope: [`docs/CODE_AUDIT.md`](docs/CODE_AUDIT.md).
Critical positioning review and implementation scope:
[`docs/POSITIONING_REVIEW_2026-10-17.md`](docs/POSITIONING_REVIEW_2026-10-17.md).

## Licenses

ReleaseProof code: MIT ([`LICENSE`](LICENSE)). Third-party tools (wolfBoot/wolfSSL GPL-3.0, Zephyr,
MCUboot Apache-2.0, Renode MIT, toolchains) are fetched at pinned commits inside runner images and
not vendored: see [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) and
[`CODE_PROVENANCE.md`](CODE_PROVENANCE.md) (what pre-existed vs. what was built during the event).
