# Deploy ReleaseProof on AWS (single host)

One EC2 **c7a.2xlarge** (AMD EPYC 4th gen "Genoa", 8 vCPU, 16 GiB) running Ubuntu 24.04 LTS,
60 GB encrypted gp3 root volume, an Elastic IP, and the whole stack under Docker Compose with
Caddy terminating TLS. LLM inference is **not** on this host: the API calls the AMD-hosted
endpoint configured in `.env` (`AMD_LLM_*`).

```
Internet ─► EIP :80/:443 ─► caddy ─┬─ /api/* ─► api:8000 ──► AMD LLM endpoint (egress)
                                   └─ /*     ─► web:3000
            api ─► runner-wolfboot:8080, runner-mcuboot:8080   (network "runners", internal: no egress)
            volume rpdata:/data  (SQLite + runs/<run_id>/artifacts, shared by api and runners)
```

| File | Purpose |
|---|---|
| `provision.sh` | Key pair, security group (22 from your IP, 80/443 public), instance, Elastic IP. Re-runnable: resources are found by name/tag and reused. |
| `cloud-init.yaml` | User data: Docker Engine + compose plugin from Docker's apt repo, log rotation, `/opt/releaseproof`. |
| `deploy.sh` | `rsync` the repo, upload `.env` (mode 600), `docker compose up -d --build`, wait for `/api/health`. |
| `destroy.sh` | Release the EIP, terminate the instance, delete the security group (optionally the key pair). |

## Prerequisites

- AWS CLI v2 configured (`aws configure` or `--profile`), `bash`, `ssh`, `scp`, `curl`, and
  either `rsync` or `tar`. On Windows use WSL (Ubuntu) or Git Bash; when rsync is absent,
  deployment streams a tar archive instead.
- IAM permissions: `ec2:*` on instances/volumes/addresses/security groups/key pairs/tags in the
  target region, `ssm:GetParameter` (Ubuntu AMI lookup), `sts:GetCallerIdentity`.
  Without SSM permission, AMI discovery falls back to Canonical-owned EC2 images and requires
  `ec2:DescribeImages`. See `iam-policy.json` for the concrete action list.
- A region that offers c7a (e.g. `eu-west-1`, `eu-central-1`, `us-east-1`, `us-east-2`,
  `us-west-2`). `provision.sh` checks the offering and fails clearly otherwise.
- A default VPC in that region (`aws ec2 create-default-vpc` if it was deleted).

## 1. Provision

```bash
deploy/aws/provision.sh --region eu-west-1            # --ssh-cidr defaults to <your public IP>/32
```

Outputs the Elastic IP, the derived hostname `A-B-C-D.sslip.io`, the SSH command, and writes
`~/.releaseproof-aws/releaseproof.env` (ids, IP, key path) used by the other scripts. The private
key is saved as `~/.releaseproof-aws/releaseproof.pem` (only when the key pair is created).

## 2. Configure

```bash
cp .env.example .env      # at the repository root; fill AMD_LLM_BASE_URL / _API_KEY / _MODEL ...
```

Leave `RELEASEPROOF_EXPOSE_EXPERIMENTAL=0` for the judged deployment: only profiles whose status
is `SUPPORTED` in `profiles/*.yaml` are selectable. Without AMD settings the platform still runs
and every AI stage reports `AI_UNAVAILABLE` (verdicts are unaffected).

## 3. Deploy

```bash
deploy/aws/deploy.sh                                   # https://A-B-C-D.sslip.io
deploy/aws/deploy.sh --site-address releaseproof.example.com   # real domain (A record -> EIP)
deploy/aws/deploy.sh --site-address :80                # plain HTTP (debug only)
deploy/aws/deploy.sh --no-build                        # restart without rebuilding images
```

The first build compiles/downloads the runner toolchains (Renode, Arm GNU toolchain, Zephyr SDK
and workspace, wolfBoot at its pinned commit): expect 20–40 minutes and ~25 GB of images. Later
deploys reuse the build cache.

### TLS

Caddy obtains a certificate for `SITE_ADDRESS` automatically (HTTP-01/TLS-ALPN on ports 80/443,
Let's Encrypt with ZeroSSL fallback) and renews it; state lives in the `caddy_data` volume.
`sslip.io` resolves `A-B-C-D.sslip.io` to `A.B.C.D`, so no DNS setup is needed. `sslip.io` is a
shared registered domain and can hit Let's Encrypt weekly rate limits; if issuance fails
(`docker compose logs caddy`), use a real domain or wait for the ZeroSSL fallback.

## Operations

```bash
source ~/.releaseproof-aws/releaseproof.env
ssh -i "$RP_KEY_FILE" ubuntu@"$RP_PUBLIC_IP"
cd /opt/releaseproof
docker compose ps
docker compose logs -f api              # orchestrator + AI traces
docker compose logs -f runner-wolfboot
docker compose restart api              # runs left RUNNING become FAILED "interrupted by restart"
# backup runs + database
docker run --rm -v releaseproof_rpdata:/data -v "$PWD":/backup alpine \
  tar czf /backup/rpdata-$(date +%Y%m%d%H%M).tgz -C /data .
```

Stop the instance when idle (the EIP keeps the hostname; public IPv4 addresses are billed hourly
even while the instance is stopped):
`aws ec2 stop-instances --region "$RP_REGION" --instance-ids "$RP_INSTANCE_ID"`; start it again
with `provision.sh` (it starts a stopped instance) and `deploy.sh --no-build`.

## Security notes

- Runners are attached only to the `internal` compose network: firmware builds and Renode runs
  have no route to the internet. Everything they need is baked into their images at build time.
- `AMD_LLM_API_KEY` is passed only to the `api` container; runners never see it.
- SSH is limited to the CIDR given at provisioning; IMDSv2 is required; the root volume is
  encrypted. The API container runs as an unprivileged user.
- `.env` is never synced by `rsync`; it is uploaded separately with mode 600.
- The API does not implement authentication, tenant isolation or usage quotas. Protect the
  public site with an authenticated gateway before giving access to untrusted users.
- Deployment synchronizes `/opt/releaseproof` as a managed application directory. Do not keep
  unrelated files there: rsync uses `--delete`, and the tar fallback replaces its contents
  except `.env`. Database/artifacts and Caddy state are kept in Docker volumes, not that tree.
- Existing local acceptance reports are not proof of a completed AWS deployment.
- Keep the API single-worker/single-replica per data volume: in-memory runner semaphores and
  restart recovery do not coordinate multiple processes. Do not add `uvicorn --workers` to this
  deployment without implementing shared job ownership first.
- Wait for active runs before updating/restarting the stack. The API's graceful shutdown drains
  workers before closing SQLite and may exceed Docker's default stop timeout; a forced kill
  interrupts the run, which restart recovery marks FAILED rather than inventing a result.

## Teardown

```bash
deploy/aws/destroy.sh               # asks for confirmation; add --delete-key to remove the key pair
```

Permission/API failures stop teardown and retain the local state file instead of claiming
success. Already-removed EIP/security-group/key resources are tolerated on a retry. Back up the
data first: terminating the instance deletes its root volume and the Docker volumes on it.
