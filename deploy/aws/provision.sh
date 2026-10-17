#!/usr/bin/env bash
# Provision (or reuse) the ReleaseProof AWS host: key pair, security group, one EC2
# c7a.2xlarge (AMD EPYC) Ubuntu 24.04 with a 60 GB gp3 root volume, and an Elastic IP.
#
# Idempotent-ish: every resource is looked up by name/tag first and reused when present.
# State (ids, IP, hostname) is written to ~/.releaseproof-aws/<name>.env for deploy.sh.
#
# Usage:
#   deploy/aws/provision.sh [--region eu-west-1] [--name releaseproof] [--profile default]
#                           [--instance-type c7a.2xlarge] [--volume-gb 60]
#                           [--ssh-cidr 203.0.113.7/32] [--key-name releaseproof]
#                           [--cloudfront-origin]
set -euo pipefail
# Git Bash on Windows rewrites POSIX-looking arguments (e.g. /dev/sda1); disable that.
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'

REGION="${AWS_REGION:-eu-west-1}"
NAME="releaseproof"
INSTANCE_TYPE="c7a.2xlarge"
VOLUME_GB=60
SSH_CIDR=""
KEY_NAME=""
CLOUDFRONT_ORIGIN=0
PROFILE_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --region) REGION="$2"; shift 2 ;;
    --name) NAME="$2"; shift 2 ;;
    --instance-type) INSTANCE_TYPE="$2"; shift 2 ;;
    --volume-gb) VOLUME_GB="$2"; shift 2 ;;
    --ssh-cidr) SSH_CIDR="$2"; shift 2 ;;
    --key-name) KEY_NAME="$2"; shift 2 ;;
    --cloudfront-origin) CLOUDFRONT_ORIGIN=1; shift ;;
    --profile) PROFILE_ARGS=(--profile "$2"); shift 2 ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ "$NAME" =~ ^[A-Za-z0-9-]{1,40}$ ]] || { echo "--name must match [A-Za-z0-9-]{1,40}" >&2; exit 2; }
KEY_NAME="${KEY_NAME:-$NAME}"
[[ "$KEY_NAME" =~ ^[A-Za-z0-9._-]{1,255}$ ]] || { echo "invalid --key-name" >&2; exit 2; }
SG_NAME="${NAME}-sg"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="${HOME}/.releaseproof-aws"
STATE_FILE="${STATE_DIR}/${NAME}.env"
KEY_FILE="${STATE_DIR}/${KEY_NAME}.pem"
USER_DATA_PATH="${SCRIPT_DIR}/cloud-init.yaml"
# aws.exe (Git Bash on Windows) cannot open POSIX paths: hand it a Windows-style path.
if command -v cygpath >/dev/null; then USER_DATA_PATH="$(cygpath -m "$USER_DATA_PATH")"; fi

aws_() { aws "${PROFILE_ARGS[@]}" --region "$REGION" "$@"; }
log() { printf '\033[1;34m[provision]\033[0m %s\n' "$*"; }
none() { [[ -z "$1" || "$1" == "None" || "$1" == "null" ]]; }

command -v aws >/dev/null || { echo "AWS CLI v2 is required" >&2; exit 1; }
mkdir -p "$STATE_DIR" && chmod 700 "$STATE_DIR"

ACCOUNT="$(aws "${PROFILE_ARGS[@]}" sts get-caller-identity --query Account --output text)"
log "account ${ACCOUNT}, region ${REGION}, name ${NAME}"

if [[ -z "$SSH_CIDR" ]]; then
  MY_IP="$(curl -fsS https://checkip.amazonaws.com | tr -d '[:space:]')"
  SSH_CIDR="${MY_IP}/32"
fi
log "SSH allowed from ${SSH_CIDR}"

# Ubuntu 24.04 AMI (amd64, gp3).
AMI_ID="$(MSYS_NO_PATHCONV=1 aws_ ssm get-parameter \
  --name /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id \
  --query Parameter.Value --output text 2>/dev/null || true)"
if none "$AMI_ID"; then
  # No ssm:GetParameter permission: fall back to Canonical's owner id + name pattern.
  AMI_ID="$(aws_ ec2 describe-images --owners 099720109477 \
    --filters 'Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*' \
              'Name=state,Values=available' \
    --query 'sort_by(Images,&CreationDate)[-1].ImageId' --output text)"
fi
none "$AMI_ID" && { echo "could not resolve an Ubuntu 24.04 AMI" >&2; exit 1; }
log "AMI ${AMI_ID} (Ubuntu 24.04 LTS)"

# Instance type must be offered in at least one AZ of the region.
OFFERED_AZ="$(aws_ ec2 describe-instance-type-offerings --location-type availability-zone \
  --filters "Name=instance-type,Values=${INSTANCE_TYPE}" \
  --query 'InstanceTypeOfferings[0].Location' --output text)"
none "$OFFERED_AZ" && { echo "${INSTANCE_TYPE} is not offered in ${REGION}" >&2; exit 1; }

if aws_ ec2 describe-key-pairs --key-names "$KEY_NAME" >/dev/null 2>&1; then
  log "key pair ${KEY_NAME} exists"
  [[ -f "$KEY_FILE" ]] || log "WARNING: ${KEY_FILE} not found locally; pass --key to deploy.sh"
else
  log "creating key pair ${KEY_NAME} -> ${KEY_FILE}"
  umask 077
  aws_ ec2 create-key-pair --key-name "$KEY_NAME" --key-type ed25519 \
    --tag-specifications "ResourceType=key-pair,Tags=[{Key=Name,Value=${NAME}},{Key=app,Value=releaseproof}]" \
    --query KeyMaterial --output text | tr -d '\r' > "$KEY_FILE"   # aws.exe emits CRLF
  chmod 600 "$KEY_FILE"
fi

# Network in the default VPC.
VPC_ID="$(aws_ ec2 describe-vpcs --filters Name=is-default,Values=true --query 'Vpcs[0].VpcId' --output text)"
none "$VPC_ID" && { echo "no default VPC in ${REGION}; create one (aws ec2 create-default-vpc)" >&2; exit 1; }
SUBNET_ID="$(aws_ ec2 describe-subnets \
  --filters "Name=vpc-id,Values=${VPC_ID}" "Name=default-for-az,Values=true" "Name=availability-zone,Values=${OFFERED_AZ}" \
  --query 'Subnets[0].SubnetId' --output text)"
none "$SUBNET_ID" && { echo "no default subnet in ${OFFERED_AZ}" >&2; exit 1; }
log "VPC ${VPC_ID}, subnet ${SUBNET_ID} (${OFFERED_AZ})"

SG_ID="$(aws_ ec2 describe-security-groups \
  --filters "Name=vpc-id,Values=${VPC_ID}" "Name=group-name,Values=${SG_NAME}" \
  --query 'SecurityGroups[0].GroupId' --output text)"
if none "$SG_ID"; then
  SG_ID="$(aws_ ec2 create-security-group --group-name "$SG_NAME" --vpc-id "$VPC_ID" \
    --description "ReleaseProof: SSH (restricted), HTTP, HTTPS" \
    --tag-specifications "ResourceType=security-group,Tags=[{Key=Name,Value=${SG_NAME}},{Key=app,Value=releaseproof}]" \
    --query GroupId --output text)"
  log "created security group ${SG_ID}"
else
  log "security group ${SG_ID} exists"
fi

# Preserve an existing CloudFront-only HTTPS rule instead of silently reopening
# the origin when provisioning is re-run. New CloudFront origins opt in explicitly.
EXISTING_HTTPS_PREFIXES="$(aws_ ec2 describe-security-groups --group-ids "$SG_ID" \
  --query 'SecurityGroups[0].IpPermissions[?IpProtocol==`tcp` && FromPort==`443` && ToPort==`443`].PrefixListIds[].PrefixListId' \
  --output text | tr '\t\n' '  ')"
CF_PREFIX=""
if [[ "$CLOUDFRONT_ORIGIN" == 1 || "$EXISTING_HTTPS_PREFIXES" == *pl-* ]]; then
  CF_PREFIX="$(aws_ ec2 describe-managed-prefix-lists \
    --filters Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing \
    --query 'PrefixLists[0].PrefixListId' --output text)"
  none "$CF_PREFIX" && { echo "CloudFront origin-facing prefix list unavailable" >&2; exit 1; }
  [[ "$CF_PREFIX" =~ ^pl-[[:alnum:]]+$ ]] || { echo "invalid CloudFront prefix list id" >&2; exit 1; }
  [[ " $EXISTING_HTTPS_PREFIXES " != *" $CF_PREFIX "* ]] || CLOUDFRONT_ORIGIN=1
fi

authorize() {  # proto port cidr-json-key cidr
  local proto="$1" port="$2" key="$3" cidr="$4" out
  local range="IpRanges=[{CidrIp=${cidr}}]"
  [[ "$key" == "v6" ]] && range="Ipv6Ranges=[{CidrIpv6=${cidr}}]"
  [[ "$key" == "prefix" ]] && range="PrefixListIds=[{PrefixListId=${cidr}}]"
  if out="$(aws_ ec2 authorize-security-group-ingress --group-id "$SG_ID" \
      --ip-permissions "IpProtocol=${proto},FromPort=${port},ToPort=${port},${range}" 2>&1)"; then
    log "ingress ${proto}/${port} from ${cidr}"
  elif grep -q InvalidPermission.Duplicate <<<"$out"; then
    :
  else
    echo "$out" >&2; exit 1
  fi
}
authorize tcp 22 v4 "$SSH_CIDR"
if [[ "$CLOUDFRONT_ORIGIN" == 1 ]]; then
  authorize tcp 80 v4 0.0.0.0/0  # Caddy ACME HTTP-01; keep certificate renewal reachable.
  authorize tcp 443 prefix "$CF_PREFIX"
  log "HTTPS origin restricted to CloudFront; no public origin QUIC/IPv6 rules added"
else
  for port in 80 443; do
    authorize tcp "$port" v4 0.0.0.0/0
    authorize tcp "$port" v6 ::/0
  done
  authorize udp 443 v4 0.0.0.0/0   # HTTP/3 for a directly exposed origin only.
fi

INSTANCE_ID="$(aws_ ec2 describe-instances \
  --filters "Name=tag:Name,Values=${NAME}" "Name=tag:app,Values=releaseproof" \
            "Name=instance-state-name,Values=pending,running,stopping,stopped" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text)"
if none "$INSTANCE_ID"; then
  log "launching ${INSTANCE_TYPE} (${VOLUME_GB} GB gp3)"
  INSTANCE_ID="$(aws_ ec2 run-instances \
    --image-id "$AMI_ID" \
    --instance-type "$INSTANCE_TYPE" \
    --key-name "$KEY_NAME" \
    --subnet-id "$SUBNET_ID" \
    --security-group-ids "$SG_ID" \
    --associate-public-ip-address \
    --block-device-mappings "DeviceName=/dev/sda1,Ebs={VolumeSize=${VOLUME_GB},VolumeType=gp3,DeleteOnTermination=true,Encrypted=true}" \
    --metadata-options "HttpTokens=required,HttpEndpoint=enabled,HttpPutResponseHopLimit=1" \
    --user-data "file://${USER_DATA_PATH}" \
    --tag-specifications \
      "ResourceType=instance,Tags=[{Key=Name,Value=${NAME}},{Key=app,Value=releaseproof}]" \
      "ResourceType=volume,Tags=[{Key=Name,Value=${NAME}-root},{Key=app,Value=releaseproof}]" \
    --query 'Instances[0].InstanceId' --output text)"
  log "instance ${INSTANCE_ID} launched"
else
  STATE="$(aws_ ec2 describe-instances --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].State.Name' --output text)"
  log "instance ${INSTANCE_ID} exists (${STATE})"
  if [[ "$STATE" == "stopped" || "$STATE" == "stopping" ]]; then
    aws_ ec2 wait instance-stopped --instance-ids "$INSTANCE_ID"
    aws_ ec2 start-instances --instance-ids "$INSTANCE_ID" >/dev/null
    log "starting ${INSTANCE_ID}"
  fi
fi
aws_ ec2 wait instance-running --instance-ids "$INSTANCE_ID"
log "instance running"

ALLOC_ID="$(aws_ ec2 describe-addresses --filters "Name=tag:Name,Values=${NAME}" \
  --query 'Addresses[0].AllocationId' --output text)"
if none "$ALLOC_ID"; then
  ALLOC_ID="$(aws_ ec2 allocate-address --domain vpc \
    --tag-specifications "ResourceType=elastic-ip,Tags=[{Key=Name,Value=${NAME}},{Key=app,Value=releaseproof}]" \
    --query AllocationId --output text)"
  log "allocated Elastic IP ${ALLOC_ID}"
fi
ASSOCIATED="$(aws_ ec2 describe-addresses --allocation-ids "$ALLOC_ID" \
  --query 'Addresses[0].InstanceId' --output text)"
if [[ "$ASSOCIATED" != "$INSTANCE_ID" ]]; then
  aws_ ec2 associate-address --allocation-id "$ALLOC_ID" --instance-id "$INSTANCE_ID" \
    --allow-reassociation >/dev/null
  log "associated ${ALLOC_ID} with ${INSTANCE_ID}"
fi
PUBLIC_IP="$(aws_ ec2 describe-addresses --allocation-ids "$ALLOC_ID" \
  --query 'Addresses[0].PublicIp' --output text)"
SSLIP_HOST="${PUBLIC_IP//./-}.sslip.io"

{
  printf '# written by deploy/aws/provision.sh on %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  # The state is sourced by deploy/destroy: shell-escape every value, including paths
  # under Windows user directories that contain spaces or apostrophes.
  printf 'RP_NAME=%q\n' "$NAME"
  printf 'RP_REGION=%q\n' "$REGION"
  printf 'RP_INSTANCE_ID=%q\n' "$INSTANCE_ID"
  printf 'RP_SECURITY_GROUP_ID=%q\n' "$SG_ID"
  printf 'RP_ALLOCATION_ID=%q\n' "$ALLOC_ID"
  printf 'RP_PUBLIC_IP=%q\n' "$PUBLIC_IP"
  printf 'RP_SSLIP_HOST=%q\n' "$SSLIP_HOST"
  printf 'RP_KEY_FILE=%q\n' "$KEY_FILE"
} > "$STATE_FILE"
chmod 600 "$STATE_FILE"

log "done"
cat <<EOF

  Elastic IP : ${PUBLIC_IP}
  Hostname   : ${SSLIP_HOST}   (or point a DNS A record of your domain to ${PUBLIC_IP})
  SSH        : ssh -i ${KEY_FILE} ubuntu@${PUBLIC_IP}
  State      : ${STATE_FILE}

  Next: deploy/aws/deploy.sh --name ${NAME}            # https://${SSLIP_HOST}
EOF
