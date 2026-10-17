# ReleaseProof — AWS infrastructure audit and scoped cleanup

Checked on **2026-10-17**, approximately 14:46–14:54 UTC. This is a point-in-time
infrastructure/transport check, not a full current-source release gate or production certification.

**Outcome:** the existing demo is operational at
**https://d1yxcnwgdgjzt6.cloudfront.net**. Scoped cleanup preserved the running
containers, images, assessment history, database, artifacts and certificate volumes.
The deployed application predates the repository's security remediation; see the
remaining boundaries below before treating the public demo as a hardened service.

## Scope and resource ownership

Resource Groups Tagging API was queried in **all 20 enabled regions** of the demo
account for `app=releaseproof`, followed by direct EC2 and CloudFront checks.
Six tagged resources were found, all required:

| Resource | Identifier | Verification |
|---|---|---|
| EC2 | `i-093ad57695cfeb2d4` | One `c7a.2xlarge`, running in `eu-west-1c` |
| Root EBS | `vol-0393ff27f12da60a7` | Attached, encrypted 60 GiB gp3; delete-on-termination |
| Elastic IP | `eipalloc-0ce3131ea9f8ed340`, `52.30.20.1` | Associated with this instance |
| Security group | `sg-041ad83d6ca4b663f` | `releaseproof-sg`; used only by the instance's ENI |
| SSH key pair | `key-04713573816a66df2`, `releaseproof` | Required for operator SSH |
| CloudFront | `EYOV800QNV3V` | Enabled, `Deployed`, tagged `app=releaseproof` |

The attached ENI `eni-075b8a1e8690d16ba` is also required. The default VPC/subnet,
AWS-managed KMS key, source AMI snapshot, managed CloudFront policies and origin-facing
prefix list are shared/AWS resources: **not cleanup targets**. Other distributions,
projects, local Docker workloads and the sibling firmware repository were not changed.
Tag discovery does not inventory every untagged resource in the account.
No duplicate/orphaned project resource or project-owned snapshot was found in these checks.

## Health and exposure

- EC2 instance, system and attached-EBS status checks: **ok**; IMDSv2 required, hop limit 1.
- Docker Engine 29.9.1, Compose 5.6.0; Docker active/enabled, cloud-init completed.
- Five required containers running with `unless-stopped`, zero restarts/OOM flags.
  API and web health checks are healthy; runners/Caddy have no container health check.
- Only ports 22, 80 and 443 are published by the host. API 8000 and runners 8080 are internal.
- The `releaseproof_runners` network is `internal=true`; runners receive no AMD credentials.
- Root filesystem after cleanup: approximately **18 GiB used, 40 GiB free (31%)**.
  About 14 GiB RAM was available; no swap or observed OOM.
- SQLite `PRAGMA quick_check`, executed read-only inside the API container: **ok**.
- `.env` mode is `0600`; its contents and private key material were not included in this report.
- Origin certificate: valid Let's Encrypt certificate for `52-30-20-1.sslip.io`,
  expires **2027-01-15**. Loopback with the correct SNI verified its chain/hostname.
- Viewer certificate: valid Amazon certificate for CloudFront, expires **2027-03-10**;
  TLS 1.3 negotiated from the workstation. The default CloudFront certificate's configured
  minimum remains AWS's `TLSv1`; this does not attest enforcement of TLS 1.2+ for all viewers.
- CloudFront uses HTTPS-only origin connections, TLS 1.2 origin policy, no response caching,
  all required methods and forwarding of cookies/query parameters/viewer headers except Host.

### Final security-group ingress

| Protocol/port | Source | Purpose |
|---|---|---|
| TCP 22 | Existing operator IPv4 `/32` (unchanged) | SSH administration |
| TCP 80 | `0.0.0.0/0` | Caddy ACME HTTP-01 and HTTPS redirect |
| TCP 443 | AWS prefix list `pl-4fa04526` | CloudFront origin-facing connections only |

IPv6 origin rules were unused (the ENI has no IPv6 address). Origin UDP/443 is unnecessary
because CloudFront uses TCP/TLS to this origin; viewer HTTP/3 remains enabled at CloudFront.
HTTP/80 must remain reachable for renewal now that public TLS-ALPN validation on 443 is blocked.
Renewal was not forced during this audit. The managed prefix list trusts CloudFront origin
servers generally, **not only this distribution**; no per-distribution origin secret was added.
It consumes 55 security-group rule slots; check quota before adding more prefix-list rules.

## Cleanup actually performed

1. Removed exactly four obsolete ingress rules from the project security group:
   `sgr-0e65c4491c615e95a`, `sgr-0f94ba234025c2edb`,
   `sgr-069f9332a1875c196`, `sgr-072b49b905a73a34c`.
   Added CloudFront-only HTTPS rule `sgr-0cba2951b63868a57` **before** removing public TCP/443,
   with successful uncached viewer health checks before and after the change.
2. Removed **eight obsolete BuildKit records by exact ID filter**, recovering **893.9 MB**.
   These were the failed first frontend dependency/source build and superseded initial API
   source layers. Only reclaimable, unshared records created before the current successful
   build were selected; no build was active. The current toolchain/build cache was retained
   (about 9.612 GB) to avoid unnecessarily slow release rebuilds.
3. Removed **eight private research/brief copies** (220,822 bytes) from
   `/opt/releaseproof/general_docs/`. Each SHA-256 was verified against the existing local
   original before unlinking that exact remote file. Local originals were preserved.
4. Updated deployment synchronization to exclude `/general_docs/` in **both rsync and tar**.
   Added CloudFront-aware provisioning and a `--viewer-url` deployment health-check option
   so re-running the local scripts does not reopen the hardened origin or probe a blocked URL.

No instance, distribution, image, persistent volume, assessment or artifact was deleted.
The five container IDs/image IDs/restart counts were unchanged by cleanup. A user assessment
active during the audit completed as `SUCCEEDED`; it was not stopped or replaced.

## Verification retained

- Post-cleanup read-only viewer smoke: **PASS** in
  [`acceptance/cloudfront-infra-smoke-20261017.json`](acceptance/cloudfront-infra-smoke-20261017.json).
  UI/assets, health, both profiles, query forwarding, completed result and manifest hash passed.
- `/reference`, `/amd` and the completed run page returned HTTP 200 via CloudFront.
- Completed run `RP-20261017T144403Z-58de1b` served **290 persisted SSE events**.
  A reconnect with `Last-Event-ID: 1025` and `?after=0` returned only events 1026/1027,
  verifying header forwarding and cursor precedence through CloudFront.
- Earlier **live** viewer smoke and browser rendering remain in
  [`../deploy/aws/CLOUDFRONT_DEMO.md`](../deploy/aws/CLOUDFRONT_DEMO.md).
  This audit did not create another assessment or consume additional AMD inference.
- Offline regression subset: `test_deploy.py`, `test_cloudfront_demo.py` and
  `test_infra_maintenance.py` — **17 passed**. These mock AWS/SSH for script tests;
  they do not stand in for the actual cloud checks above.

## Remaining boundaries — do not confuse repository fixes with deployed controls

Subsequent owner decision: judging access must remain **anonymous**, with no login.
This supersedes the earlier proposed authenticated gateway, not the observed budget/runner drift.

1. **Public viewer access is anonymous by design.** The public override now explicitly permits it;
   login is not a missing requirement for judging. Resource budgets remain necessary.
2. **Old runtime has no new API capacity/rate limiter.** Inspection found neither
   `max_active_runs`/`mutation_requests_per_minute` settings nor the new API budget module.
   Public requests can consume demo resources/AMD quota beyond the intended bounds.
3. **Old runners are root and mount the whole `rpdata` volume.** They have CPU/RAM/PID limits,
   no-new-privileges and no egress, but not the newer UID 10001/capability-drop/`runs/`-only mount.
   The API itself is UID 10001. This is a pinned open-fixture demo, not hostile multi-tenancy.
4. **Single-host persistence and operational monitoring are basic.** No project snapshot or
   AWS Backup protection was found, no direct EC2 InstanceId alarm was configured, and no
   `releaseproof*` CloudWatch log group was found. Detailed EC2 monitoring and CloudFront access
   logging are disabled. Docker logs/status checks exist; this is not a no-monitoring claim.
5. This audit does not assert that AWS image contents match the changing worktree, that the
   strengthened AMD-required acceptance passes on AWS, or that organizer/judge access is approved.

An application rebuild/redeploy was deliberately **not** performed: the worktree contains
ongoing changes and the demo was in use. Plan a reviewed release, preserve database/artifacts,
wait for active jobs, deploy the hardened anonymous public configuration and rerun strict
current-source acceptance before claiming those controls on AWS. Judges receive no credentials.

## Operations and teardown

- Keep EC2, EIP and CloudFront enabled during judging. Stopping EC2 makes the demo unavailable;
  the EIP remains billed and CloudFront continues to exist.
- Use the CloudFront viewer URL in submission fields, never the blocked dynamic-DNS origin URL.
- Diagnose Caddy locally over SSH with `curl --resolve 52-30-20-1.sslip.io:443:127.0.0.1
  https://52-30-20-1.sslip.io/api/health`; do not reopen origin 443 or disable TLS verification.
- Back up SQLite/artifacts **off-host** before teardown. A tar copy of an actively written SQLite
  volume is not a consistent backup; quiesce/stop the stack or use SQLite's online backup API.
- `destroy.sh` only removes EC2/EIP/security group and optionally the SSH key. It does **not**
  remove CloudFront. Separately verify the distribution ID/tag, disable it with its current ETag,
  wait for deployment, fetch its new ETag and delete only `EYOV800QNV3V` after judging.
- Do not delete shared VPC/subnet, AWS prefix lists/policies, the AMI snapshot or other projects.
  Do not run account-wide cleanup, local Docker prune, `docker system prune` or volume prune.
