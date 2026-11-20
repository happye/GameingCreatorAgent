"""F05 之后的 F06：高光模式混合源走真实 HTTP，带转场和音量包络。

用抽帧看叠化是否真的发生，用频谱看源声和音量曲线是否按输出时钟变化，不只看回执。
不编造画面理解或创意质量分。
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
from f_mixed_sources import (
    FFMPEG,
    MAX_PRODUCT_BYTES,
    RGB,
    enforce_product_caps,
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

from gamingcreator.application.material_scoring import UNKNOWN
from gamingcreator.application.rendering import output_start_frames
from gamingcreator.domain.creation_audio import GainPoint, envelope_db
from gamingcreator.ui import package_jobs
from gamingcreator.ui.creation_jobs import CreationJobs

pytestmark = pytest.mark.skipif(not FFMPEG.is_file(), reason="本机未准备项目内的 FFmpeg")

FPS = 30
TARGET_SECONDS = 15
SOURCE_SECONDS = 8
OVERLAP = 12
UNKNOWN_PARTS = ("visualQuality", "emotionalIntensity", "narrativeValue")
ENVELOPE_DIP_DB = -12.0


def all_frame_rgb(path: Path) -> list[tuple[int, int, int]]:
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
            "scale=1:1",
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
    if len(pixels) < 3 or len(pixels) % 3:
        raise RuntimeError(f"抽帧结果不完整（{len(pixels)} 字节）。")
    return [(pixels[i], pixels[i + 1], pixels[i + 2]) for i in range(0, len(pixels), 3)]


def _distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> int:
    return sum(abs(left[i] - right[i]) for i in range(3))


def _exclusive(start: int, frames: int, incoming: int, outgoing: int) -> tuple[int, int]:
    begin = start + incoming
    end = start + frames - outgoing
    if end - begin < 2:
        raise RuntimeError("转场后没有留下可核对的独占画面。")
    return begin, end


def test_highlight_mixed_source_transitions_and_volume_envelope(tmp_path):
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
                    "contentType": "highlight",
                    "platforms": ["bilibili"],
                    "targetDuration": TARGET_SECONDS,
                    "objective": "把高光串起来，带转场和音量变化",
                    "audience": "观众",
                    "tone": "清楚",
                    "mandatoryTopics": [],
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
        highlight = next(item for item in plan["plans"] if item["id"] == "highlight-climax")
        assert highlight["mode"] == "highlight"
        assert highlight["modeLabel"] == "高光"
        segments = highlight["segments"]
        assert len(segments) >= 3
        roles = [segment["role"] for segment in segments]
        assert roles[-1] == "高潮"
        assert roles[:-1] == [f"高光{i}" for i in range(1, len(segments))]
        for segment in segments:
            for name in UNKNOWN_PARTS:
                assert segment["score"]["parts"][name] is None

        snapshot = jobs.edit(plan["jobId"], "highlight-climax")
        rows = snapshot["clips"]
        assert len(rows) == len(segments)
        lengths = [row["outputFrames"] for row in rows]
        assert all(length > OVERLAP * 2 + 1 for length in lengths)
        transitions = [0 if index == 0 else OVERLAP for index in range(len(rows))]
        expected_starts = list(output_start_frames(tuple(lengths), tuple(transitions)))
        planned_frames = expected_starts[-1] + lengths[-1]
        assert planned_frames == sum(lengths) - sum(transitions)
        assert planned_frames > 0

        voiced = [
            index for index, row in enumerate(rows) if by_event[row["eventId"]].get("audio_hz")
        ]
        assert voiced, "这条实例需要至少一段有源声的高光，才能核对象量包络。"
        first_voiced, last_voiced = voiced[0], voiced[-1]
        first_begin, first_end = _exclusive(
            expected_starts[first_voiced],
            lengths[first_voiced],
            transitions[first_voiced],
            transitions[first_voiced + 1] if first_voiced + 1 < len(rows) else 0,
        )
        last_begin, last_end = _exclusive(
            expected_starts[last_voiced],
            lengths[last_voiced],
            transitions[last_voiced],
            transitions[last_voiced + 1] if last_voiced + 1 < len(rows) else 0,
        )
        hold_zero = first_begin + max((first_end - first_begin) // 2, 1)
        hold_dip = last_begin + max((last_end - last_begin) // 4, 1)
        if first_voiced == last_voiced:
            hold_zero = first_begin + 2
            hold_dip = max(hold_zero + 2, last_end - 3)
        assert 0 <= hold_zero < hold_dip < planned_frames
        envelope = [
            {"frame": 0, "gainDb": 0},
            {"frame": hold_zero, "gainDb": 0},
            {"frame": hold_dip, "gainDb": ENVELOPE_DIP_DB},
        ]

        revision_job = http_json(
            base,
            "/api/creation/revisions",
            {
                "requestId": uuid4().hex,
                "parentJobId": plan["jobId"],
                "planId": "highlight-climax",
                "expectedParentReceiptSha256": snapshot["expectedParentReceiptSha256"],
                "clips": [
                    {
                        "clipId": row["clipId"],
                        "startUs": row["startUs"],
                        "endUs": row["endUs"],
                        "speed": {"numerator": 1, "denominator": 1},
                        "transitionIn": (
                            {"type": "cut", "frames": 0}
                            if incoming == 0
                            else {"type": "crossfade", "frames": incoming}
                        ),
                    }
                    for row, incoming in zip(rows, transitions, strict=True)
                ],
                "audioMix": {
                    "bgm": None,
                    "sourceGainDb": 0,
                    "ducking": "off",
                    "sourceEnvelope": envelope,
                },
            },
        )
        revised = wait_job(base, revision_job["jobId"])
        assert revised["status"] == "completed", revised
        revision_edl = jobs.read(
            jobs.directory(revision_job["jobId"]) / "result" / "edit-decision.json"
        )
        assert revision_edl["schemaVersion"] == "edit-decision-revision-v3"
        revised_rows = revision_edl["segments"]
        assert [row["outputFrames"] for row in revised_rows] == lengths
        assert [row["outputStartFrame"] for row in revised_rows] == expected_starts
        assert [row["transitionIn"]["frames"] for row in revised_rows] == transitions

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

        pixels = all_frame_rgb(video)
        assert abs(len(pixels) - planned_frames) <= 1
        expected_colors = [by_event[row["eventId"]]["color"] for row in revised_rows]
        seen = []
        blend_checks = []
        for index, (start, frames, color, incoming) in enumerate(
            zip(expected_starts, lengths, expected_colors, transitions, strict=True)
        ):
            outgoing = transitions[index + 1] if index + 1 < len(rows) else 0
            begin, end = _exclusive(start, frames, incoming, outgoing)
            mid = min((begin + end) // 2, len(pixels) - 1)
            seen.append(nearest_color(pixels[mid]))
            if incoming:
                blend_at = min(start + incoming // 2, len(pixels) - 1)
                previous = expected_colors[index - 1]
                rgb = pixels[blend_at]
                to_prev = _distance(rgb, RGB[previous])
                to_curr = _distance(rgb, RGB[color])
                span = _distance(RGB[previous], RGB[color])
                assert to_prev > 40 and to_curr > 40, (
                    "转场中间不能还是某一侧的纯色，否则只是硬切。",
                    previous,
                    color,
                    rgb,
                    blend_at,
                )
                assert to_prev + to_curr < span * 1.4, (
                    "转场中间的颜色应落在两侧之间。",
                    previous,
                    color,
                    rgb,
                    blend_at,
                )
                blend_checks.append(
                    {
                        "frame": blend_at,
                        "from": previous,
                        "to": color,
                        "rgb": list(rgb),
                    }
                )
        assert seen == expected_colors, (seen, expected_colors)

        samples = pcm(video)
        duration_sec = planned_frames / FPS
        overlap_tones = []
        for index in range(1, len(revised_rows)):
            start = expected_starts[index]
            incoming = transitions[index]
            left_hz = by_event[revised_rows[index - 1]["eventId"]].get("audio_hz")
            right_hz = by_event[revised_rows[index]["eventId"]].get("audio_hz")
            overlap_start = start / FPS
            overlap_end = (start + incoming) / FPS
            window_start = overlap_start + 0.08
            window_end = overlap_end - 0.08
            if window_end <= window_start:
                window_start, window_end = overlap_start + 0.04, overlap_end - 0.04
            entry = {
                "from": revised_rows[index - 1]["eventId"],
                "to": revised_rows[index]["eventId"],
                "startFrame": start,
                "frames": incoming,
            }
            if left_hz and right_hz and window_end > window_start + 0.05:
                left_level = amplitude(samples, left_hz, window_start, window_end)
                right_level = amplitude(samples, right_hz, window_start, window_end)
                assert left_level > 0.01 and right_level > 0.01, (
                    "有声镜头的转场里，两侧源声应同时听得到。",
                    left_hz,
                    right_hz,
                    left_level,
                    right_level,
                    window_start,
                    window_end,
                )
                entry.update(leftHz=left_hz, rightHz=right_hz, left=left_level, right=right_level)
            overlap_tones.append(entry)

        early_hz = by_event[revised_rows[first_voiced]["eventId"]]["audio_hz"]
        late_hz = by_event[revised_rows[last_voiced]["eventId"]]["audio_hz"]
        early_start = (first_begin + 2) / FPS
        early_end = min((hold_zero) / FPS, (first_end - 2) / FPS)
        late_start = (hold_dip + 2) / FPS
        late_end = (last_end - 2) / FPS
        if early_end <= early_start + 0.08:
            early_start, early_end = first_begin / FPS + 0.05, first_end / FPS - 0.05
        if late_end <= late_start + 0.08:
            late_start, late_end = last_begin / FPS + 0.08, last_end / FPS - 0.05
        assert early_end > early_start + 0.08 and late_end > late_start + 0.08
        assert late_start < duration_sec
        early_level = amplitude(samples, early_hz, early_start, early_end)
        late_level = amplitude(samples, late_hz, late_start, late_end)
        assert early_level > 0.02, (early_hz, early_level, early_start, early_end)
        measured_db = 20 * math.log10(late_level / early_level)
        points = tuple(GainPoint(item["frame"], item["gainDb"]) for item in envelope)
        expected_db = envelope_db(points, (late_start + late_end) / 2 * FPS) - envelope_db(
            points, (early_start + early_end) / 2 * FPS
        )
        assert measured_db == pytest.approx(expected_db, abs=2.0), (
            "音量包络应按输出时钟落在成片里，不能只看回执。",
            measured_db,
            expected_db,
            early_level,
            late_level,
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
        summary = {
            "mode": "高光",
            "planId": "highlight-climax",
            "understandingVerified": report["understandingVerified"],
            "unknownScoreParts": {name: report["scoring"]["basis"][name] for name in UNKNOWN_PARTS},
            "planJobId": plan["jobId"],
            "revisionJobId": revision_job["jobId"],
            "renderJobId": rendered["jobId"],
            "publicationJobId": published["jobId"],
            "packageJobId": package["jobId"],
            "plannedFrames": planned_frames,
            "renderFrames": actual_frames,
            "packageFrames": package_frames,
            "publicationEligibility": facts["publicationEligibility"],
            "transitionFrames": transitions,
            "envelope": envelope,
            "envelopeMeasuredDb": measured_db,
            "envelopeExpectedDb": expected_db,
            "blendChecks": blend_checks,
            "overlapTones": overlap_tones,
            "segmentOrder": [
                {
                    "eventId": row["eventId"],
                    "role": segments[index]["role"],
                    "color": by_event[row["eventId"]]["color"],
                    "source": by_event[row["eventId"]]["name"],
                    "outputStartFrame": expected_starts[index],
                    "outputFrames": lengths[index],
                    "transitionIn": transitions[index],
                    "scoreTotal": segments[index]["score"]["total"],
                }
                for index, row in enumerate(revised_rows)
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
