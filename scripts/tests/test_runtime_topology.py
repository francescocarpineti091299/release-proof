from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_runners_are_nonroot_and_cannot_mount_database():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    for family in ("wolfboot", "mcuboot"):
        dockerfile = (ROOT / f"runners/{family}/Dockerfile").read_text()
        assert "USER rp" in dockerfile
        service = compose["services"][f"runner-{family}"]
        assert service["cap_drop"] == ["ALL"]
        assert service["networks"] == ["runners"]
        assert service["volumes"] == [
            {
                "type": "volume",
                "source": "rpdata",
                "target": "/data/runs",
                "volume": {"subpath": "runs"},
            }
        ]
        assert service["depends_on"]["api"]["condition"] == "service_healthy"
    mcu = (ROOT / "runners/mcuboot/Dockerfile").read_text()
    assert mcu.index("USER rp") < mcu.index("RUN python -m rp_mcuboot.warm")
    assert "XDG_CACHE_HOME=/home/rp/.cache" in mcu
    assert "west config --local zephyr.base zephyr" in mcu
    assert compose["networks"]["runners"]["internal"] is True


def test_public_override_is_anonymous_bounded_and_has_no_api_host_port():
    compose = yaml.safe_load((ROOT / "docker-compose.public.yml").read_text())
    assert not compose["services"]["caddy"].get("environment")
    assert "ports" not in compose["services"]["api"]
    assert "RELEASEPROOF_MAX_ACTIVE_RUNS" in compose["services"]["api"]["environment"]
    assert "RELEASEPROOF_MUTATION_RPM" in compose["services"]["api"]["environment"]
    assert "basic_auth" not in (ROOT / "deploy/access/public.caddy").read_text()
