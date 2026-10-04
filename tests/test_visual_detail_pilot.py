"""Offline experiment safety; fixture model output is never a quality label."""

import asyncio
import hashlib
import importlib.util
import json
import struct
import sys
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from gamingcreator.application.media import SamplingParameters
from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.errors import AppError
from gamingcreator.domain.media import (
    MediaAsset,
    MediaPreprocessingResult,
    MediaStream,
    VisualEvidence,
)
from gamingcreator.domain.time import SourceInstant
from gamingcreator.infrastructure.http_transport import HttpResponse

SPEC = importlib.util.spec_from_file_location(
    "visual_detail_pilot",
    Path(__file__).resolve().parents[1] / "scripts/validate-visual-details.py",
)
assert SPEC is not None and SPEC.loader is not None
pilot = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pilot
SPEC.loader.exec_module(pilot)


def media_fixture(directory: Path, width: int, run_id: str) -> MediaPreprocessingResult:
    directory.mkdir(parents=True, exist_ok=True)
    asset = MediaAsset(
        "media",
        directory / "source.mp4",
        "a" * 64,
        (MediaStream(0, "video", Fraction(1, 1000), 5000, 20_000),),
        Fraction(5),
        20_000_000,
        "probe-v1",
    )
    images = []
    for index in range(9):
        # Bounded framing fixture only; no decoder or quality assertion is involved.
        data = (
            b"\xff\xd8\xff\xc0\x00\x0b\x08"
            + struct.pack(">HH", width * 9 // 16, width)
            + b"\x01\x01\x11\x00\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00"
            + bytes([index + 1])
            + b"\xff\xd9"
        )
        path = directory / f"frame-{index}.jpg"
        path.write_bytes(data)
        images.append(
            VisualEvidence(
                f"{run_id}:media:image:{index:06d}",
                path,
                hashlib.sha256(data).hexdigest(),
                15_000 + index * 500,
                Fraction(1, 1000),
                SourceInstant(10_000_000 + index * 500_000, 20_000_000),
            )
        )
    manifest = directory / "media.json"
    manifest.write_text(json.dumps({"width": width, "runId": run_id}))
    return MediaPreprocessingResult(
        asset, tuple(images), None, manifest, "transform-v1", "processor-v1"
    )


def fake_processor(monkeypatch: pytest.MonkeyPatch, repository: Path) -> None:
    class Processor:
        def __init__(self, root: Path) -> None:
            assert root == repository

        async def probe(self, video: Path, context: CancellationContext) -> MediaAsset:
            return MediaAsset(
                "media",
                video,
                "a" * 64,
                (MediaStream(0, "video", Fraction(1, 1000), 5000, 20_000),),
                Fraction(5),
                20_000_000,
                "probe-v1",
            )

        async def preprocess(
            self,
            video: Path,
            directory: Path,
            parameters: SamplingParameters,
            context: CancellationContext,
        ) -> MediaPreprocessingResult:
            assert parameters.interval_seconds == Fraction(1, 2)
            assert parameters.max_width in (512, 1280)
            return media_fixture(directory, parameters.max_width, context.run_id)

    monkeypatch.setattr(pilot, "FfmpegMediaProcessor", Processor)


def test_three_profiles_share_nine_source_instants_with_distinct_variants(tmp_path: Path) -> None:
    low, high = (
        media_fixture(tmp_path / "low", 512, "low"),
        media_fixture(tmp_path / "high", 1280, "high"),
    )
    a, b, c, static, reverse = pilot.make_cases(low, high, [10_000_000], "low", "high")
    assert a.frames == b.frames and len(a.frames) == 9
    assert [item.source_time for item in b.frames] == [item.source_time for item in c.frames]
    assert [item.sha256 for item in b.frames] != [item.sha256 for item in c.frames]
    assert a.prompt_version == "phase0-vision-v4"
    assert b.prompt_version == c.prompt_version == "phase0-vision-v5"
    assert a.image_max_width == b.image_max_width == 512 and c.image_max_width == 1280
    assert [item.source_time for item in static.frames] == [item.source_time for item in c.frames]
    assert len({item.sha256 for item in static.frames}) == 1
    assert len({item.evidence_id for item in static.frames}) == 9
    assert reverse.frames == c.frames[::-1]
    with pytest.raises(AppError) as caught:
        pilot.make_cases(low, high, [10_250_000], "low", "high")
    assert caught.value.code == "detail_pilot.window_frames"


@pytest.mark.parametrize("mutation", ["source", "clock"])
def test_mismatched_decodes_are_rejected(tmp_path: Path, mutation: str) -> None:
    low = media_fixture(tmp_path / "low", 512, "low")
    high = media_fixture(tmp_path / "high", 1280, "high")
    if mutation == "source":
        high = replace(high, asset=replace(high.asset, sha256="b" * 64))
    else:
        high = replace(
            high,
            images=(replace(high.images[0], source_time=SourceInstant(10_000_001, 20_000_000)),)
            + high.images[1:],
        )
    with pytest.raises(AppError) as caught:
        pilot.make_cases(low, high, [10_000_000], "low", "high")
    assert caught.value.code == "detail_pilot.source_alignment"


def test_dry_pilot_freezes_dimensions_price_and_hashes_without_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_processor(monkeypatch, tmp_path)

    def forbidden_transport() -> None:
        raise AssertionError("Dry runs must not construct a transport.")

    monkeypatch.setattr(pilot, "HttpxVisionTransport", forbidden_transport)
    output = tmp_path / "artifacts/dry"
    report = asyncio.run(pilot.run_pilot(tmp_path, tmp_path / "video.mp4", output, [10_000_000]))
    frozen = json.loads((output / "frozen-manifest.json").read_text())
    assert report["status"] == "frozen" and report["qualityGate"] is None
    assert frozen["humanLabels"] is None and frozen["sourceClockOriginSeconds"] == "5"
    assert frozen["maxOutputTokens"] == 4096 and frozen["requestLimit"] == 8
    assert frozen["maxCostCny"] == "5"
    assert frozen["priceSnapshot"]["version"] == "deepseek-flash-cny-2026-10-04"
    assert len(frozen["preprocessingVariants"]) == 2
    assert [case["selectedFrames"][0]["width"] for case in frozen["cases"]] == [
        512,
        512,
        1280,
        1280,
        1280,
    ]
    assert [case["selectedFrames"][0]["height"] for case in frozen["cases"]] == [
        288,
        288,
        720,
        720,
        720,
    ]
    assert all(len(case["selectedFrames"]) == 9 for case in frozen["cases"])
    assert all(len(case["promptSha256"]) == 64 for case in frozen["cases"])
    assert report["cost"]["requestCount"] == 0
    assert json.loads((output / "invocations.json").read_text()) == []


def test_existing_directory_and_outside_outputs_are_not_mutated(tmp_path: Path) -> None:
    existing = tmp_path / "artifacts/existing"
    existing.mkdir(parents=True)
    marker = existing / "report.json"
    marker.write_text("original evidence")
    for output, code in (
        (existing, "detail_pilot.output_exists"),
        (tmp_path / "outside", "detail_pilot.output"),
    ):
        with pytest.raises(AppError) as caught:
            asyncio.run(pilot.run_pilot(tmp_path, tmp_path / "video.mp4", output, [0]))
        assert caught.value.code == code
    assert marker.read_text() == "original evidence"
    assert not (tmp_path / "outside").exists()


def test_missing_auth_keeps_frozen_report_and_empty_invocations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_processor(monkeypatch, tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    output = tmp_path / "artifacts/missing-auth"
    with pytest.raises(AppError) as caught:
        asyncio.run(
            pilot.run_pilot(tmp_path, tmp_path / "video.mp4", output, [10_000_000], execute=True)
        )
    assert caught.value.code == "provider.auth"
    assert (output / "frozen-manifest.json").exists()
    report = json.loads((output / "report.json").read_text())
    assert report["status"] == "failed" and report["errorCode"] == "provider.auth"
    assert report["cost"]["requestCount"] == 0


@pytest.mark.parametrize("known_usage", [True, False])
def test_each_outcome_is_durable_and_reverse_sends_no_http(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, known_usage: bool
) -> None:
    fake_processor(monkeypatch, tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "offline-fixture")
    output = tmp_path / "artifacts/execute"
    calls: list[dict[str, object]] = []

    class Transport:
        async def post(self, payload: dict[str, object], timeout_seconds: float) -> HttpResponse:
            assert 0 < timeout_seconds <= 90
            assert (output / "frozen-manifest.json").exists()
            invocations = json.loads((output / "invocations.json").read_text())
            assert invocations[-1]["status"] == "running"
            if calls:
                assert (output / f"window-0-{'ABC'[len(calls) - 1]}.json").exists()
            calls.append(payload)
            body: dict[str, object] = {
                "id": "offline-response",
                "model": "deepseek-flash",
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": '{"events":[]}'},
                    }
                ],
            }
            if known_usage:
                body["usage"] = {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "prompt_cache_hit_tokens": 0,
                }
            return HttpResponse(200, json.dumps(body).encode())

    monkeypatch.setattr(pilot, "HttpxVisionTransport", Transport)
    report = asyncio.run(
        pilot.run_pilot(tmp_path, tmp_path / "video.mp4", output, [10_000_000], execute=True)
    )
    assert report["status"] == ("completed" if known_usage else "completed_with_failures")
    assert len(calls) == (4 if known_usage else 2)
    assert report["qualityGate"] is None and report["humanLabels"] is None
    assert report["cost"]["requestCount"] == len(calls)
    assert report["cost"]["unknownCostAttempts"] == (0 if known_usage else 2)
    if not known_usage:
        assert report["cost"]["totalApiCostCny"] is None
        assert float(report["cost"]["reservedCny"]) > 4
        assert report["cases"][2]["errorCode"] == "budget.exhausted"
    assert report["cases"][-1]["errorCode"] == "provider.input"
    assert report["cases"][-1]["temporalControlPassed"] is True
    assert len(json.loads((output / "invocations.json").read_text())) == len(calls)
    assert all((output / f"{case['id']}.json").exists() for case in report["cases"])
    assert "offline-fixture" not in (output / "report.json").read_text()


def test_changed_image_hash_is_rejected_before_freezing(tmp_path: Path) -> None:
    media = media_fixture(tmp_path / "media", 1280, "run")
    item = pilot._references(media)[0]
    item.artifact_path.write_bytes(b"changed bytes")
    with pytest.raises(AppError) as caught:
        pilot.frame_record(item, tmp_path)
    assert caught.value.code == "detail_pilot.image_hash"
