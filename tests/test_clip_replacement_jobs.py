import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_creation_jobs import finish, request, service  # noqa: F401
from test_creation_render import decision

from gamingcreator.application.creation_insertions import insertion_id
from gamingcreator.application.showcase_topics import candidate_topic_projector
from gamingcreator.domain.errors import AppError
from gamingcreator.domain.models import EvidenceReference
from gamingcreator.domain.time import SourceInstant, SourceRange
from gamingcreator.infrastructure.creation_files import write_creation
from gamingcreator.infrastructure.ffmpeg_media import hash_file
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.ui.creation_draft_restore import preview as preview_draft
from gamingcreator.ui.creation_jobs import CreationJobs
from gamingcreator.ui.replacement_jobs import candidate_video, candidates


@pytest.fixture
def replacements(service, monkeypatch):  # noqa: F811
    _, report, timelines = decision()
    a = timelines[0]
    source = service.repository / "footage/source.mp4"
    source.parent.mkdir(exist_ok=True)
    source.write_bytes(b"source A")
    a.run.asset = replace(a.run.asset, source_path=source, sha256=hash_file(source))
    a.run.status = "completed"
    a.run.config_hash = "config"
    a.run.configuration = SimpleNamespace(pipeline_version="v1", pipeline_hash="pipeline")
    a.transcripts = ()
    a.evidence = tuple(
        EvidenceReference(
            e.evidence_ids[0],
            "media",
            "image",
            SourceInstant(e.source_range.start_us, a.run.asset.duration_us),
            source,
            "d" * 64,
            "v1",
        )
        for e in a.events
    )
    other = source.with_name("B.mp4")
    other.write_bytes(b"source B")
    b = SimpleNamespace(
        run=SimpleNamespace(
            **{
                **a.run.__dict__,
                "run_id": "B",
                "asset": replace(
                    a.run.asset, media_id="B", source_path=other, sha256=hash_file(other)
                ),
            }
        ),
        events=tuple(replace(e, run_id="B", media_id="B") for e in a.events),
        evidence=tuple(replace(e, media_id="B") for e in a.evidence),
        transcripts=(),
    )
    for plan in report["plans"]:
        for row in plan["segments"]:
            row.update(sourcePath=str(source), sourceSha256=a.run.asset.sha256)

    async def planner(
        project,
        runs,
        brief,
        output,
        events,
        fps,
        selection,
        preferences=None,
        edit_kinds=None,
        *,
        repository=None,
    ):
        report["brief"] = json.loads(brief.read_text())
        write_creation(output, {"plans.json": report}, ())

    async def open_store(*args, **kwargs):
        async def completed(run):
            return {"run": a, "B": b}[run]

        async def load(run):
            return (await completed(run)).run

        async def close():
            pass

        return SimpleNamespace(load_run=load, load_completed_timeline=completed, close=close)

    monkeypatch.setattr("gamingcreator.ui.creation_jobs.execute_plan_creation", planner)
    monkeypatch.setattr(SqliteTimelineStore, "open", open_store)
    req = request()
    req["runIds"] = ["run", "B"]
    req["brief"]["targetDuration"] = 6
    root = service.submit("plan", req)["jobId"]
    assert finish(service, root)["status"] == "completed"
    return service, root, b


@pytest.fixture
def framed_replacements(replacements, monkeypatch):
    from test_creation_planner import brief

    from gamingcreator.application.creative_planner import candidates as planning_candidates
    from gamingcreator.application.creative_planner import plan_creation

    jobs, _, other = replacements

    async def load():
        store = await SqliteTimelineStore.open(jobs.repository / "artifacts/project")
        return await store.load_completed_timeline("run")

    saved = asyncio.run(load())
    selected = [
        dict(
            runId="run",
            eventId=e.event_id,
            startUs=e.source_range.start_us,
            endUs=e.source_range.start_us + 2_000_000,
        )
        for e in saved.events
    ]
    saved.events = tuple(
        replace(
            e,
            source_range=SourceRange(
                e.source_range.start_us + 500_000,
                e.source_range.start_us + 500_001,
                e.source_range.duration_us,
            ),
        )
        for e in saved.events
    )
    material = planning_candidates((saved,), tuple(e.event_id for e in saved.events), selected)
    report = plan_creation(brief(), material, 30)

    async def planner(
        project,
        runs,
        brief,
        output,
        events,
        fps,
        selection,
        preferences=None,
        edit_kinds=None,
        *,
        repository=None,
    ):
        report["brief"] = json.loads(brief.read_text())
        write_creation(output, {"plans.json": report}, ())

    monkeypatch.setattr("gamingcreator.ui.creation_jobs.execute_plan_creation", planner)
    req = request()
    req.update(requestId="f" * 32, runIds=["run", "B"])
    req["brief"]["targetDuration"] = 6
    root = jobs.submit("plan", req)["jobId"]
    assert finish(jobs, root)["status"] == "completed"
    return jobs, root, other


def replacement_request(jobs, root, token="b"):
    snapshot = jobs.edit(root, "hook-first")
    catalog = candidates(jobs, root, "hook-first")
    candidate = next(c for c in catalog["candidates"] if c["runId"] == "B")
    clips = [
        {
            "clipId": r["clipId"],
            "startUs": r["startUs"],
            "endUs": r["startUs"] + 1_000_000,
            "speed": {"numerator": 1, "denominator": 1},
            "transitionIn": {"type": "cut", "frames": 0},
        }
        for r in snapshot["clips"]
    ]
    clips[0].update(startUs=candidate["startUs"], endUs=candidate["startUs"] + 1_000_000)
    return {k: snapshot[k] for k in ("parentJobId", "planId", "expectedParentReceiptSha256")} | {
        "requestId": token * 32,
        "clips": clips,
        "candidateManifestSha256": catalog["candidateManifestSha256"],
        "replacements": [
            {"targetClipId": clips[0]["clipId"], "candidateId": candidate["candidateId"]}
        ],
    }


def test_cross_run_restart_and_v4_descendant(replacements):
    jobs, root, _ = replacements
    req = replacement_request(jobs, root)
    revision = jobs.submit("revision", req)["jobId"]
    result = finish(jobs, revision)
    assert result["status"] == "completed", result
    snap = CreationJobs(jobs.repository).edit(revision, "hook-first")
    assert snap["clips"][0]["runId"] == "B"
    assert snap["clips"][0]["clipId"] != req["clips"][0]["clipId"]
    child = req | {
        "requestId": "c" * 32,
        "parentJobId": revision,
        "expectedParentReceiptSha256": snap["expectedParentReceiptSha256"],
        "replacements": [],
        "clips": [{k: row[k] for k in req["clips"][0]} for row in snap["clips"]],
    }
    assert finish(jobs, jobs.submit("revision", child)["jobId"])["status"] == "completed"
    receipt = jobs.read(jobs.directory(revision) / "result/receipt.json")
    assert set(receipt["files"]) == {"revision.json", "edit-decision.json", "candidates.json"}


def test_replacement_topic_evidence_binds_selected_run_without_persisting_projection(replacements):
    jobs, _, other = replacements
    events = list(other.events)
    events[1] = replace(events[1], modality="audio", observable_facts=events[0].observable_facts)
    events[2] = replace(events[2], mechanic_tags=("fact 0",))
    other.events = tuple(events)
    req = request()
    req.update(requestId="9" * 32, runIds=["run", "B"])
    req["brief"].update(targetDuration=6, mandatoryTopics=["fact 0"])
    root = jobs.submit("plan", req)["jobId"]
    assert finish(jobs, root)["status"] == "completed"
    candidate_view = candidates(jobs, root, "hook-first")
    catalog = candidate_view["candidates"]
    same_quote = [row["candidateTopicEvidence"] for row in catalog if row["eventId"] == "0"]
    assert {row["runId"] for row in same_quote} == {"run", "B"}
    audio_only = next(row for row in catalog if row["runId"] == "B" and row["eventId"] == "1")
    assert "candidateTopicEvidence" not in audio_only
    tagged = next(row for row in catalog if row["runId"] == "B" and row["eventId"] == "2")
    assert tagged["candidateTopicEvidence"]["matches"][0]["evidenceKind"] == "tag"
    for plan_id in ("guide-evidence", "commentary-evidence"):
        assert candidate_topic_projector((other,), ["fact 0"], plan_id=plan_id)(tagged) is None
    assert len({row["sourceSha256"] for row in same_quote}) == 2
    original = jobs.edit(root, "hook-first")
    assert all("candidateTopicEvidence" not in row for row in original["clips"])

    revision = jobs.submit("revision", replacement_request(jobs, root))["jobId"]
    assert finish(jobs, revision)["status"] == "completed"
    path = jobs.directory(revision) / "result/edit-decision.json"
    stored = path.read_bytes()
    first = CreationJobs(jobs.repository).edit(revision, "hook-first")["clips"][0]
    proof = first["candidateTopicEvidence"]
    assert proof == next(row for row in same_quote if row["runId"] == "B")
    assert proof["sourceStartUs"] == first["startUs"]
    assert proof["sourceEndUs"] > first["endUs"]
    assert b"candidateTopicEvidence" not in stored and path.read_bytes() == stored
    assert b"candidateTopicEvidence" not in (jobs.directory(revision) / "status.json").read_bytes()

    inserted_candidate = next(
        row for row in catalog if row["runId"] == "B" and row["eventId"] == "0"
    )
    cut = {
        "speed": {"numerator": 1, "denominator": 1},
        "transitionIn": {"type": "cut", "frames": 0},
    }
    clips = [
        {**cut, **{key: clip[key] for key in ("clipId", "startUs", "endUs")}}
        for clip in original["clips"]
    ]
    insertion = {
        "afterClipId": clips[0]["clipId"],
        "candidateId": inserted_candidate["candidateId"],
        "startUs": inserted_candidate["startUs"],
        "endUs": inserted_candidate["startUs"] + 1_000_000,
    }
    parent_sha = original["expectedParentReceiptSha256"]
    insertion["newClipId"] = insertion_id(parent_sha, insertion)
    clips.insert(
        1,
        {
            **cut,
            "clipId": insertion["newClipId"],
            "startUs": insertion["startUs"],
            "endUs": insertion["endUs"],
        },
    )
    draft = {
        "projectId": req["projectId"],
        "parentJobId": root,
        "planId": "hook-first",
        "expectedParentReceiptSha256": parent_sha,
        "clips": clips,
        "subtitleOverrides": [],
        "audioMix": original["audioMix"],
        "narration": None,
        "overlays": {"schemaVersion": "creation-overlays-v1", "items": []},
        "candidateManifestSha256": candidate_view["candidateManifestSha256"],
        "replacements": [],
        "insertions": [insertion],
    }
    assert preview_draft(jobs, draft)["clips"][1]["candidateTopicEvidence"] == proof
    saved = {key: value for key, value in draft.items() if key != "projectId"}
    saved["requestId"] = "8" * 32
    insert_job = jobs.submit("revision", saved)["jobId"]
    assert finish(jobs, insert_job)["status"] == "completed"
    assert jobs.edit(insert_job, "hook-first")["clips"][1]["candidateTopicEvidence"] == proof


@pytest.mark.parametrize("fault", ["sha", "candidate", "source", "status"])
def test_refuse_stale_or_forged(replacements, fault):
    jobs, root, b = replacements
    req = replacement_request(jobs, root)
    if fault == "sha":
        req["candidateManifestSha256"] = "0" * 64
    elif fault == "candidate":
        req["replacements"][0]["candidateId"] = "0" * 64
    elif fault == "source":
        b.run.asset.source_path.write_bytes(b"changed")
    else:
        b.run.status = "failed"
    with pytest.raises((ValueError, AppError)):
        jobs.submit("revision", req)


def test_catalog_readonly_and_source_resource(replacements):
    jobs, root, b = replacements
    before = sorted(p for p in jobs.jobs.iterdir())
    catalog = candidates(jobs, root, "hook-first")
    candidate = next(c for c in catalog["candidates"] if c["runId"] == "B")
    assert "sourcePath" not in candidate
    assert candidate["sourceClock"]["originUs"] == 0
    assert (
        candidate_video(
            jobs, root, "hook-first", catalog["candidateManifestSha256"], candidate["candidateId"]
        ).path
        == b.run.asset.source_path
    )
    assert before == sorted(jobs.jobs.iterdir())


def test_inherited_subtitle_removed_and_downgrade_rejected(replacements):
    jobs, root, _ = replacements
    req = replacement_request(jobs, root)
    old = req["clips"][0]["clipId"]
    req["replacements"] = []
    start = jobs.edit(root, "hook-first")["clips"][0]["startUs"]
    req["clips"][0].update(startUs=start, endUs=start + 1_000_000)
    req["subtitleOverrides"] = [{"clipId": old, "text": "old words"}]
    parent = jobs.submit("revision", req)["jobId"]
    assert finish(jobs, parent)["status"] == "completed"
    next_req = replacement_request(jobs, parent, "c")
    revision = jobs.submit("revision", next_req)["jobId"]
    result = finish(jobs, revision)
    assert result["status"] == "completed", result
    assert result["editor"]["subtitleOverrides"] == []
    downgrade = replacement_request(jobs, revision, "d")
    downgrade.pop("candidateManifestSha256")
    downgrade.pop("replacements")
    with pytest.raises(ValueError, match="v4"):
        jobs.submit("revision", downgrade)


@pytest.mark.parametrize("name", ["candidates.json", "revision.json", "edit-decision.json"])
def test_saved_revision_tamper_rejected(replacements, name):
    jobs, root, _ = replacements
    revision = jobs.submit("revision", replacement_request(jobs, root))["jobId"]
    assert finish(jobs, revision)["status"] == "completed"
    path = jobs.directory(revision) / "result" / name
    path.write_text("{}")
    with pytest.raises(ValueError):
        CreationJobs(jobs.repository).edit(revision, "hook-first")
    assert jobs.edit(root, "hook-first")["parentJobId"] == root


def test_narration_draft_and_timeline_export_work_on_a_replaced_version(replacements):
    """A version with replaced footage (v4) still drafts narration and exports a timeline."""
    jobs, root, _ = replacements
    revision = jobs.submit("revision", replacement_request(jobs, root))["jobId"]
    assert finish(jobs, revision)["status"] == "completed"
    draft = jobs.narration_script(revision, "hook-first")
    # The fixture output is a few seconds, so only the opening fits the speaking budget.
    assert draft["text"] and draft["generator"] == "offline-template-v2"
    body, _, _ = jobs.timeline_export(revision, "hook-first", "fcpxml")
    assert body
