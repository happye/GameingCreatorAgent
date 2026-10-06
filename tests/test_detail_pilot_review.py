"""Human review provenance, absence barriers and real local-file editing round trips."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from test_detail_pilot_comparison import fixture as _comparison_fixture
from test_detail_pilot_comparison import prepare, publish, script
from test_detail_temporal_provider import temporal_model

from gamingcreator.application.detail_pilot_review import (
    DIMENSIONS,
    MAX_REVIEW_BYTES,
    review_entity_ids,
    validate_pilot_review,
)
from gamingcreator.infrastructure.deepseek_detail_temporal import parse_temporal_detail
from gamingcreator.infrastructure.detail_pilot_review_files import (
    read_pilot_review_file,
    write_pilot_review_bundle,
)
from gamingcreator.ui.pilot_review import render_review_editor, render_review_summary

comparison_fixture = _comparison_fixture


@pytest.fixture
def missing(comparison_fixture):
    comparison = prepare(comparison_fixture)
    return comparison, script.review_template(comparison)


@pytest.fixture
def saved(comparison_fixture):
    request = comparison_fixture["requests"][0]
    detail = parse_temporal_detail(json.dumps(temporal_model(request)), request)
    publish(comparison_fixture["args"][0], request, detail)
    comparison = prepare(comparison_fixture)
    template = script.review_template(comparison)
    return comparison, template


def validate(context, record):
    comparison, template = context
    return validate_pilot_review(
        json.dumps(record, ensure_ascii=True),
        expected_template=template,
        entity_ids_by_case=review_entity_ids(comparison),
    )


def judged(context):
    comparison, template = context
    record = deepcopy(template)
    record["recordedOn"] = "2026-10-06"
    record["reviewer"] = "fixture-only-reviewer"
    row = record["cases"][0]
    row["objectMistakenForActor"] = False
    row["shotBoundariesAreReal"] = None
    row["positiveDescriptionsRetained"] = True
    row["queriedClipUsable"] = False
    row["reviewedTemporalEntityIds"] = list(review_entity_ids(comparison)[row["caseId"]])
    row["statement"] = "fixture only：物品/角色已分开，但同一查询仍不可用。"
    return record


def test_blank_record_round_trip_keeps_all_judgments_and_quality_empty(missing):
    comparison, template = missing
    result = validate(missing, template)
    assert json.loads(result.payload_json) == template
    assert result.recorded_on is result.reviewer is None and not result.judged_case_ids
    assert review_entity_ids(comparison) == {row["caseId"]: () for row in template["cases"]}


def test_partial_dimensions_are_independent_and_target_exact_new_entities(saved):
    record = judged(saved)
    result = validate(saved, record)
    assert result.judged_case_ids == (record["cases"][0]["caseId"],)
    assert json.loads(result.payload_json) == record
    assert json.loads(result.payload_json)["humanLabels"] is None
    assert json.loads(result.payload_json)["phase0QualityGate"] is None
    assert json.loads(result.payload_json)["newProviderCalls"] == 0


@pytest.mark.parametrize("field", [*DIMENSIONS, "reviewedTemporalEntityIds", "statement"])
def test_no_saved_result_cannot_acquire_any_new_review(missing, field):
    record = deepcopy(missing[1])
    record.update(recordedOn="2026-10-06", reviewer="fixture-only")
    record["cases"][0][field] = (
        "没有结果"
        if field == "statement"
        else ["e1"]
        if field == "reviewedTemporalEntityIds"
        else False
    )
    with pytest.raises(ValueError):
        validate(missing, record)


@pytest.mark.parametrize(
    "field",
    [
        "schemaVersion",
        "proposalSha256",
        "inputSha256",
        "instructions",
        "humanLabels",
        "phase0QualityGate",
        "newProviderCalls",
    ],
)
def test_record_cannot_change_frozen_sources_or_gate_policy(missing, field):
    record = deepcopy(missing[1])
    record[field] = False if field == "newProviderCalls" else "substituted"
    with pytest.raises(ValueError):
        validate(missing, record)


@pytest.mark.parametrize(
    "field",
    [
        "caseId",
        "runId",
        "eventId",
        "legacyRequestHash",
        "legacyPayloadHash",
        "temporalRequestHash",
        "temporalPayloadHash",
    ],
)
def test_record_cannot_be_rebound_to_another_case_or_result(saved, field):
    record = judged(saved)
    record["cases"][0][field] = "other"
    with pytest.raises(ValueError):
        validate(saved, record)


@pytest.mark.parametrize(
    "field,value",
    [("evidenceId", "other"), ("sourceUs", False), ("durationUs", 1), ("sha256", "f" * 64)],
)
def test_review_frame_identity_clock_and_hash_cannot_change(saved, field, value):
    record = judged(saved)
    record["cases"][0]["frames"][0][field] = value
    with pytest.raises(ValueError):
        validate(saved, record)


@pytest.mark.parametrize("value", [0, 1, "true", {}, []])
def test_judgments_require_real_booleans(saved, value):
    record = judged(saved)
    record["cases"][0]["queriedClipUsable"] = value
    with pytest.raises(ValueError):
        validate(saved, record)


@pytest.mark.parametrize("value", [[], ["shot-1/actor-1"], ["foreign"], [True], ["e1", "e1"], "e1"])
def test_targets_are_unique_new_scene_ids(saved, value):
    record = judged(saved)
    record["cases"][0]["reviewedTemporalEntityIds"] = value
    with pytest.raises(ValueError):
        validate(saved, record)


@pytest.mark.parametrize("date", ["2026-02-29", "0000-01-01", "2026-10-6", "2026-13-01", True])
def test_metadata_requires_calendar_date(saved, date):
    record = judged(saved)
    record["recordedOn"] = date
    with pytest.raises(ValueError):
        validate(saved, record)


@pytest.mark.parametrize(
    "field,value",
    [
        ("reviewer", None),
        ("reviewer", "  "),
        ("reviewer", "a" * 121),
        ("recordedOn", None),
        ("statement", None),
        ("statement", " "),
        ("statement", "a" * 2049),
        ("statement", "\ud800"),
    ],
)
def test_judgment_requires_bounded_metadata_and_explanation(saved, field, value):
    record = judged(saved)
    if field == "statement":
        record["cases"][0][field] = value
    else:
        record[field] = value
    with pytest.raises(ValueError):
        validate(saved, record)


def test_reordered_cases_are_normalized_without_moving_judgments(saved):
    record = judged(saved)
    record["cases"].reverse()
    validated = json.loads(validate(saved, record).payload_json)
    assert validated["cases"][0]["caseId"] == saved[1]["cases"][0]["caseId"]
    assert validated["cases"][0]["queriedClipUsable"] is False


def test_duplicate_fields_extra_fields_and_byte_limit_are_rejected(missing):
    comparison, template = missing
    for text in (
        json.dumps(template).replace('"reviewer": null', '"reviewer": null, "reviewer": "fake"'),
        json.dumps(template | {"unexpected": 0}),
        json.dumps(template).replace('"newProviderCalls": 0', '"newProviderCalls": NaN'),
        " " * MAX_REVIEW_BYTES + "{}",
    ):
        with pytest.raises(ValueError):
            validate_pilot_review(
                text, expected_template=template, entity_ids_by_case=review_entity_ids(comparison)
            )


def test_stale_review_cannot_attach_after_new_payload_is_published(saved):
    record = judged(saved)
    new_template = deepcopy(saved[1])
    new_template["cases"][0]["temporalPayloadHash"] = "f" * 64
    with pytest.raises(ValueError):
        validate((saved[0], new_template), record)


def test_new_bundle_preserves_input_and_has_readable_safe_summary(saved, tmp_path):
    comparison, template = saved
    record = judged(saved)
    record["cases"][0]["statement"] = '</script><img src=x onerror="alert(1)">原话😀'
    data = ("\ufeff" + json.dumps(record, ensure_ascii=False)).encode("utf-8")
    path = tmp_path / "input.json"
    path.write_bytes(data)
    review = validate(saved, record)
    output = tmp_path / "new-bundle"
    files = write_pilot_review_bundle(
        comparison=comparison,
        expected_template=template,
        input_path=path,
        input_bytes=data,
        output_dir=output,
        summary_html=render_review_summary(comparison, review),
    )
    assert len(files) == 5
    assert (output / "review-input.json").read_bytes() == data
    assert json.loads((output / "human-review-record.json").read_bytes()) == record
    provenance = json.loads((output / "review-provenance.json").read_bytes())
    assert provenance["inputRecordSha256"] == hashlib.sha256(data).hexdigest()
    assert (
        provenance["comparisonSha256"]
        == hashlib.sha256((output / "comparison.json").read_bytes()).hexdigest()
    )
    page = (output / "review-summary.html").read_text(encoding="utf-8")
    assert '<img src=x onerror="alert(1)">' not in page and "&lt;/script&gt;" in page
    assert "未核对" in page and "不可用" in page and "未发现误认" in page
    assert provenance["phase0QualityGate"] is provenance["humanLabels"] is None
    assert (
        validate(
            saved, json.loads((output / "human-review-record.json").read_bytes())
        ).judged_case_ids
        == review.judged_case_ids
    )
    with pytest.raises(FileExistsError):
        write_pilot_review_bundle(
            comparison=comparison,
            expected_template=template,
            input_path=path,
            input_bytes=data,
            output_dir=output,
            summary_html=page,
        )


@pytest.mark.parametrize("destination", ["project", "input-parent", "relative"])
def test_output_cannot_contain_sources_or_use_implicit_path(missing, tmp_path, destination):
    comparison, template = missing
    source = tmp_path / "source" / "review.json"
    source.parent.mkdir()
    source.write_text(json.dumps(template), encoding="utf-8")
    output = (
        Path(comparison["project"]) / "reviews"
        if destination == "project"
        else source.parent
        if destination == "input-parent"
        else Path("relative")
    )
    with pytest.raises(ValueError):
        write_pilot_review_bundle(
            comparison=comparison,
            expected_template=template,
            input_path=source,
            input_bytes=source.read_bytes(),
            output_dir=output,
            summary_html="unused",
        )


def test_changed_input_is_rejected_before_output_and_reads_are_bounded(missing, tmp_path):
    comparison, template = missing
    source = tmp_path / "review.json"
    data = json.dumps(template).encode()
    source.write_bytes(data + b" ")
    with pytest.raises(ValueError, match="改变"):
        write_pilot_review_bundle(
            comparison=comparison,
            expected_template=template,
            input_path=source,
            input_bytes=data,
            output_dir=tmp_path / "must-not-exist",
            summary_html="unused",
        )
    assert not (tmp_path / "must-not-exist").exists()
    source.write_bytes(b" " * (MAX_REVIEW_BYTES + 1))
    with pytest.raises(ValueError):
        read_pilot_review_file(source)
    with pytest.raises(ValueError):
        read_pilot_review_file(Path("relative.json"))


def cli_inputs(comparison_fixture):
    values = comparison_fixture["args"]
    flags = ("--project", "--proposal", "--proposal-sha256", "--legacy-report", "--feedback")
    return [item for flag, value in zip(flags, values, strict=True) for item in (flag, str(value))]


def test_cli_editor_and_read_only_review_round_trip(comparison_fixture, tmp_path, capsys):
    args = cli_inputs(comparison_fixture)
    editor = tmp_path / "editor-package"
    assert script.main([*args, "--review-editor", "--output-dir", str(editor)]) == 0
    assert len(json.loads(capsys.readouterr().out)["outputs"]) == 4
    assert (editor / "review-editor.html").is_file()
    template = editor / "human-review-template.json"
    before = script._snapshot(comparison_fixture["args"][0])
    assert script.main([*args, "--review-file", str(template), "--dry-run"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["judgedCaseIds"] == [] and summary["phase0QualityGate"] is None
    bundle = tmp_path / "saved-package"
    assert script.main([*args, "--review-file", str(template), "--output-dir", str(bundle)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert len(summary["outputs"]) == 5 and summary["paidRequestsSent"] == 0
    assert script._snapshot(comparison_fixture["args"][0]) == before
    assert (
        script.main([*args, "--review-file", str(bundle / "human-review-record.json"), "--dry-run"])
        == 0
    )
    capsys.readouterr()
    record = json.loads(template.read_bytes())
    record["cases"][0]["queriedClipUsable"] = True
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(record), encoding="utf-8")
    must_not_exist = tmp_path / "refused"
    assert (
        script.main([*args, "--review-file", str(tampered), "--output-dir", str(must_not_exist)])
        == 1
    )
    assert not must_not_exist.exists() and "暂无真实结果" in capsys.readouterr().err


def test_cli_editor_modes_are_explicit_before_any_read(comparison_fixture):
    args = cli_inputs(comparison_fixture)
    with pytest.raises(SystemExit) as error:
        script.main([*args, "--review-editor", "--dry-run"])
    assert error.value.code == 2
    with pytest.raises(SystemExit) as error:
        script.main([*args, "--review-editor", "--review-file", "other.json", "--dry-run"])
    assert error.value.code == 2


@pytest.mark.parametrize("has_saved", [False, True])
def test_actual_file_editor_download_load_and_invalid_record_preservation(
    missing, saved, tmp_path, has_saved
):
    from playwright.sync_api import expect, sync_playwright

    context = saved if has_saved else missing
    comparison, template = context
    page_path = tmp_path / "editor.html"
    page_path.write_text(render_review_editor(comparison, template), encoding="utf-8")
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            for width in (1366, 390):
                page = browser.new_page(
                    viewport={"width": width, "height": 900}, accept_downloads=True
                )
                errors, requests = [], []
                page.on("pageerror", lambda error, captured=errors: captured.append(str(error)))
                page.on(
                    "request",
                    lambda req, captured=requests: (
                        captured.append(req.url)
                        if not req.url.startswith(("file:", "data:", "blob:"))
                        else None
                    ),
                )
                page.goto(page_path.as_uri())
                expect(page.locator("img")).to_have_count(6)
                page.wait_for_function(
                    "Array.from(document.images).every(image => image.complete && image.naturalWidth > 0)"
                )
                page.locator("#recordedOn").fill("2026-10-06")
                page.locator("#reviewer").fill("fixture-only-reviewer")
                if has_saved:
                    page.locator(
                        "select[data-dimension=objectMistakenForActor]"
                    ).first.select_option("false")
                    page.locator("select[data-dimension=queriedClipUsable]").first.select_option(
                        "false"
                    )
                    page.locator("textarea").first.fill("</script>纯文本依据😀")
                    page.locator("input[type=checkbox]").first.check()
                else:
                    expect(page.locator("select").first).to_be_disabled()
                with page.expect_download() as pending:
                    page.get_by_role("button", name="下载当前记录").click()
                downloaded = Path(pending.value.path()).read_bytes()
                record = json.loads(downloaded)
                result = validate(context, record)
                assert bool(result.judged_case_ids) == has_saved
                incoming = tmp_path / f"incoming-{width}.json"
                incoming.write_bytes(downloaded)
                page.locator("#reviewer").fill("changed")
                page.locator("#load-record").set_input_files(incoming)
                expect(page.locator("#status")).to_contain_text("记录已载入")
                expect(page.locator("#reviewer")).to_have_value("fixture-only-reviewer")
                # Duplicate keys must fail without changing the previous form.
                duplicate = tmp_path / "duplicate.json"
                duplicate.write_text(
                    downloaded.decode().replace(
                        '"reviewer": "fixture-only-reviewer"',
                        '"reviewer": "fixture-only-reviewer", "reviewer": "intruder"',
                    ),
                    encoding="utf-8",
                )
                page.locator("#load-record").set_input_files(duplicate)
                expect(page.locator("#status")).to_contain_text("重复字段")
                expect(page.locator("#reviewer")).to_have_value("fixture-only-reviewer")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                assert not errors and not requests
                page.close()
        finally:
            browser.close()
