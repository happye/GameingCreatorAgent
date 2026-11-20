"""F10 之后的 F11：用现有小红书本地导出配置，单独打一份 3:4 竖屏七件套。

横竖尺寸和封面必须按这份配置真实生效，不能拿别的平台包改后缀冒充。
不改预设里的限值，不调用平台发布接口。
"""

from __future__ import annotations

import json
import zipfile
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

PLATFORM = "xiaohongshu"
OTHER_PROFILE_SHA256 = {
    "e7773c8ddfd24b38a88edf29d0a1f318a24480285f852a5ddabe72c41706f71c",  # douyin
    "1888c3b4704911ef45894319185415a702703fd5790630ba1384c34a15760c37",  # kuaishou
    "dfddc3fa617c711a25f404f6862fba57ef4bc44aa2867b41dc7764de7f5595c0",  # bilibili
}


def test_xiaohongshu_profile_package_uses_official_size(tmp_path):
    require_space(tmp_path)
    link_tools(tmp_path)
    profile = official_profile(PLATFORM)
    assert profile["Source"]["label"] == "用户可编辑本地导出配置，非官方规则"
    assert profile["Fields"]["video"]["width"] == 720
    assert profile["Fields"]["video"]["height"] == 960
    assert profile["Fields"]["video"]["fit"] == "pad"
    assert profile["Fields"]["cover"]["width"] == 720
    assert profile["Fields"]["cover"]["height"] == 960
    assert "bitrate" not in profile["Fields"]["video"]
    for key in (
        "maxBytes",
        "minDurationMs",
        "maxDurationMs",
        "titleMaxChars",
        "descriptionMaxChars",
        "tagMaxCount",
    ):
        assert profile["Fields"]["limits"][key] is None
    assert profile["Fields"]["limits"]["requiredTags"] == []
    assert profile_digest(profile) not in OTHER_PROFILE_SHA256

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
                    "objective": "打一份小红书本地导出配置的真实平台包",
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
        snapshot = jobs.edit(plan["jobId"], "showcase")
        rows = snapshot["clips"]
        assert len(rows) == len(segments)
        planned_frames = rows[-1]["outputStartFrame"] + rows[-1]["outputFrames"]
        assert planned_frames == sum(row["outputFrames"] for row in rows)

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
        result = jobs.directory(rendered["jobId"]) / "result"
        render_video = result / "video.mp4"
        render_receipt = jobs.read(result / "receipt.json")
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
        with zipfile.ZipFile(zip_path) as archive:
            names = set(archive.namelist())
            assert names == set(package_jobs.FILES)
            archive.extractall(products)
        package_video = products / "video.mp4"
        if not package_video.is_file():
            with zipfile.ZipFile(zip_path) as archive:
                archive.extract("video.mp4", products)
        for name in ("title.txt", "description.txt", "tags.json"):
            assert (products / name).read_bytes() == (publication_dir / name).read_bytes()
            assert (products / name).stat().st_size > 0
        title = (products / "title.txt").read_text(encoding="utf-8")
        assert "玩法展示" in title

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
        assert recorded["width"] == 720 and recorded["height"] == 960
        assert recorded["codec"] == "h264" and recorded["pixelFormat"] == "yuv420p"
        assert abs(recorded["frames"] - planned_frames) <= 1
        assert validation["checks"]["width"] == "pass"
        assert validation["checks"]["height"] == "pass"
        assert validation["checks"]["codec"] == "pass"
        assert validation["checks"]["pixelFormat"] == "pass"
        assert validation["checks"]["frames"] == "pass"
        assert validation["checks"]["fps"] == "pass"
        for key in (
            "maxBytes",
            "minDurationMs",
            "maxDurationMs",
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
        assert platform_doc["profileSha256"] not in OTHER_PROFILE_SHA256
        assert platform_doc["profile"] == profile

        cover = products / "cover.png"
        assert png_size(cover) == (720, 960)
        mid = min(planned_frames // 2, recorded["frames"] - 1)
        video_pixels = read_frame(package_video, mid, 720, 960)
        cover_pixels = read_frame(cover, 0, 720, 960)
        top = region_mean(video_pixels, 720, (200, 20, 520, 80))
        bottom = region_mean(video_pixels, 720, (200, 880, 520, 940))
        center = region_mean(video_pixels, 720, (300, 430, 420, 530))
        cover_top = region_mean(cover_pixels, 720, (200, 20, 520, 80))
        cover_center = region_mean(cover_pixels, 720, (300, 430, 420, 530))
        assert top == (0, 0, 0) and bottom == (0, 0, 0), ("3:4 竖屏应上下留黑边。", top, bottom)
        assert cover_top == (0, 0, 0)
        assert nearest_color(center) in {item["color"] for item in planted}
        hook_color = by_event[rows[0]["eventId"]]["color"]
        assert nearest_color(cover_center) == hook_color
        assert snap["coverFrame"] == 0
        seen = []
        for row in rows:
            start = row["outputStartFrame"]
            frames = row["outputFrames"]
            frame = min(start + frames // 2, recorded["frames"] - 1)
            pixels = read_frame(package_video, frame, 720, 960)
            color = nearest_color(region_mean(pixels, 720, (300, 430, 420, 530)))
            seen.append({"eventId": row["eventId"], "color": color})
            assert color == by_event[row["eventId"]]["color"]
            assert region_mean(pixels, 720, (200, 20, 520, 80)) == (0, 0, 0)

        summary = {
            "platform": PLATFORM,
            "profileSource": profile["Source"],
            "profileSha256": platform_doc["profileSha256"],
            "notOtherPlatformPackage": platform_doc["profileSha256"] not in OTHER_PROFILE_SHA256,
            "note": "本地导出配置，不是官方小红书规则；预设限值全是空的，没有写明的规则保持未知",
            "planId": "showcase",
            "planJobId": plan["jobId"],
            "renderJobId": rendered["jobId"],
            "publicationJobId": published["jobId"],
            "packageJobId": package["jobId"],
            "renderSize": {"width": RENDER_WIDTH, "height": RENDER_HEIGHT},
            "packageSize": {"width": recorded["width"], "height": recorded["height"]},
            "plannedFrames": planned_frames,
            "packageFrames": recorded["frames"],
            "measuredBitRate": measured["bitRate"],
            "sizeBytes": recorded["sizeBytes"],
            "durationMs": recorded["durationMs"],
            "presetLimits": profile["Fields"]["limits"],
            "sevenFiles": sorted(package_jobs.FILES),
            "publicationEligibility": facts["publicationEligibility"],
            "platformRules": validation["platformRules"],
            "localChecks": facts["localChecks"],
            "checks": validation["checks"],
            "title": title,
            "coverFrame": snap["coverFrame"],
            "segmentOrder": [
                {
                    "eventId": row["eventId"],
                    "color": by_event[row["eventId"]]["color"],
                    "source": by_event[row["eventId"]]["name"],
                    "outputStartFrame": row["outputStartFrame"],
                    "outputFrames": row["outputFrames"],
                    "role": segment["role"],
                }
                for row, segment in zip(rows, segments, strict=True)
            ],
            "colorChecks": seen,
            "portraitCheck": {
                "top": top,
                "center": center,
                "bottom": bottom,
                "coverTop": cover_top,
                "coverCenter": list(cover_center),
            },
            "packageZip": str(zip_path),
        }
        (products / "核对.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        enforce_product_caps(products)
        assert zip_path.stat().st_size < MAX_PRODUCT_BYTES
    finally:
        stop_http(server, thread)
