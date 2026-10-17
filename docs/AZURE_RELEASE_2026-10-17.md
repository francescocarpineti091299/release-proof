# ReleaseProof — superseded Azure attempt / incident record (2026-10-17)

Former endpoint (not a submission URL): `https://releaseproof-4662d679-crg8f4ataygnbwax.z03.azurefd.net`.

**Status: cancelled. The owner subsequently instructed AWS only, with no further Azure
deployment.** The Git release remains published. Azure scaffolding was removed from the
current source; this record preserves the actual attempt without claiming a working Azure demo.

The build completed and all five containers started, but on 2026-10-17 at
**15:30:51 UTC (17:30:51 CEST)** an independently authenticated administrator initiated
`Delete resource group` for `rg-releaseproof-demo-weu` (correlation
`fa4ebbe1-4d30-4d17-a416-6b0c406dc5d2`). The group was observed as `Deleting`; VM and endpoint
lookups returned NotFound, SSH timed out and viewer/browser tests failed with HTTP 404/UI not ready.
No successful public Azure acceptance/source-evidence/browser report was fabricated.
No resource lock, cancellation override or new Azure deployment was attempted after the owner's
AWS-only instruction. The AWS fallback and its existing assessment history were preserved.

## Owner-approved access policy

The owner explicitly requires **anonymous judging**, without login, passwords, an Azure
account or browser-supplied tokens. This supersedes the previous optional authenticated
gateway proposal. Public API jobs/POST requests remain bounded; only pinned open-source
fixtures are accepted. This is not a customer-data or arbitrary-code hosting service.

The VM origin is admitted only from `AzureFrontDoor.Backend` and the matching
`X-Azure-FDID`; that header is provided by Front Door, not judges. Origin admission is not
viewer authentication. HTTPS verification is not disabled anywhere in the deployment.

## Source publication and private history cleanup

Public repository: https://github.com/francescocarpineti091299/release-proof

Application release commit: `ff64d5f572692e2d159d965a643d2bd2e1a772a0`.

The work was separated into four commits:

| Commit | Scope |
|---|---|
| `9fe9731` | Backend evidence/AI guards and non-root, artifact-only firmware runners |
| `df682be` | Truthful UI verdict phases and portable evidence |
| `7a18fbe` | Anonymous public deployment, API budgets, Azure/Front Door and deployment checks |
| `ff64d5f` | Submission/provenance kit and retained engineering evidence |

With explicit owner approval, only `ReleaseProof_AMD_ACT_III_Engineering_Brief.md`
was removed from reachable Git history in a separate fresh clone. The final tree hash
was unchanged; original working files were never reset or checked out. The original history
was preserved in a local bundle outside the repository. Push used an exact
`--force-with-lease` check so concurrent remote changes could not be overwritten.

The public repository/main commit were independently read without authentication.
A heuristic scan of **688 reachable blobs** found no configured credential values,
tested AWS/GitHub/private-key patterns or reachable private brief/general-doc/env paths.
This is not a comprehensive gitleaks/legal certification, and rewriting a branch does not
guarantee deletion of old GitHub caches, copies or previously downloaded content.

## Provisioned infrastructure

All new resources are in dedicated group `rg-releaseproof-demo-weu`, tagged
`app=releaseproof`, in the operator's explicitly selected default subscription.
No other subscription or project was modified. The existing AWS demo/data remain separate
and available as fallback; they were not automatically migrated, stopped or deleted.

- VM `releaseproof-vm`, `Standard_D8as_v4`, West Europe zone 1, Ubuntu 24.04 x64 Gen2.
- **8 guest vCPU, 32 GiB SKU RAM**, 128 GiB Standard SSD managed OS disk.
- Guest `lscpu`: `AuthenticAMD`, **AMD EPYC 7763** (model name, not a claim of 64 allocated cores).
- Dedicated VNet/subnet/NIC, static public IPv4 `40.113.169.77`, project NSG.
- Origin DNS `releaseproof-4662d679.westeurope.cloudapp.azure.com`.
- Front Door Standard profile `releaseproof-frontdoor`, endpoint `releaseproof-4662d679`.
- Docker bootstrap complete; Compose 5.6.0 observed over SSH.

Inbound SSH is operator IPv4-only; HTTP/80 is public for ACME HTTP-01, while HTTPS/443
accepts the Front Door backend service tag. Public origin QUIC/API/runner ports are not opened.
Front Door uses HTTP→HTTPS redirect, HTTPS-only forwarding, origin certificate-name enforcement,
no route caching and a 240-second origin response timeout. The route matches `/*` and links
to the assigned default domain. Viewer HTTPS already validated at the transport layer before
application startup; a pre-start edge 404 is not recorded as an application success.

Normal VM/disk/IPv4/Front Door base and traffic charges apply. The AWS fallback has its own
ongoing charges until deliberately retired. No local GPU is allocated: AMD inference remains
the configured AMD Token Factory `DeepSeek-V4-Flash` endpoint; its managed GPU is undisclosed.

## Release mechanism and intended controls (historical attempt)

Deployment uses a Git archive of the exact release commit and uploads `.env` separately over
SSH with mode `0600`; no API key/private key is put into Git, cloud-init or resource metadata.
The source is under `/opt/releaseproof/releases/<commit>` and the active `current` symlink
is set after a successful Compose deployment. The fixed Compose project name retains volumes.

The intended public configuration fixes `RELEASEPROOF_ENV=demo`, experimental profiles off,
four active jobs and 20 mutation requests/minute. Runners are UID 10001, capabilities dropped,
with CPU/RAM/PID limits, internal/no-egress network and only the `runs/` volume subpath.
Actual deployed settings/source equivalence must be checked, not inferred from this description.

## Completed offline checks

- Backend: **422 passed, 1 skipped**; a Starlette/AnyIO deprecation warning remains.
- Script tests: **57 passed**, including anonymous public and Azure-origin/config checks.
- Runner regressions: **38 passed, 2 skipped** (live Docker cases are separate).
- Frontend: lint/typecheck OK, **8 tests passed**; Node experimental/module warnings are non-fatal.
- Ruff lint and formatting: OK. PowerShell scripts parsed successfully.
- Azure Caddy configuration adapted/validated successfully; no insecure TLS flag or login gate.

These are not a substitute for cloud runner/AMD acceptance or actual browser access.

## Live verification and external deliverables

Not completed on Azure because the administrator deletion interrupted verification:

- Anonymous UI/API HTTP 200, valid origin/viewer certificates and rendered browser journeys.
- Live assessment on **both** profiles, strict AMD planning/reporting/citation checks, source
  fingerprints, artifact/result/manifest integrity, event streaming and cursor forwarding.
- Actual runner UID/capabilities/database isolation, effective API budgets and SQLite integrity.
- Consistent off-host data backup and final reviewed pitch exports.

`pitch/submission_fields.json` still requires a real uploaded **video URL** and operator
confirmation of video/PDF; no video or successful organizer submission is fabricated here.
Public access verification is recorded only after successful final browser/cloud tests.

Current operations and submission endpoint: [`../deploy/aws/README.md`](../deploy/aws/README.md).
