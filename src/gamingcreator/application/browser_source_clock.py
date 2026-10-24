"""Pure player-clock ↔ canonical-source-clock semantics for both acceptance pages.

The browser's media timeline is decided by the media resource, so `currentTime` cannot be
assumed to be canonical source seconds before it is measured (WHATWG HTML media element
timeline).  Chromium was observed with real probe data and visual frame marks to expose the
container's absolute presentation clock: for the verified MP4 classes below, the settled
`currentTime` axis starts at the probed stream start (``MediaAsset.origin_seconds``), and a
player position converts to canonical source µs by subtracting that origin.  This module
only holds the pure arithmetic and the observation checks; it performs no I/O, stores
nothing in frozen identities and never changes `MediaAsset`.

Verified classes (2026-10-24, project FFmpeg + Chromium, synthetic marker clips):
zero origin; a whole-file non-zero PTS offset; audio starting later than video; video
starting later than audio (clock verified, but the no-picture head is not replayable);
a negative whole-file offset muxed back to zero; and a fragmented MP4 with a small origin.
A container whose header duration disagrees with the probed stream span is refused.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction

from gamingcreator.domain.media import MediaAsset, ceil_us, floor_us

CLOCK_VERSION = "browser-source-clock-v1"
QUANTUM_US = 1_000_000
MAX_SAFE_INTEGER = 9_007_199_254_740_991

# The measured axis start is read back from `currentTime` as an IEEE-754 double, so it is
# microsecond-exact for any realistic length.  2 ms absorbs container timebase rounding
# while staying far below one video frame (16.7 ms at 60 fps) and one AAC priming block
# (21.3 ms at 48 kHz); a different stream start can therefore never be mistaken for the
# probed origin.
AXIS_TOLERANCE_US = 2_000
# The container header duration and the probed stream span may legitimately differ by
# encoder priming/padding.  50 ms is below two 30 fps frames; a larger difference means the
# browser timeline and the probed asset disagree about the media length.
DURATION_TOLERANCE_US = 50_000

_UNSET = object()


def _microseconds(value: Fraction) -> int:
    """Round an exact rational second value to the nearest microsecond (half up)."""
    return floor_us(value + Fraction(1, 2 * QUANTUM_US))


@dataclass(frozen=True, slots=True)
class BrowserSourceClock:
    """Runtime-only mapping between the browser player axis and canonical source µs."""

    origin_us: int
    duration_us: int
    video_start_us: int
    video_end_us: int
    audio_start_us: int | None
    audio_end_us: int | None
    axis_tolerance_us: int = AXIS_TOLERANCE_US
    duration_tolerance_us: int = DURATION_TOLERANCE_US

    def __post_init__(self) -> None:
        integer_fields = (
            self.origin_us,
            self.duration_us,
            self.video_start_us,
            self.video_end_us,
            self.axis_tolerance_us,
            self.duration_tolerance_us,
        )
        if any(type(value) is not int for value in integer_fields):
            raise ValueError("Browser source clock needs integer microsecond bounds.")
        if (
            self.origin_us < 0
            or self.duration_us <= 0
            or self.axis_tolerance_us <= 0
            or self.duration_tolerance_us <= 0
            or not 0 <= self.video_start_us < self.video_end_us <= self.duration_us
        ):
            raise ValueError("Browser source clock bounds are invalid.")
        audio = (self.audio_start_us, self.audio_end_us)
        if (audio[0] is None) != (audio[1] is None):
            raise ValueError("Audio coverage needs both bounds.")
        if audio[0] is not None and (
            any(type(value) is not int for value in audio)
            or not 0 <= audio[0] < audio[1] <= self.duration_us  # type: ignore[operator]
        ):
            raise ValueError("Audio coverage bounds are invalid.")
        for value in integer_fields:
            if abs(value) > MAX_SAFE_INTEGER:
                raise ValueError("Browser source clock exceeds safe integer range.")

    @property
    def axis_start_us(self) -> int:
        """Canonical source µs at player position zero, once the mapping is established."""
        return self.origin_us

    @property
    def axis_end_us(self) -> int:
        return self.origin_us + self.duration_us


def build_source_clock(asset: MediaAsset) -> BrowserSourceClock | None:
    """Derive the runtime clock document for one probed asset, or None if not representable.

    A media whose canonical origin is negative cannot be addressed by a browser player
    (``currentTime`` cannot go below zero), and a media without exactly one selected video
    stream is outside the verified contract; both fall back to manual entry.
    """
    videos = [stream for stream in asset.streams if stream.kind == "video"]
    audios = [stream for stream in asset.streams if stream.kind == "audio"]
    if len(videos) != 1 or len(audios) > 1:
        return None
    if asset.origin_seconds < 0 or type(asset.duration_us) is not int or asset.duration_us <= 0:
        return None
    video = videos[0]
    origin = asset.origin_seconds
    video_start = max(floor_us(video.start_seconds - origin), 0)
    video_end = min(ceil_us(video.end_seconds - origin), asset.duration_us)
    audio_start = audio_end = None
    if audios:
        audio = audios[0]
        audio_start = max(floor_us(audio.start_seconds - origin), 0)
        audio_end = min(ceil_us(audio.end_seconds - origin), asset.duration_us)
    try:
        return BrowserSourceClock(
            origin_us=_microseconds(origin),
            duration_us=asset.duration_us,
            video_start_us=video_start,
            video_end_us=video_end,
            audio_start_us=audio_start,
            audio_end_us=audio_end,
        )
    except ValueError:
        return None


def clock_document(clock: BrowserSourceClock) -> dict[str, object]:
    """JSON-ready runtime context for one page; never written into frozen identities."""
    return {
        "schemaVersion": CLOCK_VERSION,
        "originUs": clock.origin_us,
        "durationUs": clock.duration_us,
        "videoStartUs": clock.video_start_us,
        "videoEndUs": clock.video_end_us,
        "audioStartUs": clock.audio_start_us,
        "audioEndUs": clock.audio_end_us,
        "axisToleranceUs": clock.axis_tolerance_us,
        "durationToleranceUs": clock.duration_tolerance_us,
    }


def player_seconds_to_source_us(clock: BrowserSourceClock, seconds: object) -> int | None:
    """Convert a measured player position to canonical source µs, or None when invalid.

    The result is clamped into ``[0, duration_us]``; a position outside the axis by more
    than ``axis_tolerance_us`` is rejected instead of silently clamped.
    """
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        return None
    value = float(seconds)
    if not math.isfinite(value):
        return None
    scaled = value * QUANTUM_US
    if not math.isfinite(scaled) or abs(scaled) > MAX_SAFE_INTEGER:
        return None
    source = math.floor(scaled + 0.5) - clock.origin_us
    if source < -clock.axis_tolerance_us or source > clock.duration_us + clock.axis_tolerance_us:
        return None
    return min(max(source, 0), clock.duration_us)


def source_us_to_player_seconds(clock: BrowserSourceClock, source_us: object) -> float | None:
    """Convert canonical source µs to the player position that displays it."""
    if isinstance(source_us, bool) or not isinstance(source_us, int):
        return None
    if not 0 <= source_us <= clock.duration_us:
        return None
    return (source_us + clock.origin_us) / QUANTUM_US


def interval_replayable(clock: BrowserSourceClock, start_us: object, end_us: object) -> bool:
    """Whether an automatic interval replay can show real picture for the whole interval."""
    if (
        isinstance(start_us, bool)
        or isinstance(end_us, bool)
        or not isinstance(start_us, int)
        or not isinstance(end_us, int)
    ):
        return False
    if not 0 <= start_us < end_us <= clock.duration_us:
        return False
    return start_us >= clock.video_start_us and end_us <= clock.video_end_us


def capture_source_us(clock: BrowserSourceClock, seconds: object) -> int | None:
    """Canonical source µs for an automatic capture, or None where no picture is shown."""
    source = player_seconds_to_source_us(clock, seconds)
    if source is None or not clock.video_start_us <= source <= clock.video_end_us:
        return None
    return source


def duration_change_verdict(
    clock: BrowserSourceClock, duration_seconds: object, *, seeked: bool
) -> str | None:
    """Judge a later ``durationchange`` against the probed clock.

    Returns None while the reported duration is acceptable, else ``duration_unavailable``
    (non-finite/absent), ``duration_mismatch`` (shrink) or ``duration_changed`` (unexpected
    growth). The only growth accepted is the measured Chromium behaviour for a non-zero-PTS
    MP4 after a seek on that element, bounded by the absolute axis end
    ``origin + span``; everything else revokes the automatic capability.
    """
    if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, (int, float)):
        return "duration_unavailable"
    value = float(duration_seconds)
    if not math.isfinite(value) or value <= 0:
        return "duration_unavailable"
    reported = value * QUANTUM_US
    if reported < clock.duration_us - clock.duration_tolerance_us:
        return "duration_mismatch"
    if reported <= clock.duration_us + clock.duration_tolerance_us:
        return None
    if (
        seeked
        and clock.origin_us > 0
        and reported <= clock.origin_us + clock.duration_us + clock.duration_tolerance_us
    ):
        return None
    return "duration_changed"


def validate_browser_observation(
    clock: BrowserSourceClock, observation: Mapping[str, object]
) -> str | None:
    """Return None when the measured browser timeline matches the probed clock.

    Reasons are stable codes so both pages and the tests share one decision table:
    ``seek_unavailable``, ``seek_incomplete``, ``duration_unavailable``,
    ``duration_mismatch``, ``axis_unavailable``, ``axis_unstable`` and ``axis_mismatch``.
    """
    seekable = observation.get("seekable", _UNSET)
    if type(seekable) is not bool:
        return "observation_invalid"
    if not seekable:
        return "seek_unavailable"
    duration = observation.get("durationSeconds")
    if isinstance(duration, bool) or not isinstance(duration, (int, float)):
        return "duration_unavailable"
    length = float(duration)
    if not math.isfinite(length) or length <= 0:
        return "duration_unavailable"
    if abs(length * QUANTUM_US - clock.duration_us) > clock.duration_tolerance_us:
        return "duration_mismatch"
    # One clamped seek at the start is not enough: the intermediate seek has to complete too.
    middle = observation.get("middleSeconds")
    if isinstance(middle, bool) or not isinstance(middle, (int, float)):
        return "seek_incomplete"
    if not math.isfinite(float(middle)):
        return "seek_incomplete"
    raw_axis = observation.get("axisStartsSeconds")
    if type(raw_axis) is not list or len(raw_axis) < 2:
        return "axis_unavailable"
    axis: list[float] = []
    for item in raw_axis:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return "axis_unavailable"
        value = float(item)
        if not math.isfinite(value):
            return "axis_unavailable"
        axis.append(value)
    if (max(axis) - min(axis)) * QUANTUM_US > clock.axis_tolerance_us:
        return "axis_unstable"
    if abs(axis[0] * QUANTUM_US - clock.origin_us) > clock.axis_tolerance_us:
        return "axis_mismatch"
    return None


def runtime_clock_document(asset: MediaAsset) -> dict[str, object] | None:
    """Clock document for a page context, or None when the asset is statically unsupported."""
    clock = build_source_clock(asset)
    return None if clock is None else clock_document(clock)
