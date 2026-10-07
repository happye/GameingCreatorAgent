"""Summarize immutable base-analysis attempts without reconciling any ledger."""

from collections.abc import Iterable
from decimal import Decimal

from gamingcreator.application.benchmark import BenchmarkCosts
from gamingcreator.application.providers import CostStatus
from gamingcreator.application.storage import StoredTimeline


def benchmark_analysis_costs(
    timelines: Iterable[StoredTimeline], *, all_runs_loaded: bool = True
) -> BenchmarkCosts:
    cold = Decimal(0)
    known = all_runs_loaded
    versions: set[str] = set()
    for timeline in timelines:
        for attempt in timeline.invocations:
            usage = attempt.metadata.usage
            if usage.cost_cny is None or usage.cost_status == CostStatus.UNVERIFIED:
                known = False
            else:
                cold += usage.cost_cny
            if attempt.metadata.provider == "deepseek" and attempt.metadata.price_version:
                versions.add(attempt.metadata.price_version)
            elif attempt.metadata.provider == "deepseek":
                known = False
    return BenchmarkCosts(
        cold if known else None,
        Decimal(0),
        "estimated" if known else "unverified",
        known,
        next(iter(versions)) if len(versions) == 1 else None,
    )
