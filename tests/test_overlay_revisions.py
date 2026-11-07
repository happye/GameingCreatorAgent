"""Overlay snapshots remain bound to immutable revision requests and assets."""

import asyncio
from pathlib import Path

import pytest
from test_creation_jobs import finish, service  # noqa: F401
from test_creation_revision_jobs import payload, revisions  # noqa: F401
from test_overlay_assets import png
from test_studio_audio_graph_browser import saved_plan

from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.overlay_assets import OverlayAssetLibrary
from gamingcreator.ui.creation_jobs import CreationJobs


@pytest.fixture
def selected(revisions, monkeypatch):  # noqa: F811
    jobs, root, _ = revisions
    tool = str(Path(".tools/ffmpeg/bin/ffmpeg.exe").resolve())
    monkeypatch.setattr(OverlayAssetLibrary, "_tool", lambda self: tool)
    asset = asyncio.run(OverlayAssetLibrary(jobs.repository).register_png(png()))
    row = dict(
        overlayId="a" * 32,
        kind="image",
        startFrame=0,
        endFrame=2,
        x=0,
        y=0,
        width=1000,
        fadeInFrames=0,
        fadeOutFrames=0,
        assetId=asset.asset_id,
        assetReceiptSha256=asset.receipt_sha256,
    )
    overlays = {"schemaVersion": "creation-overlays-v1", "items": [row]}
    return jobs, root, asset, overlays


def save(jobs, parent, token, overlays=None):
    request = payload(jobs, parent, token)
    if overlays is not None:
        request["overlays"] = overlays
    job = jobs.submit("revision", request)["jobId"]
    state = finish(jobs, job)
    assert state["status"] == "completed", state
    return job, state


def test_overlay_save_inherit_clear_and_restart(selected):
    jobs, root, asset, overlays = selected
    root_bytes = {p: p.read_bytes() for p in jobs.directory(root).rglob("*") if p.is_file()}
    parent, state = save(jobs, root, "b", overlays)
    assert state["editor"]["overlays"] == overlays
    public = state["editor"]["overlayAssets"][0]
    assert public["assetReceiptSha256"] == asset.receipt_sha256
    assert "path" not in public and "imageUrl" in public
    child, state = save(jobs, parent, "c")
    assert state["editor"]["overlays"] == overlays
    assert CreationJobs(jobs.repository).edit(child, "hook-first")["overlays"] == overlays
    cleared, state = save(jobs, child, "d", {"schemaVersion": "creation-overlays-v1", "items": []})
    assert "overlays" not in state["editor"]
    assert "overlays" not in CreationJobs(jobs.repository).edit(cleared, "hook-first")
    assert all(p.read_bytes() == raw for p, raw in root_bytes.items())


def test_shortening_rejects_inherited_overlay_instead_of_truncating(selected):
    jobs, root, _, overlays = selected
    parent, _ = save(jobs, root, "b", overlays)
    request = payload(jobs, parent, "c")
    request["clips"] = [{**request["clips"][0], "outputFrames": 1}]
    with pytest.raises((ValueError, AppError), match="[Oo]verlay"):
        jobs.submit("revision", request)
    assert jobs.edit(parent, "hook-first")["overlays"] == overlays


def test_saved_asset_tampering_blocks_revision_read(selected):
    jobs, root, asset, overlays = selected
    parent, _ = save(jobs, root, "b", overlays)
    asset.path.write_bytes(png(3, 2))
    with pytest.raises((ValueError, AppError)):
        jobs.edit(parent, "hook-first")


def test_saved_overlay_revision_renders_with_real_job_and_ffmpeg(service, monkeypatch):  # noqa: F811
    root, _, _ = saved_plan(service, monkeypatch)
    asset = asyncio.run(OverlayAssetLibrary(service.repository).register_png(png()))
    row = dict(
        overlayId="a" * 32,
        kind="image",
        startFrame=0,
        endFrame=2,
        x=0,
        y=0,
        width=1000,
        fadeInFrames=0,
        fadeOutFrames=0,
        assetId=asset.asset_id,
        assetReceiptSha256=asset.receipt_sha256,
    )
    overlays = {"schemaVersion": "creation-overlays-v1", "items": [row]}
    parent, _ = save(service, root, "b", overlays)
    accepted = service.submit(
        "render", {"requestId": "e" * 32, "revisionJobId": parent, "width": 160, "height": 96}
    )
    state = finish(service, accepted["jobId"])
    assert state["status"] == "completed", state
    directory = service.directory(accepted["jobId"])
    receipt = service.read(directory / "result/receipt.json")
    assert receipt["overlays"] == overlays
    assert (directory / "result/video.mp4").stat().st_size > 0
    assert CreationJobs(service.repository).get(accepted["jobId"])["status"] == "completed"
