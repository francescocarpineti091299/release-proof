# ReleaseProof public judging demo on Azure

The owner explicitly requires **anonymous UI/API access: no viewer login or password**.
API mutation/job budgets, HTTPS and pinned-fixture runner isolation are retained.
Azure CLI/SSH operator credentials are for deployment only, never for judges.

## Topology

```text
Browser HTTPS → Azure Front Door Standard (*.azurefd.net)
                  → HTTPS, validated origin certificate → Ubuntu VM/Caddy
                      → web / api → isolated wolfBoot and MCUboot runners
                                → configured AMD Token Factory inference
```

Use one dedicated resource group tagged `app=releaseproof`. Default provisioning uses
West Europe, zone 1, `Standard_D8as_v4` (AMD EPYC, 8 vCPU/32 GiB) and a 128 GiB Standard SSD.
This SKU was selected because the active subscription has DASv4 quota but zero DASv5 quota.
No local GPU is provisioned; AMD inference remains the configured managed AMD endpoint.
VM, disk, static public IPv4 and Front Door base/traffic incur normal Azure charges.

The NSG accepts SSH only from the operator IPv4, HTTP/80 for ACME HTTP-01 and HTTPS/443
from `AzureFrontDoor.Backend`. Caddy additionally verifies the profile's `X-Azure-FDID`.
This is **origin admission**, not judge authentication: browsers need no header or token.
An explicit Caddy `route` ensures the guard executes before UI/API proxy handlers.
HTTP-01 is used because public TLS-ALPN cannot reach the restricted origin port.

Front Door redirects HTTP viewers to HTTPS, forwards to HTTPS only, validates origin
certificate names, disables caching on all routes and uses a 240-second response timeout.
SSE heartbeat/flush behavior and the origin's API budgets remain enabled.

## Provision and release

From the repository root with Azure CLI, Python, Git and OpenSSH installed:

```powershell
$subscription = az account show --query id -o tsv
powershell -NoProfile -ExecutionPolicy Bypass -File deploy/azure/provision.ps1 `
  -SubscriptionId $subscription

# Commit and review the release first. .env is excluded from Git and uploaded separately.
powershell -NoProfile -ExecutionPolicy Bypass -File deploy/azure/deploy.ps1 -Commit HEAD
```

State and SSH key are retained under `~/.releaseproof-azure/`; neither is committed.
The Docker bootstrap is shared with `deploy/aws/cloud-init.yaml` (it contains no AWS calls
or application secrets). Provisioning refuses a resource group with another owner tag.
It does not modify another subscription or unrelated projects.

Deployment uploads a **Git archive of the specified commit**, not uncommitted source/private
research. Secrets travel only over SSH and the remote `.env` is `0600`. Releases are placed
in `/opt/releaseproof/releases/<commit>` with `/opt/releaseproof/current` pointing to the
active release. Compose's explicit project name retains the same persistent volumes.
The script refuses to redeploy over an active/queued assessment; it never forces a stop.
The existing AWS demo/data are not automatically deleted or migrated by these scripts.

## Verification before submission

Read the actual `viewer_url` from the state file; do not submit an unverified endpoint.

```powershell
$state = Get-Content ~/.releaseproof-azure/releaseproof.json -Raw | ConvertFrom-Json
backend/.venv/Scripts/python.exe scripts/cloudfront_smoke.py --base $state.viewer_url
backend/.venv/Scripts/python.exe scripts/acceptance.py --base $state.viewer_url `
  --require-ai --env-file .env
backend/.venv/Scripts/python.exe scripts/release_evidence.py `
  --ssh-host "ubuntu@$($state.public_ip)" --ssh-key $state.key_file `
  --output docs/AZURE_RELEASE_EVIDENCE_20261017.json
```

The existing transport-smoke script's filename is historical; it uses any validated HTTPS
viewer URL, including Front Door. Strict acceptance creates **real new runs and AMD calls**
on both profiles, verifies artifacts/result hashes and compares deployed source fingerprints.
Also inspect actual runner UID/capabilities/mounts, budgets, public HTTP 200 (not 401), SSE,
both browser journeys and manifest/evidence downloads. Do not fake completed operator fields.

## Persistence and cleanup

Do not delete the `rpdata`, `caddy_data` or `caddy_config` volumes or live release directory.
Before any teardown, wait for active runs and make consistent off-host SQLite/artifact backups.
Keep judging endpoints running. Azure and AWS are separate deployments with separate bills;
retiring the fallback is a deliberate operator step, not a deployment side effect.
After judging, verify the resource-group owner tag and every contained resource before deleting
only this project's Azure group. Never perform subscription-wide cleanup or remove other groups.
