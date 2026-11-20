from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest

from gamingcreator.ui.creation_budget_scope import request_digest
from gamingcreator.ui.creation_jobs import CreationJobs
from gamingcreator.ui.package_jobs import profiles

PROJECT = "artifacts/project"


@pytest.fixture
def batch_jobs(tmp_path, monkeypatch):
    jobs = CreationJobs(tmp_path)
    project = tmp_path / PROJECT
    project.mkdir(parents=True)
    monkeypatch.setattr(jobs, "project", lambda key: project)
    root = "a" * 32
    receipt = "b" * 64
    rows = {
        root: {
            "jobId": root,
            "projectId": PROJECT,
            "status": "completed",
            "kind": "plan",
            "brief": {"contentType": "ad"},
            "resultReceiptSha256": receipt,
            "plans": [
                {"id": "ad-evidence-hook", "ready": True},
                {"id": "ad-evidence-demo", "ready": True},
            ],
        }
    }
    submitted = []
    first = Event()

    def get(job_id, *, include_receipt=False):
        return dict(rows[job_id])

    def submit(kind, request):
        job_id = uuid4().hex
        parent_key, receipt_key = {
            "render": ("planJobId", "expectedParentReceiptSha256"),
            "publication": ("renderJobId", "expectedRenderReceiptSha256"),
            "package": ("publicationJobId", "expectedPublicationReceiptSha256"),
        }[kind]
        rows[job_id] = {
            "jobId": job_id,
            "kind": kind,
            "status": "running" if not submitted else "completed",
            "resultReceiptSha256": job_id * 2,
            "projectId": PROJECT,
            "parentJobId": request[parent_key],
        }
        directory = jobs.jobs / job_id
        directory.mkdir()
        digest = request_digest(kind, request)
        jobs.save(
            directory / "request.json",
            {
                "request": request,
                "digest": digest,
                "parentReceiptSha256": request[receipt_key],
            },
        )
        jobs.save(
            jobs.root / (request["requestId"] + ".json"),
            {"jobId": job_id, "digest": digest},
        )
        submitted.append((kind, dict(request), job_id))
        first.set()
        return get(job_id)

    monkeypatch.setattr(jobs, "get", get)
    monkeypatch.setattr(jobs, "submit", submit)
    monkeypatch.setattr(
        jobs,
        "publication",
        lambda job_id: {
            "renderJobId": job_id,
            "expectedRenderReceiptSha256": rows[job_id]["resultReceiptSha256"],
            "coverFrame": 0,
            "title": "游戏广告",
            "description": "画面依据与行动号召",
            "tags": ["游戏"],
        },
    )
    request = {
        "requestId": uuid4().hex,
        "projectId": PROJECT,
        "planJobId": root,
        "expectedPlanReceiptSha256": receipt,
        "profile": next(p for p in profiles()["profiles"] if p["Platform"] == "douyin"),
        "variants": [
            {"planId": "ad-evidence-hook", "subtitleStyle": "large"},
            {"planId": "ad-evidence-demo", "subtitleStyle": "boxed"},
        ],
    }
    return jobs, request, rows, submitted, first


def joined(jobs, request):
    jobs.threads[-1].join(5)
    assert not jobs.threads[-1].is_alive()
    return jobs.ad_batches.get(request["requestId"], PROJECT)


def test_cancel_finishes_current_stage_and_resume_reuses_its_render(batch_jobs):
    jobs, request, rows, submitted, first = batch_jobs
    assert jobs.ad_batches.submit(request)["batchId"] == request["requestId"]
    assert first.wait(2)
    assert jobs.ad_batches.submit(request)["batchId"] == request["requestId"]
    jobs.ad_batches.cancel(request["requestId"], PROJECT)
    first_render = submitted[0][2]
    rows[first_render]["status"] = "completed"
    cancelled = joined(jobs, request)
    assert cancelled["status"] == "cancelled"
    assert cancelled["items"][0]["stages"]["render"]["status"] == "completed"
    assert len(submitted) == 1

    jobs.ad_batches.resume(request["requestId"], PROJECT)
    complete = joined(jobs, request)
    assert complete["status"] == "completed"
    assert [kind for kind, _, _ in submitted] == ["render", "publication", "package"] * 2
    for index, item in enumerate(complete["items"]):
        render, publication, package = submitted[index * 3 : index * 3 + 3]
        assert render[1]["planId"] == item["planId"]
        assert render[1]["expectedParentReceiptSha256"] == request["expectedPlanReceiptSha256"]
        assert publication[1]["renderJobId"] == render[2]
        assert package[1]["publicationJobId"] == publication[2]
        assert package[1]["expectedPublicationReceiptSha256"] == publication[2] * 2
        assert item["stages"]["package"]["jobId"] == package[2]


def test_interrupted_child_retries_only_on_resume_and_keeps_original_attempt(batch_jobs):
    jobs, request, rows, submitted, first = batch_jobs
    jobs.ad_batches.submit(request)
    assert first.wait(2)
    first_render = submitted[0][2]
    rows[first_render]["status"] = "interrupted"
    stopped = joined(jobs, request)
    assert stopped["status"] == "interrupted"
    jobs.ad_batches.catalog(PROJECT, request["planJobId"])
    assert [job_id for kind, _, job_id in submitted if kind == "render"].count(first_render) == 1

    jobs.ad_batches.resume(request["requestId"], PROJECT)
    complete = joined(jobs, request)
    stage = complete["items"][0]["stages"]["render"]
    assert complete["status"] == "completed"
    assert stage["attempt"] == 2 and stage["jobId"] != first_render
    assert stage["history"][0]["jobId"] == first_render
    assert stage["payload"] == stage["history"][0]["payload"]


def test_batch_checks_receipt_and_duplicate_combinations_before_registration(batch_jobs):
    jobs, request, _, submitted, _ = batch_jobs
    with pytest.raises(ValueError, match="回执"):
        jobs.ad_batches.submit({**request, "expectedPlanReceiptSha256": "wrong"})
    with pytest.raises(ValueError, match="重复"):
        jobs.ad_batches.submit({**request, "variants": [request["variants"][0]] * 2})
    assert not (Path(jobs.ad_batches.root) / request["requestId"]).exists()
    assert not submitted


def test_stage_rejects_a_registration_that_points_to_another_child(batch_jobs):
    jobs, request, rows, submitted, first = batch_jobs
    jobs.ad_batches.submit(request)
    assert first.wait(2)
    rows[submitted[0][2]]["status"] = "completed"
    finished = joined(jobs, request)
    first, second = [item["stages"]["render"] for item in finished["items"]]
    actual_request = {"requestId": first["childRequestId"], **first["payload"]}
    with pytest.raises(ValueError, match="请求或父回执"):
        jobs.ad_batches.bound_child("render", actual_request, second["jobId"], PROJECT)


def test_pre_registration_crash_is_settled_before_charging_quota(tmp_path):
    jobs = CreationJobs(tmp_path)
    orphan = "a" * 32
    job_dir = jobs.jobs / orphan
    job_dir.mkdir()
    jobs.save(job_dir / "request.json", {"request": {"requestId": "b" * 32}})
    jobs.save(job_dir / "status.json", {"jobId": orphan, "status": "pending", "kind": "render"})
    assert jobs._quota_statuses()[0]["status"] == "interrupted"
    assert jobs.read(job_dir / "status.json")["status"] == "interrupted"


def test_continuing_a_cancelled_batch_does_not_retry_failed_variants(batch_jobs, monkeypatch):
    jobs, request, rows, submitted, started = batch_jobs
    batches = jobs.ad_batches
    with monkeypatch.context() as scoped:
        scoped.setattr(batches, "start", lambda directory: None)
        batches.submit(request)
    directory = batches.directory(request["requestId"])
    state = batches.read(directory)
    state.update(status="cancelled", cancelRequested=True)
    state["items"][0]["status"] = "failed"
    batches.save(directory, state)
    batches.resume(request["requestId"], PROJECT)
    assert started.wait(2)
    assert submitted[0][1]["planId"] == "ad-evidence-demo"
    rows[submitted[0][2]]["status"] = "completed"
    partial = joined(jobs, request)
    assert [item["status"] for item in partial["items"]] == ["failed", "completed"]

    batches.resume(request["requestId"], PROJECT)
    assert joined(jobs, request)["status"] == "completed"
    assert submitted[3][1]["planId"] == "ad-evidence-hook"
    assert len(submitted) == 6
