#!/usr/bin/env bash
# Tear down what provision.sh created (instance, Elastic IP, security group; key pair with
# --delete-key). Asks for confirmation unless --yes. Data on the instance volume is lost.
#
#   deploy/aws/destroy.sh [--name releaseproof] [--profile default] [--delete-key] [--yes]
set -euo pipefail

NAME="releaseproof"
PROFILE_ARGS=()
DELETE_KEY=0
YES=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --name) NAME="$2"; shift 2 ;;
    --profile) PROFILE_ARGS=(--profile "$2"); shift 2 ;;
    --delete-key) DELETE_KEY=1; shift ;;
    --yes) YES=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ "$NAME" =~ ^[A-Za-z0-9-]{1,40}$ ]] || { echo "invalid --name" >&2; exit 2; }
STATE_FILE="${HOME}/.releaseproof-aws/${NAME}.env"
[[ -f "$STATE_FILE" ]] || { echo "no state file ${STATE_FILE}" >&2; exit 1; }
# shellcheck disable=SC1090
source "$STATE_FILE"
aws_() { aws "${PROFILE_ARGS[@]}" --region "$RP_REGION" "$@"; }
aws_if_present() {
  local missing_code="$1" output
  shift
  if output="$(aws_ "$@" 2>&1)"; then
    [[ -z "$output" ]] || printf '%s\n' "$output"
  elif [[ "$output" == *"(${missing_code})"* ]]; then
    : # A previous partial teardown already removed this resource.
  else
    printf '%s\n' "$output" >&2
    return 1
  fi
}

echo "Will terminate ${RP_INSTANCE_ID}, release ${RP_PUBLIC_IP} (${RP_ALLOCATION_ID}), delete ${RP_SECURITY_GROUP_ID} in ${RP_REGION}."
if [[ "$YES" != 1 ]]; then
  read -r -p "Type the name '${NAME}' to confirm: " answer
  [[ "$answer" == "$NAME" ]] || { echo "aborted"; exit 1; }
fi

ASSOC="$(aws_if_present InvalidAllocationID.NotFound ec2 describe-addresses --allocation-ids "$RP_ALLOCATION_ID" \
  --query 'Addresses[0].AssociationId' --output text)"
if [[ -n "$ASSOC" && "$ASSOC" != "None" ]]; then
  aws_if_present InvalidAssociationID.NotFound ec2 disassociate-address --association-id "$ASSOC"
fi
aws_if_present InvalidAllocationID.NotFound ec2 release-address --allocation-id "$RP_ALLOCATION_ID"
aws_ ec2 terminate-instances --instance-ids "$RP_INSTANCE_ID" >/dev/null
aws_ ec2 wait instance-terminated --instance-ids "$RP_INSTANCE_ID"
aws_if_present InvalidGroup.NotFound ec2 delete-security-group --group-id "$RP_SECURITY_GROUP_ID"
if [[ "$DELETE_KEY" == 1 ]]; then
  aws_if_present InvalidKeyPair.NotFound ec2 delete-key-pair --key-name "$(basename "$RP_KEY_FILE" .pem)"
  rm -f "$RP_KEY_FILE"
fi
rm -f "$STATE_FILE"
echo "destroyed ${NAME}"
