from releaseproof.contracts.runner import RunnerEventEnvelope
from releaseproof.profiles.registry import load_catalog, load_profiles


def test_registry_loads_both_profiles() -> None:
    profiles = load_profiles()
    assert set(profiles) == {"nrf52840-wolfboot-pqc", "nrf52840-mcuboot-pqc"}
    assert profiles["nrf52840-wolfboot-pqc"].bootloader.family == "wolfboot"
    assert profiles["nrf52840-mcuboot-pqc"].bootloader.family == "mcuboot"


def test_every_change_has_a_negative_required_test() -> None:
    catalog = {t.template_id: t for t in load_catalog().templates}
    for profile in load_profiles().values():
        for change in profile.changes:
            assert any(catalog[t].negative for t in change.required_templates), change.change_id


def test_runner_event_envelope_parses_each_type() -> None:
    base = {"seq": 0, "ts": "2026-10-17T12:00:00Z", "run_id": "RP-test01"}
    samples = [
        {**base, "type": "stage", "stage": "BUILD_SIGN", "status": "RUNNING"},
        {**base, "type": "log", "stream": "build", "line": "make"},
        {
            **base,
            "type": "observation",
            "observation": {
                "observation_id": "OBS-E01-1",
                "test_id": "E01",
                "subject": "deployed_state",
                "fact": "boot_outcome",
                "value": "BOOT_OK",
                "origin": "OBSERVED_EMULATION",
                "acquisition_mode": "EMULATED",
                "parser": "wolfboot_uart@1",
            },
        },
        {**base, "type": "done", "status": "SUCCEEDED"},
    ]
    for sample in samples:
        assert RunnerEventEnvelope.model_validate({"event": sample}).event.type == sample["type"]
