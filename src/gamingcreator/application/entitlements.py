"""Creator plan entitlements and metered usage (master plan §40), with no payment system.

Plans are enforced for real at the feature entry points; usage is counted from saved jobs.
Selecting a plan here is a local evaluation, not a purchase: there is no billing, and the
default "founder" plan (§42 founder-led validation) keeps every feature available.
"""

from datetime import datetime
from typing import Any

PLANS: dict[str, dict[str, Any]] = {
    "founder": {
        "label": "创始人验证版（默认，不限）",
        "features": {"activityRules", "multiPlatform", "timelineExport", "sandboxPublish"},
        "monthlyRenders": None,
        "monthlyPreparationMinutes": None,
    },
    "free": {
        "label": "Free",
        "features": set(),
        "monthlyRenders": 10,
        "monthlyPreparationMinutes": 60,
        "watermark": "GamingCreator Free",
    },
    "creator": {
        "label": "Creator",
        "features": {"activityRules", "multiPlatform", "sandboxPublish"},
        "monthlyRenders": 100,
        "monthlyPreparationMinutes": None,
    },
    "pro": {
        "label": "Creator Pro",
        "features": {"activityRules", "multiPlatform", "timelineExport", "sandboxPublish"},
        "monthlyRenders": 1000,
        "monthlyPreparationMinutes": None,
    },
}
FEATURE_LABELS = {
    "activityRules": "活动规则解析",
    "multiPlatform": "同一成片生成多个平台包",
    "timelineExport": "专业时间线导出",
    "sandboxPublish": "发布流程（沙箱）",
}


def watermark_for(selection: dict[str, Any] | None) -> str | None:
    """The visible mark a plan burns into rendered videos, or None (paid and founder plans)."""
    value = PLANS[plan_of(selection)].get("watermark")
    return value if isinstance(value, str) else None


class EntitlementError(PermissionError):
    pass


def plan_of(selection: dict[str, Any] | None) -> str:
    plan = (selection or {}).get("plan", "founder")
    return plan if plan in PLANS else "founder"


def require(selection: dict[str, Any] | None, feature: str) -> None:
    plan = plan_of(selection)
    if feature not in PLANS[plan]["features"]:
        raise EntitlementError(
            f"当前套餐“{PLANS[plan]['label']}”不包含“{FEATURE_LABELS[feature]}”。"
            "可在“套餐与用量”里切换（本地评估，不涉及付费）。"
        )


def month_key(timestamp: str) -> str:
    return datetime.fromisoformat(timestamp).strftime("%Y-%m")


def renders_this_month(jobs: list[dict[str, Any]], now: str) -> int:
    month = month_key(now)
    return sum(
        1
        for job in jobs
        if job.get("kind") == "render"
        and job.get("status") in ("pending", "running", "completed")
        and job.get("createdAt")
        and month_key(job["createdAt"]) == month
    )


def require_render(selection: dict[str, Any] | None, used: int) -> None:
    plan = plan_of(selection)
    limit = PLANS[plan]["monthlyRenders"]
    if limit is not None and used >= limit:
        raise EntitlementError(
            f"当前套餐“{PLANS[plan]['label']}”本月成片额度已用完（{used}/{limit}）。"
        )


def require_preparation_minutes(
    selection: dict[str, Any] | None, used_minutes: float, additional_minutes: float
) -> None:
    """Refuse a new media-preparation submit that would exceed this month's Free cap.

    Creator / Pro / founder have monthlyPreparationMinutes=None (unlimited). Usage is
    counted when a new prepare submit is accepted; failed batches still count; resume
    must not call this with a duplicate key that adds again.
    """
    if additional_minutes < 0:
        raise ValueError("additional_minutes must be non-negative")
    plan = plan_of(selection)
    limit = PLANS[plan].get("monthlyPreparationMinutes")
    if limit is None:
        return
    projected = used_minutes + additional_minutes
    if projected > float(limit) + 1e-9:
        raise EntitlementError(
            f"当前套餐“{PLANS[plan]['label']}”本月准备录像额度不足"
            f"（已用约 {used_minutes:.1f} 分钟，本次约 {additional_minutes:.1f} 分钟，"
            f"上限 {limit} 分钟）。可在“套餐与用量”切换套餐（本地评估，不涉及付费）。"
        )


def require_package_platform(
    selection: dict[str, Any] | None, platforms_already_packaged: set[str], platform: str
) -> None:
    if platform in platforms_already_packaged or not platforms_already_packaged:
        return
    require(selection, "multiPlatform")


def summary(
    selection: dict[str, Any] | None,
    used_renders: int,
    *,
    preparation_minutes_used: float = 0.0,
) -> dict[str, Any]:
    plan = plan_of(selection)
    definition = PLANS[plan]
    return {
        "plan": plan,
        "label": definition["label"],
        "billing": "none-local-evaluation",
        "features": {name: name in definition["features"] for name in FEATURE_LABELS},
        "featureLabels": FEATURE_LABELS,
        "monthlyRenders": definition["monthlyRenders"],
        "rendersThisMonth": used_renders,
        "monthlyPreparationMinutes": definition.get("monthlyPreparationMinutes"),
        "preparationMinutesThisMonth": round(float(preparation_minutes_used), 2),
        "watermark": watermark_for(selection),
        "plans": {name: value["label"] for name, value in PLANS.items()},
    }
