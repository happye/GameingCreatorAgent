import zipfile
from uuid import uuid4

import pytest
from test_creation_publication import ROOT, finish, payload, rendered, service  # noqa: F401

from gamingcreator.ui import package_jobs
from gamingcreator.ui.creation_jobs import CreationJobs


@pytest.mark.parametrize("index", range(4))
def test_platform_package_real(rendered, monkeypatch, index):  # noqa: F811
    jobs, render = rendered
    pub_id = jobs.submit("publication", payload(jobs, render))["jobId"]
    assert finish(jobs, pub_id)["status"] == "completed"
    snap = jobs.publication(pub_id)
    profile = package_jobs.profiles()["profiles"][index]
    # Real transforms at modest test sizes preserve each preset aspect/orientation.
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
    package = result["package"]
    assert package["localChecks"] == "pass"
    assert package["publicationEligibility"] == "unverified"
    assert package["validation"]["platformRules"] == "unknown"
    assert package["validation"]["checks"]["maxBytes"] == "not_configured"
    assert package["validation"]["facts"]["frames"] == 4
    with zipfile.ZipFile(jobs.package_file(job, "package.zip").path) as archive:
        assert set(archive.namelist()) == set(package_jobs.FILES)
        assert not any(
            b"localPath" in archive.read(name) for name in ("platform.json", "validation.json")
        )
    assert jobs.submit("package", req)["jobId"] == job
    restarted = CreationJobs(jobs.repository)
    assert restarted.package(job) == package
    assert not restarted.threads
    profile["Fields"]["limits"]["maxBytes"] = 1
    req["requestId"] = uuid4().hex
    limited = jobs.submit("package", req)["jobId"]
    assert finish(jobs, limited)["package"]["localChecks"] == "fail"
    assert jobs.package(job)["profile"]["Fields"]["limits"]["maxBytes"] is None
    jobs.package_file(job, "title.txt").path.write_text("tampered")
    assert jobs.get(job)["status"] == "failed"


def test_test_only_music_blocks():
    from gamingcreator.application.package_validation import validate_package

    profile = package_jobs.profiles()["profiles"][0]
    facts = dict(
        width=1280,
        height=720,
        codec="h264",
        pixelFormat="yuv420p",
        frames=4,
        fps=dict(numerator=2, denominator=1),
        durationMs=2000,
        sizeBytes=200,
    )
    parent = dict(frames=4, fpsNumerator=2, fpsDenominator=1, music=dict(licenseStatus="test_only"))
    assert (
        validate_package(profile, facts, dict(title="x", description="y", tags=[]), parent)[
            "publicationEligibility"
        ]
        == "blocked"
    )


def test_real_audio_and_crop(tmp_path):
    import asyncio
    import subprocess

    from gamingcreator.infrastructure.publication_assets import extract_cover
    from gamingcreator.infrastructure.publication_package import encode

    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            str(ROOT / ".tools/ffmpeg/bin/ffmpeg.exe"),
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=red:s=64x48:r=30000/1001:d=0.5",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:duration=0.5",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(source),
        ],
        check=True,
    )
    cover = tmp_path / "source.png"
    asyncio.run(extract_cover(ROOT, source, cover, 0, 64, 48))
    target = tmp_path / "output"
    target.mkdir()
    profile = package_jobs.profiles()["profiles"][1]
    for kind in ("video", "cover"):
        profile["Fields"][kind].update(width=48, height=64, fit="crop")
    facts = asyncio.run(encode(ROOT, source, cover, target, profile))
    assert facts["audioCodecs"] == ["aac"]
    assert facts["fps"] == dict(numerator=30000, denominator=1001)
    source_frames = subprocess.check_output(
        [
            str(ROOT / ".tools/ffmpeg/bin/ffprobe.exe"),
            "-v",
            "error",
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=nb_read_frames",
            "-of",
            "csv=p=0",
            str(source),
        ]
    )
    assert facts["frames"] == int(source_frames)
    assert (facts["width"], facts["height"]) == (48, 64)


def test_profile_strict_validation():
    from gamingcreator.domain.platform_profile import validate_profile

    for change in ({"Source": dict(kind="official", label="x")}, {"extra": "path"}):
        with pytest.raises(ValueError):
            validate_profile({**package_jobs.profiles()["profiles"][0], **change})
    value = package_jobs.profiles()["profiles"][0]
    value["Fields"]["video"]["width"] = True
    with pytest.raises(ValueError):
        validate_profile(value)


def test_package_async_parent_boundary_and_failure(rendered, monkeypatch):  # noqa: F811
    import asyncio

    from gamingcreator.domain.errors import AppError

    jobs, render = rendered
    pub = jobs.submit("publication", payload(jobs, render))["jobId"]
    assert finish(jobs, pub)["status"] == "completed"
    req = dict(
        requestId=uuid4().hex,
        publicationJobId=pub,
        expectedPublicationReceiptSha256=jobs.publication(pub)["publicationReceiptSha256"],
        profile=package_jobs.profiles()["profiles"][0],
    )
    for changes in ({"expectedPublicationReceiptSha256": "0" * 64}, {"path": "outside"}):
        with pytest.raises((ValueError, AppError)):
            jobs.submit("package", {**req, **changes})
    original = jobs.verify
    calls = []

    async def source_check():
        return True

    def verify(directory, state):
        calls.append(asyncio.run(source_check()))
        return original(directory, state)

    monkeypatch.setattr(jobs, "verify", verify)

    async def broken(*args):
        raise ValueError("encoding failed")

    monkeypatch.setattr(package_jobs, "encode", broken)
    job = jobs.submit("package", req)["jobId"]
    assert finish(jobs, job)["status"] == "failed"
    assert calls
    assert not (jobs.directory(job) / "result/receipt.json").exists()
