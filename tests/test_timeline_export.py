"""Timeline export: frame-exact layout, crossfades as centred transitions, valid documents."""

# ruff: noqa: F811
import json
import threading
import urllib.error
import urllib.request
import xml.etree.ElementTree as ElementTree
from fractions import Fraction

import pytest
from test_creation_jobs import finish, service  # noqa: F401
from test_creation_revision_jobs import payload, revisions  # noqa: F401

from gamingcreator.application.timeline_export import layout, to_fcpxml, to_otio


def segment(start_us, frames, speed=(1, 1), transition=("cut", 0), source="C:/footage/a.mp4"):
    return {
        "sourcePath": source,
        "sourceSha256": "a" * 64,
        "sourceDurationUs": 60_000_000,
        "startUs": start_us,
        "endUs": start_us + frames * 1_000_000 // 30 * speed[0] // speed[1],
        "outputFrames": frames,
        "speed": {"numerator": speed[0], "denominator": speed[1]},
        "transitionIn": {"type": transition[0], "frames": transition[1]},
    }


EDL = {
    "fpsNumerator": 30,
    "segments": [
        segment(0, 60),
        segment(10_000_000, 60, speed=(2, 1), transition=("crossfade", 7)),
        segment(30_000_000, 30, source="C:/footage/b.mp4", transition=("crossfade", 6)),
    ],
}


def test_layout_trims_whole_frames_and_keeps_rendered_length():
    placed = layout(EDL)
    # Rendered length is 60+60+30-7-6 = 137 frames.
    assert sum(item["frames"] for item in placed) == 137
    assert [item["frames"] for item in placed] == [57, 53, 27]
    assert [item["offset"] for item in placed] == [0, 57, 110]
    assert placed[1]["transition"] == (54, 7) and placed[2]["transition"] == (107, 6)
    # The trimmed source start moves by the right-side trim at the clip's own speed.
    assert placed[1]["sourceStart"] == Fraction(10) + Fraction(4, 30) * 2
    with pytest.raises(ValueError):
        layout(
            {
                "fpsNumerator": 30,
                "segments": [segment(0, 4), segment(1_000_000, 4, transition=("crossfade", 8))],
            }
        )


def test_fcpxml_is_well_formed_with_assets_transitions_and_time_maps():
    assert 'width="1280" height="720"' in to_fcpxml(EDL, "测试", 1280, 720)
    root = ElementTree.fromstring(to_fcpxml(EDL, "测试"))
    assert root.get("version") == "1.9"
    assert len(root.findall("./resources/asset")) == 2
    spine = root.find(".//spine")
    assert [child.tag for child in spine] == [
        "asset-clip",
        "transition",
        "asset-clip",
        "transition",
        "asset-clip",
    ]
    clips = spine.findall("asset-clip")
    assert [c.get("offset") for c in clips] == ["0s", "19/10s", "11/3s"]
    assert root.find(".//sequence").get("duration") == "137/30s"
    assert clips[1].find("timeMap") is not None and clips[0].find("timeMap") is None
    assert root.find(".//media-rep").get("src").startswith("file:///")


def test_otio_track_duration_matches_render():
    timeline = json.loads(to_otio(EDL, "测试"))
    track = timeline["tracks"]["children"][0]
    clips = [c for c in track["children"] if c["OTIO_SCHEMA"] == "Clip.2"]
    transitions = [c for c in track["children"] if c["OTIO_SCHEMA"] == "Transition.1"]
    assert sum(c["source_range"]["duration"]["value"] for c in clips) == 137
    assert [t["in_offset"]["value"] + t["out_offset"]["value"] for t in transitions] == [7, 6]
    assert clips[1]["effects"][0]["time_scalar"] == 2.0
    assert timeline["metadata"]["gamingcreator"]["importVerified"] is False


def test_http_export_from_saved_revision(revisions):
    jobs, root, _ = revisions
    child = jobs.submit("revision", payload(jobs, root))["jobId"]
    assert finish(jobs, child)["status"] == "completed"
    from gamingcreator.ui.server import create_server

    server = create_server("127.0.0.1", 0, jobs.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}/api/creation/jobs/{child}/timeline?planId=hook-first"
        with urllib.request.urlopen(base + "&format=fcpxml") as response:
            assert "attachment" in response.headers["Content-Disposition"]
            ElementTree.fromstring(response.read())
        with urllib.request.urlopen(base + "&format=fcpxml&size=720x1280") as response:
            assert 'width="720" height="1280"' in response.read().decode("utf-8")
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(base + "&format=fcpxml&size=721x1280")
        error.value.close()
        with urllib.request.urlopen(base + "&format=otio") as response:
            assert json.loads(response.read())["OTIO_SCHEMA"] == "Timeline.1"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_premiere_xmeml_keeps_frames_and_flags_speed():
    from gamingcreator.application.timeline_export import to_xmeml

    root = ElementTree.fromstring(to_xmeml(EDL, "测试"))
    assert root.get("version") == "4"
    assert root.find("./sequence/duration").text == "137"
    track = root.find(".//video/track")
    assert [child.tag for child in track] == [
        "clipitem",
        "transitionitem",
        "clipitem",
        "transitionitem",
        "clipitem",
    ]
    clips = track.findall("clipitem")
    assert [(c.find("start").text, c.find("end").text) for c in clips] == [
        ("0", "57"),
        ("57", "110"),
        ("110", "137"),
    ]
    assert clips[1].find("in").text == "308" and "（2倍）" in clips[1].find("name").text
    effect = clips[1].find("./filter/effect")
    assert effect is not None and effect.findtext("effectid") == "timeremap"
    params = {p.findtext("parameterid"): p for p in effect.findall("parameter")}
    assert params["variablespeed"].findtext("value") == "0"
    assert params["speed"].findtext("value") == "200"
    keys = params["graphdict"].findall("./graphdict/keyframe")
    duration = int(clips[1].findtext("duration"))
    assert [(k.findtext("when"), k.findtext("value")) for k in keys] == [
        ("0", "0"),
        (str(duration), f"{duration * 2:g}"),
    ]
    assert clips[0].find("filter") is None
    assert len(root.findall(".//file/pathurl")) == 2
    transition = track.find("transitionitem")
    assert (transition.find("start").text, transition.find("end").text) == ("54", "61")
