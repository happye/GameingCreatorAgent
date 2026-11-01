"""Load versioned local platform export presets from JSON (not official rules)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gamingcreator.domain.platform_profile import validate_profile

MANIFEST_NAME = "manifest.json"
SCHEMA = "platform-presets-v1"
DEFAULT_ROOT = Path(__file__).resolve().parent / "platform_presets"


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"无法读取平台预设 {path.name}。") from error


def load_platform_manifest(root: Path | None = None) -> dict[str, Any]:
    directory = (root or DEFAULT_ROOT).resolve()
    document = _read_json(directory / MANIFEST_NAME)
    if not isinstance(document, dict):
        raise ValueError("平台预设清单格式无效。")
    if document.get("schemaVersion") != SCHEMA:
        raise ValueError("平台预设清单版本不受支持。")
    platforms = document.get("platforms")
    rule_version = document.get("ruleVersion")
    disclaimer = document.get("disclaimer")
    if (
        not isinstance(platforms, list)
        or not platforms
        or any(type(item) is not str or not item for item in platforms)
        or type(rule_version) is not str
        or not rule_version
        or type(disclaimer) is not str
        or "not official" not in disclaimer.lower()
    ):
        raise ValueError("平台预设清单字段不完整或未声明非官方。")
    return document


def load_platform_profiles(root: Path | None = None) -> list[dict[str, Any]]:
    """Return validated local presets in manifest order; never network-fetched."""
    directory = (root or DEFAULT_ROOT).resolve()
    manifest = load_platform_manifest(directory)
    profiles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for name in manifest["platforms"]:
        if name in seen:
            raise ValueError(f"平台预设重复：{name}")
        seen.add(name)
        path = directory / f"{name}.json"
        if not path.is_file():
            raise ValueError(f"缺少平台预设文件：{name}.json")
        profile = validate_profile(_read_json(path))
        if profile["Platform"] != name:
            raise ValueError(f"预设文件名与 Platform 不一致：{name}")
        if profile["RuleVersion"] != manifest["ruleVersion"]:
            raise ValueError(f"预设 RuleVersion 与清单不一致：{name}")
        if profile["Source"].get("kind") != "local_preset":
            raise ValueError(f"预设必须是 local_preset：{name}")
        profiles.append(profile)
    return profiles