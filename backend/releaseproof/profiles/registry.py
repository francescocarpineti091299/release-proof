"""Load and validate the configuration registry (profiles/*.yaml + test catalog)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

from releaseproof.contracts.profile import Profile, ProfileStatus, TestCatalog, TestTemplate

PROFILES_DIR = Path(
    os.environ.get("RELEASEPROOF_PROFILES_DIR", Path(__file__).resolve().parents[3] / "profiles")
)


class RegistryError(ValueError):
    pass


@lru_cache(maxsize=1)
def load_catalog() -> TestCatalog:
    raw = yaml.safe_load((PROFILES_DIR / "test_catalog.yaml").read_text(encoding="utf-8"))
    catalog = TestCatalog.model_validate(raw)
    ids = [t.template_id for t in catalog.templates]
    if len(ids) != len(set(ids)):
        raise RegistryError("duplicate template_id in test catalog")
    for template in catalog.templates:
        if template.test_id not in catalog.tests:
            raise RegistryError(f"{template.template_id}: unknown test_id {template.test_id}")
    return catalog


@lru_cache(maxsize=1)
def load_profiles() -> dict[str, Profile]:
    catalog = {t.template_id: t for t in load_catalog().templates}
    profiles: dict[str, Profile] = {}
    for path in sorted(PROFILES_DIR.glob("*.yaml")):
        if path.name == "test_catalog.yaml":
            continue
        profile = Profile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        if profile.id in profiles:
            raise RegistryError(f"duplicate profile id {profile.id}")
        for change in profile.changes:
            for tid in [*change.required_templates, *change.optional_templates]:
                template = catalog.get(tid)
                if template is None:
                    raise RegistryError(f"{profile.id}/{change.change_id}: unknown template {tid}")
                if template.family != profile.bootloader.family:
                    raise RegistryError(f"{tid} belongs to family {template.family}")
            plan_ids = [a.plan_id for a in change.alternatives]
            if change.default_plan_id in plan_ids or len(plan_ids) != len(set(plan_ids)):
                raise RegistryError(f"{profile.id}/{change.change_id}: plan ids not unique")
        profiles[profile.id] = profile
    return profiles


def selectable_profiles(*, include_experimental: bool) -> list[Profile]:
    allowed = {ProfileStatus.SUPPORTED}
    if include_experimental:
        allowed.add(ProfileStatus.EXPERIMENTAL)
    return [p for p in load_profiles().values() if p.status in allowed]


def get_profile(profile_id: str) -> Profile:
    try:
        return load_profiles()[profile_id]
    except KeyError as exc:
        raise RegistryError(f"unknown configuration {profile_id}") from exc


def get_template(template_id: str) -> TestTemplate:
    for template in load_catalog().templates:
        if template.template_id == template_id:
            return template
    raise RegistryError(f"unknown template {template_id}")
