"""Read-only source-bound candidate browsing for immutable creation revisions."""

import asyncio
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from gamingcreator.application.browser_source_clock import runtime_clock_document
from gamingcreator.application.creation_replacements import (
    build_candidate_manifest,
    candidate_manifest_sha,
)
from gamingcreator.application.storage import StoredTimeline
from gamingcreator.infrastructure.ffmpeg_media import hash_file
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.ui.media import MediaResource
from gamingcreator.ui.revision_jobs import Chain, load_chain


def root_sources(jobs: Any, root_id: str) -> tuple[StoredTimeline, ...]:
    request = jobs.read(jobs.directory(root_id) / "request.json")["request"]

    async def load() -> tuple[StoredTimeline, ...]:
        store = await SqliteTimelineStore.open(jobs.project(request["projectId"]), read_only=True)
        try:
            return tuple([await store.load_completed_timeline(run) for run in request["runIds"]])
        finally:
            await store.close()

    timelines = asyncio.run(load())
    for timeline in timelines:
        asset = timeline.run.asset
        if hash_file(asset.source_path) != asset.sha256:
            raise ValueError("Candidate source changed")
    return timelines


def manifest_for_chain(
    jobs: Any, chain: Chain
) -> tuple[dict[str, Any], tuple[StoredTimeline, ...]]:
    request = jobs.read(jobs.directory(chain.root_id) / "request.json")["request"]
    timelines = root_sources(jobs, chain.root_id)
    manifest = build_candidate_manifest(
        chain.root_sha, chain.project_id, request["runIds"], timelines
    )
    if chain.manifest is not None and manifest != chain.manifest:
        raise ValueError("Candidate manifest changed")
    return manifest, timelines


def candidates(jobs: Any, job_id: str, plan_id: str) -> dict[str, Any]:
    chain = load_chain(jobs, job_id, plan_id)
    manifest, timelines = manifest_for_chain(jobs, chain)
    digest = candidate_manifest_sha(manifest)
    clocks = {t.run.run_id: runtime_clock_document(t.run.asset) for t in timelines}
    public = []
    for candidate in manifest["candidates"]:
        row = {k: v for k, v in candidate.items() if k != "sourcePath"}
        row["sourceName"] = Path(candidate["sourcePath"]).name
        row["sourceClock"] = clocks[row["runId"]]
        row["previewUrl"] = (
            "/api/creation/jobs/"
            + job_id
            + "/candidate-video?"
            + urlencode(
                {
                    "planId": plan_id,
                    "candidateManifestSha256": digest,
                    "candidateId": row["candidateId"],
                }
            )
        )
        public.append(row)
    return {"candidateManifestSha256": digest, "candidates": public}


def candidate_video(
    jobs: Any, job_id: str, plan_id: str, digest: str, candidate_id: str
) -> MediaResource:
    chain = load_chain(jobs, job_id, plan_id)
    manifest, timelines = manifest_for_chain(jobs, chain)
    if digest != candidate_manifest_sha(manifest):
        raise ValueError("Candidate manifest changed")
    candidate = next((c for c in manifest["candidates"] if c["candidateId"] == candidate_id), None)
    if candidate is None:
        raise ValueError("Unknown candidate")
    asset = next(t.run.asset for t in timelines if t.run.run_id == candidate["runId"])
    return MediaResource(asset.source_path, asset.sha256, "video/mp4")
