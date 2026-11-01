"""Export an edit decision to professional timeline formats (FCPXML 1.9, OpenTimelineIO JSON, xmeml).

Times are exact, frame-aligned rationals on the output clock; source in/out points come from the
saved source microseconds. Our renders overlap two clips by N frames for a crossfade; both
formats instead place clips end to end with a transition centred on the cut that borrows
handle media. Each clip is therefore trimmed by whole frames at the cut (N//2 on the left,
the rest on the right), so the exported timeline has exactly the rendered length.

Optional best-effort caption markers and stereo audio declarations can be included for
experimentation. Nothing here has been verified by importing into Final Cut, DaVinci Resolve
or Premiere — do not treat exports as NLE-certified.
"""

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape, quoteattr

from gamingcreator.domain.creation_subtitles import SubtitleCue


@dataclass(frozen=True, slots=True)
class ExportCaption:
    """Half-open output-timeline frames carrying caption text for experimental export."""

    start_frame: int
    end_frame: int
    text: str

    def __post_init__(self) -> None:
        if type(self.start_frame) is not int or type(self.end_frame) is not int:
            raise ValueError("Caption frames must be integers.")
        if not 0 <= self.start_frame < self.end_frame:
            raise ValueError("Caption interval must be nonempty and nonnegative.")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("Caption text must be nonempty.")
        object.__setattr__(self, "text", self.text.strip())


def captions_from_cues(cues: Iterable[SubtitleCue], fps: int) -> tuple[ExportCaption, ...]:
    """Quantize output-clock cues to whole frames; drop intervals that collapse."""
    if type(fps) is not int or fps <= 0:
        raise ValueError("fps must be a positive integer.")
    captions: list[ExportCaption] = []
    for cue in cues:
        start = (cue.start * fps).__floor__()
        end = (cue.end * fps).__floor__()
        if start >= end:
            continue
        captions.append(ExportCaption(start, end, cue.text))
    return tuple(captions)


def _normalize_captions(captions: Sequence[ExportCaption] | None) -> tuple[ExportCaption, ...]:
    if captions is None:
        return ()
    return tuple(ExportCaption(item.start_frame, item.end_frame, item.text) for item in captions)


def _rows(edl: dict[str, Any]) -> list[dict[str, Any]]:
    rows = edl.get("segments")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Timeline export needs at least one segment.")
    for row in rows:
        if not all(
            type(row.get(k)) is int
            for k in ("startUs", "endUs", "outputFrames", "sourceDurationUs")
        ):
            raise ValueError("Segments need integer source and output timing.")
        if not isinstance(row.get("sourcePath"), str):
            raise ValueError("Segments need their source file.")
    return rows


def _speed(row: dict[str, Any]) -> Fraction:
    speed = row.get("speed") or {"numerator": 1, "denominator": 1}
    return Fraction(speed["numerator"], speed["denominator"])


def _overlap(row: dict[str, Any]) -> int:
    transition = row.get("transitionIn") or {"type": "cut", "frames": 0}
    return int(transition["frames"]) if transition["type"] == "crossfade" else 0


def layout(edl: dict[str, Any]) -> list[dict[str, Any]]:
    """Per clip: output offset/duration (frames), source start (seconds), transition before."""
    rows = _rows(edl)
    fps = int(edl["fpsNumerator"])
    overlaps = [0, *(_overlap(row) for row in rows[1:])]
    placed, offset = [], 0
    for index, row in enumerate(rows):
        incoming = overlaps[index]
        outgoing = overlaps[index + 1] if index + 1 < len(rows) else 0
        trim_start = incoming - incoming // 2
        trim_end = outgoing // 2
        duration = row["outputFrames"] - trim_start - trim_end
        if duration <= 0:
            raise ValueError("A clip is shorter than its crossfades.")
        speed = _speed(row)
        placed.append(
            {
                "row": row,
                "offset": offset,
                "frames": duration,
                "sourceStart": Fraction(row["startUs"], 1_000_000)
                + Fraction(trim_start, fps) * speed,
                "speed": speed,
                # The transition before this clip starts incoming//2 frames before the cut.
                "transition": (offset - incoming // 2, incoming) if incoming else None,
            }
        )
        offset += duration
    return placed


def _seconds(value: Fraction) -> str:
    """FCPXML rational time string, e.g. 1/30s or 3s."""
    return (
        f"{value.numerator}s"
        if value.denominator == 1
        else f"{value.numerator}/{value.denominator}s"
    )


def _uri(path: str) -> str:
    return Path(path).resolve().as_uri()


def to_fcpxml(
    edl: dict[str, Any],
    name: str,
    width: int = 1920,
    height: int = 1080,
    captions: Sequence[ExportCaption] | None = None,
    include_audio_track: bool = False,
) -> str:
    placed = layout(edl)
    caption_rows = _normalize_captions(captions)
    fps = int(edl["fpsNumerator"])
    frame = Fraction(1, fps)
    sources = list(dict.fromkeys(item["row"]["sourcePath"] for item in placed))
    assets = []
    for index, source in enumerate(sources, 1):
        duration = max(
            Fraction(i["row"]["sourceDurationUs"], 1_000_000)
            for i in placed
            if i["row"]["sourcePath"] == source
        )
        assets.append(
            f'    <asset id="a{index}" name={quoteattr(Path(source).name)} start="0s" '
            f'duration="{_seconds(duration)}" hasVideo="1" hasAudio="1" format="r1">\n'
            f'      <media-rep kind="original-media" src={quoteattr(_uri(source))}/>\n    </asset>'
        )
    spine = []
    for item in placed:
        row = item["row"]
        if item["transition"]:
            start, frames = item["transition"]
            spine.append(
                f'            <transition name="Cross Dissolve" offset="{_seconds(start * frame)}" '
                f'duration="{_seconds(frames * frame)}"/>'
            )
        duration = item["frames"] * frame
        asset = f"a{sources.index(row['sourcePath']) + 1}"
        clip = (
            f'            <asset-clip ref="{asset}" offset="{_seconds(item["offset"] * frame)}" '
            f'start="{_seconds(item["sourceStart"])}" duration="{_seconds(duration)}" '
            f"name={quoteattr(row.get('role') or Path(row['sourcePath']).name)}"
        )
        inner: list[str] = []
        if item["speed"] != 1:
            # timeMap maps clip-local output time to source time for a constant speed.
            end = item["sourceStart"] + duration * item["speed"]
            inner.append(
                "              <timeMap>\n"
                f'                <timept time="0s" value="{_seconds(item["sourceStart"])}" interp="linear"/>\n'
                f'                <timept time="{_seconds(duration)}" value="{_seconds(end)}" interp="linear"/>\n'
                "              </timeMap>"
            )
        if include_audio_track:
            # Best-effort stereo declaration; not verified in Final Cut / Resolve.
            inner.append(
                '              <audio-channel-source srcCh="1,2" role="dialogue.dialogue"/>'
            )
        if inner:
            clip += ">\n" + "\n".join(inner) + "\n            </asset-clip>"
        else:
            clip += "/>"
        spine.append(clip)
    for caption in caption_rows:
        start = caption.start_frame * frame
        duration = (caption.end_frame - caption.start_frame) * frame
        spine.append(
            f'            <title name={quoteattr("Basic Title")} lane="1" '
            f'offset="{_seconds(start)}" ref="r1" duration="{_seconds(duration)}" '
            f'start="0s">\n'
            f'              <text>{escape(caption.text)}</text>\n'
            "            </title>"
        )
    total = sum(item["frames"] for item in placed) * frame
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n<fcpxml version="1.9">\n'
        "  <resources>\n"
        f'    <format id="r1" frameDuration="{_seconds(frame)}" width="{width}" height="{height}"/>\n'
        + "\n".join(assets)
        + '\n  </resources>\n  <library>\n    <event name="GamingCreator">\n'
        f"      <project name={quoteattr(name)}>\n"
        f'        <sequence format="r1" duration="{_seconds(total)}" tcStart="0s">\n'
        "          <spine>\n"
        + "\n".join(spine)
        + "\n          </spine>\n        </sequence>\n      </project>\n    </event>\n"
        "  </library>\n</fcpxml>\n"
    )


def _xmeml_timeremap(timeline_frames: int, speed: Fraction) -> str:
    """FCP7 / Premiere Time Remap filter for a constant speed (Apple xmeml effectid=timeremap).

    Constant speed uses parameter speed as a percent (100 = 1x), with variablespeed=0, as in
    the Final Cut Pro XML Interchange Format Time Remap effect that Premiere imports.
    Live import into Premiere is still unverified on this machine.
    """
    if speed == 1:
        return ""
    percent = float(speed * 100)
    return (
        "<filter><effect><name>Time Remap</name><effectid>timeremap</effectid>"
        "<effectcategory>motion</effectcategory><effecttype>filter</effecttype>"
        "<mediatype>video</mediatype>"
        "<parameter><parameterid>variablespeed</parameterid><name>variablespeed</name>"
        "<value>0</value></parameter>"
        f"<parameter><parameterid>speed</parameterid><name>speed</name>"
        f"<value>{percent:g}</value></parameter>"
        "<parameter><parameterid>reverse</parameterid><name>reverse</name>"
        "<value>FALSE</value></parameter>"
        "<parameter><parameterid>frameblending</parameterid><name>frameblending</name>"
        "<value>FALSE</value></parameter>"
        f"<parameter><parameterid>graphdict</parameterid><name>graphdict</name><graphdict>"
        f"<keyframe><when>0</when><value>0</value></keyframe>"
        f"<keyframe><when>{timeline_frames}</when><value>{float(timeline_frames * speed):g}</value>"
        "</keyframe></graphdict></parameter></effect></filter>"
    )


def to_xmeml(
    edl: dict[str, Any],
    name: str,
    captions: Sequence[ExportCaption] | None = None,
    include_audio_track: bool = False,
) -> str:
    """Final Cut Pro 7 XML (xmeml v4), which Premiere Pro often imports.

    Speed-changed clips keep exact timeline length and source in/out, and carry an FCP7
    Time Remap filter (effectid=timeremap, constant speed percent + linear graphdict).
    Optional caption markers and a mirrored stereo audio track are best-effort only;
    live Premiere import of those extras is unverified.
    """
    placed = layout(edl)
    caption_rows = _normalize_captions(captions)
    fps = int(edl["fpsNumerator"])
    rate = f"<rate><timebase>{fps}</timebase><ntsc>FALSE</ntsc></rate>"
    sources = list(dict.fromkeys(item["row"]["sourcePath"] for item in placed))
    declared: set[str] = set()
    items = []
    for index, item in enumerate(placed, 1):
        row = item["row"]
        if item["transition"]:
            start, frames = item["transition"]
            items.append(
                f"        <transitionitem>{rate}<start>{start}</start><end>{start + frames}</end>"
                "<alignment>center</alignment><effect><name>Cross Dissolve</name>"
                "<effectid>Cross Dissolve</effectid><effectcategory>Dissolve</effectcategory>"
                "<effecttype>transition</effecttype><mediatype>video</mediatype></effect></transitionitem>"
            )
        source = row["sourcePath"]
        file_id = f"file-{sources.index(source) + 1}"
        source_in = int(item["sourceStart"] * fps)
        span = int(item["frames"] * item["speed"])
        label = row.get("role") or Path(source).name
        if item["speed"] != 1:
            label += f"（{item['speed']}倍）"
        if file_id in declared:
            file_xml = f'<file id="{file_id}"/>'
        else:
            declared.add(file_id)
            duration = int(Fraction(row["sourceDurationUs"], 1_000_000) * fps)
            file_xml = (
                f'<file id="{file_id}"><name>{escape(Path(source).name)}</name>'
                f"<pathurl>{escape(_uri(source))}</pathurl>{rate}<duration>{duration}</duration>"
                "<media><video/><audio/></media></file>"
            )
        remap = _xmeml_timeremap(item["frames"], item["speed"])
        items.append(
            f'        <clipitem id="clip-{index}"><name>{escape(label)}</name>{rate}'
            f"<start>{item['offset']}</start><end>{item['offset'] + item['frames']}</end>"
            f"<in>{source_in}</in><out>{source_in + span}</out>"
            f"<duration>{item['frames']}</duration>{file_xml}{remap}</clipitem>"
        )
    total = sum(item["frames"] for item in placed)
    audio_items: list[str] = []
    if include_audio_track:
        declared_audio: set[str] = set()
        for index, item in enumerate(placed, 1):
            row = item["row"]
            source = row["sourcePath"]
            file_id = f"file-{sources.index(source) + 1}"
            source_in = int(item["sourceStart"] * fps)
            span = int(item["frames"] * item["speed"])
            if file_id in declared_audio:
                file_xml = f'<file id="{file_id}"/>'
            else:
                declared_audio.add(file_id)
                # File already fully declared on the video track; reference by id only.
                file_xml = f'<file id="{file_id}"/>'
            audio_items.append(
                f'        <clipitem id="audio-{index}"><name>{escape(Path(source).name)}</name>{rate}'
                f"<start>{item['offset']}</start><end>{item['offset'] + item['frames']}</end>"
                f"<in>{source_in}</in><out>{source_in + span}</out>"
                f"<duration>{item['frames']}</duration>{file_xml}"
                "<sourcetrack><mediatype>audio</mediatype><trackindex>1</trackindex></sourcetrack>"
                "</clipitem>"
            )
    markers = []
    for caption in caption_rows:
        markers.append(
            f"    <marker><name>{escape(caption.text)}</name>"
            f"<in>{caption.start_frame}</in><out>{caption.end_frame}</out>"
            f"<pproColor>4284590335</pproColor></marker>"
        )
    audio_xml = (
        "\n    <audio><numOutputChannels>2</numOutputChannels><track>\n"
        + "\n".join(audio_items)
        + "\n    </track></audio>"
        if include_audio_track
        else ""
    )
    marker_xml = ("\n" + "\n".join(markers)) if markers else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="4">\n'
        f"  <sequence><name>{escape(name)}</name><duration>{total}</duration>{rate}\n"
        "    <media><video><track>\n"
        + "\n".join(items)
        + "\n    </track></video>"
        + audio_xml
        + "</media>"
        + marker_xml
        + "\n  </sequence>\n</xmeml>\n"
    )


def _time(value: Fraction, rate: int) -> dict[str, Any]:
    return {"OTIO_SCHEMA": "RationalTime.1", "rate": float(rate), "value": float(value * rate)}


def _range(start: Fraction, duration: Fraction, rate: int) -> dict[str, Any]:
    return {
        "OTIO_SCHEMA": "TimeRange.1",
        "start_time": _time(start, rate),
        "duration": _time(duration, rate),
    }


def to_otio(
    edl: dict[str, Any],
    name: str,
    captions: Sequence[ExportCaption] | None = None,
    include_audio_track: bool = False,
) -> str:
    placed = layout(edl)
    caption_rows = _normalize_captions(captions)
    fps = int(edl["fpsNumerator"])
    children: list[dict[str, Any]] = []
    for item in placed:
        row = item["row"]
        if item["transition"]:
            _, frames = item["transition"]
            children.append(
                {
                    "OTIO_SCHEMA": "Transition.1",
                    "name": "Cross Dissolve",
                    "transition_type": "SMPTE_Dissolve",
                    "in_offset": _time(Fraction(frames // 2, fps), fps),
                    "out_offset": _time(Fraction(frames - frames // 2, fps), fps),
                    "metadata": {},
                }
            )
        clip: dict[str, Any] = {
            "OTIO_SCHEMA": "Clip.2",
            "name": row.get("role") or Path(row["sourcePath"]).name,
            "source_range": _range(item["sourceStart"], Fraction(item["frames"], fps), fps),
            "media_references": {
                "DEFAULT_MEDIA": {
                    "OTIO_SCHEMA": "ExternalReference.1",
                    "target_url": _uri(row["sourcePath"]),
                    "available_range": _range(
                        Fraction(0), Fraction(row["sourceDurationUs"], 1_000_000), fps
                    ),
                    "metadata": {},
                }
            },
            "active_media_reference_key": "DEFAULT_MEDIA",
            "effects": [],
            "markers": [],
            "metadata": {
                "gamingcreator": {
                    "sourceSha256": row.get("sourceSha256"),
                    "speed": str(item["speed"]),
                }
            },
        }
        if item["speed"] != 1:
            clip["effects"] = [
                {
                    "OTIO_SCHEMA": "LinearTimeWarp.1",
                    "name": "speed",
                    "effect_name": "LinearTimeWarp",
                    "time_scalar": float(item["speed"]),
                    "metadata": {},
                }
            ]
        children.append(clip)
    tracks: list[dict[str, Any]] = [
        {
            "OTIO_SCHEMA": "Track.1",
            "name": "V1",
            "kind": "Video",
            "children": children,
            "source_range": None,
            "effects": [],
            "markers": [],
            "metadata": {},
        }
    ]
    if include_audio_track:
        audio_children: list[dict[str, Any]] = []
        for item in placed:
            row = item["row"]
            audio_children.append(
                {
                    "OTIO_SCHEMA": "Clip.2",
                    "name": row.get("role") or Path(row["sourcePath"]).name,
                    "source_range": _range(item["sourceStart"], Fraction(item["frames"], fps), fps),
                    "media_references": {
                        "DEFAULT_MEDIA": {
                            "OTIO_SCHEMA": "ExternalReference.1",
                            "target_url": _uri(row["sourcePath"]),
                            "available_range": _range(
                                Fraction(0), Fraction(row["sourceDurationUs"], 1_000_000), fps
                            ),
                            "metadata": {},
                        }
                    },
                    "active_media_reference_key": "DEFAULT_MEDIA",
                    "effects": [],
                    "markers": [],
                    "metadata": {
                        "gamingcreator": {
                            "audio": "stereo-best-effort",
                            "importVerified": False,
                        }
                    },
                }
            )
        tracks.append(
            {
                "OTIO_SCHEMA": "Track.1",
                "name": "A1",
                "kind": "Audio",
                "children": audio_children,
                "source_range": None,
                "effects": [],
                "markers": [],
                "metadata": {"gamingcreator": {"channels": 2, "importVerified": False}},
            }
        )
    if caption_rows:
        caption_children = [
            {
                "OTIO_SCHEMA": "Clip.2",
                "name": caption.text,
                "source_range": _range(
                    Fraction(caption.start_frame, fps),
                    Fraction(caption.end_frame - caption.start_frame, fps),
                    fps,
                ),
                "media_references": {},
                "active_media_reference_key": None,
                "effects": [],
                "markers": [],
                "metadata": {"gamingcreator": {"caption": True, "importVerified": False}},
            }
            for caption in caption_rows
        ]
        tracks.append(
            {
                "OTIO_SCHEMA": "Track.1",
                "name": "Captions",
                "kind": "Video",
                "children": caption_children,
                "source_range": None,
                "effects": [],
                "markers": [],
                "metadata": {"gamingcreator": {"role": "captions", "importVerified": False}},
            }
        )
    timeline = {
        "OTIO_SCHEMA": "Timeline.1",
        "name": name,
        "global_start_time": _time(Fraction(0), fps),
        "metadata": {
            "gamingcreator": {
                "fps": fps,
                "importVerified": False,
                "captionTrack": "best-effort",
                "audioTrack": "stereo-best-effort" if include_audio_track else "none",
            }
        },
        "tracks": {
            "OTIO_SCHEMA": "Stack.1",
            "name": "tracks",
            "children": tracks,
            "source_range": None,
            "effects": [],
            "markers": [],
            "metadata": {},
        },
    }
    return json.dumps(timeline, ensure_ascii=False, indent=2) + "\n"
