from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_azure_origin_guard_is_not_viewer_authentication():
    config = (ROOT / "deploy/azure/Caddyfile").read_text()
    assert "basic_auth" not in config
    assert "route {" in config
    assert config.index("respond @wrong_origin") < config.index("handle /api/*")
    assert "X-Azure-FDID {$AZURE_FRONT_DOOR_ID}" in config
    assert "disable_tlsalpn_challenge" in config
    assert "flush_interval -1" in config


def test_azure_overlay_only_changes_the_origin_proxy():
    overlay = yaml.safe_load((ROOT / "docker-compose.azure.yml").read_text())
    assert set(overlay["services"]) == {"caddy"}
    caddy = overlay["services"]["caddy"]
    assert caddy["volumes"] == ["./deploy/azure/Caddyfile:/etc/caddy/Caddyfile:ro"]
    assert "AZURE_FRONT_DOOR_ID:?" in caddy["environment"]["AZURE_FRONT_DOOR_ID"]


def test_azure_provisioning_is_scoped_https_and_uncached():
    script = (ROOT / "deploy/azure/provision.ps1").read_text()
    assert "[Parameter(Mandatory = $true)][string]$SubscriptionId" in script
    assert "Refusing to use a resource group not owned by ReleaseProof" in script
    assert "AzureFrontDoor.Backend" in script
    assert "'--enforce-certificate-name-check', 'true'" in script
    assert "'--forwarding-protocol', 'HttpsOnly'" in script
    assert "'--enable-caching', 'false'" in script
    # Never embed secrets in cloud-init or resource metadata.
    assert "AMD_LLM_API_KEY" not in script


def test_azure_release_uses_committed_archive_and_preserves_active_jobs():
    script = (ROOT / "deploy/azure/deploy.ps1").read_text()
    assert "archive --format=tar.gz" in script
    assert "Wait for active assessments" in script
    assert "chmod 600" in script
    assert "'RELEASEPROOF_MAX_ACTIVE_RUNS=4'" in script
    assert "'RELEASEPROOF_MUTATION_RPM=20'" in script
    assert "docker-compose.public.yml -f docker-compose.azure.yml" in script
    assert "reset --hard" not in script
    assert "rm -rf" not in script
