import json
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from gamingcreator.application.pricing import (
    DEEPSEEK_FLASH_20261004,
    estimate_usage,
    pricing_period,
    reservation_cny,
)
from gamingcreator.application.providers import CostStatus, ProviderUsage


def test_exact_cached_uncached_and_output_tariff_estimates() -> None:
    usage = ProviderUsage(1000, 200, 300)
    offpeak = estimate_usage(usage, "DeepSeek-V4.1-Flash", "deepseek-flash", period="offpeak")
    peak = estimate_usage(usage, "deepseek-v4-flash-vision-exp", "deepseek-flash", period="peak")
    assert offpeak.original_cost == offpeak.cost_cny == Decimal("0.001506")
    assert peak.original_cost == peak.cost_cny == Decimal("0.003012")
    assert offpeak.currency == peak.currency == "CNY"
    assert offpeak.cost_status == peak.cost_status == CostStatus.ESTIMATED
    assert usage.original_cost is None  # Frozen inputs remain reusable.


@pytest.mark.parametrize(
    "usage,actual,requested",
    [
        (ProviderUsage(), "deepseek-flash", "deepseek-flash"),
        (ProviderUsage(100, 10), "deepseek-flash", "deepseek-flash"),
        (ProviderUsage(None, 10, 0), "deepseek-flash", "deepseek-flash"),
        (ProviderUsage(100, None, 0), "deepseek-flash", "deepseek-flash"),
        (ProviderUsage(100, 10, 0), None, "deepseek-flash"),
        (ProviderUsage(100, 10, 0), "future-flash", "deepseek-flash"),
        (ProviderUsage(100, 10, 0), "deepseek-flash", "deepseek-v4-pro"),
    ],
)
def test_unknown_price_inputs_preserve_unknown_cost(
    usage: ProviderUsage, actual: str | None, requested: str
) -> None:
    result = estimate_usage(usage, actual, requested, period="offpeak")
    assert result.input_tokens == usage.input_tokens
    assert result.cached_input_tokens == usage.cached_input_tokens
    assert result.cost_cny is result.original_cost is None
    assert result.currency is None
    assert result.cost_status == CostStatus.UNVERIFIED


def test_explicit_zero_usage_is_estimated_zero_and_bad_period_is_rejected() -> None:
    usage = ProviderUsage(0, 0, 0)
    assert estimate_usage(usage, "deepseek-flash", "deepseek-flash", period="peak").cost_cny == 0
    with pytest.raises(ValueError, match="period"):
        estimate_usage(usage, "deepseek-flash", "deepseek-flash", period="holiday")


def test_reservation_uses_peak_uncached_price_with_full_context_default() -> None:
    assert reservation_cny(1_000_000, 2048) == Decimal("2.016384")
    assert reservation_cny(1000, 100) == Decimal("0.0028")


@pytest.mark.parametrize("ceiling", [0, -1, True, 1.5, 1_000_001])
def test_invalid_input_and_output_ceilings_are_rejected(ceiling: int) -> None:
    with pytest.raises(ValueError, match="ceilings"):
        reservation_cny(ceiling, 100)
    with pytest.raises(ValueError, match="ceilings"):
        reservation_cny(100, ceiling)


@pytest.mark.parametrize(
    "timestamp,period,basis",
    [
        ("2026-10-04T03:00:00+00:00", "offpeak", "china_weekend"),
        ("2026-10-04T16:00:00+00:00", "offpeak", "outside_china_peak_hours"),
        ("2026-10-05T00:59:59+00:00", "offpeak", "outside_china_peak_hours"),
        ("2026-10-05T01:00:00+00:00", "peak", "weekday_peak_or_holiday_unknown_conservative"),
        ("2026-10-05T04:00:00+00:00", "offpeak", "outside_china_peak_hours"),
        ("2026-10-05T06:00:00+00:00", "peak", "weekday_peak_or_holiday_unknown_conservative"),
        ("2026-10-05T10:00:00+00:00", "offpeak", "outside_china_peak_hours"),
        ("2026-10-02T16:00:00+00:00", "offpeak", "china_weekend"),
    ],
)
def test_period_uses_china_local_weekday_and_half_open_peak_hours(
    timestamp: str, period: str, basis: str
) -> None:
    assert pricing_period(datetime.fromisoformat(timestamp)) == (period, basis)


def test_naive_timestamp_is_rejected_and_offset_does_not_change_period() -> None:
    with pytest.raises(ValueError, match="aware"):
        pricing_period(datetime(2026, 10, 5, 9))
    assert pricing_period(datetime(2026, 10, 5, 1, tzinfo=UTC)) == pricing_period(
        datetime.fromisoformat("2026-10-05T09:00:00+08:00")
    )


def test_frozen_snapshot_matches_dated_public_evidence_and_rejects_bad_rates() -> None:
    snapshot = DEEPSEEK_FLASH_20261004
    evidence = json.loads(
        (Path(__file__).resolve().parents[1] / "docs/references/deepseek-pricing.json").read_text(
            encoding="utf-8"
        )
    )
    assert evidence["version"] == snapshot.version
    assert evidence["sourceUrl"] == snapshot.source_url
    assert evidence["capturedDate"] == snapshot.captured_date == "2026-10-04"
    assert evidence["effectiveDate"] is snapshot.effective_date is None
    assert evidence["modelAliases"] == list(snapshot.model_aliases)
    assert evidence["contextLimitTokens"] == snapshot.context_limit_tokens
    assert (
        Decimal(evidence["rates"]["peak"]["uncachedInput"])
        == snapshot.peak_uncached_input_per_million
    )
    with pytest.raises(FrozenInstanceError):
        snapshot.currency = "USD"  # type: ignore[misc]
    with pytest.raises(ValueError, match="Tariffs"):
        replace(snapshot, peak_output_per_million=Decimal("NaN"))
