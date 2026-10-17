from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash") if os.name != "nt" else str(Path("C:/Program Files/Git/bin/bash.exe"))
pytestmark = pytest.mark.skipif(not BASH or not Path(BASH).is_file(), reason="Bash unavailable")


def test_shell_scripts_have_valid_syntax():
    for path in (ROOT / "deploy").rglob("*.sh"):
        subprocess.run([BASH, "-n", path.as_posix()], check=True, capture_output=True)


def test_failed_teardown_retains_state_without_claiming_success(tmp_path):
    state_dir = tmp_path / ".releaseproof-aws"
    state_dir.mkdir()
    state = state_dir / "releaseproof.env"
    state.write_text(
        "RP_REGION=test\nRP_INSTANCE_ID=i-test\nRP_ALLOCATION_ID=eipalloc-test\n"
        "RP_PUBLIC_IP=127.0.0.1\nRP_SECURITY_GROUP_ID=sg-test\n"
    )
    # An exported shell function shadows AWS: this test never contacts AWS or deletes
    # resources. Simulate AccessDenied on the very first describe operation.
    command = 'aws() { echo "AccessDenied" >&2; return 13; }; export -f aws; bash "$1" --yes'
    env = {**os.environ, "HOME": tmp_path.as_posix()}
    result = subprocess.run(
        [BASH, "-c", command, "test", (ROOT / "deploy/aws/destroy.sh").as_posix()],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert state.exists()
    assert "destroyed releaseproof" not in result.stdout


def test_mcu_profile_preserves_issue_number():
    import yaml

    data = yaml.safe_load((ROOT / "profiles/nrf52840-mcuboot-pqc.yaml").read_text())
    alternatives = data["changes"][0]["alternatives"]
    assert alternatives[-1]["title"].endswith("(PR #2707)")


def test_provision_state_can_be_sourced_with_spaces_and_quotes_in_home(tmp_path):
    home = tmp_path / "User's home"
    home.mkdir()
    # Every AWS command is intercepted; no credentials or network requests are used.
    command = """
aws() {
  case "$*" in
    *sts*) echo 123456789012 ;;
    *ssm*) echo ami-test ;;
    *describe-instance-type-offerings*) echo test-az ;;
    *describe-key-pairs*) ;;
    *describe-vpcs*) echo vpc-test ;;
    *describe-subnets*) echo subnet-test ;;
    *describe-security-groups*) echo sg-test ;;
    *authorize-security-group-ingress*) ;;
    *describe-instances*State.Name*) echo running ;;
    *describe-instances*) echo i-test ;;
    *wait*) ;;
    *describe-addresses*PublicIp*) echo 127.0.0.1 ;;
    *describe-addresses*InstanceId*) echo i-test ;;
    *describe-addresses*) echo eipalloc-test ;;
    *) echo "Unexpected AWS call: $*" >&2; return 99 ;;
  esac
}
export -f aws
bash "$1" --ssh-cidr 127.0.0.1/32 || exit
source "$HOME/.releaseproof-aws/releaseproof.env" || exit
[[ "$RP_KEY_FILE" == "$HOME/.releaseproof-aws/releaseproof.pem" ]]
"""
    result = subprocess.run(
        [BASH, "-c", command, "test", (ROOT / "deploy/aws/provision.sh").as_posix()],
        env={**os.environ, "HOME": home.as_posix()},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_retry_teardown_tolerates_only_missing_resources(tmp_path):
    state_dir = tmp_path / ".releaseproof-aws"
    state_dir.mkdir()
    state = state_dir / "releaseproof.env"
    state.write_text(
        "RP_REGION=test\nRP_INSTANCE_ID=i-test\nRP_ALLOCATION_ID=eipalloc-test\n"
        "RP_PUBLIC_IP=127.0.0.1\nRP_SECURITY_GROUP_ID=sg-test\n"
    )
    command = """
aws() {
  case "$*" in
    *describe-addresses*|*release-address*)
      echo "An error occurred (InvalidAllocationID.NotFound)" >&2; return 1 ;;
    *delete-security-group*)
      echo "An error occurred (InvalidGroup.NotFound)" >&2; return 1 ;;
    *terminate-instances*|*wait*) ;;
    *) echo "Unexpected AWS call: $*" >&2; return 99 ;;
  esac
}
export -f aws
bash "$1" --yes
"""
    result = subprocess.run(
        [BASH, "-c", command, "test", (ROOT / "deploy/aws/destroy.sh").as_posix()],
        env={**os.environ, "HOME": tmp_path.as_posix()},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert not state.exists()


def test_deploy_health_url_preserves_nondefault_port(tmp_path):
    key = tmp_path / "key.pem"
    key.write_text("test-key-not-a-real-secret")
    command = """
ssh() { return 0; }
scp() { return 0; }
rsync() { return 0; }
curl() { return 0; }
export -f ssh scp rsync curl
bash "$1" --host 127.0.0.1 --key "$2" --env-file "$3" \\
  --site-address :8080 --no-build --trusted-local
"""
    result = subprocess.run(
        [
            BASH,
            "-c",
            command,
            "test",
            (ROOT / "deploy/aws/deploy.sh").as_posix(),
            key.as_posix(),
            (ROOT / ".env.example").as_posix(),
        ],
        env={**os.environ, "HOME": tmp_path.as_posix()},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "up: http://127.0.0.1:8080" in result.stdout
