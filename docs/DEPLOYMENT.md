# Public deployment (AWS)

**Demo URL:** https://d1yxcnwgdgjzt6.cloudfront.net. It is anonymous: no login, password or
cloud account is needed.

## Runtime (17 Oct 2026)

- **Host and edge.** AWS EC2 `c7a.2xlarge` (4th-gen AMD EPYC, 8 vCPU, 16 GiB) in `eu-west-1`,
  behind CloudFront. The origin is HTTPS-only, caching is disabled and HTTP redirects to HTTPS.
- **Release.** The application is built from commit `ca344e1`. The backend and runner source
  fingerprints were measured on the host and match this repository:
  [`AWS_RELEASE_EVIDENCE_20261017.json`](AWS_RELEASE_EVIDENCE_20261017.json).
- **Container isolation.**
  - The API and both runners run as UID 10001.
  - The runners drop all capabilities and have CPU/RAM/PID limits.
  - The runners have no network egress and mount only the `runs/` volume subpath, so they
    cannot see SQLite or the AMD credentials.
- **Budgets.** At most 4 active assessments and 20 POST requests per minute. Experimental
  profiles are disabled.
- **Health.** The anonymous UI/API health check returns HTTP 200 with normal certificate
  validation, and SQLite `quick_check` reports `ok`.

## Live proof

[`acceptance/AWS_RELEASE_20261017.json`](acceptance/AWS_RELEASE_20261017.json) combines the
unchanged records from `20261017T154918Z.json` and `20261017T155244Z.json`. A second complete
pass of both profiles is in `20261017T154930Z.json`.

| Profile | LIVE run | Strict gates | Hashed artifacts | Verdict (candidate / transition / migration) |
|---|---|---|---|---|
| MCUboot | `RP-20261017T154354Z-092e99` | 27/27 PASS | 45 | INCOMPATIBLE / INCOMPATIBLE / INCOMPATIBLE |
| wolfBoot | `RP-20261017T154902Z-43d7a0` | 27/27 PASS | 57 | COMPATIBLE / INCOMPATIBLE / INCOMPATIBLE |

Each run passes these checks:

- **Gemma-4-31B-IT on AMD Token Factory** planning, explanation and alternatives, validated
  for that run;
- source fingerprints matching this repository;
- independent result and artifact hash checks.

The MCUboot record was resumed with `acceptance.py --resume-run-id` after the local checker
restarted. It verifies that the run was created after the deployment, instead of starting a
duplicate assessment.

The [browser report](aws-browser-20261017/report.json) records real Chrome 155 anonymous
journeys for both profiles: the Run buttons were enabled and there were no network or runtime
errors. Screenshots are kept next to the report. During a live MCUboot run, SSE events arrived
through CloudFront in 93 ms, and the completed evidence ZIP downloaded with HTTP 200.

## Updates and persistence

- **Deploys never interrupt a run.** `deploy/aws/deploy.sh` builds new images while the current
  release keeps serving. It checks for active assessments immediately before `up -d` and aborts
  if any are running or queued.
- **Data stays outside the release.** Assessment data and artifacts live in Docker volumes, not
  in the application directory, and are preserved across releases.
- **Backups are manual.** A consistent SQLite online backup and artifact archive were taken
  before the release and copied off-host.

This is a single-host, pinned-fixture demo. It is not a high-availability or multi-tenant
service. Operation scripts: [`../deploy/aws/README.md`](../deploy/aws/README.md).
