"""Strict local export configuration; no official platform rules are implied."""

import hashlib
import json
from typing import Any


def validate_profile(profile: Any) -> dict[str, Any]:
    if not isinstance(profile, dict) or set(profile) != {
        "Platform",
        "RuleVersion",
        "UpdatedAt",
        "Source",
        "Fields",
    }:
        raise ValueError("Invalid platform profile")
    for key in ("Platform", "RuleVersion", "UpdatedAt"):
        if not isinstance(profile[key], str) or not profile[key].strip() or len(profile[key]) > 200:
            raise ValueError("Invalid profile identity")
    if profile["Platform"] not in {"bilibili", "douyin", "kuaishou", "xiaohongshu"} or profile[
        "Source"
    ] != {"kind": "local_preset", "label": "用户可编辑本地导出配置，非官方规则"}:
        raise ValueError("Unsupported local profile")
    fields = profile["Fields"]
    if not isinstance(fields, dict) or set(fields) != {"video", "cover", "limits"}:
        raise ValueError("Invalid profile fields")
    for kind in ("video", "cover"):
        value = fields[kind]
        expected = {"width", "height", "fit"} | (
            {"codec", "pixelFormat"} if kind == "video" else set()
        )
        if (
            not isinstance(value, dict)
            or set(value) != expected
            or value["fit"] not in ("pad", "crop")
        ):
            raise ValueError("Invalid transform")
        for key in ("width", "height"):
            if type(value[key]) is not int or not 16 <= value[key] <= 3840 or value[key] % 2:
                raise ValueError("Invalid dimensions")
        if kind == "video" and (value["codec"], value["pixelFormat"]) != ("h264", "yuv420p"):
            raise ValueError("Unsupported encoding")
    limits = fields["limits"]
    keys = {
        "maxBytes",
        "minDurationMs",
        "maxDurationMs",
        "titleMaxChars",
        "descriptionMaxChars",
        "tagMaxCount",
        "requiredTags",
    }
    if not isinstance(limits, dict) or set(limits) != keys:
        raise ValueError("Invalid limits")
    for key in keys - {"requiredTags"}:
        if limits[key] is not None and (
            type(limits[key]) is not int or not 0 <= limits[key] <= 10**12
        ):
            raise ValueError("Invalid limit")
    tags = limits["requiredTags"]
    if (
        not isinstance(tags, list)
        or len(tags) > 100
        or any(not isinstance(t, str) or not t.strip() or len(t) > 200 for t in tags)
    ):
        raise ValueError("Invalid required tags")
    if (
        limits["minDurationMs"] is not None
        and limits["maxDurationMs"] is not None
        and limits["minDurationMs"] > limits["maxDurationMs"]
    ):
        raise ValueError("Inverted duration limits")
    return profile


def profile_digest(profile: dict[str, Any]) -> str:
    validate_profile(profile)
    return hashlib.sha256(
        json.dumps(profile, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
