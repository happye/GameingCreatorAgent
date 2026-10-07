"""A live local worker owns preparation; saved state never claims another worker is alive."""

import asyncio
import hashlib
import json
import time
from urllib.parse import urlencode

import pytest
from test_inspection_http import get, workspace
from test_media_batch import batch, task_snapshot  # noqa: F401 - pytest fixture

from gamingcreator.domain.errors import AppError
from gamingcreator.ui.media_preparation import MediaPreparationJobs


@pytest.fixture
def preparation(request):
    _, _, config, media, _ = request.getfixturevalue("batch")
    root = config.parent
    (root / "config.example.json").write_bytes(config.read_bytes())
    jobs = MediaPreparationJobs(root)
    document = {
        "project": "artifacts/准备项目",
        "paths": [str(path) for path in media.bundles],
        "profile": "frames",
        "maxCostCny": "1.25",
        "timeoutSeconds": 30,
    }
    try:
        yield jobs, document, media
    finally:
        jobs.close()


def wait_job(jobs, job, predicate=None):
    began = time.monotonic()
    while time.monotonic() - began < 10:
        value = jobs.get(job["project"], job["jobId"])
        if (
            predicate(value)
            if predicate
            else value["status"] in {"finished", "partial", "failed", "cancelled"}
            and not value["live"]
        ):
            return value
        time.sleep(0.01)
    raise AssertionError(value)


def hashes(root):
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file() and not path.name.endswith(("-wal", "-shm", ".lock"))
    }


def test_three_prepared_tasks_live_progress_and_fresh_manager_reads_saved_history(preparation):
    jobs, document, media = preparation
    job = jobs.submit(document)
    done = wait_job(jobs, job)
    assert done["status"] == "finished"
    assert done["progress"]["batchId"] == done["batchId"]
    assert [row["status"] for row in done["progress"]["items"]] == ["prepared"] * 3
    assert {row["sourceName"] for row in done["progress"]["items"]} == {
        path.name for path in media.bundles
    }
    result = done["result"]
    assert result["modelInvocations"] == result["newReservations"] == 0
    project = jobs.repository / document["project"]
    tasks = asyncio.run(task_snapshot(project, result["items"]))
    assert all(
        str(run.status) == "pending" and str(run.configuration.max_cost_cny) == "1.25" and not calls
        for run, _, calls in tasks
    )
    before = hashes(project)
    fresh = MediaPreparationJobs(jobs.repository)
    try:
        catalog = fresh.catalog(document["project"])
        assert catalog["activeJob"] is None
        assert len(catalog["batches"]) == 1
        assert catalog["batches"][0]["batchId"] == done["batchId"]
        with pytest.raises(AppError):
            fresh.get(document["project"], job["jobId"])
        assert hashes(project) == before
    finally:
        fresh.close()


def test_bad_item_continues_and_resume_reuses_original_completed_tasks(preparation):
    jobs, document, media = preparation
    bad = list(media.bundles)[1]
    media.bad.add(bad)
    original = wait_job(jobs, jobs.submit(document))
    assert original["status"] == "partial"
    assert [row["status"] for row in original["result"]["items"]] == [
        "prepared",
        "failed",
        "prepared",
    ]
    identities = [row["runId"] for row in original["result"]["items"]]
    extractions = list(media.extractions)
    media.bad.clear()
    resume = {"project": document["project"], "resume": original["batchId"], "timeoutSeconds": 30}
    completed = wait_job(jobs, jobs.submit(resume))
    assert completed["status"] == "finished"
    assert [row["runId"] for row in completed["result"]["items"]] == identities
    assert completed["result"]["reusedPreparedTasks"] == 2
    assert media.extractions == [*extractions, bad]


def test_stop_saves_current_item_and_resume_keeps_allocated_ids(preparation):
    jobs, document, media = preparation
    media.probe_delay = 0.3
    job = jobs.submit(document)
    ready = wait_job(
        jobs,
        job,
        lambda value: (
            value["progress"] is not None and value["progress"]["items"][0]["status"] == "prepared"
        ),
    )
    original_ids = [row["runId"] for row in ready["progress"]["items"]]
    requested = jobs.cancel(document["project"], job["jobId"])
    assert requested["cancellationRequested"]
    done = wait_job(jobs, job)
    assert done["status"] == "cancelled"
    assert done["result"]["exitCode"] == 130
    assert done["result"]["items"][0]["status"] == "prepared"
    media.probe_delay = 0
    result = wait_job(
        jobs,
        jobs.submit(
            {"project": document["project"], "resume": done["batchId"], "timeoutSeconds": 30}
        ),
    )
    assert [row["runId"] for row in result["result"]["items"]] == original_ids
    assert result["status"] == "finished"


def test_one_worker_scope_guard_close_and_no_implicit_restart(preparation):
    jobs, document, media = preparation
    media.probe_delay = 0.3
    job = jobs.submit(document)
    wait_job(jobs, job, lambda value: value["progress"] is not None)
    with pytest.raises(AppError, match="已有批次"):
        jobs.submit(document)
    with pytest.raises(AppError):
        jobs.cancel("artifacts/其他项目", job["jobId"])
    assert jobs.catalog(document["project"])["activeJob"]["jobId"] == job["jobId"]
    jobs.close()
    stopped = jobs.get(document["project"], job["jobId"])
    assert stopped["status"] == "cancelled" and not stopped["live"]
    before = list(media.probes)
    fresh = MediaPreparationJobs(jobs.repository)
    try:
        assert fresh.catalog(document["project"])["activeJob"] is None
        assert media.probes == before
    finally:
        fresh.close()


@pytest.mark.parametrize(
    "changes",
    [
        {"project": "outside"},
        {"project": "artifacts"},
        {"project": "../outside"},
        {"paths": []},
        {"paths": ["same.mp4", "./same.mp4"]},
        {"paths": [None]},
        {"paths": ["https://remote.invalid/video.mp4"]},
        {"paths": ["\\\\remote\\share\\video.mp4"]},
        {"profile": "custom"},
        {"maxCostCny": "0"},
        {"maxCostCny": "NaN"},
        {"timeoutSeconds": True},
        {"timeoutSeconds": 86401},
        {"extra": True},
    ],
)
def test_invalid_request_creates_no_job_batch_or_staging_files(preparation, changes):
    jobs, document, media = preparation
    before = hashes(jobs.repository)
    with pytest.raises(AppError):
        jobs.submit({**document, **changes})
    assert hashes(jobs.repository) == before
    assert media.probes == media.extractions == []


def post(base, path, value, **headers):
    return get(
        base,
        path,
        data=json.dumps(value, ensure_ascii=False).encode(),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )


def test_http_submit_is_nonblocking_poll_and_explicit_cancel_scope(preparation):
    jobs, document, media = preparation
    media.probe_delay = 0.5
    with workspace(jobs.repository) as base:
        began = time.monotonic()
        status, _, raw = post(base, "/api/prepare-media-batch", document)
        assert status == 202 and time.monotonic() - began < 1
        job = json.loads(raw)
        query = urlencode({"project": document["project"], "job": job["jobId"]})
        assert get(base, "/api/media-preparation?" + query)[0] == 200
        assert (
            post(
                base,
                "/api/cancel-media-preparation",
                {"project": "artifacts/other", "job": job["jobId"]},
            )[0]
            == 404
        )
        assert post(base, "/api/prepare-media-batch", document)[0] == 409
        assert (
            post(
                base,
                "/api/cancel-media-preparation",
                {"project": document["project"], "job": job["jobId"]},
            )[0]
            == 200
        )
        end = time.monotonic() + 5
        while time.monotonic() < end:
            state = json.loads(get(base, "/api/media-preparation?" + query)[2])
            if not state["live"]:
                break
            time.sleep(0.01)
        assert state["status"] == "cancelled" and not state["live"]


def test_http_origin_and_exact_fields_rejected_without_writes(preparation):
    jobs, document, media = preparation
    before = hashes(jobs.repository)
    with workspace(jobs.repository) as base:
        assert (
            post(base, "/api/prepare-media-batch", document, Origin="https://outside.invalid")[0]
            == 403
        )
        assert post(base, "/api/prepare-media-batch", {**document, "resume": "a" * 32})[0] == 400
        assert (
            post(base, "/api/prepare-media-batch", {**document, "paths": ["file"] * 101})[0] == 400
        )
        assert (
            get(base, "/api/media-batches?" + urlencode({"project": document["project"]}))[0] == 200
        )
    assert hashes(jobs.repository) == before
    assert media.probes == []
