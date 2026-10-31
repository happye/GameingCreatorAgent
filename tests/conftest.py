"""Reclaim large generated media after fixtures finish, without creating fixtures."""

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "cache_maintenance", Path(__file__).resolve().parents[1] / "scripts/cache-maintenance.py"
)
assert _spec and _spec.loader
_maintenance = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_maintenance)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.failed:
        item._media_test_failed = True


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_teardown(item, nextitem):
    root = item.funcargs.get("tmp_path")
    outcome = yield
    if root is None:
        return
    cache = Path(__file__).resolve().parents[1] / ".cache"
    try:
        base = item.config._tmp_path_factory.getbasetemp()
        _maintenance.reclaim(
            root,
            cache,
            failed=getattr(item, "_media_test_failed", False)
            or bool(getattr(outcome, "excinfo", None)),
            apply=True,
            fixture_base=base,
        )
    except (OSError, ValueError):
        # Cleanup cannot replace the original test outcome.
        pass
