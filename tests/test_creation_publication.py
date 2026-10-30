import asyncio
import json
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from test_creation_jobs import finish, request, service  # noqa: F401

from gamingcreator.domain.errors import AppError
from gamingcreator.domain.publication import validate_metadata
from gamingcreator.infrastructure.ffmpeg_media import hash_file
from gamingcreator.infrastructure.publication_assets import extract_cover
from gamingcreator.ui.creation_jobs import CreationJobs

ROOT = Path(__file__).resolve().parents[1]
ROOT = next(
    (p for p in (ROOT, *ROOT.parents) if (p / ".tools/ffmpeg/bin/ffmpeg.exe").is_file()), ROOT
)
FFMPEG = ROOT / ".tools/ffmpeg/bin/ffmpeg.exe"


@pytest.fixture
def rendered(service, monkeypatch):  # noqa: F811
    if not FFMPEG.is_file():
        pytest.skip("Pinned FFmpeg is unavailable")
    import gamingcreator.ui.creation_jobs as implementation
    import gamingcreator.ui.publication_jobs as publication

    old = implementation.execute_render_creation

    async def renderer(project, selection, output, tool, width, height, subtitle_mode="none"):
        await old(project, selection, output, tool, width, height, subtitle_mode)
        subprocess.run(
            [
                str(FFMPEG),
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=red:s=64x48:r=2:d=1",
                "-f",
                "lavfi",
                "-i",
                "color=blue:s=64x48:r=2:d=1",
                "-filter_complex",
                "[0:v][1:v]concat=n=2:v=1:a=0[v]",
                "-map",
                "[v]",
                "-c:v",
                "libx264",
                str(output / "video.mp4"),
            ],
            check=True,
        )
        receipt = json.loads((output / "receipt.json").read_text())
        receipt.update(frames=4, fpsNumerator=2, fpsDenominator=1)
        receipt["files"]["video.mp4"] = hash_file(output / "video.mp4")
        (output / "receipt.json").write_text(json.dumps(receipt))

    async def extract(repository, *args):
        await extract_cover(ROOT, *args)

    monkeypatch.setattr(implementation, "execute_render_creation", renderer)
    monkeypatch.setattr(publication, "extract_cover", extract)
    parent = service.submit("plan", request())["jobId"]
    assert finish(service, parent)["status"] == "completed"
    job_id = service.submit(
        "render",
        {
            "requestId": "b" * 32,
            "planJobId": parent,
            "planId": "chronological",
            "width": 64,
            "height": 48,
        },
    )["jobId"]
    assert finish(service, job_id)["status"] == "completed"
    return service, job_id


def payload(jobs, render):
    snap = jobs.publication(render)
    return {
        "requestId": uuid4().hex,
        **{
            k: snap[k]
            for k in (
                "renderJobId",
                "expectedRenderReceiptSha256",
                "coverFrame",
                "title",
                "description",
                "tags",
            )
        },
    }


@pytest.mark.parametrize("description", ["发布简介", "玩法\r\n\t步骤\r提示"])
def test_real_version_files_frame_and_restart(rendered, description):
    jobs, render = rendered
    before = {p: p.read_bytes() for p in jobs.directory(render).rglob("*") if p.is_file()}
    value = payload(jobs, render)
    value.update(coverFrame=2, title="真实标题", description=description, tags=["游戏", "本地"])
    job_id = jobs.submit("publication", value)["jobId"]
    result = finish(jobs, job_id)
    assert result["status"] == "completed", result
    assert (
        jobs.publication_file(job_id, "description.txt").path.read_bytes().decode("utf-8")
        == description
    )
    assert jobs.submit("publication", value)["jobId"] == job_id
    assert all(p.read_bytes() == data for p, data in before.items())
    cover = jobs.publication_file(job_id, "cover.png").path
    pixels = subprocess.run(
        [str(FFMPEG), "-v", "error", "-i", str(cover), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        check=True,
        capture_output=True,
    ).stdout
    assert pixels[2] > 200 and pixels[0] < 30  # exact output frame 2 is blue
    restored = CreationJobs(jobs.repository)
    assert restored.publication(job_id)["title"] == "真实标题"
    assert not restored.threads
    value.update(requestId=uuid4().hex, title="另一版")
    another = jobs.submit("publication", value)["jobId"]
    assert finish(jobs, another)["status"] == "completed"
    assert jobs.publication(job_id)["title"] == "真实标题"
    assert jobs.publication(render)["draft"] is True


@pytest.mark.parametrize(
    "field,value",
    [
        ("coverFrame", True),
        ("coverFrame", -1),
        ("coverFrame", 4),
        ("title", ""),
        ("title", "a" * 201),
        ("description", "a" * 5001),
        ("title", "x\x00"),
        ("description", "x\x01"),
        ("tags", ["a", "a"]),
        ("tags", ["x"] * 21),
        ("tags", ["x" * 51]),
        ("tags", [[]]),
    ],
)
def test_metadata_boundaries(field, value):
    data = {"coverFrame": 0, "title": "标题", "description": "", "tags": []}
    data[field] = value
    with pytest.raises(ValueError):
        validate_metadata(data, 4)


def test_description_accepts_paragraphs_without_allowing_control_characters():
    validate_metadata(
        {
            "coverFrame": 0,
            "title": "标题",
            "description": "玩法简介\n\n操作步骤\r\n\t提示",
            "tags": [],
        },
        4,
    )


@pytest.mark.parametrize(
    "target",
    [
        "cover.png",
        "title.txt",
        "description.txt",
        "tags.json",
        "publication.json",
        "receipt.json",
        "request.json",
        "parent-video",
        "parent-receipt",
    ],
)
def test_tamper_blocks_all_artifacts(rendered, target):
    jobs, render = rendered
    job_id = jobs.submit("publication", payload(jobs, render))["jobId"]
    assert finish(jobs, job_id)["status"] == "completed"
    path = (
        jobs.directory(render)
        / "result"
        / ("video.mp4" if target == "parent-video" else "receipt.json")
        if target.startswith("parent-")
        else jobs.directory(job_id)
        / ("request.json" if target == "request.json" else "result/" + target)
    )
    path.write_bytes(path.read_bytes() + b" ")
    # JSON whitespace cannot invalidate the request digest, so change its semantic metadata.
    if target == "request.json":
        saved = jobs.read(path)
        saved["request"]["title"] = "changed"
        jobs.save(path, saved)
    assert jobs.get(job_id)["status"] == "failed"
    with pytest.raises(ValueError):
        jobs.publication_file(job_id, "cover.png")


def test_orphan_recovery_never_dispatches(rendered):
    jobs, render = rendered
    job_id = jobs.submit("publication", payload(jobs, render))["jobId"]
    assert finish(jobs, job_id)["status"] == "completed"
    directory = jobs.directory(job_id)
    state = jobs.read(directory / "status.json")
    state.update(status="running")
    state.pop("resultReceiptSha256")
    jobs.save(directory / "status.json", state)
    restored = CreationJobs(jobs.repository)
    assert restored.get(job_id)["status"] == "completed"
    assert not restored.threads
    (directory / "result/receipt.json").unlink()
    jobs.save(directory / "status.json", state)
    assert restored.get(job_id)["status"] == "interrupted"
    assert not restored.threads


def test_failed_extraction_and_strict_submit(rendered, monkeypatch):
    import gamingcreator.ui.publication_jobs as publication

    jobs, render = rendered
    value = payload(jobs, render)
    count = len(jobs.threads)
    for changed in (
        {"expectedRenderReceiptSha256": "0" * 64},
        {"coverFrame": 4},
        {"title": ""},
        {"path": "outside"},
    ):
        with pytest.raises((ValueError, AppError)):
            jobs.submit("publication", {**value, **changed})
    assert len(jobs.threads) == count

    async def broken(*args):
        raise ValueError("decoder failure")

    monkeypatch.setattr(publication, "extract_cover", broken)
    job_id = jobs.submit("publication", value)["jobId"]
    assert finish(jobs, job_id)["status"] == "failed"
    assert not (jobs.directory(job_id) / "result/receipt.json").exists()
    assert jobs.get(render)["status"] == "completed"


def test_async_save_runs_parent_verification_outside_its_event_loop(rendered, monkeypatch):
    from gamingcreator.ui.publication_jobs import save_publication

    jobs, render = rendered
    value = payload(jobs, render)
    original_verify = jobs.verify
    calls = []

    async def source_check():
        return "sources-verified"

    def verify_with_source_loop(directory, state):
        # Minimal reproduction of load_chain's asyncio.run(sources()). Keep
        # render_parent and the actual persisted render verification intact.
        calls.append(asyncio.run(source_check()))
        return original_verify(directory, state)

    monkeypatch.setattr(jobs, "verify", verify_with_source_loop)
    directory = jobs.safe(jobs.jobs / uuid4().hex)
    directory.mkdir()
    asyncio.run(save_publication(jobs, directory, value))
    assert calls == ["sources-verified", "sources-verified"]
    assert jobs.read(directory / "result/receipt.json")["status"] == "completed"
    assert (directory / "result/cover.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
