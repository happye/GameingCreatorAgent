"""F03：攻略模式混合源走真实 HTTP 计划、编辑决策、成片和七文件包。

来源脚本只保留已保存的画面摘要，缺口和未知评分保持官方结果，不编造游戏事实或创意质量分。
"""

import json
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

from gamingcreator.application.material_scoring import UNKNOWN
from gamingcreator.ui import package_jobs
from gamingcreator.ui.creation_jobs import CreationJobs

pytestmark = pytest.mark.skipif(not FFMPEG.is_file(), reason="本机未准备项目内的 FFmpeg")

# 摘要里没有这个主题，用来确认缺口提示会留下来，而不会被写进脚本。
MISSING_TOPIC = "隐藏结局"
INVENTED = ("冷却时间是10秒", "背景故事", "画面理解已验证", "创意质量优秀", "人评已通过")
UNKNOWN_PARTS = ("visualQuality", "emotionalIntensity", "narrativeValue")


def test_guide_mixed_source_keeps_scripts_gaps_and_unknown_scores(tmp_path):
    require_space(tmp_path)
    link_tools(tmp_path)
    footage = tmp_path / "素材"
    sources = write_mixed_sources(footage, duration=2)
    project = tmp_path / "artifacts" / "project"
    planted = __import__("asyncio").run(plant_completed_runs(project, sources))
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
                "contentType": "guide",
                "platforms": ["bilibili"],
                "targetDuration": 8,
                "objective": "按步骤说明怎么过关",
                "audience": "新手",
                "tone": "清楚",
                "mandatoryTopics": [MISSING_TOPIC],
                "exclude": [],
            },
        }
        plan_job = http_json(base, "/api/creation/plans", plan_request)
        plan = wait_job(base, plan_job["jobId"])
        assert plan["status"] == "completed", plan
        report = json.loads(
            (jobs.directory(plan["jobId"]) / "result" / "plans.json").read_text(encoding="utf-8")
        )
        assert report["understandingVerified"] is False
        assert report["modeHonesty"] == "描述代理评分、非画面理解／未做人评／投放未验证"
        scoring = report["scoring"]
        assert scoring["version"] == "material-score-v1"
        for name in UNKNOWN_PARTS:
            assert scoring["basis"][name] == UNKNOWN
        guide = next(item for item in plan["plans"] if item["id"] == "guide-steps")
        assert guide["mode"] == "guide"
        assert guide["modeLabel"] == "攻略"
        assert guide["scriptStatus"] == "saved-descriptions-draft-human-review-required"
        assert guide["honesty"] == "描述代理评分、非画面理解／未做人评／投放未验证"
        assert isinstance(guide["gaps"], list)
        assert (
            guide["gaps"]
            == report["plans"][
                next(i for i, item in enumerate(report["plans"]) if item["id"] == "guide-steps")
            ]["gaps"]
        )
        assert guide.get("ready") is True
        segments = guide["segments"]
        assert len(segments) >= 3
        roles = [segment["role"] for segment in segments]
        assert roles == [f"第{i}步" for i in range(1, len(segments) + 1)]
        missing_note = f"主题未在画面摘要中找到：{MISSING_TOPIC}（可在旁白或字幕里讲，或补充画面）"
        assert missing_note in guide["advisories"]
        for segment in segments:
            planted_item = by_event[segment["eventId"]]
            expected_script = "；".join(planted_item["facts"])
            assert segment["scriptDraft"] == expected_script
            assert MISSING_TOPIC not in segment["scriptDraft"]
            for phrase in INVENTED:
                assert phrase not in segment["scriptDraft"]
            parts = segment["score"]["parts"]
            for name in UNKNOWN_PARTS:
                assert parts[name] is None
        blob = json.dumps(guide, ensure_ascii=False)
        for phrase in INVENTED:
            assert phrase not in blob

        render_job = http_json(
            base,
            "/api/creation/renders",
            {
                "requestId": uuid4().hex,
                "planJobId": plan["jobId"],
                "planId": "guide-steps",
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
            packaged_text = " ".join(
                archive.read(name).decode("utf-8", "replace")
                for name in archive.namelist()
                if name.endswith((".txt", ".json"))
            )
        for phrase in INVENTED:
            assert phrase not in packaged_text
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
        summary = {
            "mode": "攻略",
            "planId": "guide-steps",
            "scriptStatus": guide["scriptStatus"],
            "understandingVerified": report["understandingVerified"],
            "gaps": guide["gaps"],
            "advisories": guide["advisories"],
            "unknownScoreParts": {name: scoring["basis"][name] for name in UNKNOWN_PARTS},
            "planJobId": plan["jobId"],
            "renderJobId": rendered["jobId"],
            "publicationJobId": published["jobId"],
            "packageJobId": package["jobId"],
            "plannedFrames": planned_frames,
            "renderFrames": actual_frames,
            "packageFrames": package_frames,
            "publicationEligibility": facts["publicationEligibility"],
            "segmentOrder": [
                {
                    "eventId": segment["eventId"],
                    "role": segment.get("role"),
                    "outputFrames": segment["outputFrames"],
                    "color": by_event[segment["eventId"]]["color"],
                    "source": by_event[segment["eventId"]]["name"],
                    "scriptDraft": segment["scriptDraft"],
                }
                for segment in segments
            ],
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
