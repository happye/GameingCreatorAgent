"""F06 之后的 F07：广告买量模式混合源走真实 HTTP，带上已有安全区、角标和水印规则。

用抽帧核对安全区裁切、左上角色标和右上角套餐水印是否真的烧进成片，不只看回执。
套餐只在隔离目录里用官方接口切到 Free 本地评估，不改门，不伪造许可。
不冒称实际投放效果。
"""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
from f_mixed_sources import (
    FFMPEG,
    MAX_PRODUCT_BYTES,
    SOURCE_SPECS,
    enforce_product_caps,
    http_json,
    link_tools,
    nearest_color,
    pcm_energy,
    plant_completed_runs,
    probe_media,
    require_space,
    run_ffmpeg,
    shrink_profile,
    start_http,
    stop_http,
    wait_job,
)

from gamingcreator.application.material_scoring import UNKNOWN
from gamingcreator.application.rendering import output_start_frames
from gamingcreator.domain.creation_presentation import safe_area_crop_filter
from gamingcreator.ui import package_jobs
from gamingcreator.ui.creation_jobs import CreationJobs

pytestmark = pytest.mark.skipif(not FFMPEG.is_file(), reason="本机未准备项目内的 FFmpeg")

FPS = 30
WIDTH = 160
HEIGHT = 90
TARGET_SECONDS = 30
SOURCE_SECONDS = 8
SAFE_MARGIN = 10
BADGE_TEXT = "试拍角标"
BADGE_CORNER = "top-left"
WATERMARK_TEXT = "GamingCreator Free"
TOPIC = "新英雄"
UNKNOWN_PARTS = ("visualQuality", "emotionalIntensity", "narrativeValue")


def _even_floor(value: int) -> int:
    return value if value % 2 == 0 else value - 1


def crop_box(width: int, height: int, margin: int) -> tuple[int, int, int, int]:
    keep = 100 - 2 * margin
    crop_w = max(2, _even_floor(width * keep // 100))
    crop_h = max(2, _even_floor(height * keep // 100))
    return (width - crop_w) // 2, (height - crop_h) // 2, crop_w, crop_h


def write_bordered_sources(footage: Path, duration: float = 1) -> list[dict[str, object]]:
    """和共用混合源一样的规格，只是画面中间是原色、四周留黑边，方便核安全区裁切。"""
    left, top, crop_w, crop_h = crop_box(WIDTH, HEIGHT, SAFE_MARGIN)
    footage.mkdir(parents=True, exist_ok=True)
    written = []
    for spec in SOURCE_SPECS:
        path = footage / spec["name"]
        command = [
            "-f",
            "lavfi",
            "-i",
            (
                f"color=c=black:s={WIDTH}x{HEIGHT}:r={spec['rate']}:d={duration},"
                f"drawbox=x={left}:y={top}:w={crop_w}:h={crop_h}:c={spec['color']}:t=fill"
            ),
        ]
        if spec["audio_hz"]:
            command += [
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={spec['audio_hz']}:sample_rate=48000:duration={duration}",
                "-c:a",
                "aac",
            ]
        if spec["vfr"]:
            command += ["-vf", "select='lt(n,8)+not(mod(n,2))'", "-fps_mode", "vfr"]
        if spec["offset"]:
            command += ["-output_ts_offset", str(spec["offset"])]
        command += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
        run_ffmpeg(command)
        written.append({**spec, "path": path})
    return written


def apply_ad_facts(sources: list[dict[str, object]]) -> None:
    for source in sources:
        facts = list(source["facts"])
        if source["color"] == "green" and "新英雄登场" not in facts:
            facts.append("新英雄登场")
        if source["color"] == "yellow" and "新英雄技能" not in facts:
            facts.append("新英雄技能")
        source["facts"] = tuple(facts)


def read_frame(path: Path, frame: int) -> bytes:
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
    if len(pixels) != WIDTH * HEIGHT * 3:
        raise RuntimeError(f"读不到第 {frame} 帧的完整画面（得到 {len(pixels)} 字节）。")
    return pixels


def rgb_at(pixels: bytes, x: int, y: int) -> tuple[int, int, int]:
    index = (y * WIDTH + x) * 3
    return (pixels[index], pixels[index + 1], pixels[index + 2])


def region_max(pixels: bytes, box: tuple[int, int, int, int], channel: int | None = None) -> int:
    x0, y0, x1, y1 = box
    highest = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            red, green, blue = rgb_at(pixels, x, y)
            value = (
                (red, green, blue)[channel] if channel is not None else (red + green + blue) // 3
            )
            if value > highest:
                highest = value
    return highest


def region_mean(pixels: bytes, box: tuple[int, int, int, int]) -> tuple[int, int, int]:
    x0, y0, x1, y1 = box
    count = (x1 - x0) * (y1 - y0)
    totals = [0, 0, 0]
    for y in range(y0, y1):
        for x in range(x0, x1):
            color = rgb_at(pixels, x, y)
            for index in range(3):
                totals[index] += color[index]
    return (totals[0] // count, totals[1] // count, totals[2] // count)


def missing_channels(color: str) -> tuple[int, ...]:
    if color == "red":
        return (1, 2)
    if color == "green":
        return (0, 2)
    if color == "blue":
        return (0, 1)
    if color == "yellow":
        return (2,)
    if color == "magenta":
        return (1,)
    return ()


def test_ad_mixed_source_safe_area_badge_and_watermark(tmp_path):
    require_space(tmp_path)
    link_tools(tmp_path)
    footage = tmp_path / "素材"
    sources = write_bordered_sources(footage, duration=SOURCE_SECONDS)
    apply_ad_facts(sources)
    border_left, border_top, crop_w, crop_h = crop_box(WIDTH, HEIGHT, SAFE_MARGIN)
    assert safe_area_crop_filter(WIDTH, HEIGHT, SAFE_MARGIN) == (
        f"crop={crop_w}:{crop_h}:{border_left}:{border_top},scale={WIDTH}:{HEIGHT}"
    )
    red_source = next(item for item in sources if item["color"] == "red")
    source_pixels = read_frame(red_source["path"], 6)
    assert sum(rgb_at(source_pixels, 2, HEIGHT // 2)) < 40, (
        "素材四周应是黑边，才能看出安全区裁切是否生效。"
    )
    assert nearest_color(rgb_at(source_pixels, WIDTH // 2, HEIGHT // 2)) == "red"

    project = tmp_path / "artifacts" / "project"
    planted = __import__("asyncio").run(plant_completed_runs(project, sources))
    by_event = {item["eventId"]: item for item in planted}
    jobs = CreationJobs(tmp_path)
    server, thread, base = start_http(tmp_path)
    products = tmp_path / "产物"
    products.mkdir()
    try:
        entitlement = http_json(base, "/api/entitlement", {"plan": "free"})
        assert entitlement["plan"] == "free"
        assert entitlement["watermark"] == WATERMARK_TEXT
        assert entitlement["billing"] == "none-local-evaluation"
        current = http_json(base, "/api/entitlement")
        assert current["plan"] == "free" and current["watermark"] == WATERMARK_TEXT

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
                    "contentType": "ad",
                    "platforms": ["bilibili"],
                    "targetDuration": TARGET_SECONDS,
                    "objective": "按广告买量模板串一条试片，核对着安全区和套餐水印",
                    "audience": "观众",
                    "tone": "清楚",
                    "mandatoryTopics": [TOPIC],
                    "exclude": [],
                },
            },
        )
        plan = wait_job(base, plan_job["jobId"])
        assert plan["status"] == "completed", plan
        report = json.loads(
            (jobs.directory(plan["jobId"]) / "result" / "plans.json").read_text(encoding="utf-8")
        )
        assert report["understandingVerified"] is False
        assert report["modeHonesty"] == "描述代理评分、非画面理解／未做人评／投放未验证"
        for name in UNKNOWN_PARTS:
            assert report["scoring"]["basis"][name] == UNKNOWN
        ad = next(item for item in plan["plans"] if item["id"] == "ad-evidence-demo")
        assert ad["mode"] == "ad"
        assert ad["modeLabel"] == "广告/买量"
        segments = ad["segments"]
        assert len(segments) >= 3
        roles = [segment["role"] for segment in segments]
        assert roles[0] == "开场钩子"
        assert roles[-1] == "号召背景"
        assert roles[1] == "卖点"
        assert all(role == "展示画面" for role in roles[2:-1])
        hook = by_event[segments[0]["eventId"]]
        assert hook["color"] == "red"
        assert by_event[segments[1]["eventId"]]["color"] == "green"
        assert segments[1]["topicUses"][0]["topic"] == TOPIC
        for segment in segments:
            for name in UNKNOWN_PARTS:
                assert segment["score"]["parts"][name] is None

        lengths = [segment["outputFrames"] for segment in segments]
        expected_starts = list(output_start_frames(tuple(lengths), tuple(0 for _ in lengths)))
        planned_frames = expected_starts[-1] + lengths[-1]
        assert planned_frames == sum(lengths)
        assert [segment["outputStartFrame"] for segment in segments] == expected_starts
        assert all(length >= 8 for length in lengths)

        render_job = http_json(
            base,
            "/api/creation/renders",
            {
                "requestId": uuid4().hex,
                "planJobId": plan["jobId"],
                "planId": ad["id"],
                "width": WIDTH,
                "height": HEIGHT,
                "safeAreaMarginPercent": SAFE_MARGIN,
                "badgeText": BADGE_TEXT,
                "badgeCorner": BADGE_CORNER,
            },
        )
        rendered = wait_job(base, render_job["jobId"], timeout=180)
        assert rendered["status"] == "completed", rendered
        result = jobs.directory(rendered["jobId"]) / "result"
        video = result / "video.mp4"
        receipt = jobs.read(result / "receipt.json")
        actual_frames = receipt.get("frames")
        probe = probe_media(video)
        video_stream = next(
            stream for stream in probe["streams"] if stream["codec_type"] == "video"
        )
        probed_frames = int(video_stream.get("nb_frames") or 0) or actual_frames
        assert actual_frames is not None
        assert abs(int(actual_frames) - planned_frames) <= 1
        assert abs(probed_frames - planned_frames) <= 1
        assert any(stream["codec_type"] == "audio" for stream in probe["streams"]), (
            "成片必须带音轨。"
        )
        assert pcm_energy(video) > 20
        assert receipt["watermark"] == WATERMARK_TEXT
        presentation = receipt["presentation"]
        assert presentation["version"] == "creation-presentation-v1"
        assert presentation["safeArea"] == {"marginPercent": SAFE_MARGIN}
        assert presentation["badge"] == {"text": BADGE_TEXT, "corner": BADGE_CORNER}
        limitations = receipt["limitations"]
        limitation_text = "；".join(limitations)
        assert "safe-area center crop then scale" in limitation_text
        assert "static corner badge overlay" in limitation_text
        assert "plan watermark overlay" in limitation_text

        overlay_checks = []
        seen = []
        badge_box = (0, 0, 56, 24)
        watermark_box = (WIDTH - 56, 0, WIDTH, 24)
        clean_box = (WIDTH - 40, HEIGHT - 24, WIDTH, HEIGHT)
        edge_box = (1, HEIGHT // 2 - 4, 8, HEIGHT // 2 + 4)
        center_box = (WIDTH // 2 - 8, HEIGHT // 2 - 8, WIDTH // 2 + 8, HEIGHT // 2 + 8)
        for start, frames, segment in zip(expected_starts, lengths, segments, strict=True):
            mid = start + frames // 2
            pixels = read_frame(video, mid)
            color = by_event[segment["eventId"]]["color"]
            center = region_mean(pixels, center_box)
            edge = region_mean(pixels, edge_box)
            clean = region_mean(pixels, clean_box)
            seen.append(
                {
                    "eventId": segment["eventId"],
                    "role": segment["role"],
                    "color": color,
                    "center": nearest_color(center),
                    "edge": nearest_color(edge),
                    "cleanCorner": nearest_color(clean),
                }
            )
            assert nearest_color(center) == color
            assert nearest_color(edge) == color, (
                "安全区裁切后，原来的黑边位置应变成镜头颜色，不能还留着黑框。",
                color,
                edge,
            )
            assert nearest_color(clean) == color
            assert sum(edge) > 80
            channels = missing_channels(color)
            if channels:
                badge_level = max(region_max(pixels, badge_box, channel) for channel in channels)
                mark_level = max(region_max(pixels, watermark_box, channel) for channel in channels)
                field_level = max(region_max(pixels, center_box, channel) for channel in channels)
                clean_level = max(region_max(pixels, clean_box, channel) for channel in channels)
                assert badge_level > 150, (
                    "左上角色标应是不透明白字，会抬高背景里没有的通道。",
                    color,
                    badge_level,
                )
                assert mark_level > field_level + 20, (
                    "右上角套餐水印应按官方规则画在画面上，不能只写在回执里。",
                    color,
                    mark_level,
                    field_level,
                )
                assert clean_level < 60, ("右下角不应被角标或水印挡住。", color, clean_level)
                overlay_checks.append(
                    {
                        "eventId": segment["eventId"],
                        "color": color,
                        "badgeMissingChannel": badge_level,
                        "watermarkMissingChannel": mark_level,
                        "centerMissingChannel": field_level,
                        "cleanMissingChannel": clean_level,
                    }
                )
        assert [item["center"] for item in seen] == [
            by_event[segment["eventId"]]["color"] for segment in segments
        ]
        assert overlay_checks, "至少要有一段纯色镜头能把角标和水印从画面里核出来。"

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
        profile = shrink_profile(package_jobs.profiles()["profiles"][0])
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
        assert facts["publicationEligibility"] == "unverified"
        assert facts["localChecks"] == "pass"
        zip_path = jobs.package_file(package["jobId"], "package.zip").path
        with zipfile.ZipFile(zip_path) as archive:
            assert set(archive.namelist()) == set(package_jobs.FILES)
            archive.extractall(products)
        package_video = products / "video.mp4"
        if not package_video.is_file():
            with zipfile.ZipFile(zip_path) as archive:
                archive.extract("video.mp4", products)
        package_probe = probe_media(package_video)
        package_video_stream = next(
            stream for stream in package_probe["streams"] if stream["codec_type"] == "video"
        )
        package_frames = int(
            package_video_stream.get("nb_frames") or facts["validation"]["facts"]["frames"]
        )
        assert abs(package_frames - planned_frames) <= 1
        assert any(stream["codec_type"] == "audio" for stream in package_probe["streams"])

        summary = {
            "mode": "广告/买量",
            "planId": ad["id"],
            "understandingVerified": report["understandingVerified"],
            "modeHonesty": report["modeHonesty"],
            "unknownScoreParts": {name: report["scoring"]["basis"][name] for name in UNKNOWN_PARTS},
            "deliveryClaim": "投放未验证，不冒称实际投放效果",
            "entitlement": {
                "plan": current["plan"],
                "billing": current["billing"],
                "watermark": current["watermark"],
                "note": "隔离目录里用官方 /api/entitlement 切到 Free 本地评估，未改套餐门，也未伪造许可",
            },
            "presentation": presentation,
            "watermark": receipt["watermark"],
            "limitations": limitations,
            "planJobId": plan["jobId"],
            "renderJobId": rendered["jobId"],
            "publicationJobId": published["jobId"],
            "packageJobId": package["jobId"],
            "plannedFrames": planned_frames,
            "renderFrames": actual_frames,
            "packageFrames": package_frames,
            "publicationEligibility": facts["publicationEligibility"],
            "safeAreaCrop": {
                "marginPercent": SAFE_MARGIN,
                "box": {"x": border_left, "y": border_top, "width": crop_w, "height": crop_h},
            },
            "segmentOrder": [
                {
                    "eventId": segment["eventId"],
                    "role": segment["role"],
                    "color": by_event[segment["eventId"]]["color"],
                    "source": by_event[segment["eventId"]]["name"],
                    "outputStartFrame": expected_starts[index],
                    "outputFrames": lengths[index],
                    "scoreTotal": segment["score"]["total"],
                }
                for index, segment in enumerate(segments)
            ],
            "colorChecks": seen,
            "overlayChecks": overlay_checks,
            "renderVideo": str(video),
            "packageZip": str(zip_path),
        }
        (products / "核对.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        enforce_product_caps(products)
        assert zip_path.stat().st_size < MAX_PRODUCT_BYTES
    finally:
        stop_http(server, thread)
