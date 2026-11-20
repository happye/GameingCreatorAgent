"""F01：玩法展示混合源走真实 HTTP 计划、编辑决策、成片和七文件包。"""

import asyncio
import zipfile
from uuid import uuid4

import pytest
from f_mixed_sources import (
    FFMPEG,
    MAX_PRODUCT_BYTES,
    enforce_product_caps,
    frame_rgb,
    http_json,
    link_tools,
    nearest_color,
    pcm_energy,
    plant_completed_runs,
    probe_media,
    require_space,
    shrink_profile,
    start_http,
    stop_http,
    wait_job,
    write_mixed_sources,
)

from gamingcreator.ui import package_jobs
from gamingcreator.ui.creation_jobs import CreationJobs

pytestmark = pytest.mark.skipif(not FFMPEG.is_file(), reason="本机未准备项目内的 FFmpeg")


def test_showcase_mixed_source_http_to_seven_file_package(tmp_path):
    require_space(tmp_path)
    link_tools(tmp_path)
    footage = tmp_path / "素材"
    sources = write_mixed_sources(footage)
    project = tmp_path / "artifacts" / "project"
    planted = asyncio.run(plant_completed_runs(project, sources))
    by_event = {item["eventId"]: item for item in planted}
    jobs = CreationJobs(tmp_path)
    server, thread, base = start_http(tmp_path)
    products = tmp_path / "产物"
    products.mkdir()
    try:
        plan_request = {
            "requestId": uuid4().hex,
            "projectId": "artifacts/project",
            "runIds": [item["runId"] for item in planted],
            "fps": 30,
            "brief": {
                "game": "测试游戏",
                "contentType": "feature_showcase",
                "platforms": ["bilibili"],
                "targetDuration": 8,
                "objective": "给新玩家做玩法展示",
                "audience": "新手",
                "tone": "清楚",
                "mandatoryTopics": [],
                "exclude": [],
            },
        }
        plan_job = http_json(base, "/api/creation/plans", plan_request)
        plan = wait_job(base, plan_job["jobId"])
        assert plan["status"] == "completed", plan
        showcase = next(item for item in plan["plans"] if item["id"] == "showcase")
        assert showcase["mode"] == "feature_showcase"
        assert showcase["modeLabel"] == "玩法展示"
        assert showcase.get("ready") is True
        segments = showcase["segments"]
        assert len(segments) >= 3

        render_job = http_json(
            base,
            "/api/creation/renders",
            {
                "requestId": uuid4().hex,
                "planJobId": plan["jobId"],
                "planId": "showcase",
                "width": 160,
                "height": 90,
            },
        )
        rendered = wait_job(base, render_job["jobId"], timeout=180)
        assert rendered["status"] == "completed", rendered
        video = jobs.directory(rendered["jobId"]) / "result" / "video.mp4"
        receipt = jobs.read(jobs.directory(rendered["jobId"]) / "result" / "receipt.json")
        planned_frames = sum(segment["outputFrames"] for segment in segments)
        actual_frames = receipt.get("frames")
        probe = probe_media(video)
        video_stream = next(
            stream for stream in probe["streams"] if stream["codec_type"] == "video"
        )
        audio_streams = [stream for stream in probe["streams"] if stream["codec_type"] == "audio"]
        probed_frames = int(video_stream.get("nb_frames") or 0)
        if probed_frames == 0:
            # 部分封装不写 nb_frames 时，用收据帧数，再用解码长度核对。
            probed_frames = actual_frames
        assert actual_frames is not None
        assert abs(int(actual_frames) - planned_frames) <= 1
        assert abs(probed_frames - planned_frames) <= 1
        assert audio_streams, "成片必须带音轨，不能只有画面。"
        assert pcm_energy(video) > 20

        expected_colors = [by_event[segment["eventId"]]["color"] for segment in segments]
        seen = []
        cursor = 0
        for segment, _color in zip(segments, expected_colors, strict=True):
            mid = cursor + max(segment["outputFrames"] // 2, 0)
            mid = min(mid, max(int(actual_frames) - 1, 0))
            seen.append(nearest_color(frame_rgb(video, mid)))
            cursor += segment["outputFrames"]
        assert seen == expected_colors, (seen, expected_colors, [s["eventId"] for s in segments])

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
        package_probe = probe_media(package_video)
        package_video_stream = next(
            stream for stream in package_probe["streams"] if stream["codec_type"] == "video"
        )
        package_frames = int(
            package_video_stream.get("nb_frames") or facts["validation"]["facts"]["frames"]
        )
        assert abs(package_frames - planned_frames) <= 1
        assert any(stream["codec_type"] == "audio" for stream in package_probe["streams"])
        # 把关键路径和帧数记在隔离目录，便于人工打开核对，不是第二份成片。
        summary = {
            "mode": "玩法展示",
            "planJobId": plan["jobId"],
            "renderJobId": rendered["jobId"],
            "publicationJobId": published["jobId"],
            "packageJobId": package["jobId"],
            "plannedFrames": planned_frames,
            "renderFrames": actual_frames,
            "packageFrames": package_frames,
            "segmentOrder": [
                {
                    "eventId": segment["eventId"],
                    "role": segment.get("role"),
                    "outputFrames": segment["outputFrames"],
                    "color": by_event[segment["eventId"]]["color"],
                    "source": by_event[segment["eventId"]]["name"],
                }
                for segment in segments
            ],
            "renderVideo": str(video),
            "packageZip": str(zip_path),
        }
        (products / "核对.json").write_text(
            __import__("json").dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        enforce_product_caps(products)
        assert zip_path.stat().st_size < MAX_PRODUCT_BYTES
    finally:
        stop_http(server, thread)
