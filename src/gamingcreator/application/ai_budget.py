"""Monthly AI budget for creation text calls (authorized by the user on 2026-11-11).

Inside the budget a creation call runs without a per-call confirmation; past either cap the
caller falls back to explicit confirmation. Pure accounting: callers supply the spend rows.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from gamingcreator.application.pricing import PriceSnapshot

POLICY_ID = "creation-ai-budget-2026-11-11"
POLICY_TEXT = (
    "用户 2026-11-11 授权：创作环节 AI 文字调用每月 ¥30、单条视频 ¥1 内自动调用，超出再询问"
)
MONTHLY_CAP_CNY = Decimal("30")
PER_VIDEO_CAP_CNY = Decimal("1")
# Chat-template and role tokens on top of the payload text.
TEMPLATE_OVERHEAD_TOKENS = 1024


@dataclass(frozen=True)
class Spend:
    month: str  # "YYYY-MM", local time of the confirmation
    job_id: str  # the creation job, i.e. one video
    cny: Decimal  # known cost, else the recorded ceiling or reservation


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    ceiling_cny: Decimal
    month_spent_cny: Decimal
    video_spent_cny: Decimal
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "policyId": POLICY_ID,
            "eligible": self.allowed,
            "ceilingCny": str(self.ceiling_cny),
            "monthSpentCny": str(self.month_spent_cny),
            "monthCapCny": str(MONTHLY_CAP_CNY),
            "videoSpentCny": str(self.video_spent_cny),
            "videoCapCny": str(PER_VIDEO_CAP_CNY),
            "reason": self.reason,
        }


def call_ceiling_cny(price: PriceSnapshot, payload_text: str, max_output_tokens: int) -> Decimal:
    """Upper bound for one call: a byte-level tokenizer never yields more tokens than UTF-8
    bytes, so payload bytes plus template overhead bound the input, at the peak price."""
    tokens = len(payload_text.encode("utf-8")) + TEMPLATE_OVERHEAD_TOKENS
    return price.reservation_cny(min(tokens, price.context_limit_tokens), max_output_tokens)


def decide(spends: Iterable[Spend], job_id: str, month: str, ceiling: Decimal) -> BudgetDecision:
    rows = list(spends)
    month_spent = sum((r.cny for r in rows if r.month == month), Decimal(0))
    # A brief has no video yet. Charge its spend conservatively to every video;
    # another brief must also fit alongside all existing spend (across months).
    # This avoids a fresh daily key giving the eventual video an extra allowance.
    video_spent = sum(
        (
            r.cny
            for r in rows
            if (
                r.job_id in {job_id, "?"}
                if job_id.startswith("work:")
                else job_id.startswith("brief-")
                or r.job_id == job_id
                or r.job_id.startswith("brief-")
                or r.job_id == "?"
            )
        ),
        Decimal(0),
    )
    if month_spent + ceiling > MONTHLY_CAP_CNY:
        reason = f"本月 AI 已用约 ¥{month_spent:.2f}，本次最多 ¥{ceiling:.2f} 会超过每月 ¥{MONTHLY_CAP_CNY}"
    elif video_spent + ceiling > PER_VIDEO_CAP_CNY:
        reason = f"这条视频 AI 已用约 ¥{video_spent:.2f}，本次最多 ¥{ceiling:.2f} 会超过单条 ¥{PER_VIDEO_CAP_CNY}"
    else:
        reason = ""
    return BudgetDecision(not reason, ceiling, month_spent, video_spent, reason)
