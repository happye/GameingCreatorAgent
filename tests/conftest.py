"""Reclaim large generated media after fixtures finish, without creating fixtures."""

import importlib.util
import os
import re
import shutil
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "cache_maintenance", Path(__file__).resolve().parents[1] / "scripts/cache-maintenance.py"
)
assert _spec and _spec.loader
_maintenance = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_maintenance)


# Marker -> pattern over the test module's source.
_AUTO_MARKS = (
    ("browser", re.compile(r"^\s*(?:from|import) playwright|importorskip\(\s*.playwright", re.M)),
    # Real local data lives in dated artifacts/ folders or GameVideos/; "artifacts/project" is a tmp id.
    ("local_data", re.compile(r"artifacts/[\w-]*20\d{6}|GameVideos")),
    ("ffmpeg", re.compile(r"ffmpeg|ffprobe", re.I)),
)
_module_marks: dict[Path, tuple[str, ...]] = {}


def _marks_for(path: Path) -> tuple[str, ...]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ()
    return tuple(name for name, pattern in _AUTO_MARKS if pattern.search(text))


def pytest_collection_modifyitems(config, items):
    # Tier filters (testing-guide.md) come from what a test module touches, so nobody tags by hand.
    for item in items:
        path = Path(str(item.fspath))
        if path not in _module_marks:
            _module_marks[path] = _marks_for(path)
        for name in _module_marks[path]:
            item.add_marker(name)


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
    # Allow-list only: the pyproject default and verify.ps1's per-run tmp.
    name = resolved.name.casefold()
    if resolved.parent == cache_resolved:
        return name == "pytest-tmp-run" or name.startswith("pt-")
    runs_root = cache_resolved / "pytest-runs"
    return name == "tmp" and resolved.parent.parent == runs_root


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
