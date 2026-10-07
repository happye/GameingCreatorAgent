"""Registration preserves unknown declarations and cannot manufacture human labels."""

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

from gamingcreator.application.benchmark_plan_draft import (
    decode_draft,
    draft_to_plan,
    empty_draft,
    plan_to_draft,
    validate_draft,
)
from gamingcreator.application.benchmark_preparation import canonical_json, loads_plan
from gamingcreator.ui.benchmark_plan_editor import render_plan_editor

ROOT = Path(__file__).resolve().parents[1]


def complete_draft():
    draft = empty_draft()
    draft["datasetId"] = "program-fixture-no-human-judgments"
    draft["sources"] = [
        {
            "id": "source-1",
            "path": "G:/fixture/录像 中文.mp4",
            "recordingGroup": None,
            "partition": "development",
            "modelResultsViewed": False,
        }
    ]
    draft["queries"] = [
        {
            "id": "query-1",
            "text": "寻找闪避片段",
            "kind": "main",
            "sourceId": "source-1",
            "family": "dodge",
        }
    ]
    return draft


def test_empty_and_unknown_drafts_save_without_becoming_valid_plans():
    draft = empty_draft()
    assert decode_draft(canonical_json(draft)) == draft
    with pytest.raises(ValueError):
        draft_to_plan(draft)
    draft = complete_draft()
    draft["sources"][0].update({"partition": "", "modelResultsViewed": None, "path": ""})
    draft["queries"][0].update({"kind": "", "sourceId": "", "text": ""})
    assert decode_draft(canonical_json(draft)) == draft
    with pytest.raises(ValueError):
        draft_to_plan(draft)


def test_completed_draft_is_the_existing_unconfirmed_plan_without_source_claims():
    draft = complete_draft()
    original = deepcopy(draft)
    plan = draft_to_plan(draft)
    assert plan.document["schemaVersion"] == "benchmark-plan-v1"
    assert plan.document["humanReferences"] == {
        "confirmed": False,
        "annotators": [],
        "reviewed": False,
    }
    assert plan.document["labelVersion"] is None
    assert plan.document["queries"][0]["referenceEvents"] == []
    assert plan.sources[0].recording_group is None
    assert plan_to_draft(plan) == draft == original
    draft["sources"][0]["recordingGroup"] = "   "
    assert draft_to_plan(draft).sources[0].recording_group is None
    assert draft["sources"][0]["recordingGroup"] == "   "


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(datasetId=""),
        lambda d: d["sources"][0].update(path="relative.mp4"),
        lambda d: d["sources"][0].update(partition=""),
        lambda d: d["sources"][0].update(modelResultsViewed=None),
        lambda d: d["sources"].append(deepcopy(d["sources"][0])),
        lambda d: d["queries"][0].update(sourceId="missing"),
        lambda d: d["queries"][0].update(kind=""),
        lambda d: d["queries"][0].update(family=""),
        lambda d: d["queries"].append(deepcopy(d["queries"][0])),
    ],
)
def test_incomplete_or_ambiguous_declarations_cannot_export(change):
    draft = complete_draft()
    change(draft)
    validate_draft(draft)
    with pytest.raises(ValueError):
        draft_to_plan(draft)


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(schemaVersion="other"),
        lambda d: d.update(humanReferences={"confirmed": True}),
        lambda d: d.update(sources=None),
        lambda d: d.update(queries=[None]),
        lambda d: d["sources"][0].update(modelResultsViewed="false"),
        lambda d: d["sources"][0].update(recordingGroup=False),
        lambda d: d["sources"][0].update(partition="training"),
        lambda d: d["queries"][0].update(referenceEvents=[]),
        lambda d: d["queries"][0].update(kind="unknown"),
        lambda d: d.update(datasetId="x" * 16385),
    ],
)
def test_unknown_fields_types_and_label_injection_refuse(change):
    draft = complete_draft()
    change(draft)
    with pytest.raises(ValueError):
        decode_draft(canonical_json(draft))


def test_duplicate_json_nonfinite_and_oversize_refuse():
    for data in (b'{"datasetId":"a","datasetId":"b"}', b'{"datasetId":NaN}', b" " * 1_048_577):
        with pytest.raises(ValueError):
            decode_draft(data)


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(labelVersion="human-v1"),
        lambda d: d["humanReferences"].update(annotators=["person"]),
        lambda d: d["humanReferences"].update(reviewed=True),
        lambda d: d["queries"][0]["referenceEvents"].append(
            {
                "humanEventId": "human-action",
                "independenceGroup": "action-1",
                "usableRanges": [{"startUs": 0, "endUs": 1_000_000}],
                "reason": "Declared reference must not be silently cleared",
            }
        ),
    ],
)
def test_existing_human_metadata_or_references_are_not_silently_cleared(change):
    document = draft_to_plan(complete_draft()).document
    change(document)
    before = deepcopy(document)
    with pytest.raises(ValueError):
        plan_to_draft(loads_plan(json.dumps(document)))
    assert document == before


def test_public_script_preserves_input_normalizes_relative_path_and_refuses_overwrite(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "plan_editor_public", ROOT / "scripts/prepare-benchmark-plan.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "录像 中文.mp4"
    source.write_bytes(b"not probed or decoded")
    plan = draft_to_plan(complete_draft()).document
    plan["sources"][0]["path"] = source.name
    input_path = tmp_path / "事前计划.json"
    input_path.write_bytes(canonical_json(plan))
    before = input_path.read_bytes()
    output = tmp_path / "登记表单"
    assert module.main(["--input", str(input_path), "--output", str(output)]) == 0
    draft = decode_draft((output / "draft.json").read_bytes())
    assert draft["sources"][0]["path"] == str(source.resolve())
    assert input_path.read_bytes() == before and source.read_bytes() == b"not probed or decoded"
    assert (output / "plan-input.json").read_bytes() == before
    snapshot = {path.name: path.read_bytes() for path in output.iterdir()}
    assert module.main(["--input", str(input_path), "--output", str(output)]) == 2
    assert snapshot == {path.name: path.read_bytes() for path in output.iterdir()}
    assert module.main(["--output", str(tmp_path / "空白登记")]) == 0
    html = render_plan_editor(empty_draft())
    assert "登记录像和事前查询" in html and "sha256-" in html and "connect-src" in html
