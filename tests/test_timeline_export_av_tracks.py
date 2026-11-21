"""Caption timing and independent audio fixtures for timeline export."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ElementTree
from fractions import Fraction
from pathlib import Path

import pytest
from test_timeline_export import EDL

from gamingcreator.application.timeline_export import (
    ExportCaption,
    ExportLayer,
    ExportMusic,
    ExportNarration,
    ExportReferenceMix,
    captions_from_cues,
    to_fcpxml,
    to_otio,
    to_xmeml,
)
from gamingcreator.domain.creation_subtitles import SubtitleCue

CAPTIONS = (
    ExportCaption(0, 15, "开场"),
    ExportCaption(30, 60, "第二句"),
)


def test_captions_from_cues_quantizes_and_drops_collapsed() -> None:
    cues = (
        SubtitleCue(Fraction(0), Fraction(1, 2), "半秒"),
        SubtitleCue(Fraction(0), Fraction(1, 10000), "tiny"),
    )
    captions = captions_from_cues(cues, 30)
    assert captions == (ExportCaption(0, 15, "半秒"),)


def test_fcpxml_caption_nodes_and_stereo_channels() -> None:
    xml = to_fcpxml(EDL, "音字实验", captions=CAPTIONS, include_audio_track=True)
    root = ElementTree.fromstring(xml)
    captions = root.findall(".//asset-clip/caption")
    assert [c.findtext("text/text-style") for c in captions] == ["开场", "第二句"]
    assert all(c.get("lane") == "1" for c in captions)
    assert not root.findall(".//title")
    sources = root.findall(".//audio-channel-source")
    assert sources and all(s.get("srcCh") == "1,2" for s in sources)
    # Defaults without extras keep the legacy spine shape.
    plain = ElementTree.fromstring(to_fcpxml(EDL, "plain"))
    assert plain.find(".//caption") is None
    assert plain.find(".//audio-channel-source") is None


def test_otio_best_effort_audio_and_caption_tracks() -> None:
    timeline = json.loads(to_otio(EDL, "音字实验", captions=CAPTIONS, include_audio_track=True))
    tracks = timeline["tracks"]["children"]
    assert [t["name"] for t in tracks] == ["V1", "A1", "Captions"]
    assert tracks[1]["kind"] == "Audio"
    assert tracks[1]["metadata"]["gamingcreator"]["channels"] == 2
    assert tracks[1]["metadata"]["gamingcreator"]["importVerified"] is False
    assert [c["name"] for c in tracks[2]["children"]] == ["开场", "", "第二句"]
    assert timeline["metadata"]["gamingcreator"]["importVerified"] is False
    plain = json.loads(to_otio(EDL, "plain"))
    assert [t["name"] for t in plain["tracks"]["children"]] == ["V1"]


def test_caption_overlap_and_gaps_survive_cut_and_sequence_end() -> None:
    cues = (
        ExportCaption(131, 144, "末尾"),
        ExportCaption(56, 63, "跨切点 & 开场"),
        ExportCaption(58, 67, "并行"),
        ExportCaption(137, 160, "片外"),
    )
    timeline = json.loads(to_otio(EDL, "重叠字幕", captions=cues))
    tracks = timeline["tracks"]["children"][1:]
    assert [track["name"] for track in tracks] == ["Captions", "Captions 2"]
    found = {}
    for track in tracks:
        position = 0
        for child in track["children"]:
            time = child["source_range"]
            assert time["start_time"]["value"] == 0
            end = position + time["duration"]["value"]
            if child["OTIO_SCHEMA"] == "Clip.2":
                assert (
                    child["media_references"]["DEFAULT_MEDIA"]["OTIO_SCHEMA"]
                    == "MissingReference.1"
                )
                found[child["name"]] = (position, end)
            position = end
    assert found == {"跨切点 & 开场": (56, 63), "并行": (58, 67), "末尾": (131, 137)}
    root = ElementTree.fromstring(to_fcpxml(EDL, "重叠字幕", captions=cues))
    assert root.find(".//spine/clip/asset-clip/timeMap") is not None
    connected = {}
    for parent in root.find(".//spine"):
        for cue in parent.findall("caption"):
            offset = Fraction(parent.get("offset")[:-1]) + Fraction(cue.get("offset")[:-1])
            offset -= Fraction(parent.get("start")[:-1])
            end = offset + Fraction(cue.get("duration")[:-1])
            connected[cue.findtext("text/text-style")] = (offset * 30, end * 30)
    assert connected == found
    assert len({node.get("role") for node in root.iter("caption")}) == 2


def test_xmeml_best_effort_audio_track_and_caption_markers() -> None:
    root = ElementTree.fromstring(
        to_xmeml(EDL, "音字实验", captions=CAPTIONS, include_audio_track=True)
    )
    audio = root.find("./sequence/media/audio")
    assert audio is not None
    assert audio.findtext("numOutputChannels") == "2"
    clips = audio.findall("./track/clipitem")
    assert len(clips) == 3
    assert all(c.findtext("./sourcetrack/mediatype") == "audio" for c in clips)
    markers = root.findall("./sequence/marker")
    assert [(m.findtext("name"), m.findtext("in"), m.findtext("out")) for m in markers] == [
        ("开场", "0", "15"),
        ("第二句", "30", "60"),
    ]
    plain = ElementTree.fromstring(to_xmeml(EDL, "plain"))
    assert plain.find("./sequence/media/audio") is None
    assert plain.findall("./sequence/marker") == []


def test_layer_bundle_documents_keep_relative_assets_stacking_and_clock() -> None:
    layers = (
        ExportLayer("layer-01.mov", 48, 76, 1280, 720),
        ExportLayer("layer-02.mov", 58, 100, 1280, 720),
    )
    subtitle = (ExportCaption(59, 70, "字幕在图层上方"),)
    fcpxml = ElementTree.fromstring(
        to_fcpxml(EDL, "layers", 1280, 720, captions=subtitle, layers=layers)
    )
    assert [
        element.get("src")
        for element in fcpxml.findall("./resources/asset[@id='overlay-1']/media-rep")
    ] == ["layers/layer-01.mov"]
    stack = []
    for parent in fcpxml.find(".//sequence/spine"):
        for clip in parent.findall("asset-clip[@srcEnable='video']"):
            start = Fraction(clip.get("offset")[:-1]) - Fraction(parent.get("start")[:-1])
            start += Fraction(parent.get("offset")[:-1])
            stack.append((clip.get("lane"), start * 30, Fraction(clip.get("duration")[:-1]) * 30))
    assert stack == [("1", 48, 28), ("2", 58, 42)]
    assert fcpxml.find(".//caption").get("lane") == "3"
    assert fcpxml.find(".//spine/clip/asset-clip/timeMap") is not None

    premiere = ElementTree.fromstring(to_xmeml(EDL, "layers", layers=layers))
    canvas = premiere.find(".//sequence/media/video/format/samplecharacteristics")
    assert (canvas.findtext("width"), canvas.findtext("height")) == ("1280", "720")
    original, *extras = premiere.findall(".//sequence/media/video/track")
    assert len(original.findall("clipitem")) == 3
    for track, layer in zip(extras, layers, strict=True):
        clip = track.find("clipitem")
        assert (int(clip.findtext("start")), int(clip.findtext("end"))) == (layer.start, layer.end)
        assert clip.findtext("alphatype") == "straight"
        assert clip.findtext("file/pathurl") == layer.url

    timeline = json.loads(to_otio(EDL, "layers", captions=subtitle, layers=layers))
    assert [track["name"] for track in timeline["tracks"]["children"]] == [
        "V1",
        "layer-01.mov",
        "layer-02.mov",
        "Captions",
    ]
    for track, layer in zip(timeline["tracks"]["children"][1:3], layers, strict=True):
        gap, clip = track["children"]
        assert gap["source_range"]["duration"]["value"] == layer.start
        assert clip["source_range"]["duration"]["value"] == layer.frames
        assert clip["media_references"]["DEFAULT_MEDIA"]["target_url"] == layer.url


def test_reference_mix_replaces_dry_audio_without_changing_video_duration() -> None:
    voice = ExportNarration("voice.wav", 5, 48_000, 1, 2, 48_000)
    music = ExportMusic("music.wav", "Tune", Fraction(2), 48_000, 2)
    mix = ExportReferenceMix(137 * 1600)
    options = dict(include_audio_track=True, narration=voice, music=music, reference_mix=mix)
    fcp = ElementTree.fromstring(to_fcpxml(EDL, "mix", **options))
    media = fcp.find("./resources/asset[@id='dry-mix']/media-rep")
    assert media.get("src") == "mix-reference.wav"
    assert not fcp.findall(".//audio-channel-source")
    for clip in fcp.findall(".//asset-clip"):
        assert clip.get("srcEnable") == ("audio" if clip.get("ref") == "dry-mix" else "video")
    assert fcp.find(".//spine//asset-clip[@ref='dry-mix']").get("duration") == "137/30s"
    premiere = ElementTree.fromstring(to_xmeml(EDL, "mix", **options))
    (audio,) = premiere.findall("./sequence/media/audio/track/clipitem")
    assert audio.findtext("start") == "0" and audio.findtext("end") == "137"
    assert audio.findtext("file/pathurl") == "mix-reference.wav"
    assert premiere.findtext("./sequence/duration") == "137"
    otio = json.loads(to_otio(EDL, "mix", **options))
    (track,) = [track for track in otio["tracks"]["children"] if track["kind"] == "Audio"]
    (clip,) = track["children"]
    assert clip["source_range"]["duration"]["value"] == 219_200
    assert clip["source_range"]["duration"]["rate"] == 48_000
    assert clip["media_references"]["DEFAULT_MEDIA"]["target_url"] == "mix-reference.wav"


def test_xmeml_music_loops_on_independent_track_to_rendered_end(tmp_path: Path) -> None:
    path = tmp_path / "配乐 & one.wav"
    music = ExportMusic(str(path), "配乐 <开场> & 收尾\uffff", Fraction(451, 300), 44_100, 2, 24)
    narration = ExportNarration("voice.wav", 3, 48_000, 1, 2, 48_000)
    root = ElementTree.fromstring(
        to_xmeml(EDL, "独立配乐", include_audio_track=True, narration=narration, music=music)
    )
    original, voice, bgm = root.findall("./sequence/media/audio/track")
    assert len(original.findall("clipitem")) == 3
    assert voice.findtext("./clipitem/name") == "Narration (dry)"
    clips = bgm.findall("clipitem")
    assert [
        tuple(clip.findtext(field) for field in ("start", "end", "in", "out")) for clip in clips
    ] == [
        ("0", "45", "0", "45"),
        ("45", "90", "0", "45"),
        ("90", "135", "0", "45"),
        ("135", "137", "0", "2"),
    ]
    assert all(clip.findtext("name") == "配乐 <开场> & 收尾\ufffd" for clip in clips)
    ids = [clip.get("id") for clip in root.findall(".//clipitem")]
    assert len(ids) == len(set(ids))
    source, *references = bgm.findall("./clipitem/file")
    assert source.findtext("pathurl") == path.resolve().as_uri()
    assert source.findtext("duration") == "45"
    assert source.findtext("./media/audio/channelcount") == "2"
    assert source.findtext("./media/audio/samplecharacteristics/samplerate") == "44100"
    assert source.findtext("./media/audio/samplecharacteristics/depth") == "24"
    assert all(ref.get("id") == source.get("id") and not len(ref) for ref in references)


def test_xmeml_music_without_original_or_known_sample_depth() -> None:
    music = ExportMusic("music.mp3", "Music", Fraction(10), 48_000, 1)
    root = ElementTree.fromstring(to_xmeml(EDL, "只配乐", music=music))
    (track,) = root.findall("./sequence/media/audio/track")
    (clip,) = track.findall("clipitem")
    assert clip.findtext("out") == "137"
    assert clip.findtext("./file/duration") == "300"
    assert clip.find("./file/media/audio/samplecharacteristics/depth") is None


def test_xmeml_rejects_music_outside_loop_bounds() -> None:
    with pytest.raises(ValueError, match="配乐短于一帧"):
        to_xmeml(EDL, "短配乐", music=ExportMusic("tiny.wav", "Music", Fraction(1, 31), 48_000, 1))

    row = {
        **EDL["segments"][0],
        "outputFrames": 10_001,
        "endUs": 333_400_000,
        "sourceDurationUs": 333_400_000,
    }
    with pytest.raises(ValueError, match="配乐循环超过 10000 段"):
        to_xmeml(
            {**EDL, "segments": [row]},
            "循环太多",
            music=ExportMusic("tiny.wav", "Music", Fraction(1, 30), 48_000, 1),
        )


def test_fcpxml_connects_dry_audio_on_sequence_clock_across_retiming(tmp_path: Path) -> None:
    voice_path = tmp_path / "旁白.wav"
    music_path = tmp_path / "配乐 & 歌.wav"
    narration = ExportNarration(str(voice_path), 75, 22_050, 1, 2, 22_051)
    music = ExportMusic(str(music_path), "首曲 & \uffff", Fraction(57, 30), 48_000, 2)
    root = ElementTree.fromstring(
        to_fcpxml(EDL, "干声交接", include_audio_track=True, narration=narration, music=music)
    )
    resources = {item.get("id"): item for item in root.findall("./resources/asset")}
    for role, path in (("dialogue", voice_path), ("music", music_path)):
        resource = resources[f"dry-{role}"]
        assert resource.get("hasAudio") == "1" and resource.get("hasVideo") is None
        assert resource.find("media-rep").get("src") == path.as_uri()
    assert resources["dry-music"].get("name") == "首曲 & \ufffd"
    primary = root.find(".//sequence/spine")
    assert [clip.tag for clip in primary] == [
        "asset-clip",
        "transition",
        "clip",
        "transition",
        "asset-clip",
    ]
    retimed = primary.find("./clip/asset-clip")
    points = retimed.findall("./timeMap/timept")
    assert points[0].get("time") == points[0].get("value") == retimed.get("start")
    assert Fraction(points[-1].get("time")[:-1]) - Fraction(points[0].get("time")[:-1]) == Fraction(
        53, 30
    )
    assert not primary.findall("./asset-clip[@lane]")
    audio = []
    for parent in primary:
        for child in parent.findall("asset-clip[@lane]"):
            offset = Fraction(parent.get("offset")[:-1]) + Fraction(child.get("offset")[:-1])
            offset -= Fraction(parent.get("start")[:-1])
            assert child.get("start") == "0s" and child.get("srcEnable") == "audio"
            audio.append(
                (
                    child.get("audioRole"),
                    child.get("lane"),
                    offset * 30,
                    Fraction(child.get("duration")[:-1]),
                )
            )
    assert sorted(audio) == [
        ("dialogue", "-1", 75, Fraction(22_051, 22_050)),
        ("music", "-2", 0, Fraction(57, 30)),
        ("music", "-2", 57, Fraction(57, 30)),
        ("music", "-2", 114, Fraction(23, 30)),
    ]

    fractional_source = {**EDL["segments"][0], "startUs": 12_345}
    unaligned = ElementTree.fromstring(
        to_fcpxml({**EDL, "segments": [fractional_source]}, "subframe", music=music)
    )
    wrapper = unaligned.find(".//spine/clip")
    assert wrapper.get("start") == "0s"
    assert wrapper.find("asset-clip[@ref='a1']").get("start") == "2469/200000s"
    assert wrapper.find("asset-clip[@lane='-2']").get("offset") == "0s"


def test_otio_dry_tracks_preserve_narration_samples_and_music_frames(tmp_path: Path) -> None:
    voice = tmp_path / "旁白.wav"
    music = tmp_path / "配乐.wav"
    project = json.loads(
        to_otio(
            EDL,
            "干声交接",
            include_audio_track=True,
            narration=ExportNarration(str(voice), 75, 22_050, 1, 2, 22_051),
            music=ExportMusic(str(music), "Music", Fraction(451, 300), 48_000, 2),
        )
    )
    video, original, dialogue, bgm = project["tracks"]["children"]
    assert [track["name"] for track in (video, original, dialogue, bgm)] == [
        "V1",
        "A1",
        "Narration (dry)",
        "Music (dry)",
    ]
    gap, voice_clip = dialogue["children"]
    assert gap["OTIO_SCHEMA"] == "Gap.1" and gap["source_range"]["duration"]["value"] == 75
    assert voice_clip["source_range"]["duration"] == {
        "OTIO_SCHEMA": "RationalTime.1",
        "value": 22_051,
        "rate": 22_050,
    }
    assert voice_clip["media_references"]["DEFAULT_MEDIA"]["target_url"] == voice.as_uri()
    assert [clip["source_range"]["duration"]["value"] for clip in bgm["children"]] == [
        45,
        45,
        45,
        2,
    ]
    assert {
        clip["media_references"]["DEFAULT_MEDIA"]["target_url"] for clip in bgm["children"]
    } == {music.as_uri()}
