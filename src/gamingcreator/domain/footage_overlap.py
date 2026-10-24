"""Shared-footage evidence between two videos from perceptual frame signatures.

Pure computation: no I/O. A sequence is a tuple of 64-bit difference hashes sampled at a fixed
rate; ``None`` marks a frame without enough visual information to be compared.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

HASH_WIDTH = 9
HASH_HEIGHT = 8
MIN_FRAME_STDEV = 8.0


def difference_hash(
    pixels: Sequence[int], width: int = HASH_WIDTH, height: int = HASH_HEIGHT
) -> int:
    """Row-major dHash: one bit per horizontally adjacent pair, ``px[c] > px[c + 1]``."""
    if width < 2 or height < 1 or len(pixels) != width * height:
        raise ValueError("Pixel count must equal width * height.")
    value = 0
    for row in range(height):
        base = row * width
        for column in range(width - 1):
            value = (value << 1) | (1 if pixels[base + column] > pixels[base + column + 1] else 0)
    return value


def pixel_stdev(pixels: Sequence[int]) -> float:
    """Population standard deviation of the pixel values."""
    if not pixels:
        raise ValueError("Pixels are required.")
    mean = sum(pixels) / len(pixels)
    return math.sqrt(sum((value - mean) ** 2 for value in pixels) / len(pixels))


def frame_signature(
    pixels: Sequence[int],
    width: int = HASH_WIDTH,
    height: int = HASH_HEIGHT,
    min_stdev: float = MIN_FRAME_STDEV,
) -> int | None:
    """Hash of an informative frame, or ``None`` when its pixel stdev is below the threshold."""
    if pixel_stdev(pixels) < min_stdev:
        return None
    return difference_hash(pixels, width, height)


@dataclass(frozen=True, slots=True)
class OverlapParameters:
    """Explicit detection parameters; every value is recorded in the inventory report."""

    samples_per_second: int = 2
    max_distance: int = 10
    merge_radius: int = 1
    min_compared: int = 20
    alpha: float = 1e-6
    background_floor: float = 0.01
    distinct_distance: int = 6
    min_distinct: int = 3
    cluster_gap: int = 4

    def __post_init__(self) -> None:
        if (
            any(
                type(value) is not int
                for value in (
                    self.samples_per_second,
                    self.max_distance,
                    self.merge_radius,
                    self.min_compared,
                    self.distinct_distance,
                    self.min_distinct,
                    self.cluster_gap,
                )
            )
            or self.samples_per_second <= 0
            or not 0 <= self.max_distance <= 64
            or self.merge_radius < 0
            or self.min_compared <= 0
            or not 1 <= self.distinct_distance <= 64
            or self.min_distinct < 1
            or self.cluster_gap < 0
            or not 0.0 < self.alpha < 1.0
            or not 0.0 < self.background_floor < 1.0
        ):
            raise ValueError("Invalid overlap parameters.")

    def to_dict(self) -> dict[str, object]:
        return {
            "samplesPerSecond": self.samples_per_second,
            "maxHammingDistance": self.max_distance,
            "mergeRadiusSamples": self.merge_radius,
            "minComparedSamples": self.min_compared,
            "alpha": self.alpha,
            "backgroundRateFloor": self.background_floor,
            "distinctContentDistance": self.distinct_distance,
            "minDistinctContents": self.min_distinct,
            "clusterMaxGapSamples": self.cluster_gap,
            "correction": "bonferroni-over-eligible-offset-windows",
        }


@dataclass(frozen=True, slots=True)
class SharedOffset:
    """One significant sample offset; ``offset_samples = index_in_A - index_in_B``."""

    offset_samples: int
    offset_seconds: float
    compared_votes: int
    matched_votes: int
    matched_frames_a: int
    cluster_count: int
    background_rate: float
    log10_corrected_p: float
    corrected_p: float
    a_first_seconds: float
    a_last_seconds: float
    b_first_seconds: float
    b_last_seconds: float


def binomial_log_sf(matches: int, trials: int, probability: float) -> float:
    """Natural log of P(X >= matches) for X ~ Binomial(trials, probability), in log space."""
    if matches <= 0:
        return 0.0
    if matches > trials or probability <= 0.0:
        return -math.inf
    if probability >= 1.0:
        return 0.0
    log_p = math.log(probability)
    log_q = math.log1p(-probability)
    log_choose_base = math.lgamma(trials + 1)
    terms: list[float] = []
    best = -math.inf
    peak = trials * probability
    for x in range(matches, trials + 1):
        term = (
            log_choose_base
            - math.lgamma(x + 1)
            - math.lgamma(trials - x + 1)
            + x * log_p
            + (trials - x) * log_q
        )
        terms.append(term)
        best = max(best, term)
        if x > peak and term < best - 45.0:
            break
    return best + math.log(sum(math.exp(term - best) for term in terms))


def _enough_distinct(
    frames: Sequence[int], hashes: Sequence[int | None], distance: int, required: int
) -> bool:
    """Greedy count of visually distinct contents among the given frame indices."""
    kept: list[int] = []
    for index in sorted(frames):
        value = hashes[index]
        assert value is not None
        if all((value ^ other).bit_count() >= distance for other in kept):
            kept.append(value)
            if len(kept) >= required:
                return True
    return False


def _clusters(indices: Sequence[int], max_gap: int) -> list[list[int]]:
    """Split sorted distinct indices where consecutive values are more than ``max_gap`` apart."""
    groups: list[list[int]] = []
    for index in sorted(indices):
        if groups and index - groups[-1][-1] <= max_gap:
            groups[-1].append(index)
        else:
            groups.append([index])
    return groups


def find_shared_offsets(
    a: Sequence[int | None],
    b: Sequence[int | None],
    parameters: OverlapParameters | None = None,
) -> tuple[SharedOffset, ...]:
    """Significant, non-overlapping offsets where A and B show near-identical frames.

    Every informative A/B frame pair votes at offset ``i - j``. A window of ``2 * merge_radius + 1``
    neighbouring offsets is evaluated together to tolerate animation timing differences. The
    background match rate is the pair-wide rate over all offsets (with a floor). Windows are
    tested with a one-sided binomial tail, Bonferroni-corrected by the number of eligible windows.
    The reported A/B ranges come from the densest contiguous cluster of matched A samples (gaps up
    to ``cluster_gap`` samples), so a distant chance hit cannot stretch them. A cluster must show
    enough distinct content on both sides (static title cards collapse to one or two distinct
    hashes and are dropped), and for one pair a less significant candidate whose cluster range
    overlaps a kept one is dropped. Votes are correlated, so p-values are nominal ranking scores.
    """
    settings = parameters or OverlapParameters()
    a_items = [(i, h) for i, h in enumerate(a) if h is not None]
    b_items = [(j, h) for j, h in enumerate(b) if h is not None]
    if not a_items or not b_items:
        return ()
    base = len(b) - 1
    size = len(a) + len(b) - 1
    compared = [0] * size
    matched = [0] * size
    hits: dict[int, list[tuple[int, int]]] = {}
    limit = settings.max_distance
    for i, hash_a in a_items:
        row = i + base
        for j, hash_b in b_items:
            k = row - j
            compared[k] += 1
            if (hash_a ^ hash_b).bit_count() <= limit:
                matched[k] += 1
                hits.setdefault(k, []).append((i, j))
    total_pairs = len(a_items) * len(b_items)
    background = min(max(sum(matched) / total_pairs, settings.background_floor), 1.0)
    radius = settings.merge_radius
    compared_prefix = [0]
    matched_prefix = [0]
    for index in range(size):
        compared_prefix.append(compared_prefix[-1] + compared[index])
        matched_prefix.append(matched_prefix[-1] + matched[index])
    windows: list[tuple[int, int, int]] = []
    for k in range(size):
        low, high = max(0, k - radius), min(size, k + radius + 1)
        window_compared = compared_prefix[high] - compared_prefix[low]
        if window_compared >= settings.min_compared:
            windows.append((k, window_compared, matched_prefix[high] - matched_prefix[low]))
    if not windows:
        return ()
    log_tests = math.log(len(windows))
    log_alpha = math.log(settings.alpha)
    candidates: list[tuple[float, int, int, int, int]] = []
    for k, window_compared, window_matched in windows:
        if window_matched <= window_compared * background:
            continue
        corrected = binomial_log_sf(window_matched, window_compared, background) + log_tests
        if corrected <= log_alpha:
            candidates.append((corrected, -window_matched, k, window_compared, window_matched))
    candidates.sort()
    accepted: list[SharedOffset] = []
    a_ranges: list[tuple[int, int]] = []
    b_ranges: list[tuple[int, int]] = []
    rate = settings.samples_per_second
    for corrected, _, k, window_compared, window_matched in candidates:
        pairs = [
            pair
            for neighbour in range(max(0, k - radius), min(size, k + radius + 1))
            for pair in hits.get(neighbour, ())
        ]
        groups = _clusters(list({i for i, _ in pairs}), settings.cluster_gap)
        cluster = max(groups, key=lambda group: (len(group), -group[0]))
        members = set(cluster)
        a_frames = cluster
        b_frames = list({j for i, j in pairs if i in members})
        if not (
            _enough_distinct(a_frames, a, settings.distinct_distance, settings.min_distinct)
            and _enough_distinct(b_frames, b, settings.distinct_distance, settings.min_distinct)
        ):
            continue
        a_range = (min(a_frames), max(a_frames))
        b_range = (min(b_frames), max(b_frames))
        if any(a_range[0] <= end and start <= a_range[1] for start, end in a_ranges) or any(
            b_range[0] <= end and start <= b_range[1] for start, end in b_ranges
        ):
            continue
        a_ranges.append(a_range)
        b_ranges.append(b_range)
        # Report the member offset carrying the most matches (nearest the centre on ties).
        peak = max(
            range(max(0, k - radius), min(size, k + radius + 1)),
            key=lambda neighbour: (matched[neighbour], -abs(neighbour - k), -neighbour),
        )
        offset = peak - base
        accepted.append(
            SharedOffset(
                offset,
                offset / rate,
                window_compared,
                window_matched,
                len(a_frames),
                len(groups),
                background,
                corrected / math.log(10),
                math.exp(corrected) if corrected > -700.0 else 0.0,
                a_range[0] / rate,
                a_range[1] / rate,
                b_range[0] / rate,
                b_range[1] / rate,
            )
        )
    return tuple(accepted)
