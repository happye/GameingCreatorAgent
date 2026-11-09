"""Versioned platform preset JSON loading; local presets only, not official rules."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gamingcreator.domain.platform_profile import profile_digest, validate_profile
from gamingcreator.infrastructure.platform_preset_loader import (
    SCHEMA,
    load_platform_manifest,
    load_platform_profiles,
)
from gamingcreator.ui import package_jobs

ROOT = Path(__file__).resolve().parents[1]
PRESETS = ROOT / "src/gamingcreator/infrastructure/platform_presets"


SOURCES = (
    Path(__file__).resolve().parents[1] / "docs/references/platform-limits-sources.md"
).read_text(encoding="utf-8")


def test_manifest_declares_non_official_versioned_catalog() -> None:
    manifest = load_platform_manifest()
    assert manifest["schemaVersion"] == SCHEMA
    assert "not official" in manifest["disclaimer"].lower()
    assert manifest["ruleVersion"] == "local-v2"
    assert manifest["platforms"] == ["bilibili", "douyin", "kuaishou", "xiaohongshu"]


def test_loader_returns_four_validated_local_presets() -> None:
    profiles = load_platform_profiles()
    assert [item["Platform"] for item in profiles] == [
        "bilibili",
        "douyin",
        "kuaishou",
        "xiaohongshu",
    ]
    for profile in profiles:
        assert profile["Source"]["kind"] == "local_preset"
        assert "非官方" in profile["Source"]["label"]
        assert profile["RuleVersion"] == "local-v2"
        # Null limits stay not_configured; every filled number must cite an official page.
        for field, value in profile["Fields"]["limits"].items():
            if field != "requiredTags" and value is not None:
                cited = f"| {profile['Platform']} | {field} | {value}"
                assert cited in SOURCES, cited
        digest = profile_digest(profile)
        assert len(digest) == 64
        assert profile_digest(validate_profile(json.loads(json.dumps(profile)))) == digest


def test_package_jobs_profiles_uses_loader() -> None:
    payload = package_jobs.profiles()
    assert {item["Platform"] for item in payload["profiles"]} == {
        "bilibili",
        "douyin",
        "kuaishou",
        "xiaohongshu",
    }


def test_page_override_keeps_preset_files_unchanged() -> None:
    before = {path.name: path.read_bytes() for path in PRESETS.glob("*.json")}
    profile = json.loads((PRESETS / "douyin.json").read_text(encoding="utf-8"))
    edited = validate_profile(profile)
    edited = {
        **edited,
        "RuleVersion": edited["RuleVersion"] + "-edited-testhash",
        "UpdatedAt": "2026-11-01T00:00:00+00:00",
        "Fields": {
            **edited["Fields"],
            "limits": {**edited["Fields"]["limits"], "titleMaxChars": 40},
        },
    }
    validate_profile(edited)
    assert edited["RuleVersion"] != "local-v2"
    after = {path.name: path.read_bytes() for path in PRESETS.glob("*.json")}
    assert after == before


def test_loader_refuses_tampered_manifest(tmp_path: Path) -> None:
    root = tmp_path / "presets"
    root.mkdir()
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "schemaVersion": SCHEMA,
                "disclaimer": "local only",  # missing not official
                "ruleVersion": "local-v1",
                "platforms": ["bilibili"],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="非官方|不完整"):
        load_platform_manifest(root)
