"""F08 之后的 F09：用现有快手本地导出配置，单独打一份真实尺寸的七件套。

不改预设里的限值，没有写明的规则仍保持未知。失败的任务不能留下空占位文件冒充成功。
不拿抖音包改后缀充数，也不调用平台发布接口。
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from f_mixed_sources import (
    FFMPEG,
    MAX_PRODUCT_BYTES,
    enforce_product_caps,
    http_json,
    link_tools,
    nearest_color,
    pcm_energy,
    plant_completed_runs,
    require_space,
    start_http,
    stop_http,
    wait_job,
    write_mixed_sources,
)
from test_f08_douyin_package import (
    FPS,
    RENDER_HEIGHT,
    RENDER_WIDTH,
    SOURCE_SECONDS,
    TARGET_SECONDS,
    official_profile,
    png_size,
    probe_facts,
    read_frame,
    region_mean,
)

from gamingcreator.application.package_validation import validate_package
from gamingcreator.domain.platform_profile import profile_digest
from gamingcreator.ui import package_jobs
from gamingcreator.ui.creation_jobs import CreationJobs

pytestmark = pytest.mark.skipif(not FFMPEG.is_file(), reason="本机未准备项目内的 FFmpeg")

PLATFORM = "kuaishou"
DOUYIN_PROFILE_SHA256 = "e7773c8ddfd24b38a88edf29d0a1f318a24480285f852a5ddabe72c41706f71c"


def test_kuaishou_profile_drives_real_vertical_package(tmp_path, monkeypatch):
    require_space(tmp_path)
    link_tools(tmp_path)
    profile = official_profile(PLATFORM)
    assert profile["Source"]["label"] == "用户可编辑本地导出配置，非官方规则"
    assert profile["Fields"]["video"]["width"] == 720
    assert profile["Fields"]["video"]["height"] == 1280
    assert profile["Fields"]["video"]["fit"] == "pad"
    assert profile["Fields"]["cover"]["width"] == 720
    assert profile["Fields"]["cover"]["height"] == 1280
    assert "bitrate" not in profile["Fields"]["video"]
    # 现有快手预设里带了体积和最长时长，原样使用，不改数字。
    assert profile["Fields"]["limits"]["maxBytes"] == 4_000_000_000
    assert profile["Fields"]["limits"]["maxDurationMs"] == 900_000
    assert profile["Fields"]["limits"]["minDurationMs"] is None
    assert profile["Fields"]["limits"]["titleMaxChars"] is None
    assert profile["Fields"]["limits"]["descriptionMaxChars"] is None
    assert profile["Fields"]["limits"]["tagMaxCount"] is None
    assert profile["Fields"]["limits"]["requiredTags"] == []
    assert profile_digest(profile) != DOUYIN_PROFILE_SHA256

    footage = tmp_path / "素材"
    sources = write_mixed_sources(footage, duration=SOURCE_SECONDS)
    project = tmp_path / "artifacts" / "project"
    planted = __import__("asyncio").run(plant_completed_runs(project, sources))
    by_event = {item["eventId"]: item for item in planted}
    jobs = CreationJobs(tmp_path)
    server, thread, base = start_http(tmp_path)
    products = tmp_path / "产物"
    products.mkdir()
    try:
        plan_job = http_json(
            base,
            "/api/creation/plans",
            {
                "requestId": uuid4().hex,
                "projectId": "artifacts/project",
                "runIds": [item["runId"] for item in planted],
                "fps": FPS,
                "brief": {
                    "game": "测试游戏",
                    "contentType": "feature_showcase",
                    "platforms": [PLATFORM],
                    "targetDuration": TARGET_SECONDS,
                    "objective": "打一份快手本地导出配置的真实尺寸平台包",
                    "audience": "观众",
                    "tone": "清楚",
                    "mandatoryTopics": [],
                    "exclude": [],
                },
            },
        )
        plan = wait_job(base, plan_job["jobId"])
        assert plan["status"] == "completed", plan
        showcase = next(item for item in plan["plans"] if item["id"] == "showcase")
        segments = showcase["segments"]
        assert len(segments) >= 3
        planned_frames = segments[-1]["outputStartFrame"] + segments[-1]["outputFrames"]
        assert planned_frames == sum(segment["outputFrames"] for segment in segments)

        render_job = http_json(
            base,
            "/api/creation/renders",
            {
                "requestId": uuid4().hex,
                "planJobId": plan["jobId"],
                "planId": "showcase",
                "width": RENDER_WIDTH,
                "height": RENDER_HEIGHT,
            },
        )
        rendered = wait_job(base, render_job["jobId"], timeout=180)
        assert rendered["status"] == "completed", rendered
        render_video = jobs.directory(rendered["jobId"]) / "result" / "video.mp4"
        render_receipt = jobs.read(jobs.directory(rendered["jobId"]) / "result" / "receipt.json")
        assert abs(int(render_receipt["frames"]) - planned_frames) <= 1
        assert pcm_energy(render_video) > 20

        publication = http_json(
            base,
            "/api/creation/publications",
            {
                "requestId": uuid4().hex,
                **{
                    key: jobs.publication(rendered["jobId"])[key]
                    for key in (
                        "renderJobId",
                        "expectedRenderReceiptSha256",
                        "coverFrame",
                        "title",
                        "description",
                        "tags",
                    )
                },
            },
        )
        published = wait_job(base, publication["jobId"], timeout=120)
        assert published["status"] == "completed", published
        snap = jobs.publication(published["jobId"])
        publication_dir = jobs.directory(published["jobId"]) / "result"
        packed = http_json(
            base,
            "/api/creation/packages",
            {
                "requestId": uuid4().hex,
                "publicationJobId": published["jobId"],
                "expectedPublicationReceiptSha256": snap["publicationReceiptSha256"],
                "profile": profile,
            },
        )
        package = wait_job(base, packed["jobId"], timeout=180)
        assert package["status"] == "completed", package
        facts = package["package"]
        validation = facts["validation"]
        assert facts["localChecks"] == "pass"
        assert facts["publicationEligibility"] == "unverified"
        assert validation["platformRules"] == "unknown"
        assert validation["sourceRights"] == "unknown"
        assert validation["humanQuality"] == "unknown"

        zip_path = jobs.package_file(package["jobId"], "package.zip").path
        import json
        import zipfile

        with zipfile.ZipFile(zip_path) as archive:
            assert set(archive.namelist()) == set(package_jobs.FILES)
            archive.extractall(products)
        package_video = products / "video.mp4"
        if not package_video.is_file():
            with zipfile.ZipFile(zip_path) as archive:
                archive.extract("video.mp4", products)
        for name in ("title.txt", "description.txt", "tags.json"):
            assert (products / name).read_bytes() == (publication_dir / name).read_bytes()
            assert (products / name).stat().st_size > 0
        for name in package_jobs.FILES:
            assert (products / name).is_file() and (products / name).stat().st_size > 0

        measured = probe_facts(package_video)
        recorded = validation["facts"]
        for key in (
            "width",
            "height",
            "codec",
            "pixelFormat",
            "frames",
            "fps",
            "durationMs",
            "sizeBytes",
            "audioCodecs",
        ):
            assert recorded[key] == measured[key], (key, recorded[key], measured[key])
        assert recorded["width"] == 720 and recorded["height"] == 1280
        assert recorded["codec"] == "h264" and recorded["pixelFormat"] == "yuv420p"
        assert abs(recorded["frames"] - planned_frames) <= 1
        assert recorded["sizeBytes"] <= 4_000_000_000
        assert recorded["durationMs"] <= 900_000
        assert validation["checks"]["width"] == "pass"
        assert validation["checks"]["height"] == "pass"
        assert validation["checks"]["codec"] == "pass"
        assert validation["checks"]["pixelFormat"] == "pass"
        assert validation["checks"]["frames"] == "pass"
        assert validation["checks"]["fps"] == "pass"
        assert validation["checks"]["maxBytes"] == "pass"
        assert validation["checks"]["maxDurationMs"] == "pass"
        for key in (
            "minDurationMs",
            "titleMaxChars",
            "descriptionMaxChars",
            "tagMaxCount",
            "requiredTags",
        ):
            assert validation["checks"][key] == "not_configured"
        recomputed = validate_package(profile, recorded, snap, render_receipt)
        assert recomputed == validation

        platform_doc = json.loads((products / "platform.json").read_text(encoding="utf-8"))
        assert platform_doc["profile"]["Platform"] == PLATFORM
        assert platform_doc["profileSha256"] == profile_digest(profile)
        assert platform_doc["profileSha256"] != DOUYIN_PROFILE_SHA256
        assert platform_doc["profile"] == profile

        cover = products / "cover.png"
        assert png_size(cover) == (720, 1280)
        mid = min(planned_frames // 2, recorded["frames"] - 1)
        video_pixels = read_frame(package_video, mid, 720, 1280)
        cover_pixels = read_frame(cover, 0, 720, 1280)
        top = region_mean(video_pixels, 720, (200, 20, 520, 80))
        bottom = region_mean(video_pixels, 720, (200, 1200, 520, 1260))
        center = region_mean(video_pixels, 720, (330, 610, 390, 670))
        cover_top = region_mean(cover_pixels, 720, (200, 20, 520, 80))
        cover_center = region_mean(cover_pixels, 720, (330, 610, 390, 670))
        assert sum(top) < 40 and sum(bottom) < 40, ("竖屏衬边应是黑边。", top, bottom)
        assert sum(cover_top) < 40
        assert nearest_color(center) in {item["color"] for item in planted}
        seen = []
        for segment in segments:
            start = segment["outputStartFrame"]
            frames = segment["outputFrames"]
            frame = min(start + frames // 2, recorded["frames"] - 1)
            pixels = read_frame(package_video, frame, 720, 1280)
            color = nearest_color(region_mean(pixels, 720, (330, 610, 390, 670)))
            seen.append({"eventId": segment["eventId"], "role": segment["role"], "color": color})
            assert color == by_event[segment["eventId"]]["color"]
            assert sum(region_mean(pixels, 720, (200, 20, 520, 80))) < 40
        assert nearest_color(cover_center) in {item["color"] for item in planted}

        # 失败路径：编码失败时不能留下空文件，也不能当成成功包下载。
        async def broken(*args, **kwargs):
            raise ValueError("encoding failed")

        monkeypatch.setattr(package_jobs, "encode", broken)
        failed_submit = http_json(
            base,
            "/api/creation/packages",
            {
                "requestId": uuid4().hex,
                "publicationJobId": published["jobId"],
                "expectedPublicationReceiptSha256": snap["publicationReceiptSha256"],
                "profile": profile,
            },
        )
        failed = wait_job(base, failed_submit["jobId"], timeout=60)
        assert failed["status"] == "failed", failed
        failed_dir = jobs.directory(failed["jobId"]) / "result"
        assert not (failed_dir / "receipt.json").exists()
        leftovers = []
        if failed_dir.exists():
            for path in failed_dir.rglob("*"):
                if path.is_file():
                    leftovers.append((path.name, path.stat().st_size))
                    assert path.stat().st_size > 0, f"失败后留下了空占位文件：{path.name}"
        # 已成功的快手包不能被这次失败冲掉。
        assert zip_path.is_file() and zip_path.stat().st_size > 0
        assert (products / "video.mp4").stat().st_size == recorded["sizeBytes"]

        summary = {
            "platform": PLATFORM,
            "profileSource": profile["Source"],
            "profileSha256": platform_doc["profileSha256"],
            "notDouyinProfile": platform_doc["profileSha256"] != DOUYIN_PROFILE_SHA256,
            "note": "本地导出配置，不是官方快手规则；体积和最长时长用预设原值，没有写明的规则保持未知",
            "planId": "showcase",
            "planJobId": plan["jobId"],
            "renderJobId": rendered["jobId"],
            "publicationJobId": published["jobId"],
            "packageJobId": package["jobId"],
            "failedPackageJobId": failed["jobId"],
            "failedLeftovers": leftovers,
            "renderSize": {"width": RENDER_WIDTH, "height": RENDER_HEIGHT},
            "packageSize": {"width": recorded["width"], "height": recorded["height"]},
            "plannedFrames": planned_frames,
            "packageFrames": recorded["frames"],
            "measuredBitRate": measured["bitRate"],
            "sizeBytes": recorded["sizeBytes"],
            "durationMs": recorded["durationMs"],
            "presetLimits": {
                "maxBytes": profile["Fields"]["limits"]["maxBytes"],
                "maxDurationMs": profile["Fields"]["limits"]["maxDurationMs"],
            },
            "sevenFiles": sorted(package_jobs.FILES),
            "publicationEligibility": facts["publicationEligibility"],
            "platformRules": validation["platformRules"],
            "localChecks": facts["localChecks"],
            "checks": validation["checks"],
            "title": (products / "title.txt").read_text(encoding="utf-8"),
            "coverFrame": snap["coverFrame"],
            "segmentOrder": [
                {
                    "eventId": segment["eventId"],
                    "role": segment["role"],
                    "color": by_event[segment["eventId"]]["color"],
                    "source": by_event[segment["eventId"]]["name"],
                    "outputStartFrame": segment["outputStartFrame"],
                    "outputFrames": segment["outputFrames"],
                }
                for segment in segments
            ],
            "colorChecks": seen,
            "padCheck": {"top": top, "center": center, "bottom": bottom, "coverTop": cover_top},
            "packageZip": str(zip_path),
        }
        (products / "核对.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        enforce_product_caps(products)
        assert zip_path.stat().st_size < MAX_PRODUCT_BYTES
    finally:
        stop_http(server, thread)
