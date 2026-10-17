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

STATE_FILE="${HOME}/.releaseproof-aws/${NAME}.env"
[[ -f "$STATE_FILE" ]] || { echo "no state file ${STATE_FILE}" >&2; exit 1; }
# shellcheck disable=SC1090
source "$STATE_FILE"
aws_() { aws "${PROFILE_ARGS[@]}" --region "$RP_REGION" "$@"; }

echo "Will terminate ${RP_INSTANCE_ID}, release ${RP_PUBLIC_IP} (${RP_ALLOCATION_ID}), delete ${RP_SECURITY_GROUP_ID} in ${RP_REGION}."
if [[ "$YES" != 1 ]]; then
  read -r -p "Type the name '${NAME}' to confirm: " answer
  [[ "$answer" == "$NAME" ]] || { echo "aborted"; exit 1; }
fi

ASSOC="$(aws_ ec2 describe-addresses --allocation-ids "$RP_ALLOCATION_ID" \
  --query 'Addresses[0].AssociationId' --output text 2>/dev/null || true)"
[[ -n "$ASSOC" && "$ASSOC" != "None" ]] && aws_ ec2 disassociate-address --association-id "$ASSOC"
aws_ ec2 release-address --allocation-id "$RP_ALLOCATION_ID" || true
aws_ ec2 terminate-instances --instance-ids "$RP_INSTANCE_ID" >/dev/null || true
aws_ ec2 wait instance-terminated --instance-ids "$RP_INSTANCE_ID" || true
aws_ ec2 delete-security-group --group-id "$RP_SECURITY_GROUP_ID" || true
if [[ "$DELETE_KEY" == 1 ]]; then
  aws_ ec2 delete-key-pair --key-name "$(basename "$RP_KEY_FILE" .pem)" || true
  rm -f "$RP_KEY_FILE"
fi
rm -f "$STATE_FILE"
echo "destroyed ${NAME}"
