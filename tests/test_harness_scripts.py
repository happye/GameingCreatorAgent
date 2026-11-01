"""Harness helpers: affected-test selection, status numbers, basetemp reclaim allow-list."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


affected = _load("affected_tests", ROOT / "scripts/affected_tests.py")
status = _load("status_script", ROOT / "scripts/status.py")
harness_conftest = _load("harness_conftest", ROOT / "tests/conftest.py")


def test_changed_test_file_selects_itself():
    tests, full, _ = affected.select(["tests/test_harness_scripts.py"])
    assert (tests, full) == (["tests/test_harness_scripts.py"], False)


def test_changed_module_selects_its_importers_only():
    tests, full, ui = affected.select(["src/gamingcreator/application/retrieval.py"])
    assert not full and not ui
    assert "tests/test_retrieval_action_aliases.py" in tests
    deep, _, _ = affected.select(["src/gamingcreator/application/retrieval.py"], deep=True)
    assert set(tests) < set(deep)


def test_config_change_selects_full_suite_and_docs_select_nothing():
    assert affected.select(["pyproject.toml"])[1] is True
    assert affected.select(["docs/references/testing-guide.md"]) == ([], False, False)


def test_unnamed_static_ui_file_selects_browser_tests():
    tests, _, ui = affected.select(["src/gamingcreator/ui/static/style.css"])
    assert ui and tests
    assert all("playwright" in (ROOT / t).read_text(encoding="utf-8") for t in tests)


def test_status_counts_match_sources():
    counts = status.feature_counts()
    data = json.loads((ROOT / "feature_list.json").read_text(encoding="utf-8"))
    assert counts["planned"] == len(data["product_features"])
    assert sum(status.tech_debt_counts().values()) > 0
    assert status.board_drift(counts) == []
    assert {j["id"] for j in status.journeys()} >= {"J1", "J2", "J3"}


@pytest.mark.parametrize(
    ("relative", "allowed"),
    [
        ("pytest-tmp-run", True),
        ("pt-run", True),
        ("pytest-runs/abc/tmp", True),
        ("pytest-runs", False),
        ("pytest-runs/abc", False),
        ("scratch", False),
        ("models", False),
        ("a/models/b", False),
        (".", False),
    ],
)
def test_reclaim_allow_list(tmp_path, relative, allowed):
    cache = tmp_path / ".cache"
    assert harness_conftest._reclaimable_basetemp(cache / relative, cache) is allowed
