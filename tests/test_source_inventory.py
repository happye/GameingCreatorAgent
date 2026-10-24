"""Shared-footage detection on constructed hash sequences and synthetic lavfi media."""

import asyncio
import json
import math
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from gamingcreator.application.source_inventory import (
    build_source_inventory,
    discover_sources,
    ensure_output_outside_sources,
)
from gamingcreator.cli.main import main
from gamingcreator.domain.errors import AppError
from gamingcreator.domain.footage_overlap import (
    OverlapParameters,
    binomial_log_sf,
    difference_hash,
    find_shared_offsets,
    frame_signature,
    pixel_stdev,
)
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.infrastructure.ffmpeg_signatures import FfmpegSignatureExtractor

ROOT = Path(__file__).resolve().parents[1]
FFMPEG = ROOT / ".tools/ffmpeg/bin/ffmpeg.exe"


def random_sequence(seed: int, length: int) -> list[int | None]:
    generator = random.Random(seed)
    return [generator.getrandbits(64) for _ in range(length)]


def flip_bits(value: int, count: int, generator: random.Random) -> int:
    for bit in generator.sample(range(64), count):
        value ^= 1 << bit
    return value


def test_difference_hash_compares_neighbours_per_row_and_rejects_bad_sizes() -> None:
    row = [9, 8, 7, 6, 5, 4, 3, 2, 1]
    assert difference_hash(row * 8) == (1 << 64) - 1
    assert difference_hash(list(reversed(row)) * 8) == 0
    first_row_only = [1, 0, 1, 0, 1, 0, 1, 0, 1] + [0] * 63
    assert difference_hash(first_row_only) == 0b10101010 << 56
    with pytest.raises(ValueError):
        difference_hash([1, 2, 3])


def test_flat_frames_are_not_informative() -> None:
    assert pixel_stdev([7] * 72) == 0.0
    assert frame_signature([7] * 72) is None
    assert frame_signature([0, 255] * 36) is not None
    assert frame_signature([100, 101] * 36) is None


def test_binomial_tail_is_exact_and_stable_in_log_space() -> None:
    assert binomial_log_sf(10, 10, 0.5) == pytest.approx(math.log(2**-10))
    assert binomial_log_sf(0, 10, 0.5) == 0.0
    assert binomial_log_sf(11, 10, 0.5) == -math.inf
    expected = math.log(sum(math.comb(5, x) * 0.2**x * 0.8 ** (5 - x) for x in range(2, 6)))
    assert binomial_log_sf(2, 5, 0.2) == pytest.approx(expected)
    deep = binomial_log_sf(2000, 3000, 0.01)
    assert math.isfinite(deep) and deep < -5000


def test_shifted_copy_with_noise_is_reported_with_exact_offset_and_ranges() -> None:
    generator = random.Random(3)
    a = random_sequence(1, 200)
    # B shows A[40:120] after 20 unrelated samples; slight per-frame hash noise stays within 10.
    b: list[int | None] = [*random_sequence(2, 20)]
    b.extend(flip_bits(value or 0, 4, generator) for value in a[40:120])
    b.extend(random_sequence(4, 30))
    found = find_shared_offsets(a, b)
    assert len(found) == 1
    shared = found[0]
    assert shared.offset_samples == 20
    assert shared.offset_seconds == 10.0
    assert shared.matched_votes >= 78
    assert shared.matched_frames_a >= 78
    assert shared.cluster_count == 1
    assert (shared.a_first_seconds, shared.a_last_seconds) == (20.0, 59.5)
    assert (shared.b_first_seconds, shared.b_last_seconds) == (10.0, 49.5)
    assert shared.corrected_p < 1e-6
    assert shared.log10_corrected_p < -6


def test_distant_chance_hit_on_the_same_offset_does_not_stretch_reported_ranges() -> None:
    generator = random.Random(31)
    a = random_sequence(32, 260)
    b: list[int | None] = [*random_sequence(33, 20)]
    b.extend(flip_bits(value or 0, 4, generator) for value in a[40:120])
    b.extend(random_sequence(34, 140))
    b[230] = a[250]  # one chance hit on the same offset (+20), 65 s after the real segment
    found = find_shared_offsets(a, b)
    assert len(found) == 1
    shared = found[0]
    assert shared.offset_samples == 20
    assert (shared.a_first_seconds, shared.a_last_seconds) == (20.0, 59.5)
    assert (shared.b_first_seconds, shared.b_last_seconds) == (10.0, 49.5)
    assert shared.matched_frames_a == 80
    assert shared.cluster_count == 2
    assert find_shared_offsets(a, b, OverlapParameters(cluster_gap=1000))[0].a_last_seconds == 125.0


def test_unrelated_and_small_samples_are_not_reported() -> None:
    assert find_shared_offsets(random_sequence(5, 300), random_sequence(6, 300)) == ()
    a = random_sequence(7, 12)
    assert find_shared_offsets(a, [*a]) == ()  # only 12 comparable frames: below min_compared
    assert find_shared_offsets([None] * 80, random_sequence(8, 80)) == ()
    assert find_shared_offsets([], random_sequence(8, 80)) == ()


def test_bonferroni_correction_multiplies_raw_tail_by_the_tested_windows() -> None:
    a = random_sequence(9, 400)
    base_b = random_sequence(10, 400)
    marginal = None
    for hits in range(6, 40):
        b = list(base_b)
        for index in range(hits):
            b[100 + index] = a[10 + index]
        if find_shared_offsets(a, b, OverlapParameters(alpha=1e-6)):
            continue
        loose = find_shared_offsets(a, b, OverlapParameters(alpha=1e-2))
        if loose:
            marginal = loose[0]
            break
    assert marginal is not None, "some hit count must be significant only without correction"
    raw = binomial_log_sf(marginal.matched_votes, marginal.compared_votes, marginal.background_rate)
    windows = math.exp(marginal.log10_corrected_p * math.log(10) - raw)
    assert marginal.offset_samples == -90
    assert marginal.corrected_p > 1e-6
    assert 500 < windows < 800  # roughly one window per scanned offset (a + b - 1 = 799)


def test_adjacent_offsets_merge_votes_and_result_is_a_single_non_overlapping_peak() -> None:
    a = random_sequence(11, 150)
    b = list(random_sequence(12, 150))
    # Timing drift: even B frames show A at -30 samples, odd B frames at -31 samples.
    for j in range(60, 140):
        b[j] = a[j - 30 - j % 2]
    merged = find_shared_offsets(a, b, OverlapParameters(merge_radius=1))
    assert len(merged) == 1
    assert merged[0].offset_samples in (-30, -31)
    assert merged[0].matched_votes == 80
    # Without merging each drift offset is its own candidate, yet both cover the same A/B
    # frames, so only the more significant one is kept.
    unmerged = find_shared_offsets(a, b, OverlapParameters(merge_radius=0))
    assert len(unmerged) == 1
    assert unmerged[0].offset_samples in (-30, -31)
    assert unmerged[0].matched_votes == 40


def test_two_distant_shared_segments_are_both_selected_in_significance_order() -> None:
    a = random_sequence(13, 300)
    b = list(random_sequence(14, 300))
    for index in range(100):
        b[index] = a[index + 150]  # offset +150
    for index in range(40):
        b[200 + index] = a[20 + index]  # offset -180
    found = find_shared_offsets(a, b)
    assert [s.offset_samples for s in found] == [150, -180]
    assert found[0].log10_corrected_p < found[1].log10_corrected_p


def test_static_title_cards_are_not_shared_footage_but_moving_content_is() -> None:
    generator = random.Random(21)
    card_a = generator.getrandbits(64)
    card_b = flip_bits(card_a, 3, generator)
    a: list[int | None] = [
        *random_sequence(22, 60),
        *(flip_bits(card_a, 2, generator) for _ in range(30)),
        *random_sequence(23, 60),
    ]
    b: list[int | None] = [
        *random_sequence(24, 10),
        *(flip_bits(card_b, 2, generator) for _ in range(30)),
        *random_sequence(25, 60),
    ]
    assert find_shared_offsets(a, b, OverlapParameters(min_distinct=1))  # hashes do match
    assert find_shared_offsets(a, b) == ()
    # Same layout with moving (distinct) content is reported.
    moving = random_sequence(26, 30)
    a[60:90] = moving
    b[10:40] = [flip_bits(v or 0, 2, generator) for v in moving]
    assert [s.offset_samples for s in find_shared_offsets(a, b)] == [50]


def test_static_card_pixels_collapse_to_one_signature() -> None:
    def card(background: int, block: int) -> list[int]:
        pixels = [background] * 72
        for row in (3, 4):
            for column in (3, 4, 5):
                pixels[row * 9 + column] = block
        return pixels

    black = frame_signature(card(0, 255))
    white = frame_signature(card(255, 0))
    assert black is not None and white is not None
    assert frame_signature(card(0, 255)) == black
    assert frame_signature(card(255, 0)) == white


def test_parameters_validate_and_serialize() -> None:
    assert OverlapParameters().to_dict()["maxHammingDistance"] == 10
    for bad in (
        {"alpha": 0.0},
        {"alpha": 1.0},
        {"min_compared": 0},
        {"max_distance": 65},
        {"background_floor": 0.0},
        {"samples_per_second": 0},
        {"min_distinct": 0},
        {"distinct_distance": 0},
    ):
        with pytest.raises(ValueError):
            OverlapParameters(**bad)  # type: ignore[arg-type]


def make_video(destination: Path, spec: str, seconds: int) -> None:
    subprocess.run(
        [
            str(FFMPEG),
            "-hide_banner",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            spec,
            "-t",
            str(seconds),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-y",
            str(destination),
        ],
        check=True,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def make_derived(original: Path, destination: Path, prefix_seconds: int, keep_seconds: int) -> None:
    """Other footage first, then the original, rescaled, brightened and re-encoded."""
    subprocess.run(
        [
            str(FFMPEG),
            "-hide_banner",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-t",
            str(prefix_seconds),
            "-i",
            "gradients=size=160x96:rate=10:speed=0.05",
            "-t",
            str(keep_seconds),
            "-i",
            str(original),
            "-filter_complex",
            "[0:v]scale=320:192,setsar=1,fps=10[p];[1:v]scale=320:192,setsar=1,fps=10[o];"
            "[p][o]concat=n=2:v=1:a=0,eq=brightness=0.05[v]",
            "-map",
            "[v]",
            "-c:v",
            "libx264",
            "-crf",
            "30",
            "-pix_fmt",
            "yuv420p",
            "-y",
            str(destination),
        ],
        check=True,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


@pytest.fixture(scope="module")
def media_directory(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not FFMPEG.is_file():
        pytest.skip("Project-local FFmpeg not prepared")
    directory = tmp_path_factory.mktemp("素材 盘点")
    make_video(directory / "原片.mp4", "mandelbrot=size=160x96:rate=10", 24)
    make_derived(directory / "原片.mp4", directory / "派生 片.mp4", 3, 16)
    make_video(directory / "无关.mp4", "testsrc2=size=160x96:rate=10", 20)
    make_video(directory / "纯色.mp4", "color=c=0x404040:size=160x96:rate=10", 12)
    shutil.copyfile(directory / "原片.mp4", directory / "副本.mp4")
    (directory / "损坏.mp4").write_bytes(b"this is not a video" * 50)
    return directory


def run_inventory(inputs: list[Path]) -> dict[str, object]:
    sources = discover_sources(inputs)
    return asyncio.run(
        build_source_inventory(
            sources, FfmpegMediaProcessor(ROOT), FfmpegSignatureExtractor(ROOT), timeout_seconds=120
        )
    )


def test_inventory_reports_derived_overlap_duplicates_and_nothing_else(
    media_directory: Path,
) -> None:
    report = run_inventory([media_directory])
    assert report["schemaVersion"] == "source-inventory-v1"
    assert report["humanDecisionRequired"] is True
    sources = {Path(str(s["path"])).name: s for s in report["sources"]}  # type: ignore[attr-defined]
    assert set(sources) == {"原片.mp4", "派生 片.mp4", "无关.mp4", "纯色.mp4", "副本.mp4"}
    assert sources["纯色.mp4"]["informativeFrames"] == 0
    not_comparable = report["notComparable"]
    assert [Path(item["path"]).name for item in not_comparable] == ["纯色.mp4"]  # type: ignore[attr-defined]
    assert not_comparable[0]["informativeFrames"] == 0  # type: ignore[index]
    failed = report["failedSources"]
    assert [Path(item["path"]).name for item in failed] == ["损坏.mp4"]  # type: ignore[attr-defined]
    assert failed[0]["code"].startswith("input.")  # type: ignore[index]
    assert failed[0]["sourceId"] not in {e["sourceId"] for e in report["sources"]}  # type: ignore[index,attr-defined]
    assert (
        report["parameters"]["samplingFilter"] == FfmpegSignatureExtractor.identity.sampling_filter
    )  # type: ignore[index]
    assert report["parameters"]["minFrameStdev"] == 8.0  # type: ignore[index]
    assert sources["原片.mp4"]["sampledFrames"] >= 46
    assert sources["原片.mp4"]["durationUs"] > 23_000_000
    assert sources["派生 片.mp4"]["video"]["width"] == 320  # type: ignore[index]
    assert str(report["ffmpegVersion"]).startswith("ffmpeg version")
    duplicates = report["duplicateGroups"]
    assert len(duplicates) == 1  # type: ignore[arg-type]
    assert sorted(Path(p).name for p in duplicates[0]["paths"]) == ["副本.mp4", "原片.mp4"]  # type: ignore[index]
    candidates = report["sharedFootageCandidates"]
    names = {(Path(c["pathA"]).name, Path(c["pathB"]).name) for c in candidates}  # type: ignore[attr-defined]
    assert names <= {("原片.mp4", "派生 片.mp4"), ("副本.mp4", "派生 片.mp4")}
    assert ("原片.mp4", "派生 片.mp4") in names
    best = next(c for c in candidates if Path(c["pathA"]).name == "原片.mp4")  # type: ignore[attr-defined]
    assert best["offsetSeconds"] == pytest.approx(-3.0, abs=1.0)
    assert best["matchedVotes"] >= 20
    assert best["matchedFramesA"] >= 20
    assert best["clusterCount"] >= 1
    assert "comparedFrames" not in best
    assert best["correctedPValue"] <= 1e-6
    assert len(report["limitations"]) == 4  # type: ignore[arg-type]
    assert "未匹配不证明独立" in report["limitations"][0]  # type: ignore[index]
    assert not any("recordingGroup" in key for key in report)


def test_cli_writes_atomic_report_and_refuses_source_directory_output(
    media_directory: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "输出" / "inventory.json"
    assert (
        main(["inventory-sources", "--input", str(media_directory), "--output", str(output)]) == 0
    )
    printed = capsys.readouterr().out
    assert "已盘点 5 个素材" in printed
    assert "有效画面不足（0/" in printed
    assert "处理失败" in printed and "损坏.mp4" in printed
    assert "票／" in printed and "帧相近" not in printed
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["schemaVersion"] == "source-inventory-v1"
    assert not list(output.parent.glob("*.tmp"))
    before = sorted(path.name for path in media_directory.iterdir())
    inside = media_directory / "report.json"
    assert (
        main(["inventory-sources", "--input", str(media_directory), "--output", str(inside)]) == 2
    )
    assert not inside.exists()
    assert sorted(path.name for path in media_directory.iterdir()) == before


def test_discovery_orders_recursively_and_rejects_missing_or_empty_inputs(tmp_path: Path) -> None:
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "z.MP4").write_bytes(b"x")
    (tmp_path / "a.mp4").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    found = discover_sources([tmp_path, tmp_path / "a.mp4"])
    assert [path.name for path in found] == ["a.mp4", "z.MP4"]
    with pytest.raises(AppError):
        discover_sources([tmp_path / "missing.mp4"])
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(AppError):
        discover_sources([empty])
    with pytest.raises(AppError):
        ensure_output_outside_sources(tmp_path / "out.json", [tmp_path], found)
    ensure_output_outside_sources(tmp_path.parent / "elsewhere" / "out.json", [tmp_path], found)
