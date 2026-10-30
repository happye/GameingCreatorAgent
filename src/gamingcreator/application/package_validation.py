"""Public local checks, independent from unknown official publication rules."""

from typing import Any


def validate_package(
    profile: dict[str, Any], facts: dict[str, Any], metadata: dict[str, Any], parent: dict[str, Any]
) -> dict[str, Any]:
    video = profile["Fields"]["video"]
    checks = {
        key: ("pass" if facts[key] == video[key] else "fail")
        for key in ("width", "height", "codec", "pixelFormat")
    }
    checks["frames"] = "pass" if facts["frames"] == parent["frames"] else "fail"
    fps = facts["fps"]
    checks["fps"] = (
        "pass"
        if fps["numerator"] * parent["fpsDenominator"]
        == fps["denominator"] * parent["fpsNumerator"]
        else "fail"
    )
    limits = profile["Fields"]["limits"]
    for key, actual, lower in (
        ("maxBytes", facts["sizeBytes"], False),
        ("minDurationMs", facts["durationMs"], True),
        ("maxDurationMs", facts["durationMs"], False),
        ("titleMaxChars", len(metadata["title"]), False),
        ("descriptionMaxChars", len(metadata["description"]), False),
        ("tagMaxCount", len(metadata["tags"]), False),
    ):
        bound = limits[key]
        checks[key] = (
            "not_configured"
            if bound is None
            else "pass"
            if (actual >= bound if lower else actual <= bound)
            else "fail"
        )
    required = limits["requiredTags"]
    checks["requiredTags"] = (
        "not_configured"
        if not required
        else "pass"
        if set(required) <= set(metadata["tags"])
        else "fail"
    )
    return {
        "facts": facts,
        "checks": checks,
        "localChecks": "fail" if "fail" in checks.values() else "pass",
        "platformRules": "unknown",
        "sourceRights": "unknown",
        "humanQuality": "unknown",
        "publicationEligibility": "blocked"
        if (parent.get("music") or {}).get("licenseStatus") == "test_only"
        else "unverified",
    }
