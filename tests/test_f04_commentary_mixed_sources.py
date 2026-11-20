"""F04：解说模式混合源走真实 HTTP，带本机旁白和背景音乐，核对位置、时长和闪避。

不用云端语音。闪避和时值按成片音频测量，不只看回执。
"""

from __future__ import annotations

import asyncio
import json
import math
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
    plant_completed_runs,
    probe_media,
    require_space,
    run_ffmpeg,
    shrink_profile,
    start_http,
    stop_http,
    wait_job,
    write_mixed_sources,
)
from test_creation_audio_render import amplitude, pcm

from gamingcreator.application.providers import CancellationContext
from gamingcreator.infrastructure.music_library import MusicLibrary
from gamingcreator.ui import package_jobs
from gamingcreator.ui.creation_jobs import CreationJobs

pytestmark = pytest.mark.skipif(not FFMPEG.is_file(), reason="本机未准备项目内的 FFmpeg")

BGM_HZ = 2000
NARRATION_TEXT = "本机解说。"


def _rms(samples, start, end):
    values = samples[round(start * 48000) : round(end * 48000)]
    if not values:
        raise RuntimeError("取样窗口是空的，无法量音频。")
    return math.sqrt(sum(value * value for value in values) / len(values))


def _residual_rms(samples, start, end, hz=BGM_HZ):
    # 去掉固定背景音后，剩下的主要是旁白；总能量在闪避时反而可能下降。
    values = samples[round(start * 48000) : round(end * 48000)]
    if len(values) < 32:
        raise RuntimeError("取样窗口太短，无法去掉背景音再量旁白。")
    rate = 48000
    real = sum(
        value * math.cos(2 * math.pi * hz * index / rate) for index, value in enumerate(values)
    )
    imag = sum(
        value * math.sin(2 * math.pi * hz * index / rate) for index, value in enumerate(values)
    )
    leftover = 0.0
    scale = 2 / len(values)
    for index, value in enumerate(values):
        tone = scale * (
            real * math.cos(2 * math.pi * hz * index / rate)
            + imag * math.sin(2 * math.pi * hz * index / rate)
        )
        leftover += (value - tone) ** 2
    return math.sqrt(leftover / len(values))


def _pick_local_voice(listed):
    voices = [
        voice
        for voice in listed.get("voices", [])
        if not voice.get("paid")
        and not str(voice.get("voiceId", "")).startswith("cosyvoice:")
        and "804" in str(voice.get("language", "")).split(";")
    ]
    if not voices:
        voices = [
            voice
            for voice in listed.get("voices", [])
            if not voice.get("paid") and not str(voice.get("voiceId", "")).startswith("cosyvoice:")
        ]
    return voices[0] if voices else None


def test_commentary_mixed_source_local_narration_bgm_and_ducking(tmp_path):
    require_space(tmp_path)
    link_tools(tmp_path)
    footage = tmp_path / "素材"
    sources = write_mixed_sources(footage, duration=3)
    project = tmp_path / "artifacts" / "project"
    planted = asyncio.run(plant_completed_runs(project, sources))
    by_event = {item["eventId"]: item for item in planted}
    jobs = CreationJobs(tmp_path)
    bgm_path = footage / "背景音乐.wav"
    run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={BGM_HZ}:sample_rate=48000:duration=20",
            str(bgm_path),
        ]
    )
    track = asyncio.run(
        MusicLibrary(tmp_path).register(
            bgm_path,
            "隔离测试用固定音调",
            "F04 隔离目录里生成的测试音调，不是商用曲库。",
            "test_only",
            None,
            CancellationContext("f04-bgm", 60),
        )
    )
    assert track.license_status == "test_only"
    server, thread, base = start_http(tmp_path)
    products = tmp_path / "产物"
    products.mkdir()
    try:
        listed = http_json(base, "/api/creation/voices")
        voice = _pick_local_voice(listed)
        if voice is None:
            pytest.skip("本机没有可用的本地语音，F04 不能实跑旁白。")
        assert not voice.get("paid")
        assert not str(voice["voiceId"]).startswith("cosyvoice:")

        plan_job = http_json(
            base,
            "/api/creation/plans",
            {
                "requestId": uuid4().hex,
                "projectId": "artifacts/project",
                "runIds": [item["runId"] for item in planted],
                "fps": 30,
                "brief": {
                    "game": "测试游戏",
                    "contentType": "commentary",
                    "platforms": ["bilibili"],
                    "targetDuration": 15,
                    "objective": "用本机旁白解说这段玩法",
                    "audience": "玩家",
                    "tone": "清楚",
                    "mandatoryTopics": [],
                    "exclude": [],
                },
            },
        )
        plan = wait_job(base, plan_job["jobId"])
        assert plan["status"] == "completed", plan
        commentary = next(item for item in plan["plans"] if item["id"] == "commentary-segments")
        assert commentary["mode"] == "commentary"
        assert commentary["modeLabel"] == "游戏解说"
        segments = commentary["segments"]
        assert len(segments) >= 3
        planned_frames = sum(segment["outputFrames"] for segment in segments)

        narrated = http_json(
            base,
            "/api/creation/narrations",
            {
                "requestId": uuid4().hex,
                "projectId": "artifacts/project",
                "text": NARRATION_TEXT,
                "voiceId": voice["voiceId"],
            },
        )
        narration = wait_job(base, narrated["jobId"], timeout=180)
        assert narration["status"] == "completed", narration
        asset = narration["narrationAsset"]
        assert asset["voice"]["voiceId"] == voice["voiceId"]
        assert asset["text"] == NARRATION_TEXT
        assert not str(asset["voice"]["voiceId"]).startswith("cosyvoice:")
        duration = float(asset["durationSeconds"])
        assert duration > 0.2
        silent = next(
            (
                segment
                for segment in segments
                if by_event[segment["eventId"]].get("audio_hz") is None
            ),
            None,
        )
        narr_frames = math.ceil(duration * 30)
        max_start = planned_frames - narr_frames - 1
        if max_start < 0:
            pytest.fail("旁白比成片还长，官方不会自动截断，不能硬塞进这条实例。")
        start_frame = 30
        if silent is not None:
            # 尽量把旁白放进无源声的镜头里，前后留一点空档，避免和下一段有声音的镜头叠在一起。
            pad = 10
            room = silent["outputFrames"]
            if narr_frames + 2 * pad <= room:
                start_frame = silent["outputStartFrame"] + pad
            elif narr_frames + pad <= room:
                start_frame = silent["outputStartFrame"] + 3
            else:
                start_frame = silent["outputStartFrame"]
        start_frame = min(max(start_frame, 0), max_start)

        snapshot = jobs.edit(plan["jobId"], "commentary-segments")
        revision_job = http_json(
            base,
            "/api/creation/revisions",
            {
                "requestId": uuid4().hex,
                "parentJobId": plan["jobId"],
                "planId": "commentary-segments",
                "expectedParentReceiptSha256": snapshot["expectedParentReceiptSha256"],
                "clips": [
                    {
                        "clipId": row["clipId"],
                        "startUs": row["startUs"],
                        "outputFrames": row["outputFrames"],
                    }
                    for row in snapshot["clips"]
                ],
                "audioMix": {
                    "bgm": {
                        "trackId": track.track_id,
                        "trackReceiptSha256": track.receipt_sha256,
                        "gainDb": 0,
                    },
                    "sourceGainDb": 0,
                    "ducking": "source-v1",
                },
                "narration": {
                    "assetJobId": asset["assetJobId"],
                    "receiptSha256": asset["receiptSha256"],
                    "startFrame": start_frame,
                    "gainDb": 0,
                    "ducking": "narration-v1",
                },
            },
        )
        revised = wait_job(base, revision_job["jobId"])
        assert revised["status"] == "completed", revised

        render_job = http_json(
            base,
            "/api/creation/renders",
            {
                "requestId": uuid4().hex,
                "revisionJobId": revision_job["jobId"],
                "width": 160,
                "height": 90,
            },
        )
        rendered = wait_job(base, render_job["jobId"], timeout=180)
        assert rendered["status"] == "completed", rendered
        video = jobs.directory(rendered["jobId"]) / "result" / "video.mp4"
        receipt = jobs.read(jobs.directory(rendered["jobId"]) / "result" / "receipt.json")
        actual_frames = receipt.get("frames")
        probe = probe_media(video)
        video_stream = next(
            stream for stream in probe["streams"] if stream["codec_type"] == "video"
        )
        audio_streams = [stream for stream in probe["streams"] if stream["codec_type"] == "audio"]
        probed_frames = int(video_stream.get("nb_frames") or 0) or actual_frames
        assert actual_frames is not None
        assert abs(int(actual_frames) - planned_frames) <= 1
        assert abs(probed_frames - planned_frames) <= 1
        assert audio_streams, "成片必须带音轨，不能只有画面。"
        assert receipt.get("audioMix", {}).get("ducking") == "source-v1"
        assert receipt.get("music", {}).get("licenseStatus") == "test_only"
        assert receipt.get("narration", {}).get("voice", {}).get("engine") == "windows-sapi"
        assert receipt["narration"]["selection"]["startFrame"] == start_frame
        assert receipt["narration"]["mixPolicy"]["ducking"] == "narration-v1"

        expected_colors = [by_event[segment["eventId"]]["color"] for segment in segments]
        seen = []
        cursor = 0
        for segment, _color in zip(segments, expected_colors, strict=True):
            mid = cursor + max(segment["outputFrames"] // 2, 0)
            mid = min(mid, max(int(actual_frames) - 1, 0))
            seen.append(nearest_color(frame_rgb(video, mid)))
            cursor += segment["outputFrames"]
        assert seen == expected_colors, (seen, expected_colors, [s["eventId"] for s in segments])

        samples = pcm(video)
        start_sec = start_frame / 30
        before_end = max(start_sec - 0.05, 0)
        before_start = max(before_end - 0.25, 0)
        during_start = start_sec + 0.12
        during_end = min(
            start_sec + min(max(duration - 0.12, 0.35), 0.9), planned_frames / 30 - 0.05
        )
        after_start = min(start_sec + duration + 0.12, planned_frames / 30 - 0.3)
        after_end = min(after_start + 0.25, planned_frames / 30 - 0.02)
        before_voice = _residual_rms(samples, before_start, before_end)
        during_voice = _residual_rms(samples, during_start, during_end)
        assert during_voice > before_voice * 2, (during_voice, before_voice, start_sec, duration)
        silent_end_sec = (
            None if silent is None else (silent["outputStartFrame"] + silent["outputFrames"]) / 30
        )
        if (
            after_end > after_start + 0.08
            and after_start >= start_sec + duration
            and (silent_end_sec is None or after_end <= silent_end_sec - 0.02)
        ):
            after_voice = _residual_rms(samples, after_start, after_end)
            assert after_voice < during_voice * 0.7, (
                after_voice,
                during_voice,
                start_sec,
                duration,
            )
        assert abs(duration - asset["sampleCount"] / asset["sampleRate"]) < 0.05

        bgm_before = amplitude(
            samples, BGM_HZ, max(start_sec - 0.45, 0.05), max(start_sec - 0.1, 0.2)
        )
        assert bgm_before > 0.01, "旁白开始前应该听得到背景音乐。"
        # 旁白不是持续正弦，闪避会随说话起伏；取旁白段里背景音被压得最低的一小段来量。
        hops = []
        cursor = during_start
        last = min(start_sec + duration - 0.05, planned_frames / 30 - 0.05)
        while cursor + 0.12 <= last:
            hops.append(amplitude(samples, BGM_HZ, cursor, cursor + 0.12))
            cursor += 0.06
        bgm_during = min(hops) if hops else amplitude(samples, BGM_HZ, during_start, during_end)
        duck_db = 20 * math.log10(bgm_during / bgm_before)
        assert duck_db <= -2, (duck_db, bgm_before, bgm_during, hops)

        if silent is not None and start_frame >= silent["outputStartFrame"]:
            quiet_source = next(
                (
                    segment
                    for segment in segments
                    if by_event[segment["eventId"]].get("audio_hz")
                    and segment["outputStartFrame"] + segment["outputFrames"] <= start_frame
                ),
                None,
            )
            if quiet_source is not None:
                # 源声有音调的窗口里，source-v1 应压低 BGM；旁白还没开始。
                loud_start = (
                    quiet_source["outputStartFrame"] + quiet_source["outputFrames"] * 0.2
                ) / 30
                loud_end = (
                    quiet_source["outputStartFrame"] + quiet_source["outputFrames"] * 0.6
                ) / 30
                silent_start = silent["outputStartFrame"] / 30 + 0.05
                silent_end = min(start_sec - 0.05, silent_start + 0.4)
                if silent_end > silent_start + 0.08:
                    source_duck = 20 * math.log10(
                        amplitude(samples, BGM_HZ, loud_start, loud_end)
                        / amplitude(samples, BGM_HZ, silent_start, silent_end)
                    )
                    assert source_duck <= -3, source_duck

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
        # 测试专用背景音乐不能假装已经有发布资格。
        assert facts["publicationEligibility"] == "blocked"
        assert facts["validation"]["sourceRights"] == "unknown"
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
        summary = {
            "mode": "游戏解说",
            "planId": "commentary-segments",
            "voiceId": voice["voiceId"],
            "voiceEngine": receipt["narration"]["voice"]["engine"],
            "narrationText": NARRATION_TEXT,
            "narrationStartFrame": start_frame,
            "narrationDurationSeconds": duration,
            "bgmHz": BGM_HZ,
            "bgmLicenseStatus": track.license_status,
            "narrationDuckDb": duck_db,
            "planJobId": plan["jobId"],
            "narrationJobId": narration["jobId"],
            "revisionJobId": revised["jobId"],
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
