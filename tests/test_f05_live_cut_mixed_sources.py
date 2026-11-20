"""F05：实况精剪混合源走真实 HTTP，带变速、字幕和源声，按输出时钟核对。

不只看文件在不在。镜头时长用官方整数时钟（和预览同一条规则）算出来，再对成片抽帧、量源声音调、核对字幕时刻。
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
from test_creation_audio_render import amplitude, pcm

from gamingcreator.domain.creation_subtitles import SubtitleCue, parse_srt, quantize_srt
from gamingcreator.ui import package_jobs
from gamingcreator.ui.creation_jobs import CreationJobs

pytestmark = pytest.mark.skipif(not FFMPEG.is_file(), reason="本机未准备项目内的 FFmpeg")

FPS = 30
TARGET_SECONDS = 30
SOURCE_SECONDS = 8
SPEED_TEXT = {
    Fraction(2, 1): "字幕-二倍速",
    Fraction(1, 2): "字幕-半速",
    Fraction(1, 1): "字幕-常速",
}


def official_clip_frames(start_us: int, end_us: int, speed: Fraction, fps: int = FPS) -> int:
    # 与 preview.js clipFrames、build_revision 同一条整数除法。
    return (end_us - start_us) * fps * speed.denominator // (1_000_000 * speed.numerator)


def _speed_plan(rows: list[dict], by_event: dict) -> list[Fraction]:
    speeds = [Fraction(1, 1)] * len(rows)
    voiced = [
        index
        for index, row in enumerate(rows)
        if index > 0 and by_event[row["eventId"]].get("audio_hz")
    ]
    if len(voiced) >= 2:
        speeds[voiced[0]] = Fraction(2, 1)
        speeds[voiced[1]] = Fraction(1, 2)
        return speeds
    if len(voiced) == 1:
        speeds[voiced[0]] = Fraction(2, 1)
        other = next(index for index in range(len(rows)) if index != voiced[0])
        speeds[other] = Fraction(1, 2)
        return speeds
    speeds[0] = Fraction(2, 1)
    speeds[-1] = Fraction(1, 2)
    return speeds


def test_live_cut_mixed_source_speed_subtitles_and_source_audio(tmp_path):
    require_space(tmp_path)
    link_tools(tmp_path)
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
                    "contentType": "live_cut",
                    "platforms": ["bilibili"],
                    "targetDuration": TARGET_SECONDS,
                    "objective": "把实况剪紧凑，保留源声并加上字幕",
                    "audience": "观众",
                    "tone": "清楚",
                    "mandatoryTopics": [],
                    "exclude": [],
                },
            },
        )
        plan = wait_job(base, plan_job["jobId"])
        assert plan["status"] == "completed", plan
        live = next(item for item in plan["plans"] if item["id"] == "live-cut")
        assert live["mode"] == "live_cut"
        assert live["modeLabel"] == "实况精剪"
        segments = live["segments"]
        assert len(segments) >= 3
        assert [segment["role"] for segment in segments] == [
            f"实况{i}" for i in range(1, len(segments) + 1)
        ]

        snapshot = jobs.edit(plan["jobId"], "live-cut")
        rows = snapshot["clips"]
        assert len(rows) == len(segments)
        speeds = _speed_plan(rows, by_event)
        assert Fraction(2, 1) in speeds and Fraction(1, 2) in speeds
        captions = [f"{SPEED_TEXT[speed]}{index + 1}" for index, speed in enumerate(speeds)]
        expected_frames = [
            official_clip_frames(row["startUs"], row["endUs"], speed)
            for row, speed in zip(rows, speeds, strict=True)
        ]
        expected_starts = []
        cursor = 0
        for frames in expected_frames:
            expected_starts.append(cursor)
            cursor += frames
        planned_frames = cursor
        assert planned_frames <= TARGET_SECONDS * FPS
        assert planned_frames > 0

        revision_job = http_json(
            base,
            "/api/creation/revisions",
            {
                "requestId": uuid4().hex,
                "parentJobId": plan["jobId"],
                "planId": "live-cut",
                "expectedParentReceiptSha256": snapshot["expectedParentReceiptSha256"],
                "clips": [
                    {
                        "clipId": row["clipId"],
                        "startUs": row["startUs"],
                        "endUs": row["endUs"],
                        "speed": {
                            "numerator": speed.numerator,
                            "denominator": speed.denominator,
                        },
                    }
                    for row, speed in zip(rows, speeds, strict=True)
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
        assert revision_edl["schemaVersion"] in (
            "edit-decision-revision-v2",
            "edit-decision-revision-v3",
        )
        revised_rows = revision_edl["segments"]
        assert [row["outputFrames"] for row in revised_rows] == expected_frames
        assert [row["outputStartFrame"] for row in revised_rows] == expected_starts
        for row, speed in zip(revised_rows, speeds, strict=True):
            assert row["speed"] == {
                "numerator": speed.numerator,
                "denominator": speed.denominator,
            }

        render_job = http_json(
            base,
            "/api/creation/renders",
            {
                "requestId": uuid4().hex,
                "revisionJobId": revision_job["jobId"],
                "width": 160,
                "height": 90,
                "subtitleMode": "burn",
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
        audio_streams = [stream for stream in probe["streams"] if stream["codec_type"] == "audio"]
        probed_frames = int(video_stream.get("nb_frames") or 0) or actual_frames
        assert actual_frames is not None
        assert abs(int(actual_frames) - planned_frames) <= 1
        assert abs(probed_frames - planned_frames) <= 1
        assert audio_streams, "成片必须带音轨，不能只有画面。"
        assert pcm_energy(video) > 20
        assert receipt.get("speedPolicy", {}).get("version") == "clip-speed-v1"
        assert receipt.get("subtitles", {}).get("mode") == "burn"
        assert receipt["subtitles"].get("cueCount") == len(captions)

        srt_path = result / "subtitles.srt"
        assert srt_path.is_file(), "烧录字幕时，官方会同时留下按输出时钟写的字幕文件。"
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

        expected_colors = [by_event[row["eventId"]]["color"] for row in revised_rows]
        seen = []
        for start, frames, _color in zip(
            expected_starts, expected_frames, expected_colors, strict=True
        ):
            mid = start + max(frames // 2, 0)
            mid = min(mid, max(int(actual_frames) - 1, 0))
            seen.append(nearest_color(frame_rgb(video, mid)))
        assert seen == expected_colors, (seen, expected_colors)

        samples = pcm(video)
        tone_checks = []
        duration_sec = planned_frames / FPS
        for start, frames, row, speed in zip(
            expected_starts, expected_frames, revised_rows, speeds, strict=True
        ):
            hz = by_event[row["eventId"]].get("audio_hz")
            start_sec = start / FPS
            end_sec = (start + frames) / FPS
            mid_start = start_sec + frames / FPS * 0.3
            mid_end = start_sec + frames / FPS * 0.7
            if hz:
                present = amplitude(samples, hz, mid_start, mid_end)
                shifted = amplitude(
                    samples,
                    hz * float(speed) if speed != 1 else hz * 2,
                    mid_start,
                    mid_end,
                )
                assert present > 0.02, (hz, speed, present, start_sec, end_sec)
                assert present > shifted * 2, (
                    "变速后源声应保持原音调，不能变成按倍数搬移的音高。",
                    hz,
                    speed,
                    present,
                    shifted,
                )
                # 镜头窗外同一音调应明显变弱，用来确认输出时钟而不是只听得到“有声音”。
                after_start = min(end_sec + 0.08, duration_sec - 0.2)
                after_end = min(after_start + 0.25, duration_sec - 0.02)
                if after_end > after_start + 0.08 and after_start >= end_sec:
                    outside = amplitude(samples, hz, after_start, after_end)
                    assert present > outside * 2, (hz, speed, present, outside, end_sec)
                tone_checks.append(
                    {
                        "eventId": row["eventId"],
                        "hz": hz,
                        "speed": f"{speed.numerator}/{speed.denominator}",
                        "outputStartFrame": start,
                        "outputFrames": frames,
                        "present": present,
                        "shifted": shifted,
                    }
                )
            else:
                quiet = max(
                    amplitude(samples, tone, mid_start, mid_end) for tone in (440, 880, 660, 550)
                )
                assert quiet < 0.02, (
                    "无源声镜头里不该听到其他镜头的音调。",
                    quiet,
                    start_sec,
                    end_sec,
                )
                tone_checks.append(
                    {
                        "eventId": row["eventId"],
                        "hz": None,
                        "speed": f"{speed.numerator}/{speed.denominator}",
                        "outputStartFrame": start,
                        "outputFrames": frames,
                        "quiet": quiet,
                    }
                )

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
        (products / "subtitles.srt").write_text(
            srt_path.read_text(encoding="utf-8"), encoding="utf-8"
        )
        summary = {
            "mode": "实况精剪",
            "planId": "live-cut",
            "planJobId": plan["jobId"],
            "revisionJobId": revision_job["jobId"],
            "renderJobId": rendered["jobId"],
            "publicationJobId": published["jobId"],
            "packageJobId": package["jobId"],
            "plannedFrames": planned_frames,
            "renderFrames": actual_frames,
            "packageFrames": package_frames,
            "publicationEligibility": facts["publicationEligibility"],
            "subtitleMode": "burn",
            "speedPolicy": receipt.get("speedPolicy"),
            "segmentOrder": [
                {
                    "eventId": row["eventId"],
                    "role": segments[index]["role"],
                    "color": by_event[row["eventId"]]["color"],
                    "source": by_event[row["eventId"]]["name"],
                    "startUs": row["startUs"],
                    "endUs": row["endUs"],
                    "speed": f"{speeds[index].numerator}/{speeds[index].denominator}",
                    "outputStartFrame": expected_starts[index],
                    "outputFrames": expected_frames[index],
                    "caption": captions[index],
                }
                for index, row in enumerate(revised_rows)
            ],
            "toneChecks": tone_checks,
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
