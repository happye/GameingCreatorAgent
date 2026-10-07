"""Pre-inference human-reference records, never real human acceptance evidence."""

import html
import importlib.util
import json
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest
from test_benchmark_preparation import plan_fixture

from gamingcreator.application.benchmark_preparation import canonical_json, loads_plan
from gamingcreator.application.benchmark_reference_review import (
    MAX_RECORD_BYTES,
    build_reference_context,
    validate_reference_record,
)
from gamingcreator.domain.media import MediaStream
from gamingcreator.infrastructure.ffmpeg_media import hash_file
from gamingcreator.ui.benchmark_reference_review import render_reference_review

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "benchmark_reference_script", ROOT / "scripts/prepare-benchmark-references.py"
)
assert SPEC is not None and SPEC.loader is not None
script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(script)


def preparation(tmp_path):
    raw, assets = plan_fixture(tmp_path)
    context, template = build_reference_context(
        loads_plan(json.dumps(raw)), assets, "2026-10-07T10:00:00+08:00"
    )
    return raw, assets, context, template


def add_reference(record):
    record["plan"]["queries"][0]["referenceEvents"] = [
        {
            "humanEventId": "synthetic-action-1",
            "independenceGroup": "synthetic-one-real-action",
            "usableRanges": [{"startUs": 0, "endUs": 1000}, {"startUs": 2000, "endUs": 3000}],
            "reason": "Synthetic fixture only; no human judged this footage.",
        }
    ]
    return record


def test_empty_reference_template_is_not_frozen_or_human_confirmed(tmp_path):
    raw, assets, context, template = preparation(tmp_path)
    assert context["isFrozen"] is False and context["qualityGate"] is None
    assert context["preparation"]["readyForIndependentEvaluation"] is False
    assert not template["plan"]["humanReferences"]["confirmed"]
    assert template["plan"]["queries"][0]["referenceEvents"] == []
    assert validate_reference_record(canonical_json(template), context, assets) == template
    assert raw["sources"][0]["path"] != context["plan"]["sources"][0]["path"]
    assert Path(context["plan"]["sources"][0]["path"]).is_absolute()


def test_manual_ranges_metadata_and_existing_plan_export_preserve_all_declarations(tmp_path):
    _, assets, context, template = preparation(tmp_path)
    record = add_reference(deepcopy(template))
    record["plan"]["labelVersion"] = "fixture-reference-v1"
    record["plan"]["humanReferences"] = {
        "confirmed": True,
        "annotators": ["synthetic-fixture"],
        "reviewed": True,
    }
    edited = validate_reference_record(canonical_json(record), context, assets)
    plan = loads_plan(canonical_json(edited["plan"]).decode())
    assert len(plan.manifest.queries[0].reference_events[0].usable_ranges) == 2
    assert plan.document["sources"] == context["plan"]["sources"]
    assert context["qualityGate"] is None
    assert template["plan"]["queries"][0]["referenceEvents"] == []


@pytest.mark.parametrize(
    "mutation",
    [
        lambda record: record.update(schemaVersion="other"),
        lambda record: record.update(contextSha256="0" * 64),
        lambda record: record.update(extra=True),
        lambda record: record["plan"].update(datasetId="different"),
        lambda record: record["plan"]["sources"][0].update(path="another.mp4"),
        lambda record: record["plan"]["sources"][0].update(recordingGroup="different"),
        lambda record: record["plan"]["sources"][0].update(partition="development"),
        lambda record: record["plan"]["sources"][0].update(modelResultsViewed=True),
        lambda record: record["plan"]["queries"][0].update(text="different query"),
        lambda record: record["plan"]["queries"][0].update(family="different"),
        lambda record: record["plan"]["queries"][0].update(kind="sparse"),
        lambda record: record["plan"]["humanReferences"].update(confirmed=True),
        lambda record: record["plan"]["queries"][0]["referenceEvents"][0]["usableRanges"][0].update(
            startUs=1000
        ),
        lambda record: record["plan"]["queries"][0]["referenceEvents"][0]["usableRanges"][0].update(
            endUs=999999999
        ),
        lambda record: record["plan"]["queries"][0]["referenceEvents"][0]["usableRanges"][0].update(
            startUs=True
        ),
    ],
)
def test_wrong_binding_declarations_ranges_and_confirmation_rejected(tmp_path, mutation):
    _, assets, context, template = preparation(tmp_path)
    record = add_reference(deepcopy(template))
    mutation(record)
    with pytest.raises(ValueError):
        validate_reference_record(canonical_json(record), context, assets)


def test_changed_actual_source_duplicate_json_nonfinite_and_size_rejected(tmp_path):
    _, assets, context, template = preparation(tmp_path)
    changed = {key: replace(asset, sha256="e" * 64) for key, asset in assets.items()}
    with pytest.raises(ValueError, match="原片"):
        validate_reference_record(canonical_json(template), context, changed)
    for data in (
        b'{"schemaVersion":0,"schemaVersion":1}',
        b'{"plan":NaN}',
        b" " * (MAX_RECORD_BYTES + 1),
    ):
        with pytest.raises(ValueError):
            validate_reference_record(data, context, assets)


def test_nonzero_or_different_stream_starts_disable_automatic_player_capture(tmp_path):
    raw, assets, _, _ = preparation(tmp_path)
    for origin, streams in [
        (Fraction(3), (MediaStream(0, "video", Fraction(1), 3, 5),)),
        (
            Fraction(0),
            (
                MediaStream(0, "video", Fraction(1), 2, 3),
                MediaStream(1, "audio", Fraction(1), 0, 5),
            ),
        ),
    ]:
        shifted = {
            key: replace(asset, origin_seconds=origin, streams=streams, duration_us=5000000)
            for key, asset in assets.items()
        }
        context, _ = build_reference_context(
            loads_plan(json.dumps(raw)), shifted, "2026-10-07T10:00:00+08:00"
        )
        assert context["media"][0]["automaticTimeCapture"] is False


def test_public_script_create_import_and_source_change_without_model_work(
    tmp_path, monkeypatch, capsys
):
    raw, assets, _, _ = preparation(tmp_path)
    original = tmp_path / "事前 计划.json"
    original.write_bytes(canonical_json(raw))
    original_bytes = original.read_bytes()

    async def probe(document, base):
        return {
            key: replace(asset, sha256=hash_file(asset.source_path))
            for key, asset in assets.items()
        }

    monkeypatch.setattr(script, "probe_plan", probe)
    output = tmp_path / "原片 标注页面"
    assert script.main(["--input", str(original), "--output", str(output)]) == 0
    context, files = script.read_editor(output)
    record = add_reference(json.loads(files["record-template.json"]))
    record_path = tmp_path / "人工 记录.json"
    record_path.write_bytes(canonical_json(record))
    checked = tmp_path / "核对后的计划"
    arguments = [
        "--review-directory",
        str(output),
        "--record",
        str(record_path),
        "--output",
        str(checked),
    ]
    assert script.main(arguments) == 0
    assert json.loads((checked / "benchmark-plan.json").read_bytes()) == record["plan"]
    assert original.read_bytes() == original_bytes
    assert script.read_editor(output)[1] == files
    assert script.main(arguments) == 2  # Never overwrite the completed output.
    next(iter(assets.values())).source_path.write_bytes(b"changed source")
    arguments[-1] = str(tmp_path / "changed-source-refused")
    assert script.main(arguments) == 2 and not Path(arguments[-1]).exists()
    capsys.readouterr()
    assert "connect-src 'none'" in html.unescape(
        render_reference_review(context, json.loads(files["record-template.json"]))
    )
