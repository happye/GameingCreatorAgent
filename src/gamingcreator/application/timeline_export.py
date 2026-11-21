"""Export an edit decision to professional timeline formats (FCPXML 1.9, OpenTimelineIO JSON, xmeml).

Times are exact, frame-aligned rationals on the output clock; source in/out points come from the
saved source microseconds. Our renders overlap two clips by N frames for a crossfade; both
formats instead place clips end to end with a transition centred on the cut that borrows
handle media. Each clip is therefore trimmed by whole frames at the cut (N//2 on the left,
the rest on the right), so the exported timeline has exactly the rendered length.

Captions use the sequence clock in each export. Audio and caption style compatibility still
needs verification in Final Cut, DaVinci Resolve and Premiere.
"""

from __future__ import annotations

import json
import re
from bisect import bisect_right
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


def _normalize_captions(
    captions: Sequence[ExportCaption] | None, total_frames: int
) -> tuple[ExportCaption, ...]:
    return tuple(
        ExportCaption(item.start_frame, min(item.end_frame, total_frames), item.text)
        for item in sorted(captions or (), key=lambda item: (item.start_frame, item.end_frame))
        if item.start_frame < total_frames
    )


def _caption_lanes(captions: Sequence[ExportCaption]) -> list[list[ExportCaption]]:
    """Place overlapping speech on separate lanes while keeping each cue's interval."""
    lanes: list[list[ExportCaption]] = []
    for caption in captions:
        for lane in lanes:
            if lane[-1].end_frame <= caption.start_frame:
                lane.append(caption)
                break
        else:
            lanes.append([caption])
    return lanes


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


def _xml_text(value: str) -> str:
    return re.sub(r"[^\x09\x0a\x0d\x20-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]", "\ufffd", value)


def _fcpxml_needs_anchor_clip(item: dict[str, Any], frame: Fraction) -> bool:
    start: Fraction = item["sourceStart"]
    return bool(item["speed"] != 1) or (start / frame).denominator != 1


def _fcpxml_anchor(
    placed: Sequence[dict[str, Any]], positions: list[int], start: int, frame: Fraction
) -> tuple[int, Fraction]:
    parent = placed[bisect_right(positions, start) - 1]
    # A zero-origin wrapper isolates anchors from retiming or an off-frame source origin.
    origin: Fraction = (
        Fraction(0) if _fcpxml_needs_anchor_clip(parent, frame) else parent["sourceStart"]
    )
    position: int = parent["offset"]
    return position, origin + (start - position) * frame


def _fcpxml_caption_anchors(
    anchors: dict[int, list[str]],
    placed: Sequence[dict[str, Any]],
    frame: Fraction,
    captions: Sequence[ExportCaption],
    first_lane: int = 1,
) -> None:
    positions = [item["offset"] for item in placed]
    for index, cues in enumerate(_caption_lanes(captions), 1):
        lane = first_lane + index - 1
        role = "Subtitles" if index == 1 else f"Subtitles {index}"
        for cue_index, caption in enumerate(cues, 1):
            position, offset = _fcpxml_anchor(placed, positions, caption.start_frame, frame)
            duration = (caption.end_frame - caption.start_frame) * frame
            style_id = f"caption-style-{lane}-{cue_index}"
            anchors.setdefault(position, []).append(
                f'              <caption lane="{lane}" offset="{_seconds(offset)}" start="0s" '
                f'duration="{_seconds(duration)}" role="{role}?captionFormat=ITT.und">\n'
                f'                <text placement="bottom"><text-style ref="{style_id}">'
                f"{escape(_xml_text(caption.text))}</text-style></text>\n"
                f'                <text-style-def id="{style_id}"><text-style/></text-style-def>\n'
                "              </caption>"
            )


@dataclass(frozen=True, slots=True)
class ExportLayer:
    """One full-canvas transparent video in the bundle, cut on the sequence clock."""

    filename: str
    start: int
    end: int
    width: int
    height: int

    @property
    def url(self) -> str:
        return f"layers/{self.filename}"

    @property
    def frames(self) -> int:
        return self.end - self.start


def _fcpxml_layers(
    layers: Sequence[ExportLayer],
    placed: Sequence[dict[str, Any]],
    frame: Fraction,
    assets: list[str],
    anchors: dict[int, list[str]],
) -> None:
    positions = [item["offset"] for item in placed]
    for lane, layer in enumerate(layers, 1):
        asset_id = f"overlay-{lane}"
        name = quoteattr(layer.filename)
        duration = _seconds(layer.frames * frame)
        assets.append(
            f'    <asset id="{asset_id}" name={name} start="0s" duration="{duration}" '
            'hasVideo="1" format="r1">'
            f'<media-rep kind="original-media" src={quoteattr(layer.url)}/></asset>'
        )
        parent, offset = _fcpxml_anchor(placed, positions, layer.start, frame)
        anchors.setdefault(parent, []).append(
            f'              <asset-clip ref="{asset_id}" name={name} lane="{lane}" '
            f'offset="{_seconds(offset)}" start="0s" duration="{duration}" srcEnable="video"/>'
        )


def _fcpxml_dry_audio(
    tracks: Sequence[_DryTrack], placed: Sequence[dict[str, Any]], fps: int
) -> tuple[list[str], dict[int, list[str]]]:
    frame = Fraction(1, fps)
    positions = [item["offset"] for item in placed]
    assets = []
    anchors: dict[int, list[str]] = {}
    for track in tracks:
        lane = -1 if track.role == "dialogue" else -2
        media = f"dry-{track.role}"
        title = quoteattr(_xml_text(track.title))
        assets.append(
            f'    <asset id="{media}" name={title} start="0s" '
            f'duration="{_seconds(track.source_duration)}" hasAudio="1" audioSources="1" '
            f'audioChannels="{track.channels}" audioRate="{track.sample_rate}">\n'
            f'      <media-rep kind="original-media" src={quoteattr(_uri(track.path))}/>\n    </asset>'
        )
        for start, length in track.cuts:
            position, offset = _fcpxml_anchor(placed, positions, start, frame)
            anchors.setdefault(position, []).append(
                f'              <asset-clip ref="{media}" name={title} lane="{lane}" '
                f'offset="{_seconds(offset)}" start="0s" duration="{_seconds(length)}" '
                f'srcEnable="audio" audioRole="{track.role}"/>'
            )
    return assets, anchors


def _fcpxml_video_clip(
    item: dict[str, Any], asset: str, frame: Fraction, audio: bool, anchors: list[str]
) -> str:
    row = item["row"]
    duration = item["frames"] * frame
    start = item["sourceStart"]
    offset = item["offset"] * frame
    retimed = item["speed"] != 1
    wrapped = bool(anchors) and _fcpxml_needs_anchor_clip(item, frame)
    name = quoteattr(row.get("role") or Path(row["sourcePath"]).name)
    clip = (
        f'            <asset-clip ref="{asset}" offset="{_seconds(Fraction(0) if wrapped else offset)}" '
        f'start="{_seconds(start)}" duration="{_seconds(duration)}" name={name}'
    )
    inner: list[str] = []
    if retimed:
        end = start + duration * item["speed"]
        inner.append(
            "              <timeMap>\n"
            f'                <timept time="{_seconds(start)}" value="{_seconds(start)}" interp="linear"/>\n'
            f'                <timept time="{_seconds(start + duration)}" value="{_seconds(end)}" interp="linear"/>\n'
            "              </timeMap>"
        )
    if not wrapped:
        inner.extend(anchors)
    if audio:
        inner.append('              <audio-channel-source srcCh="1,2" role="dialogue.dialogue"/>')
    if inner:
        clip += ">\n" + "\n".join(inner) + "\n            </asset-clip>"
    else:
        clip += "/>"
    if wrapped:
        clip = (
            f'            <clip name={name} offset="{_seconds(offset)}" start="0s" '
            f'duration="{_seconds(duration)}">\n'
            + clip
            + "\n"
            + "\n".join(anchors)
            + "\n            </clip>"
        )
    return clip


def to_fcpxml(
    edl: dict[str, Any],
    name: str,
    width: int = 1920,
    height: int = 1080,
    captions: Sequence[ExportCaption] | None = None,
    include_audio_track: bool = False,
    narration: ExportNarration | None = None,
    music: ExportMusic | None = None,
    layers: Sequence[ExportLayer] = (),
) -> str:
    placed = layout(edl)
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
    total_frames = sum(item["frames"] for item in placed)
    dry_assets, anchors = _fcpxml_dry_audio(
        _dry_tracks(narration, music, fps, total_frames), placed, fps
    )
    assets.extend(dry_assets)
    _fcpxml_layers(layers, placed, frame, assets, anchors)
    _fcpxml_caption_anchors(
        anchors, placed, frame, _normalize_captions(captions, total_frames), len(layers) + 1
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
        asset = f"a{sources.index(row['sourcePath']) + 1}"
        spine.append(
            _fcpxml_video_clip(
                item, asset, frame, include_audio_track, anchors.get(item["offset"], [])
            )
        )
    total = total_frames * frame
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


@dataclass(frozen=True, slots=True)
class ExportNarration:
    """Verified WAV facts and output placement; carries no mix claims or I/O."""

    wav_path: str
    start_frame: int
    sample_rate: int
    channels: int
    sample_width: int
    sample_count: int


@dataclass(frozen=True, slots=True)
class ExportMusic:
    """Verified source audio facts for a dry background music track."""

    audio_path: str
    title: str
    duration: Fraction
    sample_rate: int
    channels: int
    sample_depth_bits: int | None = None


class MusicTimelineError(ValueError):
    """A registered track cannot be represented on the export clock."""


def _validate_narration(narration: ExportNarration, fps: int, total: int) -> None:
    from gamingcreator.domain.creation_narration import NarrationSelection, validate_narration_fit

    validate_narration_fit(
        NarrationSelection("0" * 32, "0" * 64, narration.start_frame, 0, "off"),
        narration.sample_count,
        narration.sample_rate,
        total,
        fps,
    )
    if type(narration.channels) is not int or narration.channels <= 0:
        raise ValueError("Narration channels must be positive.")
    if type(narration.sample_width) is not int or narration.sample_width not in (1, 2, 3, 4):
        raise ValueError("Unsupported narration sample width.")


def _xmeml_narration(narration: ExportNarration, fps: int, total: int, rate: str) -> str:
    _validate_narration(narration, fps, total)
    frames = -(-narration.sample_count * fps // narration.sample_rate)
    return (
        '<track><clipitem id="narration-clip"><name>Narration (dry)</name>'
        f"{rate}<start>{narration.start_frame}</start>"
        f"<end>{narration.start_frame + frames}</end><in>0</in><out>{frames}</out>"
        f'<duration>{frames}</duration><file id="narration-file">'
        f"<name>{escape(Path(narration.wav_path).name)}</name>"
        f"<pathurl>{escape(_uri(narration.wav_path))}</pathurl>{rate}"
        f"<duration>{frames}</duration><media><audio><samplecharacteristics>"
        f"<depth>{narration.sample_width * 8}</depth><samplerate>{narration.sample_rate}</samplerate>"
        f"</samplecharacteristics><channelcount>{narration.channels}</channelcount>"
        "</audio></media></file><sourcetrack><mediatype>audio</mediatype>"
        "<trackindex>1</trackindex></sourcetrack></clipitem></track>"
    )


def _music_source_frames(music: ExportMusic, fps: int, total: int) -> int:
    source_frames = (music.duration * fps).__floor__()
    if source_frames < 1:
        raise MusicTimelineError("配乐短于一帧。")
    if -(-total // source_frames) > 10_000:
        raise MusicTimelineError("配乐循环超过 10000 段。")
    if any(type(value) is not int or value <= 0 for value in (music.sample_rate, music.channels)):
        raise ValueError("Music sample rate and channels must be positive integers.")
    depth = music.sample_depth_bits
    if depth is not None and (type(depth) is not int or depth <= 0):
        raise ValueError("Music sample depth must be a positive integer when known.")
    return source_frames


def _xmeml_music(music: ExportMusic, fps: int, total: int, rate: str) -> str:
    source_frames = _music_source_frames(music, fps, total)
    depth = music.sample_depth_bits
    depth_xml = f"<depth>{depth}</depth>" if depth is not None else ""
    title = escape(_xml_text(music.title))
    full_file = (
        f'<file id="music-file"><name>{title}</name>'
        f"<pathurl>{escape(_uri(music.audio_path))}</pathurl>{rate}"
        f"<duration>{source_frames}</duration><media><audio><samplecharacteristics>"
        f"{depth_xml}<samplerate>{music.sample_rate}</samplerate></samplecharacteristics>"
        f"<channelcount>{music.channels}</channelcount></audio></media></file>"
    )
    clips = []
    for index, start in enumerate(range(0, total, source_frames), 1):
        end = min(start + source_frames, total)
        span = end - start
        file_xml = full_file if index == 1 else '<file id="music-file"/>'
        clips.append(
            f'<clipitem id="music-{index}"><name>{title}</name>{rate}'
            f"<start>{start}</start><end>{end}</end><in>0</in><out>{span}</out>"
            f"<duration>{span}</duration>{file_xml}<sourcetrack><mediatype>audio</mediatype>"
            "<trackindex>1</trackindex></sourcetrack></clipitem>"
        )
    return "<track>" + "".join(clips) + "</track>"


def to_xmeml(
    edl: dict[str, Any],
    name: str,
    captions: Sequence[ExportCaption] | None = None,
    include_audio_track: bool = False,
    narration: ExportNarration | None = None,
    music: ExportMusic | None = None,
    layers: Sequence[ExportLayer] = (),
) -> str:
    """Final Cut Pro 7 XML (xmeml v4), which Premiere Pro often imports.

    Speed-changed clips keep exact timeline length and source in/out, and carry an FCP7
    Time Remap filter (effectid=timeremap, constant speed percent + linear graphdict).
    Background music loops as whole-frame source clips on a separate dry audio track.
    Optional caption markers and a mirrored stereo audio track are best-effort only;
    live Premiere import of those extras is unverified.
    """
    placed = layout(edl)
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
    for caption in _normalize_captions(captions, total):
        markers.append(
            f"    <marker><name>{escape(_xml_text(caption.text))}</name>"
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
    extra_tracks = []
    if narration is not None:
        extra_tracks.append(_xmeml_narration(narration, fps, total, rate))
    if music is not None:
        extra_tracks.append(_xmeml_music(music, fps, total, rate))
    if extra_tracks:
        tracks_xml = "".join(extra_tracks)
        audio_xml = (
            audio_xml.removesuffix("</audio>") + tracks_xml + "</audio>"
            if audio_xml
            else "\n    <audio>" + tracks_xml + "</audio>"
        )
    marker_xml = ("\n" + "\n".join(markers)) if markers else ""
    video_layers = "".join(
        _xmeml_layer(layer, index, rate) for index, layer in enumerate(layers, 1)
    )
    canvas = ""
    if layers:
        first = layers[0]
        canvas = (
            f"<format><samplecharacteristics>{rate}<width>{first.width}</width>"
            f"<height>{first.height}</height><pixelaspectratio>square</pixelaspectratio>"
            "</samplecharacteristics></format>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="4">\n'
        f"  <sequence><name>{escape(name)}</name><duration>{total}</duration>{rate}\n"
        f"    <media><video>{canvas}<track>\n"
        + "\n".join(items)
        + "\n    </track>"
        + video_layers
        + "</video>"
        + audio_xml
        + "</media>"
        + marker_xml
        + "\n  </sequence>\n</xmeml>\n"
    )


def _xmeml_layer(layer: ExportLayer, index: int, rate: str) -> str:
    title = escape(layer.filename)
    return (
        f'<track><clipitem id="overlay-{index}"><name>{title}</name>{rate}'
        f"<start>{layer.start}</start><end>{layer.end}</end><in>0</in><out>{layer.frames}</out>"
        f"<duration>{layer.frames}</duration><alphatype>straight</alphatype>"
        f'<file id="overlay-file-{index}"><name>{title}</name><pathurl>{escape(layer.url)}</pathurl>{rate}'
        f"<duration>{layer.frames}</duration><media><video><samplecharacteristics>{rate}"
        f"<width>{layer.width}</width><height>{layer.height}</height></samplecharacteristics>"
        "<alphatype>straight</alphatype></video></media></file></clipitem></track>"
    )


def _time(value: Fraction, rate: int) -> dict[str, Any]:
    return {"OTIO_SCHEMA": "RationalTime.1", "rate": float(rate), "value": float(value * rate)}


def _range(start: Fraction, duration: Fraction, rate: int) -> dict[str, Any]:
    return {
        "OTIO_SCHEMA": "TimeRange.1",
        "start_time": _time(start, rate),
        "duration": _time(duration, rate),
    }


@dataclass(frozen=True, slots=True)
class _DryTrack:
    role: str
    title: str
    path: str
    source_duration: Fraction
    sample_rate: int
    channels: int
    # Each cut starts at media time zero. Offsets belong to the sequence clock.
    cuts: tuple[tuple[int, Fraction], ...]


def _dry_tracks(
    narration: ExportNarration | None, music: ExportMusic | None, fps: int, total: int
) -> list[_DryTrack]:
    tracks = []
    if narration is not None:
        _validate_narration(narration, fps, total)
        length = Fraction(narration.sample_count, narration.sample_rate)
        tracks.append(
            _DryTrack(
                "dialogue",
                "Narration (dry)",
                narration.wav_path,
                length,
                narration.sample_rate,
                narration.channels,
                ((narration.start_frame, length),),
            )
        )
    if music is not None:
        loop = _music_source_frames(music, fps, total)
        tracks.append(
            _DryTrack(
                "music",
                music.title,
                music.audio_path,
                music.duration,
                music.sample_rate,
                music.channels,
                tuple(
                    (start, Fraction(min(loop, total - start), fps))
                    for start in range(0, total, loop)
                ),
            )
        )
    return tracks


def _otio_gap(duration: Fraction, fps: int) -> dict[str, Any]:
    return {
        "OTIO_SCHEMA": "Gap.1",
        "name": "",
        "effects": [],
        "markers": [],
        "source_range": _range(Fraction(0), duration, fps),
        "metadata": {},
    }


def _otio_dry_track(track: _DryTrack, fps: int) -> dict[str, Any]:
    children = []
    position = Fraction(0)
    for start, length in track.cuts:
        offset = Fraction(start, fps)
        if offset > position:
            children.append(_otio_gap(offset - position, fps))
        children.append(
            {
                "OTIO_SCHEMA": "Clip.2",
                "name": track.title,
                "source_range": _range(
                    Fraction(0), length, fps if track.role == "music" else track.sample_rate
                ),
                "media_references": {
                    "DEFAULT_MEDIA": {
                        "OTIO_SCHEMA": "ExternalReference.1",
                        "target_url": _uri(track.path),
                        "available_range": _range(
                            Fraction(0), track.source_duration, track.sample_rate
                        ),
                        "metadata": {},
                    }
                },
                "active_media_reference_key": "DEFAULT_MEDIA",
                "effects": [],
                "markers": [],
                "metadata": {},
            }
        )
        position = offset + length
    return {
        "OTIO_SCHEMA": "Track.1",
        "name": "Music (dry)" if track.role == "music" else track.title,
        "kind": "Audio",
        "children": children,
        "source_range": None,
        "effects": [],
        "markers": [],
        "metadata": {
            "gamingcreator": {
                "role": track.role,
                "channels": track.channels,
                "sampleRate": track.sample_rate,
                "importVerified": False,
            }
        },
    }


def _otio_caption_track(captions: Sequence[ExportCaption], lane: int, fps: int) -> dict[str, Any]:
    children = []
    end = 0
    for caption in captions:
        if caption.start_frame > end:
            children.append(_otio_gap(Fraction(caption.start_frame - end, fps), fps))
        children.append(
            {
                "OTIO_SCHEMA": "Clip.2",
                "name": caption.text,
                "source_range": _range(
                    Fraction(0), Fraction(caption.end_frame - caption.start_frame, fps), fps
                ),
                "media_references": {
                    "DEFAULT_MEDIA": {
                        "OTIO_SCHEMA": "MissingReference.1",
                        "name": "",
                        "available_range": None,
                        "metadata": {},
                    }
                },
                "active_media_reference_key": "DEFAULT_MEDIA",
                "effects": [],
                "markers": [],
                "metadata": {"gamingcreator": {"caption": True, "importVerified": False}},
            }
        )
        end = caption.end_frame
    return {
        "OTIO_SCHEMA": "Track.1",
        "name": "Captions" if lane == 1 else f"Captions {lane}",
        "kind": "Video",
        "children": children,
        "source_range": None,
        "effects": [],
        "markers": [],
        "metadata": {"gamingcreator": {"role": "captions", "importVerified": False}},
    }


def _otio_layer(layer: ExportLayer, fps: int) -> dict[str, Any]:
    duration = _range(Fraction(0), Fraction(layer.frames, fps), fps)
    children = [_otio_gap(Fraction(layer.start, fps), fps)] if layer.start else []
    children.append(
        {
            "OTIO_SCHEMA": "Clip.2",
            "name": layer.filename,
            "source_range": duration,
            "media_references": {
                "DEFAULT_MEDIA": {
                    "OTIO_SCHEMA": "ExternalReference.1",
                    "target_url": layer.url,
                    "available_range": duration,
                    "metadata": {},
                }
            },
            "active_media_reference_key": "DEFAULT_MEDIA",
            "effects": [],
            "markers": [],
            "metadata": {},
        }
    )
    return {
        "OTIO_SCHEMA": "Track.1",
        "name": layer.filename,
        "kind": "Video",
        "children": children,
        "source_range": None,
        "effects": [],
        "markers": [],
        "metadata": {"gamingcreator": {"role": "overlay"}},
    }


def to_otio(
    edl: dict[str, Any],
    name: str,
    captions: Sequence[ExportCaption] | None = None,
    include_audio_track: bool = False,
    narration: ExportNarration | None = None,
    music: ExportMusic | None = None,
    layers: Sequence[ExportLayer] = (),
) -> str:
    placed = layout(edl)
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
    total = sum(item["frames"] for item in placed)
    tracks.extend(
        _otio_dry_track(track, fps) for track in _dry_tracks(narration, music, fps, total)
    )
    tracks.extend(_otio_layer(layer, fps) for layer in layers)
    caption_lanes = _caption_lanes(_normalize_captions(captions, total))
    tracks.extend(
        _otio_caption_track(cues, lane, fps) for lane, cues in enumerate(caption_lanes, 1)
    )
    timeline = {
        "OTIO_SCHEMA": "Timeline.1",
        "name": name,
        "global_start_time": _time(Fraction(0), fps),
        "metadata": {
            "gamingcreator": {
                "fps": fps,
                "importVerified": False,
                "captionTrack": "timed-text" if caption_lanes else "none",
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
