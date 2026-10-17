from __future__ import annotations

import adapter_facts
import pytest

from releaseproof.profiles.registry import get_profile


@pytest.fixture
def wolfboot_profile():
    return get_profile("nrf52840-wolfboot-pqc")


@pytest.fixture
def mcuboot_profile():
    return get_profile("nrf52840-mcuboot-pqc")


@pytest.fixture
def wolfboot_run():
    return adapter_facts.wolfboot_run


@pytest.fixture
def mcuboot_run():
    return adapter_facts.mcuboot_run
