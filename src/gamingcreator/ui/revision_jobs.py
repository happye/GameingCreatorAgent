"""Immutable revision chains rooted in verified creation jobs, with no client paths."""

import asyncio
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gamingcreator.application.creation_editing import (
    build_revision,
    validate_revision,
)
from gamingcreator.application.creation_editing import (
    editable_clips as legacy_editable_clips,
)
from gamingcreator.application.creation_replacements import (
    build_candidate_manifest,
    build_revision_v4,
    candidate_manifest_sha,
    validate_revision_v4,
)
from gamingcreator.application.creation_subtitles import build_subtitles, validate_override_text
from gamingcreator.application.edit_decision import select_edit_decision
from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.rendering import RenderPlan, validate_render_plan
from gamingcreator.application.storage import StoredTimeline
from gamingcreator.domain.creation_audio import AudioMix
from gamingcreator.infrastructure.creation_files import write_creation
from gamingcreator.infrastructure.ffmpeg_media import hash_file
from gamingcreator.infrastructure.ffmpeg_render import FfmpegCreationRenderer
from gamingcreator.infrastructure.music_library import MusicLibrary
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


@dataclass
class Chain:
    root_id: str
    root_sha: str
    plan_id: str
    report: dict[str, Any]
    edl: dict[str, Any]
    plan: RenderPlan
    timelines: tuple[StoredTimeline, ...]
    project_id: str
    digest: str
    ancestry: list[dict[str, Any]]
    subtitle_overrides: list[dict[str, str]]
    audio_mix: AudioMix
    manifest: dict[str, Any] | None = None


def resolve_audio(jobs: Any, request: dict[str, Any], inherited: AudioMix) -> AudioMix:
    mix = AudioMix.from_json(request["audioMix"]) if "audioMix" in request else inherited
    if mix.bgm is not None:
        MusicLibrary(jobs.repository).resolve(mix.bgm.track_id, mix.bgm.track_receipt_sha256)
    return mix


def resolve_overrides(
    request: dict[str, Any], inherited: list[dict[str, str]], edl: dict[str, Any], root_sha: str
) -> list[dict[str, str]]:
    """Resolve a complete override snapshot, filtering deleted inherited clips only."""
    ids = {row["clipId"] for row in editable_clips(edl, root_sha)}
    if "subtitleOverrides" not in request:
        return [dict(item) for item in inherited if item["clipId"] in ids]
    items = request["subtitleOverrides"]
    if not isinstance(items, list):
        raise ValueError("Subtitle overrides must be an array.")
    result = []
    seen = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {"clipId", "text"}:
            raise ValueError("Subtitle overrides accept only clipId and text.")
        clip_id = item["clipId"]
        if not isinstance(clip_id, str) or clip_id not in ids or clip_id in seen:
            raise ValueError("Subtitle override clip identity is unknown or duplicated.")
        validate_override_text(item["text"])
        result.append(dict(item))
        seen.add(clip_id)
    return result


def _record(
    jobs: Any, job_id: str, *, pending: bool = False
) -> tuple[dict[str, Any], dict[str, Any], str]:
    directory = jobs.directory(job_id)
    state = jobs.read(directory / "status.json")
    if state["status"] != "completed" and not pending:
        raise ValueError("Revision parent must be completed")
    stored = jobs.read(directory / "request.json")
    receipt = jobs.read(directory / "result/receipt.json")
    digest = hash_file(jobs.safe(directory / "result/receipt.json"))
    canonical = json.dumps(
        {"kind": state["kind"], "request": stored["request"]}, sort_keys=True, ensure_ascii=False
    )
    if (
        state["jobId"] != job_id
        or hashlib.sha256(canonical.encode()).hexdigest() != stored["digest"]
        or receipt.get("jobId") != job_id
        or receipt.get("requestDigest") != stored["digest"]
        or (state["status"] == "completed" and state.get("resultReceiptSha256") != digest)
    ):
        raise ValueError("Revision job identity or receipt changed")
    return state, stored, digest


def load_chain(
    jobs: Any, job_id: str, plan_id: str | None = None, *, pending: bool = False
) -> Chain:
    """Read all ancestors, then validate from the original ready plan forward."""
    records = []
    seen = set()
    current = job_id
    for _ in range(64):
        if current in seen:
            raise ValueError("Revision ancestry cycle")
        seen.add(current)
        state, stored, digest = _record(jobs, current, pending=pending and current == job_id)
        records.append((current, state, stored, digest))
        if state["kind"] == "plan":
            break
        if state["kind"] != "revision":
            raise ValueError("Unsupported revision parent")
        request = stored["request"]
        if state["parentJobId"] != request["parentJobId"]:
            raise ValueError("Revision parent identity changed")
        if plan_id is None:
            plan_id = request["planId"]
        if request["planId"] != plan_id:
            raise ValueError("Revision plan identity changed")
        current = request["parentJobId"]
    else:
        raise ValueError("Revision ancestry exceeds 64 jobs")
    root_id, root_state, root_stored, root_sha = records[-1]
    jobs.verify(jobs.directory(root_id), dict(root_state))
    if root_state["projectId"] != root_stored["request"]["projectId"]:
        raise ValueError("Root project identity changed")
    report = jobs.plan_report(jobs.directory(root_id))
    if not isinstance(plan_id, str):
        raise ValueError("Expected selected root plan")
    root_edl: dict[str, Any] = select_edit_decision(report, plan_id)
    project = jobs.project(root_state["projectId"])

    async def sources() -> tuple[StoredTimeline, ...]:
        store = await SqliteTimelineStore.open(project, read_only=True)
        try:
            return tuple(
                [
                    await store.load_completed_timeline(run)
                    for run in dict.fromkeys(row["runId"] for row in root_edl["segments"])
                ]
            )
        finally:
            await store.close()

    timelines = asyncio.run(sources())
    manifest = None
    if any("candidateManifestSha256" in item[2]["request"] for item in records[:-1]):
        from gamingcreator.ui.replacement_jobs import root_sources

        timelines = root_sources(jobs, root_id)
    plan = validate_render_plan(root_edl, report, timelines)
    edl = root_edl
    parent_sha = root_sha
    overrides: list[dict[str, str]] = []
    audio_mix = AudioMix()
    for current_id, state, stored, digest in reversed(records[:-1]):
        request = stored["request"]
        if (
            state["projectId"] != root_state["projectId"]
            or stored.get("parentReceiptSha256") != parent_sha
            or request.get("expectedParentReceiptSha256") != parent_sha
        ):
            raise ValueError("Revision parent receipt or project changed")
        directory = jobs.directory(current_id)
        receipt = jobs.read(directory / "result/receipt.json")
        is_v4 = "candidateManifestSha256" in request
        expected_schema = (
            "creation-revision-receipt-v2" if is_v4 else "creation-revision-receipt-v1"
        )
        expected_files = {"revision.json", "edit-decision.json"}
        if is_v4:
            expected_files.add("candidates.json")
        if (
            receipt.get("schemaVersion") != expected_schema
            or set(receipt.get("files", {})) != expected_files
        ):
            raise ValueError("Invalid revision receipt")
        for name, expected in receipt["files"].items():
            if hash_file(jobs.safe(directory / "result" / name)) != expected:
                raise ValueError("Revision file changed")
        metadata = jobs.read(directory / "result/revision.json")
        expected_metadata = {
            "rootJobId": root_id,
            "rootPlanId": plan_id,
            "rootReceiptSha256": root_sha,
            "parentJobId": request["parentJobId"],
            "parentReceiptSha256": parent_sha,
            "edits": request["clips"],
        }
        if "subtitleOverrides" in request:
            expected_metadata["subtitleOverrides"] = request["subtitleOverrides"]
        if "audioMix" in request:
            expected_metadata["audioMix"] = request["audioMix"]
        if is_v4:
            expected_metadata.update(
                candidateManifestSha256=request["candidateManifestSha256"],
                replacements=request["replacements"],
            )
        if metadata != expected_metadata:
            raise ValueError("Revision metadata changed")
        revised = jobs.read(directory / "result/edit-decision.json")
        if is_v4:
            expected_manifest = build_candidate_manifest(
                root_sha, root_state["projectId"], root_stored["request"]["runIds"], timelines
            )
            saved_manifest = jobs.read(directory / "result/candidates.json")
            if saved_manifest != expected_manifest or request[
                "candidateManifestSha256"
            ] != candidate_manifest_sha(expected_manifest):
                raise ValueError("Candidate manifest changed")
            manifest = expected_manifest
            plan = validate_revision_v4(
                edl,
                revised,
                root_sha,
                parent_sha,
                request["clips"],
                request["replacements"],
                manifest,
                timelines,
            )
        else:
            if manifest is not None:
                raise ValueError("Replacement descendants require v4")
            if revised != build_revision(edl, root_sha, request["clips"]):
                raise ValueError("Revision differs from its saved request")
            plan = validate_revision(root_edl, report, edl, revised, timelines, root_sha)
        overrides = resolve_overrides(request, overrides, revised, root_sha)
        audio_mix = resolve_audio(jobs, request, audio_mix)
        edl, parent_sha = revised, digest
    ancestry = [
        {"jobId": key, "kind": state["kind"], "planId": plan_id} for key, state, _, _ in records[1:]
    ]
    assert isinstance(plan_id, str)
    return Chain(
        root_id,
        root_sha,
        plan_id,
        report,
        edl,
        plan,
        timelines,
        root_state["projectId"],
        records[0][3],
        ancestry,
        overrides,
        audio_mix,
        manifest,
    )


def editor(chain: Chain, job_id: str) -> dict[str, Any]:
    rows = editable_clips(chain.edl, chain.root_sha)
    for row in rows:
        row.pop("sourcePath", None)
    return {
        "parentJobId": job_id,
        "planId": chain.plan_id,
        "expectedParentReceiptSha256": chain.digest,
        "rootReceiptSha256": chain.root_sha,
        "fps": chain.plan.fps,
        "targetDuration": chain.report["brief"]["targetDuration"],
        "actualDuration": chain.plan.frames / chain.plan.fps,
        "clips": rows,
        "ancestry": chain.ancestry,
        "subtitleOverrides": [dict(item) for item in chain.subtitle_overrides],
        "audioMix": chain.audio_mix.to_json(),
        **(
            {"candidateManifestSha256": candidate_manifest_sha(chain.manifest)}
            if chain.manifest is not None
            else {}
        ),
    }


def save_revision(jobs: Any, directory: Path, request: dict[str, Any], chain: Chain) -> None:
    revised, manifest = prepare_revision(jobs, request, chain)
    metadata = {
        "rootJobId": chain.root_id,
        "rootPlanId": chain.plan_id,
        "rootReceiptSha256": chain.root_sha,
        "parentJobId": request["parentJobId"],
        "parentReceiptSha256": chain.digest,
        "edits": request["clips"],
    }
    resolve_overrides(request, chain.subtitle_overrides, revised, chain.root_sha)
    if "subtitleOverrides" in request:
        metadata["subtitleOverrides"] = request["subtitleOverrides"]
    resolve_audio(jobs, request, chain.audio_mix)
    if "audioMix" in request:
        metadata["audioMix"] = request["audioMix"]
    files: dict[str, object] = {"revision.json": metadata, "edit-decision.json": revised}
    if manifest is not None:
        metadata.update(
            candidateManifestSha256=request["candidateManifestSha256"],
            replacements=request["replacements"],
        )
        files["candidates.json"] = manifest
    jobs.safe(directory / "result")
    write_creation(
        directory / "result",
        files,
        (jobs.project(chain.project_id),),
    )
    path = directory / "result/receipt.json"
    receipt = jobs.read(path)
    receipt["schemaVersion"] = (
        "creation-revision-receipt-v2" if manifest is not None else "creation-revision-receipt-v1"
    )
    jobs.save(path, receipt)


async def render_revision(
    jobs: Any, directory: Path, request: dict[str, Any], chain: Chain
) -> None:
    project = jobs.project(chain.project_id)
    jobs.safe(directory / "selection")
    write_creation(
        directory / "selection",
        {"plans.json": chain.report, "edit-decision.json": chain.edl},
        (project,),
    )
    runs = {timeline.run.run_id: timeline for timeline in chain.timelines}
    mode = request.get("subtitleMode", "none")
    overrides = {item["clipId"]: item["text"] for item in chain.subtitle_overrides}
    cues = (
        ()
        if mode == "none"
        else build_subtitles(
            chain.plan,
            (),
            per_clip=(runs[row["runId"]].transcripts for row in chain.edl["segments"]),
            overrides=(
                overrides.get(row["clipId"]) for row in editable_clips(chain.edl, chain.root_sha)
            ),
        )
    )
    await FfmpegCreationRenderer(jobs.repository).render(
        chain.plan,
        directory / "result",
        (project, directory / "selection", *(clip.asset.source_path for clip in chain.plan.clips)),
        CancellationContext("revision-render", 3600),
        request["width"],
        request["height"],
        hash_file(directory / "selection/receipt.json"),
        cues,
        mode,
        audio_mix=chain.audio_mix,
        music=None
        if chain.audio_mix.bgm is None
        else MusicLibrary(jobs.repository).resolve(
            chain.audio_mix.bgm.track_id, chain.audio_mix.bgm.track_receipt_sha256
        ),
    )


def prepare_revision(
    jobs: Any, request: dict[str, Any], chain: Chain
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if "candidateManifestSha256" not in request:
        if chain.manifest is not None or "replacements" in request:
            raise ValueError("Replacement descendants require v4")
        return build_revision(chain.edl, chain.root_sha, request["clips"]), None
    from gamingcreator.ui.replacement_jobs import manifest_for_chain

    if "replacements" not in request:
        raise ValueError("Replacement operations are required for v4")
    manifest, timelines = manifest_for_chain(jobs, chain)
    if request["candidateManifestSha256"] != candidate_manifest_sha(manifest):
        raise ValueError("Candidate manifest changed")
    revised = build_revision_v4(
        chain.edl, chain.root_sha, chain.digest, request["clips"], request["replacements"], manifest
    )
    validate_revision_v4(
        chain.edl,
        revised,
        chain.root_sha,
        chain.digest,
        request["clips"],
        request["replacements"],
        manifest,
        timelines,
    )
    return revised, manifest


def editable_clips(edl: dict[str, Any], root_sha: str) -> list[dict[str, Any]]:
    if edl.get("schemaVersion") == "edit-decision-revision-v4":
        edl = {**edl, "schemaVersion": "edit-decision-revision-v3"}
    return legacy_editable_clips(edl, root_sha)
