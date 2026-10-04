"""Offline pilot safety: freeze before execution, preserve clocks and unknown charges."""

import asyncio
import importlib.util
import json
import sys
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from gamingcreator.application.budget import BudgetLedger
from gamingcreator.application.providers import InvocationMetadata, ProviderUsage
from gamingcreator.application.storage import InvocationStatus
from gamingcreator.domain.errors import AppError
from gamingcreator.domain.media import (
    MediaAsset,
    MediaPreprocessingResult,
    MediaStream,
    VisualEvidence,
)
from gamingcreator.domain.time import SourceInstant

SPEC = importlib.util.spec_from_file_location(
    "temporal_pilot", Path(__file__).resolve().parents[1] / "scripts/validate-temporal-gameplay.py"
)
assert SPEC is not None and SPEC.loader is not None
pilot = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pilot
SPEC.loader.exec_module(pilot)


def media_fixture(tmp_path: Path) -> MediaPreprocessingResult:
    asset = MediaAsset(
        "media",
        tmp_path / "source.mp4",
        "a" * 64,
        (MediaStream(0, "video", Fraction(1, 1000), 5000, 20_000),),
        Fraction(5),
        20_000_000,
        "probe-v1",
    )
    frames = tuple(
        VisualEvidence(
            f"run:media:image:{index:06d}",
            tmp_path / f"{index}.jpg",
            str(index) * 64,
            15_000 + index * 500,
            Fraction(1, 1000),
            SourceInstant(10_000_000 + index * 500_000, 20_000_000),
        )
        for index in range(9)
    )
    return MediaPreprocessingResult(
        asset, frames, None, tmp_path / "media.json", "transform-v1", "processor-v1"
    )


def test_ab_and_static_controls_retain_original_source_instants(tmp_path: Path) -> None:
    media = media_fixture(tmp_path)
    a, b, static, reversed_case = pilot.make_cases(media, [10_000_000])
    assert [item.source_time.time_us for item in a.frames] == [
        10_000_000,
        11_000_000,
        12_000_000,
        13_000_000,
        14_000_000,
    ]
    assert tuple(item.source_time for item in b.frames) == tuple(
        item.source_time for item in media.images
    )
    assert tuple(item.source_time for item in static.frames) == tuple(
        item.source_time for item in b.frames
    )
    assert len({item.sha256 for item in static.frames}) == 1
    assert len({item.evidence_id for item in static.frames}) == 9
    assert reversed_case.frames[0].source_time == b.frames[-1].source_time
    with pytest.raises(AppError, match="九个真实采样帧"):
        pilot.make_cases(media, [10_250_000])


def test_recorder_persists_start_finish_and_unknown_charge(tmp_path: Path) -> None:
    path = tmp_path / "attempts.json"
    recorder = pilot.JsonInvocationRecorder(path)
    metadata = InvocationMetadata(
        "deepseek",
        "deepseek-flash",
        None,
        None,
        "phase0-vision-v3",
        "semantic-events-v1",
        1,
        ProviderUsage(),
    )
    budget = BudgetLedger(Decimal(5), 12, 108)
    reservation = budget.reserve(9, Decimal("2.032768"))
    asyncio.run(recorder.begin_invocation("id", "run", "B", "logical", metadata))
    assert json.loads(path.read_text())[0]["status"] == "running"
    budget.settle(reservation, None)
    asyncio.run(
        recorder.finish_invocation("id", InvocationStatus.FAILED, metadata, "provider.schema")
    )
    stored = json.loads(path.read_text())[0]
    assert stored["error_code"] == "provider.schema"
    assert stored["metadata"]["usage"]["cost_cny"] is None
    summary = pilot.cost_summary(recorder, budget)
    assert summary["totalApiCostCny"] is None
    assert summary["reservedCny"] == "2.032768"
    assert summary["attemptCount"] == 1
    assert not path.with_suffix(".json.tmp").exists()


def test_existing_evidence_directory_is_never_overwritten(tmp_path: Path) -> None:
    output = tmp_path / "artifacts/pilot"
    output.mkdir(parents=True)
    evidence = output / "frozen-manifest.json"
    evidence.write_text("immutable evidence")
    with pytest.raises(AppError) as caught:
        asyncio.run(
            pilot.run_pilot(tmp_path, tmp_path / "source.mp4", output, [0], Decimal(5), 12, True)
        )
    assert caught.value.code == "pilot.output_exists"
    assert evidence.read_text() == "immutable evidence"
    assert not (output / "invocations.json").exists()


def test_dry_pilot_freezes_before_any_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "artifacts/dry"

    class Processor:
        def __init__(self, repository: Path) -> None:
            assert repository == tmp_path

        async def probe(self, video: Path, context: object) -> MediaAsset:
            return media_fixture(output / "media").asset

        async def preprocess(
            self, video: Path, directory: Path, parameters: object, context: object
        ) -> MediaPreprocessingResult:
            directory.mkdir()
            media = media_fixture(directory)
            media.manifest_path.write_text("local preprocessing")
            return media

    def forbidden_transport() -> None:
        raise AssertionError("Dry preparation must never construct a transport.")

    monkeypatch.setattr(pilot, "FfmpegMediaProcessor", Processor)
    monkeypatch.setattr(pilot, "HttpxVisionTransport", forbidden_transport)
    report = asyncio.run(
        pilot.run_pilot(
            tmp_path, tmp_path / "source.mp4", output, [10_000_000], Decimal(5), 12, False
        )
    )
    frozen = json.loads((output / "frozen-manifest.json").read_text())
    assert report["status"] == "frozen"
    assert report["qualityGate"] is None
    assert frozen["sourceClockOriginSeconds"] == "5"
    assert frozen["sourceSha256"] == "a" * 64
    assert [len(case["selectedFrames"]) for case in frozen["cases"]] == [5, 9, 9, 9]
    assert frozen["humanLabels"] is None
    assert report["cost"]["requestCount"] == 0
    assert report["cost"]["totalApiCostCny"] == "0"
    assert json.loads((output / "invocations.json").read_text()) == []
