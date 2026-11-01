"""Best-effort caption + stereo audio track fixtures for timeline export (NLE import unclaimed)."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ElementTree
from fractions import Fraction

from test_timeline_export import EDL

from gamingcreator.application.timeline_export import (
    ExportCaption,
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


def test_fcpxml_best_effort_titles_and_stereo_channels() -> None:
    xml = to_fcpxml(EDL, "音字实验", captions=CAPTIONS, include_audio_track=True)
    root = ElementTree.fromstring(xml)
    titles = root.findall(".//spine/title")
    assert [t.findtext("text") for t in titles] == ["开场", "第二句"]
    assert all(t.get("lane") == "1" for t in titles)
    sources = root.findall(".//audio-channel-source")
    assert sources and all(s.get("srcCh") == "1,2" for s in sources)
    # Defaults without extras keep the legacy spine shape.
    plain = ElementTree.fromstring(to_fcpxml(EDL, "plain"))
    assert plain.find(".//title") is None
    assert plain.find(".//audio-channel-source") is None


def test_otio_best_effort_audio_and_caption_tracks() -> None:
    timeline = json.loads(to_otio(EDL, "音字实验", captions=CAPTIONS, include_audio_track=True))
    tracks = timeline["tracks"]["children"]
    assert [t["name"] for t in tracks] == ["V1", "A1", "Captions"]
    assert tracks[1]["kind"] == "Audio"
    assert tracks[1]["metadata"]["gamingcreator"]["channels"] == 2
    assert tracks[1]["metadata"]["gamingcreator"]["importVerified"] is False
    assert [c["name"] for c in tracks[2]["children"]] == ["开场", "第二句"]
    assert timeline["metadata"]["gamingcreator"]["importVerified"] is False
    plain = json.loads(to_otio(EDL, "plain"))
    assert [t["name"] for t in plain["tracks"]["children"]] == ["V1"]


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
