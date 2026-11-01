"""Reclaim large generated media after fixtures finish, without creating fixtures."""

import importlib.util
import os
import shutil
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


def _reclaimable_basetemp(base: Path, cache: Path) -> bool:
    """Allow `.cache/pt-*` and `.cache/pytest-runs/<guid>/tmp`; never protected roots."""
    try:
        resolved = base.resolve()
        cache_resolved = cache.resolve()
        resolved.relative_to(cache_resolved)
    except (OSError, ValueError):
        return False
    if resolved == cache_resolved:
        return False
    protected = {name.casefold() for name in _maintenance.PROTECTED}
    # Direct child of .cache with a protected name (models, etc.)
    if resolved.parent == cache_resolved and resolved.name.casefold() in protected:
        return False
    # Top-level protected path anywhere in the chain
    for parent in resolved.parents:
        if parent == cache_resolved:
            break
        if parent.parent == cache_resolved and parent.name.casefold() in protected:
            return False
    return True


def pytest_sessionfinish(session, exitstatus):
    # A fully passing run keeps nothing: per-run basetemps otherwise pile up under .cache.
    if exitstatus != 0 or os.environ.get("GC_KEEP_TEST_MEDIA") == "1":
        return
    factory = getattr(session.config, "_tmp_path_factory", None)
    base = getattr(factory, "_basetemp", None)
    cache = Path(__file__).resolve().parents[1] / ".cache"
    try:
        if base is None or not _reclaimable_basetemp(base, cache):
            return
        for directory, names, files in os.walk(base):
            if any(_maintenance.linked(Path(directory, n)) for n in (*names, *files)):
                return
        shutil.rmtree(base)
        # verify.ps1 uses .cache/pytest-runs/<guid>/tmp — also drop the empty guid parent if safe.
        parent = base.resolve().parent
        runs_root = (cache / "pytest-runs").resolve()
        try:
            parent.relative_to(runs_root)
        except ValueError:
            return
        if parent != runs_root and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
    except OSError:
        pass
