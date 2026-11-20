"""F09 之后的 F10：用现有 B 站本地导出配置，单独打一份横屏七件套。

字幕、封面和文案都要对应这条成片的输出时钟和发布稿，不能拿抖音或快手包改后缀冒充。
不改预设里的限值，不调用平台发布接口。
"""

from __future__ import annotations

import json
import zipfile
from fractions import Fraction
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
from gamingcreator.domain.creation_subtitles import SubtitleCue, parse_srt, quantize_srt
from gamingcreator.domain.platform_profile import profile_digest
from gamingcreator.ui import package_jobs
from gamingcreator.ui.creation_jobs import CreationJobs

pytestmark = pytest.mark.skipif(not FFMPEG.is_file(), reason="本机未准备项目内的 FFmpeg")

PLATFORM = "bilibili"
OTHER_PROFILE_SHA256 = {
    "e7773c8ddfd24b38a88edf29d0a1f318a24480285f852a5ddabe72c41706f71c",  # douyin
    "1888c3b4704911ef45894319185415a702703fd5790630ba1384c34a15760c37",  # kuaishou
}
COLOR_ZH = {
    "red": "红",
    "green": "绿",
    "blue": "蓝",
    "yellow": "黄",
    "magenta": "品红",
}


def test_bilibili_profile_package_cites_this_cut(tmp_path):
    require_space(tmp_path)
    link_tools(tmp_path)
    profile = official_profile(PLATFORM)
    assert profile["Source"]["label"] == "用户可编辑本地导出配置，非官方规则"
    assert profile["Fields"]["video"]["width"] == 1280
    assert profile["Fields"]["video"]["height"] == 720
    assert profile["Fields"]["video"]["fit"] == "pad"
    assert profile["Fields"]["cover"]["width"] == 1280
    assert profile["Fields"]["cover"]["height"] == 720
    assert "bitrate" not in profile["Fields"]["video"]
    assert profile["Fields"]["limits"]["maxDurationMs"] == 36_000_000
    assert profile["Fields"]["limits"]["maxBytes"] is None
    assert profile["Fields"]["limits"]["minDurationMs"] is None
    assert profile["Fields"]["limits"]["titleMaxChars"] is None
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
                    "objective": "打一份 B 站本地导出配置的真实横屏平台包",
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
        captions = [
            f"{segment['role']}（{COLOR_ZH[by_event[row['eventId']]['color']]}）"
            for segment, row in zip(segments, rows, strict=True)
        ]

        revision_job = http_json(
            base,
            "/api/creation/revisions",
            {
                "requestId": uuid4().hex,
                "parentJobId": plan["jobId"],
                "planId": "showcase",
                "expectedParentReceiptSha256": snapshot["expectedParentReceiptSha256"],
                "clips": [
                    {
                        "clipId": row["clipId"],
                        "startUs": row["startUs"],
                        "endUs": row["endUs"],
                        "speed": {"numerator": 1, "denominator": 1},
                    }
                    for row in rows
                ],
                "subtitleOverrides": [
                    {"clipId": row["clipId"], "text": text}
                    for row, text in zip(rows, captions, strict=True)
                ],
            },
        )
        revised = wait_job(base, revision_job["jobId"])
        assert revised["status"] == "completed", revised
        revision_edl = jobs.read(
            jobs.directory(revision_job["jobId"]) / "result" / "edit-decision.json"
        )
        revised_rows = revision_edl["segments"]
        expected_starts = [row["outputStartFrame"] for row in revised_rows]
        expected_frames = [row["outputFrames"] for row in revised_rows]
        assert expected_starts == [row["outputStartFrame"] for row in rows]
        assert expected_frames == [row["outputFrames"] for row in rows]

        render_job = http_json(
            base,
            "/api/creation/renders",
            {
                "requestId": uuid4().hex,
                "revisionJobId": revision_job["jobId"],
                "width": RENDER_WIDTH,
                "height": RENDER_HEIGHT,
                "subtitleMode": "sidecar",
            },
        )
        rendered = wait_job(base, render_job["jobId"], timeout=180)
        assert rendered["status"] == "completed", rendered
        result = jobs.directory(rendered["jobId"]) / "result"
        render_video = result / "video.mp4"
        render_receipt = jobs.read(result / "receipt.json")
        assert abs(int(render_receipt["frames"]) - planned_frames) <= 1
        assert pcm_energy(render_video) > 20
        assert render_receipt.get("subtitles", {}).get("mode") == "sidecar"
        assert render_receipt["subtitles"].get("cueCount") == len(captions)
        srt_path = result / "subtitles.srt"
        assert srt_path.is_file(), "外挂字幕必须按这条成片的输出时钟落到字幕文件里。"
        expected_cues = tuple(
            SubtitleCue(
                Fraction(start, FPS),
                Fraction(start + frames, FPS),
                text,
                "user-written",
                index,
            )
            for index, (start, frames, text) in enumerate(
                zip(expected_starts, expected_frames, captions, strict=True)
            )
        )
        saved_cues = parse_srt(srt_path.read_text(encoding="utf-8"))
        quantized = quantize_srt(expected_cues)
        assert [cue.text for cue in saved_cues] == captions
        assert [(cue.start, cue.end) for cue in saved_cues] == [
            (cue.start, cue.end) for cue in quantized
        ]

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
            assert "subtitles.srt" not in names
            archive.extractall(products)
        package_video = products / "video.mp4"
        if not package_video.is_file():
            with zipfile.ZipFile(zip_path) as archive:
                archive.extract("video.mp4", products)
        (products / "subtitles.srt").write_text(
            srt_path.read_text(encoding="utf-8"), encoding="utf-8"
        )
        for name in ("title.txt", "description.txt", "tags.json"):
            assert (products / name).read_bytes() == (publication_dir / name).read_bytes()
            assert (products / name).stat().st_size > 0
        # 文案应提到这条成片的模式，不能是空稿或别的平台留下的稿。
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
        assert recorded["width"] == 1280 and recorded["height"] == 720
        assert recorded["codec"] == "h264" and recorded["pixelFormat"] == "yuv420p"
        assert abs(recorded["frames"] - planned_frames) <= 1
        assert recorded["durationMs"] <= 36_000_000
        assert validation["checks"]["width"] == "pass"
        assert validation["checks"]["height"] == "pass"
        assert validation["checks"]["codec"] == "pass"
        assert validation["checks"]["pixelFormat"] == "pass"
        assert validation["checks"]["frames"] == "pass"
        assert validation["checks"]["fps"] == "pass"
        assert validation["checks"]["maxDurationMs"] == "pass"
        for key in (
            "maxBytes",
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
        assert platform_doc["profileSha256"] not in OTHER_PROFILE_SHA256
        assert platform_doc["profile"] == profile

        cover = products / "cover.png"
        assert png_size(cover) == (1280, 720)
        # 16:9 横屏铺满，上下不应再留下竖屏那种大黑边。
        mid = min(planned_frames // 2, recorded["frames"] - 1)
        video_pixels = read_frame(package_video, mid, 1280, 720)
        cover_pixels = read_frame(cover, 0, 1280, 720)
        top = region_mean(video_pixels, 1280, (80, 8, 240, 40))
        bottom = region_mean(video_pixels, 1280, (80, 680, 240, 712))
        center = region_mean(video_pixels, 1280, (600, 330, 680, 390))
        cover_top = region_mean(cover_pixels, 1280, (80, 8, 240, 40))
        cover_center = region_mean(cover_pixels, 1280, (600, 330, 680, 390))
        assert sum(top) > 80 and sum(bottom) > 80, (
            "B 站横屏应铺满 1280×720，不能还是竖屏黑边。",
            top,
            bottom,
        )
        assert sum(cover_top) > 80
        assert nearest_color(center) in {item["color"] for item in planted}
        hook_color = by_event[revised_rows[0]["eventId"]]["color"]
        assert nearest_color(cover_center) == hook_color
        assert snap["coverFrame"] == 0
        seen = []
        for row, text in zip(revised_rows, captions, strict=True):
            start = row["outputStartFrame"]
            frames = row["outputFrames"]
            frame = min(start + frames // 2, recorded["frames"] - 1)
            pixels = read_frame(package_video, frame, 1280, 720)
            color = nearest_color(region_mean(pixels, 1280, (600, 330, 680, 390)))
            seen.append(
                {
                    "eventId": row["eventId"],
                    "role": row["role"] if "role" in row else None,
                    "color": color,
                    "caption": text,
                }
            )
            assert color == by_event[row["eventId"]]["color"]
            assert sum(region_mean(pixels, 1280, (80, 8, 240, 40))) > 80

        summary = {
            "platform": PLATFORM,
            "profileSource": profile["Source"],
            "profileSha256": platform_doc["profileSha256"],
            "notOtherPlatformPackage": platform_doc["profileSha256"] not in OTHER_PROFILE_SHA256,
            "note": "本地导出配置，不是官方 B 站规则；最长时长用预设原值，没有写明的规则保持未知",
            "planId": "showcase",
            "planJobId": plan["jobId"],
            "revisionJobId": revision_job["jobId"],
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
            "presetLimits": {"maxDurationMs": profile["Fields"]["limits"]["maxDurationMs"]},
            "subtitleMode": "sidecar",
            "captions": captions,
            "subtitleTimes": [
                {"text": cue.text, "start": str(cue.start), "end": str(cue.end)}
                for cue in saved_cues
            ],
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
                    "caption": text,
                }
                for row, text in zip(revised_rows, captions, strict=True)
            ],
            "colorChecks": seen,
            "landscapeCheck": {
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
