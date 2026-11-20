"""F12：改坏或移走隔离平台包里的一件后，不能再当成功下载。

原任务记录要保留，错误要指出缺的或坏的是哪一个文件。
工作台打开已完成的包时，不能再出现下载成功入口。
"""
# ruff: noqa: F811

from __future__ import annotations

import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest
from test_creation_jobs import service  # noqa: F401
from test_creation_publication import ROOT, finish, payload, rendered  # noqa: F401

from gamingcreator.domain.errors import AppError
from gamingcreator.ui import package_jobs
from gamingcreator.ui.creation_jobs import CreationJobs
from gamingcreator.ui.server import create_server


def _build_package(rendered, monkeypatch):
    jobs, render = rendered
    pub_id = jobs.submit("publication", payload(jobs, render))["jobId"]
    assert finish(jobs, pub_id)["status"] == "completed"
    snap = jobs.publication(pub_id)
    profile = package_jobs.profiles()["profiles"][0]
    for kind in ("video", "cover"):
        profile["Fields"][kind]["width"] //= 10
        profile["Fields"][kind]["height"] //= 10
        for key in ("width", "height"):
            profile["Fields"][kind][key] += profile["Fields"][kind][key] % 2
    original = package_jobs.encode

    async def encode(repository, *args):
        return await original(ROOT, *args)

    monkeypatch.setattr(package_jobs, "encode", encode)
    req = dict(
        requestId=uuid4().hex,
        publicationJobId=pub_id,
        expectedPublicationReceiptSha256=snap["publicationReceiptSha256"],
        profile=profile,
    )
    job = jobs.submit("package", req)["jobId"]
    result = finish(jobs, job)
    assert result["status"] == "completed", result
    return jobs, job


def _records(jobs: CreationJobs, job: str) -> dict[str, bytes]:
    directory = jobs.directory(job)
    return {
        name: (directory / name).read_bytes()
        for name in ("status.json", "request.json", "result/receipt.json")
    }


def _assert_records_kept(jobs: CreationJobs, job: str, before: dict[str, bytes]) -> None:
    after = _records(jobs, job)
    assert after == before
    status = json.loads(after["status.json"])
    assert status["status"] == "completed"
    assert "resultReceiptSha256" in status


def _http_error(base: str, path: str) -> tuple[int, dict]:
    try:
        with urlopen(Request(base + path), timeout=30) as response:
            raise AssertionError(f"应当拒绝下载或读取，却返回了 {response.status}")
    except HTTPError as error:
        body = error.read()
        payload = json.loads(body) if body else {}
        error.close()
        return error.code, payload


def test_missing_or_damaged_package_file_is_not_a_successful_download(rendered, monkeypatch):
    jobs, job = _build_package(rendered, monkeypatch)
    directory = jobs.directory(job)
    before = _records(jobs, job)
    title = directory / "result" / "title.txt"
    backup = directory / "title.txt.bak"
    backup.write_bytes(title.read_bytes())
    missing = directory / "moved-title.txt"
    title.replace(missing)
    assert not title.exists()

    state = jobs.get(job)
    assert state["status"] == "failed"
    assert state["error"]["code"] == "creation.artifact_invalid"
    assert "title.txt" in state["error"]["message"]
    assert "缺少" in state["error"]["message"]
    _assert_records_kept(jobs, job, before)
    with pytest.raises(AppError) as missing_package:
        jobs.package(job)
    assert missing_package.value.code == "creation.artifact_invalid"
    assert "title.txt" in missing_package.value.message
    with pytest.raises(AppError) as missing_file:
        jobs.package_file(job, "package.zip")
    assert missing_file.value.code == "creation.artifact_invalid"
    assert "title.txt" in missing_file.value.message
    with pytest.raises(AppError):
        jobs.package_file(job, "title.txt")

    server = create_server("127.0.0.1", 0, jobs.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        for path in (
            f"/api/creation/jobs/{job}/package",
            f"/api/creation/jobs/{job}/package-files/package.zip?download=1",
            f"/api/creation/jobs/{job}/package-files/title.txt?download=1",
            f"/api/creation/jobs/{job}/package-files/video.mp4?download=1",
        ):
            status, body = _http_error(base, path)
            assert status == 409, (path, status, body)
            assert body["code"] == "creation.artifact_invalid"
            assert "title.txt" in body["message"]
            assert "缺少" in body["message"]
        _assert_records_kept(jobs, job, before)

        missing.replace(title)
        restored = jobs.get(job)
        assert restored["status"] == "completed"
        assert "package" in restored
        assert jobs.package(job)["generationStatus"] == "completed"
        assert jobs.package_file(job, "package.zip").path.is_file()
        _assert_records_kept(jobs, job, before)

        title.write_text("tampered", encoding="utf-8")
        damaged = jobs.get(job)
        assert damaged["status"] == "failed"
        assert damaged["error"]["code"] == "creation.artifact_invalid"
        assert "title.txt" in damaged["error"]["message"]
        assert "损坏" in damaged["error"]["message"]
        _assert_records_kept(jobs, job, before)
        with pytest.raises(AppError) as damaged_file:
            jobs.package_file(job, "package.zip")
        assert damaged_file.value.code == "creation.artifact_invalid"
        assert "title.txt" in damaged_file.value.message
        status, body = _http_error(
            base, f"/api/creation/jobs/{job}/package-files/package.zip?download=1"
        )
        assert status == 409
        assert body["code"] == "creation.artifact_invalid"
        assert "title.txt" in body["message"]
        assert "损坏" in body["message"]
        status, body = _http_error(base, f"/api/creation/jobs/{job}/package")
        assert status == 409 and "title.txt" in body["message"]
        _assert_records_kept(jobs, job, before)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
