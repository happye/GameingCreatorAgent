"""F07 之后的 F08：用现有抖音本地导出配置，打一份真实尺寸和命名的七件套。

不缩小预设宽高，不编造预设里没有的码率或官方限值。预检记录必须和成包后的媒体事实一致。
封面和成片都要真正变成竖屏并留下衬边。不调用平台发布接口。
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
from f_mixed_sources import (
    FFMPEG,
    FFPROBE,
    MAX_PRODUCT_BYTES,
    enforce_product_caps,
    http_json,
    link_tools,
    nearest_color,
    pcm_energy,
    plant_completed_runs,
    probe_media,
    require_space,
    start_http,
    stop_http,
    wait_job,
    write_mixed_sources,
)

from gamingcreator.application.package_validation import validate_package
from gamingcreator.domain.platform_profile import profile_digest
from gamingcreator.ui import package_jobs
from gamingcreator.ui.creation_jobs import CreationJobs

pytestmark = pytest.mark.skipif(not FFMPEG.is_file(), reason="本机未准备项目内的 FFmpeg")

FPS = 30
RENDER_WIDTH = 160
RENDER_HEIGHT = 90
SOURCE_SECONDS = 2
TARGET_SECONDS = 15
PLATFORM = "douyin"


def official_profile(platform: str) -> dict:
    profile = next(
        item for item in package_jobs.profiles()["profiles"] if item["Platform"] == platform
    )
    return copy.deepcopy(profile)


def png_size(path: Path) -> tuple[int, int]:
    probe = probe_media(path)
    stream = next(item for item in probe["streams"] if item["codec_type"] == "video")
    return int(stream["width"]), int(stream["height"])


def read_frame(path: Path, frame: int, width: int, height: int) -> bytes:
    pixels = subprocess.run(
        [
            str(FFMPEG),
            "-hide_banner",
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(path),
            "-vf",
            "select=eq(n\\," + str(frame) + ")",
            "-frames:v",
            "1",
            "-pix_fmt",
            "rgb24",
            "-f",
            "rawvideo",
            "-",
        ],
        check=True,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    ).stdout
    if len(pixels) != width * height * 3:
        raise RuntimeError(f"读不到第 {frame} 帧的完整画面（得到 {len(pixels)} 字节）。")
    return pixels


def rgb_at(pixels: bytes, width: int, x: int, y: int) -> tuple[int, int, int]:
    index = (y * width + x) * 3
    return (pixels[index], pixels[index + 1], pixels[index + 2])


def region_mean(pixels: bytes, width: int, box: tuple[int, int, int, int]) -> tuple[int, int, int]:
    x0, y0, x1, y1 = box
    count = (x1 - x0) * (y1 - y0)
    totals = [0, 0, 0]
    for y in range(y0, y1):
        for x in range(x0, x1):
            color = rgb_at(pixels, width, x, y)
            for index in range(3):
                totals[index] += color[index]
    return (totals[0] // count, totals[1] // count, totals[2] // count)


def probe_facts(path: Path) -> dict:
    data = json.loads(
        subprocess.run(
            [
                str(FFPROBE),
                "-v",
                "error",
                "-count_frames",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        ).stdout
    )
    stream = next(item for item in data["streams"] if item["codec_type"] == "video")
    num, den = map(int, stream["r_frame_rate"].split("/"))
    fmt = data["format"]
    return {
        "width": stream["width"],
        "height": stream["height"],
        "codec": stream["codec_name"],
        "pixelFormat": stream["pix_fmt"],
        "frames": int(stream["nb_read_frames"]),
        "fps": {"numerator": num, "denominator": den},
        "durationMs": round(float(fmt["duration"]) * 1000),
        "sizeBytes": path.stat().st_size,
        "audioCodecs": [
            item["codec_name"] for item in data["streams"] if item["codec_type"] == "audio"
        ],
        "bitRate": int(fmt["bit_rate"]) if fmt.get("bit_rate") not in (None, "N/A", "") else None,
    }


def test_douyin_profile_drives_real_vertical_package(tmp_path):
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
    assert all(
        profile["Fields"]["limits"][key] is None or key == "requiredTags"
        for key in profile["Fields"]["limits"]
    )
    assert profile["Fields"]["limits"]["requiredTags"] == []

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
                    "objective": "打一份抖音本地导出配置的真实尺寸平台包",
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
        lengths = [segment["outputFrames"] for segment in segments]
        planned_frames = segments[-1]["outputStartFrame"] + segments[-1]["outputFrames"]
        assert planned_frames == sum(lengths)

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
        assert render_receipt["width"] == RENDER_WIDTH
        assert render_receipt["height"] == RENDER_HEIGHT
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
        assert validation["publicationEligibility"] == "unverified"

        zip_path = jobs.package_file(package["jobId"], "package.zip").path
        with zipfile.ZipFile(zip_path) as archive:
            assert set(archive.namelist()) == set(package_jobs.FILES)
            archive.extractall(products)
        package_video = products / "video.mp4"
        if not package_video.is_file():
            with zipfile.ZipFile(zip_path) as archive:
                archive.extract("video.mp4", products)
        # 文案必须来自这一条成片的发布稿，不能另写一份空的或别的平台的稿。
        for name in ("title.txt", "description.txt", "tags.json"):
            assert (products / name).read_bytes() == (publication_dir / name).read_bytes()
            assert (products / name).stat().st_size > 0

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
        assert measured["fps"] == {"numerator": FPS, "denominator": 1}
        assert measured["audioCodecs"]
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
        assert platform_doc["profile"] == profile

        cover = products / "cover.png"
        assert png_size(cover) == (720, 1280)
        mid = planned_frames // 2
        video_pixels = read_frame(package_video, min(mid, recorded["frames"] - 1), 720, 1280)
        cover_pixels = read_frame(cover, 0, 720, 1280)
        top = region_mean(video_pixels, 720, (200, 20, 520, 80))
        bottom = region_mean(video_pixels, 720, (200, 1200, 520, 1260))
        center = region_mean(video_pixels, 720, (330, 610, 390, 670))
        cover_top = region_mean(cover_pixels, 720, (200, 20, 520, 80))
        cover_center = region_mean(cover_pixels, 720, (330, 610, 390, 670))
        assert sum(top) < 40 and sum(bottom) < 40, (
            "竖屏衬边应是黑边，不能还是横屏铺满。",
            top,
            bottom,
        )
        assert sum(cover_top) < 40
        assert nearest_color(center) in {item["color"] for item in planted}
        assert nearest_color(cover_center) in {item["color"] for item in planted}
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

        summary = {
            "platform": PLATFORM,
            "profileSource": profile["Source"],
            "profileSha256": platform_doc["profileSha256"],
            "note": "本地导出配置，不是官方抖音规则；预设没有码率字段，测到的码率只是这次成包的媒体事实，不是官方限值",
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
