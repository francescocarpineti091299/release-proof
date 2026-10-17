# Verification evidence

Every number in the README and the submission copy comes from a file in this repository or from
the public demo. This page lists those files and says what each check establishes and what it
does not.

## 1. Live acceptance on the public demo (AWS, AMD Gemma)

`scripts/acceptance.py --require-ai` starts a **new LIVE run** for each supported profile on the
target deployment. A profile passes only if all 27 gates pass. The gates cover:

- the pipeline succeeded, all required templates ran, and at least one positive boot and one
  negative test were observed;
- the deterministic verdict was issued, its canonical hash was recomputed, and every artifact
  hash was rechecked;
- the deployed backend and runner source fingerprints match this repository;
- the AMD planner, explainer and alternatives calls belong to this run, the accepted AMD plan is
  the one that ran, and the AI output passed validation.

Report: [`acceptance/20261017T154930Z.json`](acceptance/20261017T154930Z.json). Target:
`https://d1yxcnwgdgjzt6.cloudfront.net`, model `Gemma-4-31B-IT` on AMD Token Factory.

| Profile | Run | Tests | Artifacts (sha256-verified) | Wall time incl. AI | Verdict (candidate / transition / migration) |
|---|---|---|---|---|---|
| nRF52840 + MCUboot / Zephyr | `RP-20261017T154354Z-092e99` | 6/6 | 45 | 190 s | INCOMPATIBLE / INCOMPATIBLE / INCOMPATIBLE |
| nRF52840 + wolfBoot | `RP-20261017T154715Z-87d365` | 7/7 | 57 | 127 s | COMPATIBLE / INCOMPATIBLE / INCOMPATIBLE |

The runs above are not cherry-picked. Every report the gate produced is kept in
[`acceptance/`](acceptance/), failed ones included:

- [`20261017T154300Z.json`](acceptance/20261017T154300Z.json) ran while the previous runtime
  was being replaced. The source-identity and result-rehash gates failed, and the API returned
  HTTP 502 mid-run. The gate rejected it; it is not counted as a pass.
- [`20261017T124626Z.json`](acceptance/20261017T124626Z.json) failed when the Renode platform
  tried to download its SVD file on a runner with no network. The fix pins the SVD inside the
  runner image.

All verdicts on the demo are reproducible from the [evidence pack](RELEASE_GATE.md) of the
corresponding run.

## 2. Deployment identity and isolation

Public browser journeys, effective budgets, backup preservation and interruption-safe deployment
are summarized in [`DEPLOYMENT.md`](DEPLOYMENT.md). A second independent pair of unchanged
strict reports is retained in [`acceptance/AWS_RELEASE_20261017.json`](acceptance/AWS_RELEASE_20261017.json).

[`AWS_RELEASE_EVIDENCE_20261017.json`](AWS_RELEASE_EVIDENCE_20261017.json) was collected over SSH
from the running AWS host (summary: [`DEPLOYMENT.md`](DEPLOYMENT.md)):

- The backend, wolfBoot runner and MCUboot runner source fingerprints match this repository
  (`source_matches_worktree`: all `true`).
- The runners run as the unprivileged `rp` user with all Linux capabilities dropped. Each mounts
  only the `runs/` subpath of the data volume, so the database is outside its filesystem. Runners
  sit on an `internal` Docker network with no internet route and no AMD credentials.
- The API and web containers run as non-root users (`rp`, `nextjs`).

[`acceptance/aws-release-transport-20261017.json`](acceptance/aws-release-transport-20261017.json)
checks the viewer URL end to end:

- HTTPS UI and static assets load;
- the health and configuration endpoints answer, and query parameters are forwarded;
- a completed result can be fetched, and its manifest downloads with a matching hash.

Host: AWS EC2 `c7a.2xlarge` (4th-gen AMD EPYC, 8 vCPU, 16 GiB) in `eu-west-1`, behind CloudFront.
CloudFront has caching disabled and validates HTTPS to the origin. The origin accepts HTTPS only
from CloudFront.

## 3. AMD inference

| File | What it records |
|---|---|
| [`AMD_SMOKE_GEMMA.json`](AMD_SMOKE_GEMMA.json) | `Gemma-4-31B-IT` on AMD Token Factory: 10/10 logical calls OK across planner, explainer, alternatives and assistant; p50 latency 21.5 s, p95 52.3 s; request IDs present for all 10 |
| [`AMD_SMOKE_TOKEN_FACTORY.json`](AMD_SMOKE_TOKEN_FACTORY.json) | Earlier smoke with `DeepSeek-V4-Flash`: 9/10 calls OK, 1 upstream outage |
| [`AMD_BENCHMARK.json`](AMD_BENCHMARK.json), [`AMD_BENCHMARK_PRIOR_20261017T133903Z.json`](AMD_BENCHMARK_PRIOR_20261017T133903Z.json) | Small samples of schema validity, citation fidelity and prompt-injection cases, including upstream timeouts |

The live `/api/amd` page shows the configured provider and the per-module models. It also shows
`fallback_provider: null` and aggregate trace counts. The managed service does not disclose the
GPU model, so no specific accelerator is claimed. A self-hosted vLLM/ROCm path for AMD Instinct
MI300X is documented in [`../deploy/amd/README.md`](../deploy/amd/README.md).

## 4. Offline test suites

| Suite | Command | Result |
|---|---|---|
| Backend: semantic conformance SV01–SV15, golden hashes, adapters, orchestrator, API, AI guardrails | `cd backend && pytest` | 422 passed, 1 skipped |
| Runners and scripts: UART parsing, build/sign classification, acceptance gate, release gate, deploy scripts | `pytest runners scripts/tests` | 96 passed, 2 skipped (Bash-only on Windows) |
| Python lint and format | `ruff check . && ruff format --check .` | clean |
| Frontend | `npm --prefix web run lint && npm --prefix web run typecheck && npm --prefix web test` | clean, 8 tests passed |

## 5. No mocks in the product path

- The web UI calls only the real API. No browser-side mock client exists.
- Synthetic AI responses and assessment scenarios exist only under `backend/tests/`. That folder
  is excluded from the runtime package and from the API image.
- Outside `RELEASEPROOF_ENV=test`, the orchestrator refuses custom runner factories and
  transports.
- The recorded proof-of-concept freeze (`reference/wp0-freeze-20261001/`) is shown only as a
  labelled **Reference run**. It is never mixed with live results.

## 6. What this evidence does not establish

- **Renode emulation, not silicon.** There is no power-loss physics and no CryptoCell, and the
  flash model is minimal.
- **Interrupted-update recovery is not exercised**, so invariant I4 stays `UNKNOWN`. No migration
  reaches `COMPATIBLE` today, by design.
- **Hashes are not trust.** Artifact hashes prove integrity of what was recorded; they do not
  prove trusted acquisition or signed provenance.
- **The demo is anonymous and single-tenant.** Jobs and POST requests are bounded, and only
  pinned open-source fixtures are accepted. It is not a customer-data service.
- **Assessments are non-official** (`official=false`). They are not a certification.
