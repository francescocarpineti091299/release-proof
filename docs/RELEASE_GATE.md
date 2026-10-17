# CI preflight gate and portable evidence

ReleaseProof sits **before** OTA delivery. A completed assessment (`SUCCEEDED`) is not
permission to deploy: the pipeline can complete correctly and find an incompatible migration.

## Download a review pack

In the run page, **Technical details → Evidence pack ZIP**, or:

`GET /api/assessments/{run_id}/evidence-pack`

The ZIP contains the run, assessment/result, original manifest, dossier, AI traces and every
artifact, plus `pack-index.json` with SHA-256 and byte lengths. Artifacts are hashed while copied;
no partial archive is served if a file is missing, changed or outside its owner directory.
Re-evaluations preserve the parent artifact ownership and are not labelled new emulation.
The archive is bounded to 64 MiB uncompressed and 512 files; larger profiles need a reviewed
capacity change. Reference and unfinished/failed runs do not have this live pack endpoint.

Hashes establish integrity and document identity, **not** trusted acquisition, signed authenticity,
silicon identity, tenant isolation or certification. Only distribute open fixtures after reviewing
the third-party notices; a pack can contain GPL firmware binaries.

## Gate an existing run (no new builds or AI calls)

Run with the installed backend Python environment, from the repository root:

```powershell
backend/.venv/Scripts/python.exe scripts/release_gate.py `
  --base http://localhost:8080 --run-id YOUR_RUN_ID `
  --configuration nrf52840-wolfboot-pqc `
  --change ecdsa_p256_to_mldsa87 --plan bootloader_self_update `
  --out review/YOUR_RUN_ID
```

Use the actual change and plan IDs returned by `/api/configurations`; do not select the latest
run implicitly. Pin these CI expectations to the product line being assessed. Remote access
requires HTTPS and refuses redirects. For a protected private deployment, optional Basic
credentials are read from `RELEASEPROOF_DEMO_USER` / `RELEASEPROOF_DEMO_PASSWORD`, never from
command-line arguments. The public demo needs none.

Offline verification of the same immutable pack:

```bash
python scripts/release_gate.py --pack review/RUN/evidence.zip \
  --configuration nrf52840-wolfboot-pqc --change ecdsa_p256_to_mldsa87 \
  --plan bootloader_self_update --out review/RUN-offline
```

The verifier never extracts ZIP paths. It verifies every indexed byte, manifest/assessment/result
bindings and verdict phases, and **replays the assessment through the locally installed engine**.
A historical pack from a different engine release may fail replay; preserve it and use its recorded
implementation, rather than rewriting its canonical hash. An index is not a signature: a trusted
API/artifact store and reviewed evidence acquisition remain prerequisites.

Exit codes:

| Code | Meaning |
|---|---|
| `0` | PASS: supported LIVE run, all three verdicts COMPATIBLE, critical checks satisfied, no open conditions/errors, required tests executed and authentication-negative coverage observed |
| `1` | BLOCK: a valid engineering assessment does not satisfy the preflight policy |
| `2` | ERROR: download, integrity, identity, schema or engine replay failed; never treat as a pass |

The output directory must be fresh. It retains `gate.json` and, for remote verification, the
downloaded `evidence.zip`, including on a policy BLOCK. No candidate-only success, CONDITIONAL,
INDETERMINATE, REFERENCE or REEVALUATION bypass is provided. AI availability does not determine
this gate; the separate `acceptance.py --require-ai` validates the complete AMD demo workflow.

**Both current configurations should BLOCK a release.** wolfBoot has a viable candidate but an
incompatible transition; a field-service re-evaluation is INDETERMINATE. A green gate cannot be
obtained by hiding missing interrupted-update evidence. Even a future PASS would cover only the
supported emulated configuration, not fleet-wide or power-loss safety.

## GitHub Actions integration

`.github/workflows/release-preflight.yml` is a manually invoked integration for an existing trusted
run. It downloads the pack, evaluates the policy and uploads the report even when BLOCK/ERROR.
Pin the trusted HTTPS origin in repository variable `RELEASEPROOF_BASE_URL`; it is not a dispatch
input that could redirect downloads to an arbitrary service. No secrets are required against the
public demo. The service must already be deployed: this workflow does not provision cloud
resources, create a firmware release or deliver OTA. Its behaviour is covered by offline
regression tests.
