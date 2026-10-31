"""Rule-based Chinese timeline commands: exact clip changes or a clear refusal."""

import pytest

from gamingcreator.application.creation_editing import build_revision
from gamingcreator.application.timeline_commands import CommandError, apply_timeline_command

FPS = 30
ONE = {"numerator": 1, "denominator": 1}
CUT = {"type": "cut", "frames": 0}


def clips(count=5, seconds=2):
    return [
        {
            "clipId": f"c{i}",
            "startUs": i * 10_000_000,
            "endUs": i * 10_000_000 + seconds * 1_000_000,
            "speed": dict(ONE),
            "transitionIn": dict(CUT),
        }
        for i in range(count)
    ]


def ids(result):
    return [row["clipId"] for row in result["clips"]]


def speeds(result):
    return [(r["speed"]["numerator"], r["speed"]["denominator"]) for r in result["clips"]]


def test_first_seconds_too_slow_speeds_up_only_overlapping_clips():
    result = apply_timeline_command("前5秒太慢", clips(), FPS)
    # Clips start at 0, 2, 4 seconds; the third begins before 5 s.
    assert speeds(result) == [(2, 1), (2, 1), (2, 1), (1, 1), (1, 1)]
    assert result["beforeSeconds"] == 10 and result["afterSeconds"] == 7
    assert result["parser"] == "rule-v3-fullmatch" and len(result["changes"]) == 3


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("删掉第3个镜头", ["c0", "c1", "c3", "c4"]),
        ("删除最后一个镜头", ["c0", "c1", "c2", "c3"]),
        ("去掉第二到第四个", ["c0", "c4"]),
        ("把最后一个镜头移到最前", ["c4", "c0", "c1", "c2", "c3"]),
        ("第1个镜头放到第3个", ["c1", "c2", "c0", "c3", "c4"]),
        ("交换第1个和第2个", ["c1", "c0", "c2", "c3", "c4"]),
        ("第五个和第一个对调", ["c4", "c1", "c2", "c3", "c0"]),
    ],
)
def test_order_and_deletion(text, expected):
    assert ids(apply_timeline_command(text, clips(), FPS)) == expected


def test_speed_trim_and_sequential_clauses():
    result = apply_timeline_command(
        "第2个镜头慢放，整体快放然后恢复第1个镜头原速。第4个镜头缩短到0.5秒", clips(), FPS
    )
    assert speeds(result) == [(1, 1), (2, 1), (2, 1), (2, 1), (2, 1)]
    row = result["clips"][3]
    # At 2x, 0.5 output seconds consume one source second.
    assert row["endUs"] - row["startUs"] == 1_000_000
    # At 2x, 1.5 output seconds would need 3 source seconds: refuse the whole command.
    with pytest.raises(CommandError):
        apply_timeline_command("整体快放，第4个镜头缩短到1.5秒", clips(), FPS)


def test_trim_variants_keep_source_inside_parent():
    trimmed = apply_timeline_command("第4个镜头缩短到1.5秒", clips(), FPS)["clips"][3]
    assert (trimmed["startUs"], trimmed["endUs"]) == (30_000_000, 31_500_000)
    shorter = apply_timeline_command("第2个镜头裁短0.5秒", clips(), FPS)["clips"][1]
    assert (shorter["startUs"], shorter["endUs"]) == (10_000_000, 11_500_000)
    head = apply_timeline_command("第1个镜头去掉开头半秒", clips(), FPS)["clips"][0]
    assert (head["startUs"], head["endUs"]) == (500_000, 2_000_000)


def test_transitions_added_removed_and_repaired():
    added = apply_timeline_command("加交叉淡化", clips(), FPS)
    assert [r["transitionIn"] for r in added["clips"]] == [CUT] + [
        {"type": "crossfade", "frames": 6}
    ] * 4
    removed = apply_timeline_command("去掉转场", added["clips"], FPS)
    assert all(r["transitionIn"] == CUT for r in removed["clips"])
    moved = apply_timeline_command("把第3个镜头移到最前", added["clips"], FPS)
    assert moved["clips"][0]["transitionIn"] == CUT


@pytest.mark.parametrize(
    "text",
    [
        "把画面调亮一点",
        "删掉第9个镜头",
        "删掉全部镜头",
        "第2个镜头缩短到5秒",
        "前5秒太慢，加点特效",
        "",
        "去掉转场",
    ],
)
def test_unknown_or_impossible_commands_are_refused_whole(text):
    original = clips()
    with pytest.raises(CommandError):
        apply_timeline_command(text, original, FPS)
    assert original == clips()


def test_result_is_a_valid_revision_edit():
    edl = {
        "schemaVersion": "edit-decision-v1",
        "fpsNumerator": FPS,
        "fpsDenominator": 1,
        "segments": [
            {
                "startUs": c["startUs"],
                "endUs": c["endUs"],
                "outputFrames": 60,
                "outputStartFrame": i * 60,
                "sourceDurationUs": 100_000_000,
            }
            for i, c in enumerate(clips())
        ],
    }
    root = "a" * 64
    from gamingcreator.application.creation_editing import editable_clips

    rows = editable_clips(edl, root)
    current = [
        {
            "clipId": r["clipId"],
            "startUs": r["startUs"],
            "endUs": r["endUs"],
            "speed": dict(ONE),
            "transitionIn": dict(CUT),
        }
        for r in rows
    ]
    result = apply_timeline_command("前3秒太慢，删掉第5个镜头，加交叉淡化", current, FPS)
    revision = build_revision(edl, root, result["clips"])
    assert len(revision["segments"]) == 4
    assert revision["segments"][-1]["outputStartFrame"] + revision["segments"][-1][
        "outputFrames"
    ] == round(result["afterSeconds"] * FPS)


def test_http_preview_and_readable_refusal(tmp_path):
    import json
    import threading
    import urllib.error
    import urllib.request

    from gamingcreator.ui.server import create_server

    server = create_server("127.0.0.1", 0, tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def post(body):
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/api/creation/timeline-commands",
            json.dumps(body).encode(),
            {"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())

    try:
        result = post({"text": "删掉第1个镜头", "fps": FPS, "clips": clips(2)})
        assert ids(result) == ["c1"]
        with pytest.raises(urllib.error.HTTPError) as refused:
            post({"text": "调亮画面", "fps": FPS, "clips": clips(2)})
        assert refused.value.code == 400
        assert "没听懂" in json.loads(refused.value.read())["message"]
        with pytest.raises(urllib.error.HTTPError):
            post({"text": "删掉第1个镜头", "fps": FPS, "clips": clips(2), "extra": 1})
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("把第4个镜头放到第1个镜头后面", ["c0", "c3", "c1", "c2", "c4"]),
        ("把第1个镜头放到第3个镜头前面", ["c1", "c0", "c2", "c3", "c4"]),
        ("第5个镜头放到第2位", ["c0", "c4", "c1", "c2", "c3"]),
        ("删掉第2个和第3个镜头", ["c0", "c3", "c4"]),
        ("删掉第1、3个镜头", ["c1", "c3", "c4"]),
        ("删掉第3个镜头、第5个镜头", ["c0", "c1", "c3"]),
        ("删掉第3个镜头，再删掉第4个镜头", ["c0", "c1", "c3"]),
    ],
)
def test_review_regressions_for_order(text, expected):
    assert ids(apply_timeline_command(text, clips(), FPS)) == expected


def test_review_regressions_for_targets_and_speed():
    both = apply_timeline_command("第2个和第3个镜头慢放", clips(), FPS)
    assert speeds(both) == [(1, 1), (1, 2), (1, 2), (1, 1), (1, 1)]
    head = apply_timeline_command("第3个镜头去掉前1秒", clips(), FPS)["clips"]
    assert head[2]["startUs"] == 21_000_000 and head[0]["startUs"] == 0
    opening = apply_timeline_command("去掉开头半秒", clips(), FPS)["clips"][0]
    assert opening["startUs"] == 500_000
    assert speeds(apply_timeline_command("整体两倍速", clips(), FPS)) == [(2, 1)] * 5
    assert speeds(apply_timeline_command("第1个镜头0.5倍", clips(), FPS))[0] == (1, 2)


@pytest.mark.parametrize(
    "text",
    [
        "第3个镜头不要太快",
        "第3个镜头不要慢放",
        "去掉交叉淡化",
        "不要交叉淡化",
        "取消淡入淡出",
        "不要加转场",
        "整体1.2倍速",
        "第十十个镜头慢放",
        "第3秒太慢",
        "第一百个镜头慢放",
        "不要第3个镜头",
        "第2个镜头又快又慢",
    ],
)
def test_review_regressions_refuse_instead_of_guessing(text):
    original = clips()
    with pytest.raises(CommandError):
        apply_timeline_command(text, original, FPS)
    assert original == clips()


def test_removing_crossfades_by_its_own_name():
    added = apply_timeline_command("加交叉淡化", clips(), FPS)["clips"]
    for text in ("去掉交叉淡化", "取消淡入淡出", "不要转场"):
        assert all(
            r["transitionIn"] == CUT for r in apply_timeline_command(text, added, FPS)["clips"]
        )


@pytest.mark.parametrize(
    "text",
    [
        "删掉第2个镜头之后的所有镜头",
        "除第3个镜头外整体快放",
        "第3个镜头的前2秒太慢",
        "第3个镜头之前的镜头都快放",
        "第2个镜头加交叉淡化",
        "给第2个镜头加转场",
        "第2个镜头前面加交叉淡化",
        "取消第2个镜头的慢放",
        "取消第2个镜头的快放",
        "不要把第3个镜头移到最前",
        "不要交换第1个和第2个",
        "不要去掉转场",
        "不要去掉前2秒",
        "整体慢放2倍",
        "第2个镜头放慢两倍",
        "整体快放三倍",
        "删掉第2到第4个镜头和第1个镜头",
        "去掉第3个镜头的慢放",
        "把前5秒删掉",
        "删掉最后3秒",
    ],
)
def test_second_review_phrasings_are_refused(text):
    original = clips()
    with pytest.raises(CommandError):
        apply_timeline_command(text, original, FPS)
    assert original == clips()


def test_second_review_phrasings_that_should_edit_exactly():
    tail = apply_timeline_command("删掉最后1秒", clips(), FPS)["clips"][-1]
    assert (tail["startUs"], tail["endUs"]) == (40_000_000, 41_000_000)
    for text in ("第3个镜头剪掉最后1秒", "去掉第3个镜头最后1秒"):
        row = apply_timeline_command(text, clips(), FPS)["clips"][2]
        assert (row["startUs"], row["endUs"]) == (20_000_000, 21_000_000), text
    head = apply_timeline_command("删掉第3个镜头的前1秒", clips(), FPS)["clips"][2]
    assert (head["startUs"], head["endUs"]) == (21_000_000, 22_000_000)
    opening = apply_timeline_command("去掉第2个镜头开头1秒", clips(), FPS)["clips"][1]
    assert opening["startUs"] == 11_000_000
    both = apply_timeline_command("删掉第3个镜头再整体快放", clips(), FPS)
    assert ids(both) == ["c0", "c1", "c3", "c4"] and speeds(both) == [(2, 1)] * 4
    for text in ("第2个镜头慢放再删掉第3个镜头", "第2个镜头慢放并删掉第3个镜头"):
        result = apply_timeline_command(text, clips(), FPS)
        assert ids(result) == ["c0", "c1", "c3", "c4"], text
        assert speeds(result)[1] == (1, 2), text


def test_third_review_minor_fixes():
    for text in (
        "把第2个镜头移到第3个镜头之前",
        "第2个镜头移到第1个镜头之后",
        "第2个镜头移到第2位",
    ):
        with pytest.raises(CommandError):
            apply_timeline_command(text, clips(), FPS)
    fast = apply_timeline_command("整体快放", clips(), FPS)["clips"]
    one_step = apply_timeline_command("第2个镜头慢一点", fast, FPS)
    assert speeds(one_step)[1] == (1, 1)
    with pytest.raises(CommandError):
        apply_timeline_command("第2个镜头快一点", fast, FPS)
    with pytest.raises(CommandError):
        apply_timeline_command("快放\n第2个镜头", clips(), FPS)
    lines = apply_timeline_command("删掉第5个镜头\n第1个镜头慢放", clips(), FPS)
    assert ids(lines) == ["c0", "c1", "c2", "c3"] and speeds(lines)[0] == (1, 2)
