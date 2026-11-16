"""Draft recovery reuses revision validation and never writes a job."""

# ruff: noqa: F811
import copy

import pytest
from test_clip_replacement_jobs import replacement_request, replacements  # noqa: F401
from test_creation_jobs import finish, service  # noqa: F401
from test_creation_revision_jobs import payload, revisions  # noqa: F401
from test_narration_jobs import choice, done, engine  # noqa: F401
from test_overlay_revisions import save, selected  # noqa: F401

from gamingcreator.domain.errors import AppError
from gamingcreator.ui.creation_draft_restore import preview


def request_for(jobs, parent):
    req = payload(jobs, parent)
    req.pop("requestId")
    editor = jobs.edit(parent, "hook-first")
    req["clips"] = [
        {
            **{key: row[key] for key in ("clipId", "startUs", "endUs")},
            "speed": row.get("speed", {"numerator": 1, "denominator": 1}),
            "transitionIn": row.get("transitionIn", {"type": "cut", "frames": 0}),
        }
        for row in editor["clips"]
    ]
    req.update(
        projectId="artifacts/project",
        subtitleOverrides=[],
        audioMix={
            "bgm": None,
            "sourceGainDb": -8,
            "ducking": "off",
            "sourceEnvelope": [{"frame": 0, "gainDb": -4}],
        },
        narration=None,
    )
    return req


def files(repository):
    return {p: p.read_bytes() for p in repository.rglob("*") if p.is_file()}


def test_restore_projection_normalizes_and_preserves_repository(revisions):
    jobs, root, _ = revisions
    req = request_for(jobs, root)
    req["subtitleOverrides"] = [{"clipId": req["clips"][0]["clipId"], "text": ""}]
    before = files(jobs.repository)
    result = preview(jobs, req)
    assert result == {
        "subtitleOverrides": req["subtitleOverrides"],
        "audioMix": req["audioMix"],
        "narration": None,
        "narrationAsset": None,
    }
    assert files(jobs.repository) == before


@pytest.mark.parametrize(
    "damage",
    [
        "receipt",
        "project",
        "url",
        "mix_url",
        "narration_url",
        "unknown_clip",
        "missing",
        "duplicate_caption",
    ],
)
def test_bad_snapshot_rejected_without_writes(revisions, damage):
    jobs, root, _ = revisions
    req = copy.deepcopy(request_for(jobs, root))
    if damage == "receipt":
        req["expectedParentReceiptSha256"] = "f" * 64
    elif damage == "project":
        req["projectId"] = "other-project"
    elif damage == "url":
        req["narrationAsset"] = {"audioUrl": "https://attacker.invalid"}
    elif damage == "mix_url":
        req["audioMix"]["url"] = "https://attacker.invalid"
    elif damage == "narration_url":
        req["narration"] = {"audioUrl": "https://attacker.invalid"}
    elif damage == "unknown_clip":
        req["clips"][0]["clipId"] = "unknown"
    elif damage == "missing":
        del req["audioMix"]
    else:
        row = {"clipId": req["clips"][0]["clipId"], "text": ""}
        req["subtitleOverrides"] = [row, row]
    before = files(jobs.repository)
    with pytest.raises(ValueError):
        preview(jobs, req)
    assert files(jobs.repository) == before


@pytest.mark.parametrize("inherited", [False, True])
def test_local_narration_revalidated_with_placement_and_no_synthesis(revisions, engine, inherited):
    jobs, root, _ = revisions
    state = done(jobs, "旁白")
    selection = choice(state, start=1, gain=-14)
    if inherited:
        req = payload(jobs, root)
        req["narration"] = selection
        root = jobs.submit("revision", req)["jobId"]
        assert finish(jobs, root)["status"] == "completed"
    req = request_for(jobs, root)
    req["narration"] = selection
    before = files(jobs.repository)
    synthesized = engine.synthesized
    result = preview(jobs, req)
    assert result["narration"] == selection
    assert result["narrationAsset"]["assetJobId"] == state["jobId"]
    assert result["narrationAsset"]["audioUrl"].startswith("/api/creation/jobs/")
    assert files(jobs.repository) == before
    assert engine.synthesized == synthesized
    req["narration"] = None
    assert preview(jobs, req)["narrationAsset"] is None


@pytest.mark.parametrize("damage", ["receipt", "project", "missing", "too_long"])
def test_unusable_narration_rejects_whole_projection(revisions, engine, damage):
    jobs, root, _ = revisions
    if damage == "project":
        other = jobs.repository / "artifacts/other"
        other.mkdir(parents=True)
        (other / "timeline.sqlite3").touch()
    state = done(jobs, "旁白", **({"project": "artifacts/other"} if damage == "project" else {}))
    req = request_for(jobs, root)
    selection = choice(state, start=1)
    if damage == "receipt":
        selection["receiptSha256"] = "f" * 64
    elif damage == "missing":
        selection["assetJobId"] = "f" * 32
    elif damage == "too_long":
        selection["startFrame"] = 999999
    req["narration"] = selection
    before = files(jobs.repository)
    with pytest.raises((ValueError, FileNotFoundError, AppError)):
        preview(jobs, req)
    assert files(jobs.repository) == before


def test_v4_parent_reuses_verified_manifest_without_new_replacements(replacements):
    jobs, root, _ = replacements
    parent = jobs.submit("revision", replacement_request(jobs, root))["jobId"]
    assert finish(jobs, parent)["status"] == "completed"
    req = request_for(jobs, parent)
    before = files(jobs.repository)
    assert preview(jobs, req)["audioMix"] == req["audioMix"]
    assert files(jobs.repository) == before


def test_parent_overlay_is_inherited_and_never_serialized_as_a_new_binding(selected):
    jobs, root, _, overlays = selected
    parent, _ = save(jobs, root, "b", overlays)
    req = request_for(jobs, parent)
    before = files(jobs.repository)
    result = preview(jobs, req)
    assert set(result) == {"subtitleOverrides", "audioMix", "narration", "narrationAsset"}
    assert files(jobs.repository) == before
    assert jobs.edit(parent, "hook-first")["overlays"] == overlays


def v3_request(jobs, root):
    req = request_for(jobs, root)
    swap = replacement_request(jobs, root)
    req.update({k: swap[k] for k in ("clips", "replacements", "candidateManifestSha256")})
    req["overlays"] = {"schemaVersion": "creation-overlays-v1", "items": []}
    return req


def test_v3_cross_source_projection_and_save_without_candidate_panel(replacements):
    jobs, root, other = replacements
    req = v3_request(jobs, root)
    before = files(jobs.repository)
    projected = preview(jobs, req)
    first = projected["clips"][0]
    assert first["runId"] == "B"
    assert first["sourceSha256"] == other.run.asset.sha256
    assert first["sourceClock"] and first["previewUrl"].startswith("/api/creation/jobs/")
    assert "sourcePath" not in first
    assert projected["bounds"][first["clipId"]]["endUs"] >= first["endUs"]
    assert files(jobs.repository) == before
    save_request = {k: v for k, v in req.items() if k != "projectId"}
    save_request["requestId"] = "e" * 32
    child = jobs.submit("revision", save_request)["jobId"]
    assert finish(jobs, child)["status"] == "completed"
    saved = jobs.edit(child, "hook-first")
    assert saved["clips"][0]["runId"] == "B"
    again = v3_request(jobs, child)
    before = files(jobs.repository)
    assert preview(jobs, again)["candidateManifestSha256"] == req["candidateManifestSha256"]
    assert files(jobs.repository) == before


@pytest.mark.parametrize("damage", ["manifest", "candidate", "bounds", "partial_extension", "url"])
def test_v3_invalid_replacement_rejects_without_writes(replacements, damage):
    jobs, root, _ = replacements
    req = v3_request(jobs, root)
    if damage == "manifest":
        req["candidateManifestSha256"] = "f" * 64
    elif damage == "candidate":
        req["replacements"][0]["candidateId"] = "f" * 64
    elif damage == "bounds":
        req["clips"][0]["endUs"] = 10**15
    elif damage == "partial_extension":
        del req["overlays"]
    else:
        req["overlayAssets"] = [{"imageUrl": "file:///fake"}]
    before = files(jobs.repository)
    with pytest.raises(ValueError):
        preview(jobs, req)
    assert files(jobs.repository) == before


@pytest.mark.parametrize("damage", [None, "receipt", "duration"])
def test_v3_overlay_projection_revalidates_assets(selected, damage):
    jobs, root, _, overlays = selected
    req = request_for(jobs, root)
    req.update(candidateManifestSha256=None, replacements=[], overlays=copy.deepcopy(overlays))
    if damage == "receipt":
        req["overlays"]["items"][0]["assetReceiptSha256"] = "f" * 64
    elif damage == "duration":
        req["overlays"]["items"][0]["endFrame"] = 10**9
    before = files(jobs.repository)
    if damage:
        with pytest.raises((ValueError, AppError)):
            preview(jobs, req)
    else:
        projected = preview(jobs, req)
        assert projected["overlays"] == overlays
        assert projected["overlayAssets"][0]["imageUrl"].startswith("/api/creation/overlay-assets/")
    assert files(jobs.repository) == before


def test_v3_v4_parent_requires_manifest_even_without_new_swaps(replacements):
    jobs, root, _ = replacements
    parent = jobs.submit("revision", replacement_request(jobs, root))["jobId"]
    assert finish(jobs, parent)["status"] == "completed"
    req = request_for(jobs, parent)
    req.update(
        candidateManifestSha256=jobs.edit(parent, "hook-first")["candidateManifestSha256"],
        replacements=[],
        overlays={"schemaVersion": "creation-overlays-v1", "items": []},
    )
    before = files(jobs.repository)
    assert preview(jobs, req)["replacements"] == []
    req["candidateManifestSha256"] = None
    with pytest.raises(ValueError):
        preview(jobs, req)
    assert files(jobs.repository) == before


@pytest.mark.parametrize("text", ["替换后手写字幕", ""])
def test_v3_replacement_caption_target_maps_for_projection_save_and_replay(replacements, text):
    jobs, root, _ = replacements
    req = v3_request(jobs, root)
    target = req["clips"][0]["clipId"]
    req["subtitleOverrides"] = [{"clipId": target, "text": text}]
    before = files(jobs.repository)
    projected = preview(jobs, req)
    assert projected["subtitleOverrides"] == req["subtitleOverrides"]
    assert files(jobs.repository) == before
    saved_request = {k: v for k, v in req.items() if k != "projectId"}
    saved_request["requestId"] = "f" * 32
    child = jobs.submit("revision", saved_request)["jobId"]
    assert finish(jobs, child)["status"] == "completed"
    editor = jobs.edit(child, "hook-first")
    new_id = editor["clips"][0]["clipId"]
    assert new_id != target
    assert editor["subtitleOverrides"] == [{"clipId": new_id, "text": text}]
