"""Draft requests share export quantization and never persist changes."""

import asyncio

# ruff: noqa: F811
import json
import threading
from dataclasses import replace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from test_clip_replacement_jobs import replacements  # noqa: F401
from test_creation_jobs import service  # noqa: F401
from test_creation_render import ROOT, run_tool
from test_creation_revision_jobs import revisions  # noqa: F401
from test_narration_jobs import engine  # noqa: F401

from gamingcreator.application.creation_editing import validate_revision
from gamingcreator.application.edit_decision import select_edit_decision
from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.creation_subtitles import parse_srt
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.infrastructure.ffmpeg_render import FfmpegCreationRenderer
from gamingcreator.ui.revision_jobs import (
    load_chain,
    prepare_revision,
    resolve_overrides,
    revision_subtitles,
)
from gamingcreator.ui.server import create_server
from gamingcreator.ui.subtitle_preview import preview

REAL_RENDER = FfmpegCreationRenderer.render


def test_http_draft_preview_is_read_only_and_checks_identity(revisions):
    jobs, root, _ = revisions
    server = create_server("127.0.0.1", 0, jobs.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    editor = jobs.edit(root, "hook-first")
    payload = {k: editor[k] for k in ("parentJobId", "planId", "expectedParentReceiptSha256")}
    payload.update(
        projectId="demo",
        subtitleMode="burn",
        clips=[{k: c[k] for k in ("clipId", "startUs", "outputFrames")} for c in editor["clips"]],
    )
    payload["projectId"] = jobs.read(jobs.directory(root) / "status.json")["projectId"]
    payload["subtitleOverrides"] = [{"clipId": editor["clips"][0]["clipId"], "text": r"{hello}\N"}]

    def post(value):
        with urlopen(
            Request(
                base + "/api/creation/subtitle-preview",
                json.dumps(value).encode(),
                {"Content-Type": "application/json", "Origin": base},
            ),
            timeout=30,
        ) as response:
            return json.load(response)

    try:
        before = {str(p): p.read_bytes() for p in jobs.repository.rglob("*") if p.is_file()}
        result = post(payload)
        assert result["cues"][0]["text"] == "｛hello｝＼N"
        assert result["cues"][0]["startUs"] == 0
        assert post({**payload, "subtitleMode": "none"})["cues"] == []
        for bad in (
            {"projectId": "wrong"},
            {"expectedParentReceiptSha256": "0" * 64},
            {"planId": "wrong"},
            {"sourcePath": "C:/outside.mp4"},
            {"clips": [{**payload["clips"][0], "sourcePath": "C:/outside.mp4"}]},
            {"clips": [{**payload["clips"][0], "clipId": "wrong"}]},
        ):
            with pytest.raises(HTTPError) as error:
                post({**payload, **bad})
            assert error.value.code == 400
            error.value.close()
        after = {str(p): p.read_bytes() for p in jobs.repository.rglob("*") if p.is_file()}
        assert before == after
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("status", ["pending", "running", "interrupted"])
def test_incomplete_parent_is_rejected_without_recovery(revisions, status):
    from gamingcreator.ui.subtitle_preview import preview

    jobs, root, _ = revisions
    editor = jobs.edit(root, "hook-first")
    state_path = jobs.directory(root) / "status.json"
    state = jobs.read(state_path)
    state["status"] = status
    jobs.save(state_path, state)
    before = {str(p): p.read_bytes() for p in jobs.repository.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="completed"):
        preview(
            jobs,
            {
                "projectId": state["projectId"],
                "parentJobId": root,
                "planId": "hook-first",
                "expectedParentReceiptSha256": editor["expectedParentReceiptSha256"],
                "clips": [],
                "subtitleMode": "burn",
            },
        )
    assert before == {str(p): p.read_bytes() for p in jobs.repository.rglob("*") if p.is_file()}


def test_v4_replacement_draft_and_stale_manifest(replacements):
    from test_clip_replacement_jobs import replacement_request

    from gamingcreator.ui.subtitle_preview import preview

    jobs, root, _ = replacements
    payload = replacement_request(jobs, root)
    payload.pop("requestId")
    payload.update(
        projectId=jobs.read(jobs.directory(root) / "status.json")["projectId"], subtitleMode="burn"
    )
    before = {str(p): p.read_bytes() for p in jobs.repository.rglob("*") if p.is_file()}
    assert preview(jobs, payload)["cues"] == []
    with pytest.raises(ValueError):
        preview(
            jobs,
            {
                **payload,
                "subtitleOverrides": [{"clipId": payload["clips"][0]["clipId"], "text": "旧身份"}],
            },
        )
    with pytest.raises(ValueError, match="manifest changed"):
        preview(jobs, {**payload, "candidateManifestSha256": "0" * 64})
    assert before == {str(p): p.read_bytes() for p in jobs.repository.rglob("*") if p.is_file()}


@pytest.mark.parametrize("mode", ["sidecar", "burn"])
def test_same_draft_real_srt_and_burn_timing(revisions, tmp_path, mode):
    jobs, root, _ = revisions
    chain = load_chain(jobs, root, "hook-first")
    editor = jobs.edit(root, "hook-first")
    payload = {k: editor[k] for k in ("parentJobId", "planId", "expectedParentReceiptSha256")}
    payload.update(
        projectId=chain.project_id,
        subtitleMode=mode,
        clips=[
            {"clipId": c["clipId"], "startUs": c["startUs"], "outputFrames": 10}
            for c in reversed(editor["clips"])
        ],
    )
    payload["subtitleOverrides"] = [
        {"clipId": c["clipId"], "text": f"字幕{i} {{安全}}"} for i, c in enumerate(editor["clips"])
    ]
    projected = preview(jobs, payload)["cues"]
    revised, _ = prepare_revision(jobs, payload, chain)
    plan = validate_revision(
        select_edit_decision(chain.report, chain.plan_id),
        chain.report,
        chain.edl,
        revised,
        chain.timelines,
        chain.root_sha,
    )
    cues = revision_subtitles(
        replace(
            chain,
            plan=plan,
            edl=revised,
            subtitle_overrides=resolve_overrides(payload, [], revised, chain.root_sha),
        ),
        mode,
    )
    source = tmp_path / "black.mp4"
    run_tool(
        ["-f", "lavfi", "-i", "color=c=black:s=320x180:r=30:d=30", "-c:v", "libx264", str(source)]
    )

    async def render():
        from gamingcreator.infrastructure.ffmpeg_render import FfmpegCreationRenderer

        context = CancellationContext("preview-real", 60)
        asset = await FfmpegMediaProcessor(ROOT).probe(source, context)
        real_plan = replace(plan, clips=tuple(replace(c, asset=asset) for c in plan.clips))
        await REAL_RENDER(
            FfmpegCreationRenderer(ROOT),
            real_plan,
            tmp_path / mode,
            (source,),
            context,
            320,
            180,
            "",
            cues,
            mode,
        )

    asyncio.run(render())
    saved = parse_srt((tmp_path / mode / "subtitles.srt").read_text(encoding="utf-8"))
    for event, cue in zip(projected, saved, strict=True):
        scale = 100 if mode == "burn" else 1000
        assert event["startUs"] == int(cue.start * scale) * (1000000 // scale)
        assert event["endUs"] == int(cue.end * scale) * (1000000 // scale)
        assert event["text"] == (
            cue.text.translate(str.maketrans("\\{}", "＼｛｝")) if mode == "burn" else cue.text
        )
    pixels = run_tool(
        ["-i", str(tmp_path / mode / "video.mp4"), "-pix_fmt", "gray", "-f", "rawvideo", "-"]
    )
    assert any(v > 100 for v in pixels) == (mode == "burn")


def test_replaced_run_transcript_speed_and_overlap_lane(replacements, tmp_path, monkeypatch):
    from test_clip_replacement_jobs import replacement_request

    from gamingcreator.domain.models import TranscriptSegment
    from gamingcreator.domain.time import SourceRange
    from gamingcreator.ui.subtitle_preview import preview

    jobs, root, timeline = replacements
    asset = timeline.run.asset
    timeline.transcripts = (
        TranscriptSegment(
            asset.media_id,
            SourceRange(0, asset.duration_us, asset.duration_us),
            "替换素材语音",
            "ASR uncertain",
        ),
    )
    payload = replacement_request(jobs, root)
    payload.pop("requestId")
    payload.update(
        projectId=jobs.read(jobs.directory(root) / "status.json")["projectId"], subtitleMode="burn"
    )
    from test_creation_jobs import finish

    saved = jobs.submit(
        "revision",
        {k: v for k, v in payload.items() if k not in ("projectId", "subtitleMode")}
        | {"requestId": "e" * 32},
    )["jobId"]
    assert finish(jobs, saved)["status"] == "completed"
    editor = jobs.edit(saved, "hook-first")
    payload.update({k: editor[k] for k in ("parentJobId", "planId", "expectedParentReceiptSha256")})
    payload["clips"] = [
        {k: c[k] for k in ("clipId", "startUs", "endUs", "speed", "transitionIn")}
        for c in editor["clips"]
    ]
    payload["replacements"] = []
    payload["clips"][0]["speed"] = {"numerator": 2, "denominator": 1}
    payload["clips"][1]["transitionIn"] = {"type": "crossfade", "frames": 3}
    payload["subtitleOverrides"] = [{"clipId": payload["clips"][1]["clipId"], "text": "后镜手写"}]
    cues = preview(jobs, payload)["cues"]
    replacement_cues = [c for c in cues if c["text"] == "替换素材语音"]
    assert replacement_cues[0]["startUs"] == 0
    assert replacement_cues[-1]["endUs"] == 500000
    assert replacement_cues[-1]["lifted"]
    assert any(c["text"] == "后镜手写" and not c["lifted"] and c["startUs"] == 400000 for c in cues)

    real_draft = _v4_draft_chain(jobs, payload)
    actual_ass = _render_draft_video(real_draft, tmp_path, monkeypatch)
    _assert_ass_preview(actual_ass, cues)
    saved = parse_srt((tmp_path / "v4-burn/subtitles.srt").read_text(encoding="utf-8"))
    sidecar = preview(jobs, {**payload, "subtitleMode": "sidecar"})["cues"]
    assert [(c["startUs"], c["endUs"], c["text"]) for c in sidecar] == [
        (int(c.start * 1000000), int(c.end * 1000000), c.text) for c in saved
    ]
    pixels = run_tool(
        ["-i", str(tmp_path / "v4-burn/video.mp4"), "-pix_fmt", "gray", "-f", "rawvideo", "-"]
    )
    frame = 320 * 180
    overlap = pixels[13 * frame : 14 * frame]
    before = pixels[5 * frame : 6 * frame]
    assert any(v > 100 for v in overlap[120 * 320 : 155 * 320])
    assert any(v > 100 for v in overlap[155 * 320 :])
    assert not any(v > 100 for v in before[120 * 320 : 155 * 320])


def _v4_draft_chain(jobs, payload):
    from gamingcreator.application.creation_replacements import validate_revision_v4
    from gamingcreator.ui.replacement_jobs import manifest_for_chain

    chain = load_chain(jobs, payload["parentJobId"], payload["planId"])
    revised, manifest = prepare_revision(jobs, payload, chain)
    _, timelines = manifest_for_chain(jobs, chain)
    plan = validate_revision_v4(
        chain.edl,
        revised,
        chain.root_sha,
        chain.digest,
        payload["clips"],
        payload["replacements"],
        manifest,
        timelines,
    )
    return replace(
        chain,
        plan=plan,
        edl=revised,
        timelines=timelines,
        subtitle_overrides=resolve_overrides(
            payload, chain.subtitle_overrides, revised, chain.root_sha
        ),
    )


def _render_draft_video(chain, tmp_path, monkeypatch):
    import gamingcreator.infrastructure.ffmpeg_render as native

    source = tmp_path / "black.mp4"
    run_tool(
        ["-f", "lavfi", "-i", "color=c=black:s=320x180:r=30:d=30", "-c:v", "libx264", str(source)]
    )
    documents = []
    original = native._burn_ass

    def capture(*args):
        result = original(*args)
        documents.append(result)
        return result

    monkeypatch.setattr(native, "_burn_ass", capture)

    async def scenario():
        context = CancellationContext("preview-v4-real", 60)
        asset = await FfmpegMediaProcessor(ROOT).probe(source, context)
        plan = replace(chain.plan, clips=tuple(replace(c, asset=asset) for c in chain.plan.clips))
        await REAL_RENDER(
            FfmpegCreationRenderer(ROOT),
            plan,
            tmp_path / "v4-burn",
            (source,),
            context,
            320,
            180,
            "",
            revision_subtitles(chain, "burn"),
            "burn",
        )

    asyncio.run(scenario())
    return documents[0]


def _assert_ass_preview(document, cues):
    def microseconds(clock):
        hour, minute, seconds = clock.split(":")
        from decimal import Decimal

        return int((int(hour) * 3600 + int(minute) * 60 + Decimal(seconds)) * 1000000)

    events = []
    for line in document.splitlines():
        if line.startswith("Dialogue:"):
            fields = line.split(",", 9)
            events.append(
                (
                    microseconds(fields[1]),
                    microseconds(fields[2]),
                    fields[9].replace(r"\N", "\n"),
                    int(fields[7]) > 4,
                )
            )
    assert events == [(c["startUs"], c["endUs"], c["text"], c["lifted"]) for c in cues]


@pytest.mark.parametrize("status", ["pending", "running", "interrupted"])
def test_narration_dependency_does_not_recover_on_preview(revisions, engine, status):
    from test_narration_jobs import choice, done, revise

    jobs, root, _ = revisions
    narration = done(jobs)
    revised = revise(jobs, root, "d", narration=choice(narration))
    assert revised["status"] == "completed"
    editor = jobs.edit(revised["jobId"], "hook-first")
    request = {k: editor[k] for k in ("parentJobId", "planId", "expectedParentReceiptSha256")}
    request.update(
        projectId=revised["projectId"],
        subtitleMode="burn",
        clips=[{k: c[k] for k in ("clipId", "startUs", "outputFrames")} for c in editor["clips"]],
    )
    path = jobs.directory(narration["jobId"]) / "status.json"
    state = jobs.read(path)
    state["status"] = status
    jobs.save(path, state)
    before = {str(p): p.read_bytes() for p in jobs.repository.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="completed"):
        preview(jobs, request)
    assert before == {str(p): p.read_bytes() for p in jobs.repository.rglob("*") if p.is_file()}


def test_repeated_run_reorder_automatic_and_deleted_inherited_overrides(replacements):
    from test_clip_replacement_jobs import replacement_request
    from test_creation_jobs import finish

    from gamingcreator.domain.models import TranscriptSegment
    from gamingcreator.domain.time import SourceRange

    jobs, root, b = replacements
    a = load_chain(jobs, root, "hook-first").timelines[0]
    for timeline, text in ((a, "来源A"), (b, "来源B")):
        asset = timeline.run.asset
        timeline.transcripts = (
            TranscriptSegment(
                asset.media_id,
                SourceRange(0, asset.duration_us, asset.duration_us),
                text,
                "uncertain",
            ),
        )
    request = replacement_request(jobs, root)
    saved = finish(jobs, jobs.submit("revision", request)["jobId"])
    assert saved["status"] == "completed"
    editor = jobs.edit(saved["jobId"], "hook-first")
    payload = {k: editor[k] for k in ("parentJobId", "planId", "expectedParentReceiptSha256")}
    payload.update(
        projectId=saved["projectId"],
        subtitleMode="sidecar",
        candidateManifestSha256=editor["candidateManifestSha256"],
        replacements=[],
        clips=[
            {k: c[k] for k in ("clipId", "startUs", "endUs", "speed", "transitionIn")}
            for c in reversed(editor["clips"])
        ],
    )
    result = preview(jobs, payload)["cues"]
    assert [c["text"] for c in result] == ["来源A", "来源A", "来源B"]
    assert [c["startUs"] for c in result] == [0, 1000000, 2000000]
    inherited = {"clipId": payload["clips"][0]["clipId"], "text": "继承手写"}
    revision_request = {k: v for k, v in payload.items() if k not in ("projectId", "subtitleMode")}
    revision_request.update(requestId="9" * 32, subtitleOverrides=[inherited])
    second = finish(jobs, jobs.submit("revision", revision_request)["jobId"])
    assert second["status"] == "completed"
    snapshot = jobs.edit(second["jobId"], "hook-first")
    payload.update(
        {k: snapshot[k] for k in ("parentJobId", "planId", "expectedParentReceiptSha256")}
    )
    assert preview(jobs, payload)["cues"][0]["text"] == "继承手写"
    payload["clips"] = payload["clips"][1:]
    assert [c["text"] for c in preview(jobs, payload)["cues"]] == ["来源A", "来源B"]
    with pytest.raises(ValueError):
        preview(jobs, {**payload, "subtitleOverrides": [inherited]})
