"""C01: read existing OCR reports with schema and digest checks; never rescan or write."""

from __future__ import annotations

import json
from pathlib import Path

from gamingcreator.application.ocr_frames import OCR_REPORT_VERSION
from gamingcreator.application.screen_text_reports import (
    BoundScreenTextFrame,
    ScreenTextLine,
    ScreenTextSource,
    accept_report_identity,
    attach_screen_text_group,
    bind_report_frames,
    check_frames_digest,
    collect_screen_text_group,
    match_screen_text,
    read_screen_text_report,
    screen_text_key,
    screen_text_matches,
    unique_screen_text_hits,
)
from gamingcreator.ui.frame_text import FRAME_TEXT_VERSION, frames_digest, scanned_frames


def _sha(prefix: str) -> str:
    return (prefix * 64)[:64]


def _snapshot(path: Path) -> tuple[bytes, int]:
    return path.read_bytes(), path.stat().st_mtime_ns


def _frame_text_report(saved, every=1, **overrides):
    chosen = scanned_frames(saved, every)
    document = {
        "schemaVersion": FRAME_TEXT_VERSION,
        "ocrSchemaVersion": OCR_REPORT_VERSION,
        "runId": "run-1",
        "sourceSha256": _sha("a"),
        "durationUs": 1_000_000,
        "density": "full" if every == 1 else "quick",
        "every": every,
        "framesDigest": frames_digest(chosen),
        "engine": {"name": "windows-ocr", "platform": "windows"},
        "frames": [
            {
                "timeUs": time_us,
                "lines": [{"text": "开始游戏", "likelyText": True}],
            }
            for _, time_us in chosen
        ],
        "readOnly": True,
        "paidRequests": 0,
        "humanReviewed": False,
    }
    document.update(overrides)
    return document


def _official_report(saved, **overrides):
    document = {
        "schemaVersion": OCR_REPORT_VERSION,
        "runId": "run-1",
        "sourceSha256": _sha("a"),
        "durationUs": 1_000_000,
        "every": 1,
        "frames": [
            {
                "evidenceId": evidence,
                "timeUs": time_us,
                "status": "text",
                "lines": [{"text": "开始游戏", "likelyText": True}],
            }
            for evidence, time_us in saved
        ],
        "readOnly": True,
        "paidRequests": 0,
        "humanReviewed": False,
    }
    document.update(overrides)
    return document


def test_reads_frame_text_and_official_reports_without_writing(tmp_path):
    saved = (("ev-1", 0), ("ev-2", 1_000_000))
    cache = tmp_path / "frame-text.json"
    official = tmp_path / "ocr-frames.json"
    cache.write_text(json.dumps(_frame_text_report(saved), ensure_ascii=False), encoding="utf-8")
    official.write_text(json.dumps(_official_report(saved), ensure_ascii=False), encoding="utf-8")
    before_cache, before_official = _snapshot(cache), _snapshot(official)
    names_before = sorted(path.name for path in tmp_path.iterdir())

    cached = read_screen_text_report(cache)
    full = read_screen_text_report(official)

    assert cached.ok and cached.report is not None
    assert cached.reason == ""
    assert cached.report.schema_version == FRAME_TEXT_VERSION
    assert cached.report.run_id == "run-1"
    assert cached.report.source_sha256 == _sha("a")
    assert cached.report.frames[0].lines[0].text == "开始游戏"
    assert cached.report.frames[0].evidence_id is None
    assert check_frames_digest(cached.report, saved).ok

    assert full.ok and full.report is not None
    assert full.report.schema_version == OCR_REPORT_VERSION
    assert full.report.frames[1].evidence_id == "ev-2"
    assert full.report.frames[1].time_us == 1_000_000
    assert check_frames_digest(full.report, saved).ok

    assert _snapshot(cache) == before_cache
    assert _snapshot(official) == before_official
    assert sorted(path.name for path in tmp_path.iterdir()) == names_before
    assert not (tmp_path / "timeline.sqlite3").exists()


def test_bad_reports_are_failures_not_empty_success_and_are_left_alone(tmp_path):
    saved = (("ev-1", 0), ("ev-2", 2_000_000))
    missing = read_screen_text_report(tmp_path / "absent.json")
    assert missing.ok is False and missing.report is None
    assert missing.reason == "找不到这份屏幕文字报告。"

    broken = tmp_path / "broken.json"
    broken.write_text("not json", encoding="utf-8")
    before = _snapshot(broken)
    bad_json = read_screen_text_report(broken)
    assert bad_json.ok is False and bad_json.report is None
    assert bad_json.reason == "报告不是合法的 JSON。"
    assert _snapshot(broken) == before

    unsupported = tmp_path / "old.json"
    unsupported.write_text(json.dumps({"schemaVersion": "ocr-v0", "frames": []}), encoding="utf-8")
    before = _snapshot(unsupported)
    bad_schema = read_screen_text_report(unsupported)
    assert bad_schema.ok is False and bad_schema.report is None
    assert bad_schema.reason == "报告的 schema 不受支持。"
    assert "\\" not in bad_schema.reason and "/" not in bad_schema.reason
    assert _snapshot(unsupported) == before

    stale = tmp_path / "stale.json"
    document = _frame_text_report(saved)
    document["framesDigest"] = "0" * 64
    stale.write_text(json.dumps(document), encoding="utf-8")
    before = _snapshot(stale)
    parsed = read_screen_text_report(stale)
    assert parsed.ok and parsed.report is not None
    checked = check_frames_digest(parsed.report, saved)
    assert checked.ok is False and checked.report is None
    assert checked.reason == "报告里的画面指纹与当前已保存帧对不上。"
    assert _snapshot(stale) == before


def test_official_report_digest_rejects_unknown_saved_frames(tmp_path):
    saved = (("ev-1", 0), ("ev-2", 1_000_000))
    path = tmp_path / "ocr.json"
    path.write_text(
        json.dumps(_official_report((("ev-1", 0), ("ev-ghost", 9_000_000)))),
        encoding="utf-8",
    )
    before = _snapshot(path)
    parsed = read_screen_text_report(path)
    assert parsed.ok and parsed.report is not None
    checked = check_frames_digest(parsed.report, saved)
    assert checked.ok is False and checked.report is None
    assert checked.reason == "报告里的画面指纹与当前已保存帧对不上。"
    assert _snapshot(path) == before


def _source(run_id="run-1", sha=None, duration=1_000_000):
    return ScreenTextSource(run_id, sha or _sha("a"), duration)


def test_identity_keeps_in_scope_reports_and_drops_stale_or_foreign_ones(tmp_path):
    saved = (("ev-1", 0),)
    in_scope = tmp_path / "in-scope.json"
    stale = tmp_path / "stale-hash.json"
    foreign = tmp_path / "other-run.json"
    in_scope.write_text(json.dumps(_frame_text_report(saved)), encoding="utf-8")
    stale_doc = _frame_text_report(saved, sourceSha256=_sha("b"))
    # keep a valid digest for schema parse; identity must still reject the stale hash
    stale.write_text(json.dumps(stale_doc), encoding="utf-8")
    other = _frame_text_report(saved, runId="run-2")
    foreign.write_text(json.dumps(other), encoding="utf-8")
    before = {path: _snapshot(path) for path in (in_scope, stale, foreign)}
    sources = (_source("run-1"), _source("run-3", _sha("c")))

    kept = accept_report_identity(
        read_screen_text_report(in_scope), sources, query_run_ids=("run-1", "run-3")
    )
    assert kept.ok and kept.report is not None
    assert kept.report.run_id == "run-1"
    assert kept.report.source_sha256 == _sha("a")

    dropped = accept_report_identity(
        read_screen_text_report(stale), sources, query_run_ids=("run-1",)
    )
    assert dropped.ok is False and dropped.report is None
    assert "原片哈希" in dropped.reason
    assert "已排除" in dropped.reason

    out_of_query = accept_report_identity(
        read_screen_text_report(foreign),
        sources + (_source("run-2", _sha("a")),),
        query_run_ids=("run-1",),
    )
    assert out_of_query.ok is False and out_of_query.report is None
    assert out_of_query.reason == "这份报告不属于本次查询范围。"

    unknown_run = accept_report_identity(
        read_screen_text_report(foreign), sources, query_run_ids=("run-2",)
    )
    assert unknown_run.ok is False and unknown_run.report is None
    assert unknown_run.reason == "这份报告不属于本次查询范围。"

    duration = accept_report_identity(
        read_screen_text_report(in_scope),
        (_source(duration=9_000_000),),
        query_run_ids=("run-1",),
    )
    assert duration.ok is False and duration.report is None
    assert "原片身份" in duration.reason

    prior = read_screen_text_report(tmp_path / "missing.json")
    carried = accept_report_identity(prior, sources, query_run_ids=("run-1",))
    assert carried.ok is False and carried.report is None
    assert carried.reason == "找不到这份屏幕文字报告。"

    for path, snap in before.items():
        assert _snapshot(path) == snap


def test_bind_uses_real_saved_frames_and_skips_ambiguous_or_unknown_times(tmp_path):
    saved = (("ev-1", 0), ("ev-2", 1_000_000), ("ev-3", 2_000_000), ("ev-4", 2_000_000))
    cache = tmp_path / "cache.json"
    document = _frame_text_report((("ev-1", 0), ("ev-2", 1_000_000)))
    document["frames"] = [
        {"timeUs": 0, "lines": [{"text": "开始", "likelyText": True}]},
        {"timeUs": 1_000_000, "lines": [{"text": "设置", "likelyText": True}]},
        {"timeUs": 2_000_000, "lines": [{"text": "歧义时刻", "likelyText": True}]},
        {"timeUs": 9_000_000, "lines": [{"text": "没有这帧", "likelyText": True}]},
    ]
    cache.write_text(json.dumps(document), encoding="utf-8")
    before = _snapshot(cache)
    parsed = read_screen_text_report(cache)
    assert parsed.ok and parsed.report is not None
    bound = bind_report_frames(parsed.report, saved)
    assert [(item.evidence_id, item.time_us, item.lines[0].text) for item in bound] == [
        ("ev-1", 0, "开始"),
        ("ev-2", 1_000_000, "设置"),
    ]
    assert all(item.run_id == "run-1" and item.source_sha256 == _sha("a") for item in bound)
    assert _snapshot(cache) == before


def test_bind_keeps_official_evidence_and_drops_mismatched_ids(tmp_path):
    saved = (("ev-1", 0), ("ev-2", 1_000_000))
    path = tmp_path / "ocr.json"
    document = _official_report(saved)
    document["frames"].append(
        {
            "evidenceId": "invented-ev",
            "timeUs": 0,
            "status": "text",
            "lines": [{"text": "伪造", "likelyText": True}],
        }
    )
    document["frames"].append(
        {
            "evidenceId": "ev-2",
            "timeUs": 0,
            "status": "text",
            "lines": [{"text": "时刻对不上", "likelyText": True}],
        }
    )
    path.write_text(json.dumps(document), encoding="utf-8")
    parsed = read_screen_text_report(path)
    assert parsed.ok and parsed.report is not None
    bound = bind_report_frames(parsed.report, saved)
    assert [(item.evidence_id, item.time_us, item.lines[0].text) for item in bound] == [
        ("ev-1", 0, "开始游戏"),
        ("ev-2", 1_000_000, "开始游戏"),
    ]
    assert all(not item.evidence_id.startswith("invented") for item in bound)


def _bound(text, time_us=0, evidence="ev-1"):
    return BoundScreenTextFrame(
        run_id="run-1",
        source_sha256=_sha("a"),
        evidence_id=evidence,
        time_us=time_us,
        lines=(ScreenTextLine(text, True),),
    )


def test_literal_match_uses_nfkc_casefold_but_returns_original_text():
    ligature = _bound("ﬃ开始游戏")
    fullwidth = _bound("进入ＡＢＣ设置", time_us=1_000_000, evidence="ev-2")
    upper = _bound("READY", time_us=2_000_000, evidence="ev-3")
    composed = _bound("CAFÉ", time_us=3_000_000, evidence="ev-4")
    unrelated = _bound("返回标题", time_us=4_000_000, evidence="ev-5")
    frames = (ligature, fullwidth, upper, composed, unrelated)

    ffi_hits = match_screen_text(frames, "FFI")
    assert [hit.text for hit in ffi_hits] == ["ﬃ开始游戏"]
    assert ffi_hits[0].text == ligature.lines[0].text
    # Normalized "ffi" is three characters; slicing the original with those indexes
    # would break the ligature. The hit must keep the whole original line.
    assert ffi_hits[0].text != screen_text_key("ﬃ开始游戏")[:3]
    assert "ﬃ" in ffi_hits[0].text

    abc_hits = match_screen_text(frames, "abc")
    assert [hit.text for hit in abc_hits] == ["进入ＡＢＣ设置"]
    assert "ＡＢＣ" in abc_hits[0].text

    case_hits = match_screen_text(frames, "ready")
    assert [hit.text for hit in case_hits] == ["READY"]

    accent_hits = match_screen_text(frames, "café")
    assert [hit.text for hit in accent_hits] == ["CAFÉ"]

    chinese_hits = match_screen_text(frames, "开始")
    assert [hit.text for hit in chinese_hits] == ["ﬃ开始游戏"]

    assert match_screen_text(frames, "   ") == ()
    assert match_screen_text(frames, "") == ()
    assert match_screen_text(frames, "没有这句") == ()


def test_same_run_evidence_and_text_are_deduped_but_other_identities_stay():
    first = BoundScreenTextFrame(
        run_id="run-1",
        source_sha256=_sha("a"),
        evidence_id="ev-1",
        time_us=0,
        lines=(
            ScreenTextLine("开始游戏", True),
            ScreenTextLine("设置", True),
            ScreenTextLine("开始游戏", True),
        ),
    )
    same_evidence = BoundScreenTextFrame(
        run_id="run-1",
        source_sha256=_sha("a"),
        evidence_id="ev-1",
        time_us=0,
        lines=(ScreenTextLine("开始游戏", True),),
    )
    other_evidence = BoundScreenTextFrame(
        run_id="run-1",
        source_sha256=_sha("a"),
        evidence_id="ev-2",
        time_us=1_000_000,
        lines=(ScreenTextLine("开始游戏", True),),
    )
    other_run = BoundScreenTextFrame(
        run_id="run-2",
        source_sha256=_sha("b"),
        evidence_id="ev-1",
        time_us=0,
        lines=(ScreenTextLine("开始游戏", True),),
    )
    hits = match_screen_text((first, same_evidence, other_evidence, other_run), "开始游戏")
    assert [(hit.frame.run_id, hit.frame.evidence_id, hit.text) for hit in hits] == [
        ("run-1", "ev-1", "开始游戏"),
        ("run-1", "ev-2", "开始游戏"),
        ("run-2", "ev-1", "开始游戏"),
    ]
    # 同刻不同原文仍各算一行；「设置」不应被「开始游戏」吞掉。
    setting = match_screen_text((first,), "设置")
    assert [hit.text for hit in setting] == ["设置"]
    assert unique_screen_text_hits(setting) == setting


def test_matches_follow_query_run_time_and_line_order_and_stop_at_ten():
    late_first = _bound("晚到的前面素材", time_us=5_000_000, evidence="ev-late")
    late_first = BoundScreenTextFrame(
        run_id="run-1",
        source_sha256=_sha("a"),
        evidence_id="ev-late",
        time_us=5_000_000,
        lines=(ScreenTextLine("晚到的前面素材", True),),
    )
    earlier = BoundScreenTextFrame(
        run_id="run-1",
        source_sha256=_sha("a"),
        evidence_id="ev-early",
        time_us=1_000_000,
        lines=(ScreenTextLine("较早时刻", True),),
    )
    same_instant = BoundScreenTextFrame(
        run_id="run-2",
        source_sha256=_sha("b"),
        evidence_id="ev-2",
        time_us=2_000_000,
        lines=(ScreenTextLine("第二行", True), ScreenTextLine("第一行", True)),
    )
    # Intentionally hand the later run and later time first; output must not follow this input order.
    hits = (
        match_screen_text((late_first, earlier, same_instant), "行")
        + match_screen_text((late_first, earlier, same_instant), "时刻")
        + match_screen_text((late_first, earlier, same_instant), "素材")
    )
    rows = screen_text_matches(hits, query_run_ids=("run-2", "run-1"))
    assert [(row["runId"], row["timeUs"], row["text"]) for row in rows] == [
        ("run-2", 2_000_000, "第二行"),
        ("run-2", 2_000_000, "第一行"),
        ("run-1", 1_000_000, "较早时刻"),
        ("run-1", 5_000_000, "晚到的前面素材"),
    ]
    assert set(rows[0]) == {"runId", "sourceSha256", "evidenceId", "timeUs", "text"}
    assert rows[0]["sourceSha256"] == _sha("b") and rows[0]["evidenceId"] == "ev-2"

    overflow = []
    for index in range(12):
        overflow.append(
            BoundScreenTextFrame(
                run_id="run-1",
                source_sha256=_sha("a"),
                evidence_id=f"ev-{index}",
                time_us=index * 1_000,
                lines=(ScreenTextLine(f"第{index}条设置", True),),
            )
        )
    limited = screen_text_matches(
        match_screen_text(tuple(overflow), "设置"), query_run_ids=("run-1",)
    )
    assert len(limited) == 10
    assert [row["text"] for row in limited] == [f"第{index}条设置" for index in range(10)]
    again = screen_text_matches(
        match_screen_text(tuple(overflow), "设置"), query_run_ids=("run-1",)
    )
    assert again == limited


def test_missing_reports_return_empty_group_and_leave_original_search_alone(tmp_path, monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("missing reports must not start a new OCR task")

    monkeypatch.setattr("gamingcreator.cli.ocr_frames.build_run_ocr_report", boom)
    monkeypatch.setattr("gamingcreator.ui.frame_text.scan_frame_text_payload", boom)
    names_before = sorted(path.name for path in tmp_path.iterdir())
    sources = (_source("run-1"),)
    group = collect_screen_text_group(
        query="开始",
        query_run_ids=("run-1",),
        sources=sources,
        reports=(None, tmp_path / "absent.json"),
        saved_by_run={"run-1": (("ev-1", 0),)},
    )
    assert group["screenTextMatches"] == ()
    assert group["screenTextPrepared"] is False
    assert group["screenTextNotice"] == "尚未准备屏幕文字，未开始新的识别任务。"
    original = {
        "candidates": ({"id": "clip-1", "score": 0.91},),
        "top10": ({"id": "clip-1", "score": 0.91},),
    }
    attached = attach_screen_text_group(original, group)
    assert attached["candidates"] == original["candidates"]
    assert attached["top10"] == original["top10"]
    assert attached["screenTextMatches"] == ()
    assert attached["screenTextPrepared"] is False
    assert original == {
        "candidates": ({"id": "clip-1", "score": 0.91},),
        "top10": ({"id": "clip-1", "score": 0.91},),
    }
    assert sorted(path.name for path in tmp_path.iterdir()) == names_before
    assert not (tmp_path / "timeline.sqlite3").exists()


def test_one_bad_report_does_not_drop_other_sources(tmp_path):
    saved = (("ev-1", 0),)
    valid = tmp_path / "valid.json"
    broken = tmp_path / "broken.json"
    stale = tmp_path / "stale.json"
    valid.write_text(json.dumps(_frame_text_report(saved), ensure_ascii=False), encoding="utf-8")
    broken.write_text("not json", encoding="utf-8")
    stale_doc = _frame_text_report(saved, sourceSha256=_sha("b"))
    stale.write_text(json.dumps(stale_doc), encoding="utf-8")
    before = {path: _snapshot(path) for path in (valid, broken, stale)}
    sources = (_source("run-1"),)
    group = collect_screen_text_group(
        query="开始游戏",
        query_run_ids=("run-1",),
        sources=sources,
        reports=(broken, valid, stale),
        saved_by_run={"run-1": saved},
    )
    assert [row["text"] for row in group["screenTextMatches"]] == ["开始游戏"]
    assert group["screenTextPrepared"] is True
    assert "报告不是合法的 JSON。" in group["screenTextDiagnostics"]
    assert any("原片哈希" in item for item in group["screenTextDiagnostics"])
    assert all(
        "/" not in item and "\\" not in item and ":\\" not in item
        for item in group["screenTextDiagnostics"]
    )
    assert all(
        tmp_path.as_posix() not in item and str(tmp_path) not in item
        for item in group["screenTextDiagnostics"]
    )
    for path, snap in before.items():
        assert _snapshot(path) == snap

    only_bad = collect_screen_text_group(
        query="开始游戏",
        query_run_ids=("run-1",),
        sources=sources,
        reports=(broken,),
        saved_by_run={"run-1": saved},
    )
    assert only_bad["screenTextMatches"] == ()
    assert only_bad["screenTextPrepared"] is False
    assert (
        only_bad["screenTextNotice"]
        == "屏幕文字报告已损坏，不能使用这份结果，也不会开始新的识别任务。"
    )
    assert "报告不是合法的 JSON。" in only_bad["screenTextDiagnostics"]
    assert only_bad["screenTextNotice"] != "尚未准备屏幕文字，未开始新的识别任务。"
    assert _snapshot(broken) == before[broken]
