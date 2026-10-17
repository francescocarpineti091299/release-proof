#!/usr/bin/env bash
# Ship the repository to the ReleaseProof host and (re)start the stack with Docker Compose.
#
#   deploy/aws/deploy.sh [--name releaseproof] [--host 203.0.113.10] [--key ~/.ssh/key.pem]
#                        [--site-address <host>|:80] [--env-file .env] [--no-build]
#
# Defaults come from ~/.releaseproof-aws/<name>.env (written by provision.sh). SITE_ADDRESS
# defaults to the sslip.io hostname of the Elastic IP, so Caddy obtains a TLS certificate.
# The local env file (default: <repo>/.env) is uploaded with mode 600; SITE_ADDRESS in it is
# replaced by the value chosen here. Nothing else on the host is touched.
set -euo pipefail

NAME="releaseproof"
HOST=""
KEY=""
SITE_ADDRESS=""
ENV_FILE=""
BUILD=1
REMOTE_DIR="/opt/releaseproof"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name) NAME="$2"; shift 2 ;;
    --host) HOST="$2"; shift 2 ;;
    --key) KEY="$2"; shift 2 ;;
    --site-address) SITE_ADDRESS="$2"; shift 2 ;;
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --no-build) BUILD=0; shift ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

STATE_FILE="${HOME}/.releaseproof-aws/${NAME}.env"
if [[ -f "$STATE_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$STATE_FILE"
fi
HOST="${HOST:-${RP_PUBLIC_IP:-}}"
KEY="${KEY:-${RP_KEY_FILE:-}}"
SITE_ADDRESS="${SITE_ADDRESS:-${RP_SSLIP_HOST:-:80}}"
ENV_FILE="${ENV_FILE:-${REPO_ROOT}/.env}"

[[ -n "$HOST" ]] || { echo "no host: run provision.sh or pass --host" >&2; exit 2; }
[[ -n "$KEY" && -f "$KEY" ]] || { echo "SSH key not found: ${KEY:-<unset>} (use --key)" >&2; exit 2; }
[[ "$SITE_ADDRESS" =~ ^(:[0-9]+|[A-Za-z0-9.-]+)$ ]] || { echo "invalid --site-address" >&2; exit 2; }
if [[ ! -f "$ENV_FILE" ]]; then
  echo "env file ${ENV_FILE} not found; using .env.example (AI will report AI_UNAVAILABLE)" >&2
  ENV_FILE="${REPO_ROOT}/.env.example"
fi

log() { printf '\033[1;34m[deploy]\033[0m %s\n' "$*"; }
SSH_OPTS=(-i "$KEY" -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30 -o ConnectTimeout=15)
TARGET="ubuntu@${HOST}"
remote() { ssh "${SSH_OPTS[@]}" "$TARGET" "$@"; }

log "waiting for SSH on ${HOST}"
for _ in $(seq 1 60); do
  remote true 2>/dev/null && break
  sleep 5
done
remote true

log "waiting for cloud-init (Docker install)"
remote 'cloud-init status --wait >/dev/null || true; test -f /var/lib/releaseproof-bootstrap-done && docker compose version'

log "syncing ${REPO_ROOT} -> ${HOST}:${REMOTE_DIR}"
EXCLUDES=(
  '/.git/' '.env' '.env.*' '/data/' 'backend/.venv/' '**/__pycache__/' '**/.pytest_cache/'
  '**/.ruff_cache/' 'web/node_modules/' 'web/.next/' 'web/out/' 'runners/**/work/' '*.egg-info/'
)
if command -v rsync >/dev/null; then
  RSYNC_EX=(--include '/.env.example')
  for ex in "${EXCLUDES[@]}"; do RSYNC_EX+=(--exclude "$ex"); done
  rsync -az --delete -e "ssh ${SSH_OPTS[*]}" "${RSYNC_EX[@]}" "${REPO_ROOT}/" "${TARGET}:${REMOTE_DIR}/"
else
  # Git Bash on Windows has no rsync: stream a tarball of the working tree instead.
  TAR_EX=()
  for ex in "${EXCLUDES[@]}"; do
    ex="${ex%/}"
    case "$ex" in
      /*) ex="./${ex#/}" ;;        # root-anchored: only the top-level entry
      \*\*/*) ex="${ex#\*\*/}" ;;  # any depth
    esac
    TAR_EX+=("--exclude=${ex}")
  done
  tar -C "$REPO_ROOT" "${TAR_EX[@]}" --exclude='.env' -czf - . \
    | remote "find ${REMOTE_DIR} -mindepth 1 -maxdepth 1 ! -name .env -exec rm -rf {} + && tar -xzf - -C ${REMOTE_DIR}"
fi

log "uploading environment (SITE_ADDRESS=${SITE_ADDRESS})"
TMP_ENV="$(mktemp)"
trap 'rm -f "$TMP_ENV"' EXIT
grep -v '^[[:space:]]*SITE_ADDRESS=' "$ENV_FILE" > "$TMP_ENV" || true
printf '\nSITE_ADDRESS=%s\n' "$SITE_ADDRESS" >> "$TMP_ENV"
chmod 600 "$TMP_ENV"
scp "${SSH_OPTS[@]}" -q "$TMP_ENV" "${TARGET}:${REMOTE_DIR}/.env"
remote "chmod 600 ${REMOTE_DIR}/.env"

if [[ "$BUILD" == 1 ]]; then
  log "docker compose up -d --build (first build of the runner images takes a while)"
  remote "cd ${REMOTE_DIR} && docker compose up -d --build --remove-orphans"
else
  log "docker compose up -d"
  remote "cd ${REMOTE_DIR} && docker compose up -d --remove-orphans"
fi
remote "cd ${REMOTE_DIR} && docker compose ps"

if [[ "$SITE_ADDRESS" == :* ]]; then
  URL="http://${HOST}${SITE_ADDRESS/#:80/}"
else
  URL="https://${SITE_ADDRESS}"
fi
log "waiting for ${URL}/api/health"
for _ in $(seq 1 60); do
  if curl -fsS --max-time 5 "${URL}/api/health" >/dev/null 2>&1; then
    log "up: ${URL}"
    curl -fsS "${URL}/api/health"; echo
    exit 0
  fi
  sleep 5
done
echo "health check did not succeed yet; inspect with: ssh -i ${KEY} ${TARGET} 'cd ${REMOTE_DIR} && docker compose logs --tail 100'" >&2
exit 1
