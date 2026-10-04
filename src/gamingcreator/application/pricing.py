"""Versioned public tariffs; computed amounts are estimates, never invoices."""

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

from gamingcreator.application.providers import CostStatus, ProviderUsage

_MILLION = Decimal(1_000_000)
_CHINA_TIME = timezone(timedelta(hours=8))


@dataclass(frozen=True, slots=True)
class PriceSnapshot:
    version: str
    source_url: str
    captured_date: str
    effective_date: str | None
    model_version: str
    model_aliases: tuple[str, ...]
    currency: str
    context_limit_tokens: int
    peak_cached_input_per_million: Decimal
    peak_uncached_input_per_million: Decimal
    peak_output_per_million: Decimal
    offpeak_cached_input_per_million: Decimal
    offpeak_uncached_input_per_million: Decimal
    offpeak_output_per_million: Decimal

    def __post_init__(self) -> None:
        if (
            not self.version
            or not self.source_url.startswith("https://")
            or not self.model_version
            or not self.model_aliases
            or any(not item for item in self.model_aliases)
            or self.currency != "CNY"
            or type(self.context_limit_tokens) is not int
            or self.context_limit_tokens <= 0
        ):
            raise ValueError("Invalid price snapshot identity or limits.")
        for rate in (
            self.peak_cached_input_per_million,
            self.peak_uncached_input_per_million,
            self.peak_output_per_million,
            self.offpeak_cached_input_per_million,
            self.offpeak_uncached_input_per_million,
            self.offpeak_output_per_million,
        ):
            if not isinstance(rate, Decimal) or not rate.is_finite() or rate < 0:
                raise ValueError("Tariffs must be finite, nonnegative Decimal amounts.")

    def estimate_usage(
        self,
        usage: ProviderUsage,
        actual_model: str | None,
        requested_model: str,
        *,
        period: str,
    ) -> ProviderUsage:
        if period not in ("peak", "offpeak"):
            raise ValueError("Unknown tariff period.")
        known = {alias.casefold() for alias in self.model_aliases}
        if (
            actual_model is None
            or actual_model.casefold() not in known
            or requested_model.casefold() not in known
            or usage.input_tokens is None
            or usage.output_tokens is None
            or usage.cached_input_tokens is None
        ):
            return replace(
                usage,
                original_cost=None,
                currency=None,
                cost_cny=None,
                cost_status=CostStatus.UNVERIFIED,
            )
        if period == "peak":
            cached_rate = self.peak_cached_input_per_million
            uncached_rate = self.peak_uncached_input_per_million
            output_rate = self.peak_output_per_million
        else:
            cached_rate = self.offpeak_cached_input_per_million
            uncached_rate = self.offpeak_uncached_input_per_million
            output_rate = self.offpeak_output_per_million
        amount = (
            Decimal(usage.cached_input_tokens) * cached_rate
            + Decimal(usage.input_tokens - usage.cached_input_tokens) * uncached_rate
            + Decimal(usage.output_tokens) * output_rate
        ) / _MILLION
        return replace(
            usage,
            original_cost=amount,
            currency=self.currency,
            cost_cny=amount,
            cost_status=CostStatus.ESTIMATED,
        )

    def reservation_cny(self, input_token_ceiling: int, max_output_tokens: int) -> Decimal:
        if any(
            type(value) is not int or not 1 <= value <= self.context_limit_tokens
            for value in (input_token_ceiling, max_output_tokens)
        ):
            raise ValueError("Token ceilings must be positive integers within the context limit.")
        # Include the requested output allowance even when the input ceiling fills context:
        # this intentionally over-reserves rather than relying on context truncation rules.
        return (
            Decimal(input_token_ceiling) * self.peak_uncached_input_per_million
            + Decimal(max_output_tokens) * self.peak_output_per_million
        ) / _MILLION


DEEPSEEK_FLASH_20261004 = PriceSnapshot(
    version="deepseek-flash-cny-2026-10-04",
    source_url="https://api-docs.deepseek.com/zh-cn/quick_start/pricing/",
    captured_date="2026-10-04",
    effective_date=None,  # The public page does not declare an effective date.
    model_version="DeepSeek-V4.1-Flash",
    model_aliases=(
        "deepseek-flash",
        "deepseek-v4-flash",
        "deepseek-v4-flash-vision-exp",
        "DeepSeek-V4.1-Flash",
    ),
    currency="CNY",
    context_limit_tokens=1_000_000,
    peak_cached_input_per_million=Decimal("0.04"),
    peak_uncached_input_per_million=Decimal("2"),
    peak_output_per_million=Decimal("8"),
    offpeak_cached_input_per_million=Decimal("0.02"),
    offpeak_uncached_input_per_million=Decimal("1"),
    offpeak_output_per_million=Decimal("4"),
)


def estimate_usage(
    usage: ProviderUsage,
    actual_model: str | None,
    requested_model: str,
    *,
    period: str,
) -> ProviderUsage:
    return DEEPSEEK_FLASH_20261004.estimate_usage(
        usage, actual_model, requested_model, period=period
    )


def reservation_cny(input_token_ceiling: int, max_output_tokens: int) -> Decimal:
    return DEEPSEEK_FLASH_20261004.reservation_cny(input_token_ceiling, max_output_tokens)


def pricing_period(requested_at: datetime) -> tuple[str, str]:
    """Return public tariff period and basis without assuming a holiday calendar."""
    if requested_at.tzinfo is None or requested_at.utcoffset() is None:
        raise ValueError("Tariff selection requires an aware request timestamp.")
    local = requested_at.astimezone(UTC).astimezone(_CHINA_TIME)
    if local.weekday() >= 5:
        return "offpeak", "china_weekend"
    if 9 <= local.hour < 12 or 14 <= local.hour < 18:
        return "peak", "weekday_peak_or_holiday_unknown_conservative"
    return "offpeak", "outside_china_peak_hours"
