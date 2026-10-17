from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash") if os.name != "nt" else "C:/Program Files/Git/bin/bash.exe"
requires_bash = pytest.mark.skipif(not BASH or not Path(BASH).is_file(), reason="Bash unavailable")


@requires_bash
@pytest.mark.parametrize("mode", ["direct", "explicit-cloudfront", "existing-cloudfront"])
def test_provision_preserves_cloudfront_only_ingress(tmp_path, mode):
    log = tmp_path / "aws.log"
    command = """
aws() {
  printf '%s\\n' "$*" >> "$AWS_LOG"
  case "$*" in
    *"sts get-caller-identity"*) echo 123456789012 ;;
    *ssm*) echo ami-test ;;
    *describe-instance-type-offerings*) echo test-az ;;
    *describe-key-pairs*) ;;
    *describe-vpcs*) echo vpc-test ;;
    *describe-subnets*) echo subnet-test ;;
    *describe-security-groups*--group-ids*)
      [[ "$EXISTING_CF" != 1 ]] || echo pl-test ;;
    *describe-security-groups*) echo sg-test ;;
    *describe-managed-prefix-lists*) echo pl-test ;;
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
if [[ "$EXPLICIT_CF" == 1 ]]; then
  bash "$1" --ssh-cidr 127.0.0.1/32 --cloudfront-origin
else
  bash "$1" --ssh-cidr 127.0.0.1/32
fi
"""
    result = subprocess.run(
        [BASH, "-c", command, "test", (ROOT / "deploy/aws/provision.sh").as_posix()],
        env={
            **os.environ,
            "HOME": tmp_path.as_posix(),
            "AWS_LOG": log.as_posix(),
            "EXISTING_CF": str(int(mode == "existing-cloudfront")),
            "EXPLICIT_CF": str(int(mode == "explicit-cloudfront")),
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    ingress = [s for s in log.read_text().splitlines() if "authorize-security-group-ingress" in s]
    if mode == "direct":
        assert any("IpProtocol=udp" in s for s in ingress)
        assert any("CidrIpv6=::/0" in s for s in ingress)
    else:
        assert len(ingress) == 3  # SSH, ACME HTTP-01, CloudFront HTTPS.
        assert not any("IpProtocol=udp" in s or "CidrIpv6=" in s for s in ingress)
        https = next(s for s in ingress if "FromPort=443" in s)
        assert "PrefixListId=pl-test" in https
        assert "CidrIp=0.0.0.0/0" not in https


@requires_bash
@pytest.mark.parametrize("sync_mode", ["rsync", "tar"])
def test_deploy_excludes_private_research_and_checks_viewer_url(tmp_path, sync_mode):
    key = tmp_path / "key.pem"
    key.write_text("test-key-not-a-real-secret")
    log = tmp_path / "sync.log"
    command = """
ssh() { return 0; }
scp() { return 0; }
curl() { return 0; }
rsync() { printf '%s\\n' "$*" >> "$SYNC_LOG"; }
tar() { printf '%s\\n' "$*" >> "$SYNC_LOG"; }
command() {
  if [[ "$*" == "-v rsync" ]]; then
    [[ "$SYNC_MODE" == rsync ]]; return
  fi
  builtin command "$@"
}
export -f ssh scp curl rsync tar command
bash "$1" --host 127.0.0.1 --key "$2" --env-file "$3" --site-address :80 \\
  --viewer-url https://demo.cloudfront.net --no-build --trusted-local
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
        env={
            **os.environ,
            "HOME": tmp_path.as_posix(),
            "SYNC_LOG": log.as_posix(),
            "SYNC_MODE": sync_mode,
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    expected = "--exclude /general_docs/" if sync_mode == "rsync" else "--exclude=./general_docs"
    assert expected in log.read_text()
    assert "up: https://demo.cloudfront.net" in result.stdout


def test_read_only_smoke_uses_completed_history_during_an_active_run(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "cloudfront_smoke", ROOT / "scripts/cloudfront_smoke.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    base = "https://demo.cloudfront.net"
    manifest = b'{"run_id":"completed"}'
    responses = {
        "/": b'<title>ReleaseProof</title><script src="/_next/static/test.js"></script>',
        "/_next/static/test.js": b"console.log('test');",
        "/api/health": {"status": "ok", "env": "demo"},
        "/api/configurations": [{"status": "SUPPORTED"}, {"status": "SUPPORTED"}],
        "/api/assessments?limit=1": [{"run_id": "active", "status": "RUNNING"}],
        "/api/assessments?limit=20": [
            {"run_id": "active", "status": "RUNNING"},
            {"run_id": "completed", "status": "SUCCEEDED"},
        ],
        "/api/assessments/completed/result": {"result": {"canonical_hash": "sha256:test"}},
        "/api/assessments/completed/artifacts": [
            {
                "artifact_id": "MANIFEST",
                "url": "/api/manifest",
                "sha256": hashlib.sha256(manifest).hexdigest(),
            }
        ],
        "/api/manifest": manifest,
    }
    called = []

    def urlopen(request, timeout):
        assert request.get_method() == "GET"
        path = request.full_url.removeprefix(base)
        called.append(path)
        data = responses[path]
        response = io.BytesIO(data if isinstance(data, bytes) else json.dumps(data).encode())
        response.status = 200
        response.headers = {"X-Cache": "Miss from cloudfront"}
        response.url = request.full_url
        return response

    monkeypatch.setattr(module.urllib.request, "urlopen", urlopen)
    report = module.check(base, live=False, timeout=60)
    assert report["passed"] is True
    assert report["run_id"] == "completed"
    assert not any("/active/result" in path for path in called)


@requires_bash
def test_deploy_refuses_jobs_started_during_the_build(tmp_path):
    key = tmp_path / "key.pem"
    key.write_text("test-key-not-a-real-secret")
    log = tmp_path / "remote.log"
    command = """
ssh() {
  printf '%s\\n' "$*" >> "$REMOTE_LOG"
  if [[ "$*" == *'Active assessments: retry deployment'* ]]; then
    echo 'Active assessments' >&2; return 23
  fi
}
scp() { return 0; }
rsync() { return 0; }
curl() { return 0; }
export -f ssh scp rsync curl
bash "$1" --host 127.0.0.1 --key "$2" --env-file "$3" \\
  --site-address :80 --trusted-local
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
        env={**os.environ, "HOME": tmp_path.as_posix(), "REMOTE_LOG": log.as_posix()},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 23
    assert "docker-compose.yml build" in log.read_text()
    assert " up -d" not in log.read_text()
