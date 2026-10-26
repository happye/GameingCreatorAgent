"""Within one project, paid analysis stops when the same bytes already ran with the same settings."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from test_sqlite_store import CONFIG, bundle_fixture

from gamingcreator.application.analysis import _run_configuration, planned_identity
from gamingcreator.application.analysis_reuse import (
    ReuseMatch,
    analysis_identity,
    find_matches,
    paid_calls,
    refuse_duplicate_analysis,
    refuse_resuming_duplicate,
    reuse_report,
    stored_identity,
)
from gamingcreator.application.inputs import PreparedAnalyze
from gamingcreator.application.storage import RunStatus
from gamingcreator.cli import main as cli
from gamingcreator.cli.main import main
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.local_files import LocalInputReader
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore

ROOT = Path(__file__).resolve().parents[1]
BASE_CONFIG = ROOT / "config.example.json"
OTHER_CONFIG = ROOT / "config.temporal.example.json"
SETTINGS = LocalInputReader().load_config(BASE_CONFIG)
STAGES = ("media", "asr", "vision")


def test_identity_ignores_spending_caps_and_budget_but_not_output_settings():
    base = analysis_identity(SETTINGS, "a" * 64, STAGES)
    capped = replace(SETTINGS, max_requests=1, max_input_frames=5)
    assert analysis_identity(capped, "a" * 64, STAGES) == base
    for changed in (
        replace(SETTINGS, vision_prompt_version="phase0-vision-v5"),
        replace(SETTINGS, sampling_interval_ms=500),
        replace(SETTINGS, window_frames=4),
        replace(SETTINGS, model="other-model"),
        replace(SETTINGS, asr_language="en"),
    ):
        assert analysis_identity(changed, "a" * 64, STAGES) != base
    assert analysis_identity(SETTINGS, "b" * 64, STAGES) != base
    assert analysis_identity(SETTINGS, "a" * 64, ("media", "vision")) != base
    assert stored_identity(replace(CONFIG, max_cost_cny=Decimal("99"))) == stored_identity(CONFIG)
    # The first prompt was stored without a pinned hash; a pinned copy is the same prompt.
    legacy = replace(SETTINGS, vision_prompt_version="phase0-vision-v1", vision_prompt_hash=None)
    pinned = replace(legacy, vision_prompt_hash="c" * 64)
    assert analysis_identity(legacy, "a" * 64, STAGES) == analysis_identity(
        pinned, "a" * 64, STAGES
    )


VIDEO = Path("C:/footage/same.mp4")


def match(run_id, status, same=True, **changes):
    return ReuseMatch(run_id, status, same, VIDEO.resolve(), **changes)


@pytest.mark.parametrize(
    "matches,code,run_id,phrase",
    [
        ((), None, None, None),
        ((match("x", RunStatus.COMPLETED, False),), None, None, None),
        (
            (match("p", RunStatus.PENDING, resumable=True),),
            "analysis.already_started",
            "p",
            "--resume p",
        ),
        (
            (match("i", RunStatus.INTERRUPTED, resumable=True),),
            "analysis.already_started",
            "i",
            "--resume i",
        ),
        (
            (
                ReuseMatch(
                    "m", RunStatus.PENDING, True, Path("D:/elsewhere/same.mp4"), resumable=True
                ),
            ),
            "analysis.already_started",
            "m",
            "另一路径",
        ),
        (
            (match("g", RunStatus.FAILED, blockers=("coverage_gap",), model_calls=270),),
            "analysis.existing_unfinished",
            "g",
            "覆盖缺口",
        ),
        (
            (match("b", RunStatus.FAILED, blockers=("budget_exhausted",), model_calls=3),),
            "analysis.existing_unfinished",
            "b",
            "费用上限已用完",
        ),
        (
            (match("p", RunStatus.INTERRUPTED, resumable=True), match("c", RunStatus.COMPLETED)),
            "analysis.already_completed",
            "c",
            "直接检索",
        ),
        # A paid but blocked run outranks a free resumable duplicate: no circular advice.
        (
            (
                match("a-paid", RunStatus.FAILED, blockers=("coverage_gap",), model_calls=9),
                match("b-free", RunStatus.PENDING, resumable=True),
            ),
            "analysis.existing_unfinished",
            "a-paid",
            "覆盖缺口",
        ),
        # Nothing was ever paid and nothing can resume (caps too small): a new run may start.
        ((match("small", RunStatus.PENDING, blockers=("coverage_limit",)),), None, None, None),
    ],
)
def test_refusal_names_the_right_next_step(matches, code, run_id, phrase):
    report = reuse_report("same.mp4", "1" * 64, VIDEO, matches)
    assert report["readOnly"] is True and report["paidRequests"] == 0
    if code is None:
        refuse_duplicate_analysis(matches, VIDEO)
        assert report["wouldStop"] is False
        return
    with pytest.raises(AppError) as refused:
        refuse_duplicate_analysis(matches, VIDEO)
    assert refused.value.code == code and refused.value.run_id == run_id
    assert phrase in refused.value.message and "--allow-reanalysis" in refused.value.message
    if code != "analysis.already_started":
        assert "--resume" not in refused.value.message
    assert report["wouldStop"] is True and report["code"] == code


def test_resuming_a_fresh_duplicate_stops_only_when_another_run_already_paid():
    fresh = match("other", RunStatus.PENDING)
    refuse_resuming_duplicate((fresh,), "mine")
    refuse_resuming_duplicate((match("x", RunStatus.COMPLETED, False),), "mine")
    for paid in (
        match("done", RunStatus.COMPLETED),
        match("half", RunStatus.FAILED, model_calls=3),
    ):
        with pytest.raises(AppError) as refused:
            refuse_resuming_duplicate((fresh, paid), "mine")
        assert refused.value.code == "analysis.duplicate_of_existing"
        assert paid.run_id in refused.value.message and refused.value.run_id == "mine"


class Reached(Exception):
    """Raised where a run would start setting up paid providers."""


def seed(tmp_path, monkeypatch, *, runs):
    """Runs of the fixture video with the example settings: (run id, status)."""
    project = tmp_path / "project"
    asset = bundle_fixture(tmp_path).asset
    prepared = PreparedAnalyze(asset.source_path, project, SETTINGS, Decimal("2"), None)

    async def create():
        store = await SqliteTimelineStore.open(project)
        try:
            for run_id, _ in runs:
                await store.create_run(run_id, asset, _run_configuration(prepared))
        finally:
            await store.close()

    asyncio.run(create())
    # Only the stored status matters to the guard; a real completion needs every stage.
    with closing(sqlite3.connect(project / "timeline.sqlite3")) as database, database:
        for run_id, status in runs:
            database.execute(
                "UPDATE analysis_runs SET status = ? WHERE run_id = ?", (str(status), run_id)
            )

    class Probe:
        def __init__(self, repository):
            pass

        async def probe(self, video, context):
            return asset

    def reached(repository):
        raise Reached

    monkeypatch.setattr("gamingcreator.cli.main.FfmpegMediaProcessor", Probe)
    monkeypatch.setattr("gamingcreator.cli.main._pinned_asr_settings", reached)
    return project, asset


def run_ids(project):
    async def load():
        store = await SqliteTimelineStore.open(project, read_only=True)
        try:
            return [row[0] for row in await store.list_runs()]
        finally:
            await store.close()

    return asyncio.run(load())


def analyze(asset, project, *extra, config=BASE_CONFIG):
    return main(
        [
            "analyze",
            str(asset.source_path),
            "--project",
            str(project),
            "--config",
            str(config),
            "--max-cost-cny",
            "3",
            *extra,
        ]
    )


@pytest.mark.parametrize(
    "status,code",
    [
        (RunStatus.COMPLETED, "analysis.already_completed"),
        (RunStatus.PENDING, "analysis.already_started"),
    ],
)
def test_new_analysis_stops_before_any_provider_when_the_same_run_exists(
    tmp_path, monkeypatch, capsys, status, code
):
    project, asset = seed(tmp_path, monkeypatch, runs=[("seen-run", status)])
    capsys.readouterr()
    assert analyze(asset, project) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["code"] == code and error["runId"] == "seen-run"
    assert run_ids(project) == ["seen-run"]
    # The explicit flag, or different output settings, reach provider setup.
    with pytest.raises(Reached):
        asyncio.run(
            cli.execute_analyze(
                PreparedAnalyze(asset.source_path, project, SETTINGS, Decimal("3"), None),
                Path.cwd(),
                allow_reanalysis=True,
            )
        )
    other = LocalInputReader().load_config(OTHER_CONFIG)
    assert planned_identity(other) != planned_identity(SETTINGS)
    with pytest.raises(Reached):
        asyncio.run(
            cli.execute_analyze(
                PreparedAnalyze(asset.source_path, project, other, Decimal("3"), None),
                Path.cwd(),
            )
        )


def test_resuming_a_freely_prepared_duplicate_stops_before_any_provider(
    tmp_path, monkeypatch, capsys
):
    project, asset = seed(
        tmp_path,
        monkeypatch,
        runs=[("paid-run", RunStatus.COMPLETED), ("prepared-run", RunStatus.PENDING)],
    )
    capsys.readouterr()
    resume = ["analyze", str(asset.source_path), "--project", str(project), "--resume"]
    assert main([*resume, "prepared-run"]) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["code"] == "analysis.duplicate_of_existing" and "paid-run" in error["message"]
    prepared = PreparedAnalyze(asset.source_path, project, None, None, "prepared-run")
    with pytest.raises(Reached):
        asyncio.run(cli.execute_analyze(prepared, Path.cwd(), allow_reanalysis=True))


def test_only_remote_model_calls_count_as_paid():
    def call(provider):
        return type("Call", (), {"metadata": type("Meta", (), {"provider": provider})()})()

    assert paid_calls([call("deepseek"), call("local-asr"), call("deepseek")]) == 2
    assert paid_calls([call("local-asr")]) == 0


def test_find_matches_reports_continuation_and_names_an_unreadable_run(tmp_path, monkeypatch):
    project, asset = seed(tmp_path, monkeypatch, runs=[("a-run", RunStatus.PENDING)])
    wanted = planned_identity(SETTINGS)

    async def matches():
        store = await SqliteTimelineStore.open(project, read_only=True)
        try:
            return await find_matches(store, asset.sha256, wanted)
        finally:
            await store.close()

    (found,) = asyncio.run(matches())
    assert found.run_id == "a-run" and found.same_settings and found.model_calls == 0
    assert found.source_path == asset.source_path
    # A run stopped by its saved budget would stop again on resume.
    with closing(sqlite3.connect(project / "timeline.sqlite3")) as database, database:
        database.execute(
            "UPDATE analysis_runs SET status = 'failed', error_code = 'budget.exhausted'"
        )
    (spent,) = asyncio.run(matches())
    assert "budget_exhausted" in spent.blockers and spent.resumable is False
    with closing(sqlite3.connect(project / "timeline.sqlite3")) as database, database:
        database.execute("UPDATE analysis_runs SET config_hash = ?", ("0" * 64,))
    with pytest.raises(AppError) as unreadable:
        asyncio.run(matches())
    assert unreadable.value.run_id == "a-run" and "--allow-reanalysis" in unreadable.value.message


def test_check_command_is_read_only_and_matches_analyze(tmp_path, monkeypatch, capsys):
    project, asset = seed(tmp_path, monkeypatch, runs=[("seen-run", RunStatus.COMPLETED)])
    before = (project / "timeline.sqlite3").read_bytes()
    args = ["check-analysis-reuse", str(asset.source_path), "--project", str(project)]
    capsys.readouterr()
    assert main([*args, "--config", str(BASE_CONFIG)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["wouldStop"] is True and report["code"] == "analysis.already_completed"
    assert report["sameSettings"][0]["runId"] == "seen-run" and report["paidRequests"] == 0
    assert main([*args, "--config", str(OTHER_CONFIG)]) == 0
    assert json.loads(capsys.readouterr().out)["wouldStop"] is False
    assert (project / "timeline.sqlite3").read_bytes() == before
    # A missing project is not created.
    missing = tmp_path / "no-project"
    assert main([*args[:2], "--project", str(missing), "--config", str(BASE_CONFIG)]) == 0
    assert json.loads(capsys.readouterr().out)["wouldStop"] is False and not missing.exists()

    # A project that needs a writer's migration gets an honest "unknown", not a crash.
    def migrate(*args, **kwargs):
        raise AppError("storage.migration_required", "需要升级", ExitCode.STORAGE)

    monkeypatch.setattr("gamingcreator.cli.main.SqliteTimelineStore.open", migrate)
    assert main([*args, "--config", str(BASE_CONFIG)]) == 0
    unknown = json.loads(capsys.readouterr().out)
    assert unknown["wouldStop"] is None and unknown["code"] == "storage.migration_required"
    monkeypatch.undo()
    # Configurations analyze would refuse are refused here too.
    bad = tmp_path / "bad.json"
    document = json.loads(BASE_CONFIG.read_text(encoding="utf-8"))
    document["vision"]["promptHash"] = "0" * 64
    bad.write_text(json.dumps(document), encoding="utf-8")
    assert main([*args, "--config", str(bad)]) == 3  # same configuration error as analyze


def test_planned_identity_matches_what_a_new_run_stores(tmp_path):
    prepared = PreparedAnalyze(tmp_path / "v.mp4", tmp_path, SETTINGS, Decimal("5"), None)
    assert planned_identity(SETTINGS) == stored_identity(_run_configuration(prepared))
