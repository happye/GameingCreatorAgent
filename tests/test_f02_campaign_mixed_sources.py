"""F02：活动投稿混合源走真实 HTTP，并套用现有活动规则约束。"""

import asyncio
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
from test_activity_rules import RULES

from gamingcreator.ui import package_jobs
from gamingcreator.ui.creation_jobs import CreationJobs

pytestmark = pytest.mark.skipif(not FFMPEG.is_file(), reason="本机未准备项目内的 FFmpeg")

# 与官方活动规则里的必带话题对应，供活动投稿结构挑镜头。
CAMPAIGN_FACTS = (
    ("角色奔跑",),
    ("新英雄登场", "技能展示"),
    ("代号Atom新版本", "限时活动入口"),
    ("星际奔跑",),
    ("技能连招",),
    ("地图互动",),
    ("结算画面",),
)


def _vertical_profile():
    for profile in package_jobs.profiles()["profiles"]:
        video = profile["Fields"]["video"]
        if video["height"] > video["width"]:
            return shrink_profile(profile)
    raise AssertionError("没有可用的竖屏平台配置。")


def test_campaign_mixed_source_respects_extracted_rules(tmp_path):
    require_space(tmp_path)
    link_tools(tmp_path)
    sources = write_mixed_sources(tmp_path / "素材", duration=7, extras=True)
    for source, facts in zip(sources, CAMPAIGN_FACTS, strict=True):
        source["facts"] = facts
    project = tmp_path / "artifacts" / "project"
    planted = asyncio.run(plant_completed_runs(project, sources))
    by_event = {item["eventId"]: item for item in planted}
    jobs = CreationJobs(tmp_path)
    server, thread, base = start_http(tmp_path)
    products = tmp_path / "产物"
    products.mkdir()
    try:
        rules = http_json(base, "/api/creation/activity-rules", {"text": RULES})
        assert rules["status"] == "extracted-human-check-required"
        fields = rules["fields"]
        topics = [item["value"] for item in fields["requiredTopics"]]
        platforms = [item["value"] for item in fields["platforms"]]
        minimum = fields["minDurationSeconds"]["value"]
        maximum = fields["maxDurationSeconds"]["value"]
        assert topics == ["代号Atom新版本", "星际奔跑"]
        assert minimum == 30 and maximum == 180
        assert "投稿成功" not in json.dumps(rules, ensure_ascii=False)

        plan_job = http_json(
            base,
            "/api/creation/plans",
            {
                "requestId": uuid4().hex,
                "projectId": "artifacts/project",
                "runIds": [item["runId"] for item in planted],
                "fps": 30,
                "brief": {
                    "game": fields["name"]["value"],
                    "contentType": "campaign",
                    "platforms": platforms,
                    "targetDuration": int(minimum),
                    "objective": "按提取到的活动规则做投稿成片",
                    "audience": "活动观众",
                    "tone": "清楚",
                    "mandatoryTopics": topics,
                    "exclude": [],
                },
            },
        )
        plan = wait_job(base, plan_job["jobId"], timeout=120)
        assert plan["status"] == "completed", plan
        campaign = next(item for item in plan["plans"] if item["id"] == "campaign-topics")
        assert campaign["modeLabel"] == "活动投稿"
        assert campaign.get("ready") is True
        roles = [segment.get("role") for segment in campaign["segments"]]
        assert "活动主题：代号Atom新版本" in roles
        assert "活动主题：星际奔跑" in roles
        segments = campaign["segments"]
        planned_frames = sum(segment["outputFrames"] for segment in segments)
        planned_seconds = planned_frames / 30
        assert minimum <= planned_seconds <= maximum

        render_job = http_json(
            base,
            "/api/creation/renders",
            {
                "requestId": uuid4().hex,
                "planJobId": plan["jobId"],
                "planId": "campaign-topics",
                "width": 90,
                "height": 160,
            },
        )
        rendered = wait_job(base, render_job["jobId"], timeout=300)
        assert rendered["status"] == "completed", rendered
        video = jobs.directory(rendered["jobId"]) / "result" / "video.mp4"
        receipt = jobs.read(jobs.directory(rendered["jobId"]) / "result" / "receipt.json")
        actual_frames = receipt["frames"]
        probe = probe_media(video)
        video_stream = next(
            stream for stream in probe["streams"] if stream["codec_type"] == "video"
        )
        probed_frames = int(video_stream.get("nb_frames") or actual_frames)
        assert abs(int(actual_frames) - planned_frames) <= 1
        assert abs(probed_frames - planned_frames) <= 1
        assert any(stream["codec_type"] == "audio" for stream in probe["streams"])
        assert pcm_energy(video) > 20
        expected = [by_event[segment["eventId"]]["color"] for segment in segments]
        seen = []
        cursor = 0
        for segment in segments:
            mid = min(cursor + max(segment["outputFrames"] // 2, 0), int(actual_frames) - 1)
            seen.append(nearest_color(frame_rgb(video, mid)))
            cursor += segment["outputFrames"]
        assert seen == expected, (seen, expected, roles)

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
        published = wait_job(base, publication["jobId"], timeout=180)
        assert published["status"] == "completed", published
        snap = jobs.publication(published["jobId"])
        packed = http_json(
            base,
            "/api/creation/packages",
            {
                "requestId": uuid4().hex,
                "publicationJobId": published["jobId"],
                "expectedPublicationReceiptSha256": snap["publicationReceiptSha256"],
                "profile": _vertical_profile(),
            },
        )
        package = wait_job(base, packed["jobId"], timeout=300)
        assert package["status"] == "completed", package
        facts = package["package"]
        assert facts["publicationEligibility"] == "unverified"
        blob = json.dumps(facts, ensure_ascii=False)
        assert "投稿成功" not in blob
        # 明确保留未核，不把本地通过当成平台已核。
        assert facts["validation"]["platformRules"] == "unknown"
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
        summary = {
            "mode": "活动投稿",
            "rulesStatus": rules["status"],
            "requiredTopics": topics,
            "durationLimits": [minimum, maximum],
            "plannedSeconds": planned_seconds,
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
