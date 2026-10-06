"""A condition draft must preserve every word and never strengthen unsupported prose."""

import json

import pytest

from gamingcreator.application.detail_query import loads_constraint
from gamingcreator.application.detail_query_draft import draft_detail_query
from gamingcreator.domain.actor_details import AttributeKind, normalize_attribute_value


def checked(text):
    report = draft_detail_query(text)
    assert set(report) == {
        "schemaVersion",
        "originalText",
        "status",
        "spanOffsetUnit",
        "constraint",
        "spans",
        "unparsed",
    }
    assert report["schemaVersion"] == "actor-detail-query-draft-v1"
    assert report["originalText"] == text
    assert report["spanOffsetUnit"] == "unicode-code-point"
    assert "".join(span["text"] for span in report["spans"]) == text
    position = 0
    for span in report["spans"]:
        assert set(span) == {"start", "end", "text", "kind", "reason"}
        assert span["start"] == position and span["end"] > span["start"]
        assert text[span["start"] : span["end"]] == span["text"]
        assert span["kind"] in ("recognized", "connector", "unparsed")
        assert span["reason"]
        position = span["end"]
    assert position == len(text)
    assert report["unparsed"] == [span for span in report["spans"] if span["kind"] == "unparsed"]
    if report["constraint"] is not None:
        constraint = loads_constraint(json.dumps(report["constraint"]))
        assert constraint.actor_all
        assert len(constraint.actor_all) + len(constraint.environment_all) <= 16
        for condition in constraint.actor_all + constraint.environment_all:
            assert normalize_attribute_value(condition.kind, condition.value) == condition.value
    return report


def atoms(report, scope="actorAll"):
    return {
        (item["kind"], item["value"], item["partGroup"]) for item in report["constraint"][scope]
    }


@pytest.mark.parametrize(
    "text",
    [
        "白发",
        "白色头发",
        "白色的头发",
        "white hair",
        "White Hair",
        "white-haired",
        "  白发  ",
        "\twhite\n hair\r\n",
        "一个角色有着白色头发",
        "找白发角色",
        "请找出白发的角色",
        "A character with white hair",
        "find clips of a character with white hair",
    ],
)
def test_supported_hair_forms_are_complete_positive_drafts(text):
    report = checked(text)
    assert report["status"] == "ready" and not report["unparsed"]
    assert atoms(report) == {("hair_color", "white", "hair")}


def test_chinese_compound_binds_color_and_shape_to_the_same_garment():
    report = checked("白发、穿着红色外套，手持蓝色扁平物体")
    assert report["status"] == "ready"
    assert atoms(report) == {
        ("hair_color", "white", "hair"),
        ("clothing_color", "red", "clothing1"),
        ("clothing_shape", "coat", "clothing1"),
        ("held_shape", "blue_flat_object", "held1"),
    }


def test_explicit_english_grammar_has_the_same_values_without_domain_vocabulary_changes():
    report = checked(
        "a character with white hair, wearing a red coat and holding a blue flat object"
    )
    assert report["status"] == "ready"
    assert atoms(report) == atoms(checked("白发，红色外套，拿着蓝色扁平物体"))


def test_multiple_garments_and_held_objects_keep_distinct_part_groups():
    report = checked("白发，红色外套，蓝色围巾，拿着蓝色扁平物体和长杆")
    assert report["status"] == "ready"
    assert ("clothing_color", "red", "clothing1") in atoms(report)
    assert ("clothing_shape", "coat", "clothing1") in atoms(report)
    assert ("clothing_color", "blue", "clothing2") in atoms(report)
    assert ("clothing_shape", "scarf", "clothing2") in atoms(report)
    assert ("held_shape", "blue_flat_object", "held1") in atoms(report)
    assert ("held_shape", "long_rod", "held2") in atoms(report)


@pytest.mark.parametrize(
    "text,kind,value",
    [
        ("红发", "hair_color", "red"),
        ("grey hair", "hair_color", "gray"),
        ("green trousers", "clothing_color", "green"),
        ("light-colored armor", "clothing_color", "light"),
        ("蓝色的手套", "clothing_color", "blue"),
        ("上装", "clothing_shape", "upper_garment"),
        ("拿着权杖", "held_class", "staff"),
        ("holding a weapon", "held_class", "weapon"),
        ("握着工具", "held_class", "tool"),
        ("curved object", "held_shape", "curved_object"),
        ("扁平物", "held_shape", "flat_object"),
        ("抬头", "action", "look_up"),
        ("移动", "action", "move"),
        ("running", "action", "run"),
        ("jumping", "action", "jump"),
        ("举起持有物", "action", "raise_item"),
        ("射击", "action", "shoot"),
        ("光弧", "effect", "light_arc"),
        ("light ring", "effect", "light_ring"),
        ("投射物", "effect", "projectile"),
    ],
)
def test_only_explicit_supported_phrases_generate_frozen_values(text, kind, value):
    report = checked(text)
    assert report["status"] == "ready"
    assert any(item[0:2] == (kind, value) for item in atoms(report))
    assert normalize_attribute_value(AttributeKind(kind), value) == value


@pytest.mark.parametrize(
    "phrase,value",
    [
        ("在水面上", "water"),
        ("on a stone platform", "stone_platform"),
        ("on the sandy ground", "sandy_ground"),
        ("场景是室内", "indoors"),
        ("outdoors", "outdoors"),
    ],
)
def test_environment_can_join_an_actor_query_but_cannot_be_ready_alone(phrase, value):
    report = checked("白发，" + phrase)
    assert report["status"] == "ready"
    assert atoms(report, "environmentAll") == {("environment", value, "environment")}
    alone = checked(phrase)
    assert alone["status"] == "needs_review" and alone["constraint"] is None
    assert alone["unparsed"] and "环境" in alone["unparsed"][0]["reason"]


@pytest.mark.parametrize(
    "unknown",
    [
        "恶魔领主",
        "某角色",
        "某技能",
        "释放某技能",
        "苍龙破",
        "漂亮的",
        "彩虹色头发",
        "red hood",
        "rainbow hair",
        "Professor Redcoat",
        "overshooting",
        "runningman",
        "look upside",
        "😀",
        "e\u0301",
        "<img src=x onerror=alert(1)>",
        "<script>alert('白发')</script>",
    ],
)
def test_unknown_names_verbs_words_and_markup_remain_visible_for_subset_confirmation(unknown):
    text = "白发，" + unknown
    report = checked(text)
    assert report["status"] == "needs_review"
    assert report["unparsed"]
    assert report["constraint"] is not None
    # Partial recognition never erases the original unknown wording or auto-runs a matcher.
    assert report["originalText"] == text
    assert ("hair_color", "white", "hair") in atoms(report)


@pytest.mark.parametrize(
    "text",
    [
        "白发，不穿红色外套",
        "不是白发",
        "没有白发",
        "白发而非黑发",
        "white hair without a red coat",
        "not white hair",
        "white hair or black hair",
        "白发或黑发",
        "白发或者黑发",
        "白发/黑发",
        "先抬头再跳跃",
        "白发然后射击",
        "white hair then shooting",
        "before jumping white hair",
        "白发角色和红发角色",
        "两个白发角色",
        "白发人物旁边的红发人物",
        "白发的角色身后有一个人",
        "two white-haired characters",
        "a white-haired person beside a red-haired person",
        "white hair with another red-haired person",
        "white hair and one red-haired person",
        "白发角色攻击另一个人",
        "white hair while running",
        "全程白发",
        "一直奔跑",
    ],
)
def test_unsupported_logic_subject_relations_and_temporal_requirements_never_emit_positive_manifest(
    text,
):
    report = checked(text)
    assert report["status"] == "unsupported" and report["constraint"] is None
    assert report["unparsed"]


@pytest.mark.parametrize(
    "text", ["白发，白发", "white hair and white-haired", "红色外套和red jacket", "长杆和long rod"]
)
def test_duplicate_requirements_are_explicitly_reviewed_instead_of_silently_dropped(text):
    report = checked(text)
    assert report["status"] == "needs_review"
    assert any("重复" in item["reason"] for item in report["unparsed"])
    assert report["constraint"] is not None


def test_conflicting_hair_colors_need_review_and_preserve_the_second_requirement():
    report = checked("白发和黑发")
    assert report["status"] == "needs_review"
    assert report["unparsed"][-1]["text"] == "黑发"
    assert "互斥" in report["unparsed"][-1]["reason"]


@pytest.mark.parametrize("text", ["白发，红色漂亮外套", "白发，红色，外套", "白发，蓝绿色外套"])
def test_color_does_not_jump_across_unknown_words_or_punctuation_into_a_garment(text):
    report = checked(text)
    assert report["status"] == "needs_review"
    assert report["unparsed"]
    if "漂亮" in text or "红色，" in text:
        assert not any(kind == "clothing_color" for kind, _, _ in atoms(report))


def test_unknown_held_item_color_cannot_become_a_new_vocabulary_value():
    report = checked("白发，绿色权杖")
    assert report["status"] == "needs_review"
    assert any("绿色" in item["text"] for item in report["unparsed"])
    assert ("held_class", "staff", "held1") in atoms(report)
    assert not any(item["kind"] == "held_color" for item in report["constraint"]["actorAll"])


@pytest.mark.parametrize("text", ["and white hair", "白发和某技能", "查询某技能", "白发的恶魔领主"])
def test_connectors_require_supported_context_and_cannot_swallow_unknown_requests(text):
    report = checked(text)
    assert report["status"] == "needs_review"
    assert report["unparsed"]


def test_exactly_sixteen_combined_conditions_are_supported_and_seventeen_are_not_truncated():
    text = "白发、红色外套、蓝色围巾、绿色短裤、黑色长裤、黄色盔甲、棕色手套、紫色上装、移动"
    report = checked(text)
    assert report["status"] == "ready"
    assert len(report["constraint"]["actorAll"]) == 16
    overflow = checked(text + "、光环")
    assert overflow["status"] == "unsupported" and overflow["constraint"] is None
    assert any("16" in item["reason"] for item in overflow["unparsed"])
    with_environment = checked(text + "、沙地")
    assert with_environment["status"] == "unsupported" and with_environment["constraint"] is None


def test_repeated_seventeenth_condition_still_does_not_evade_the_input_condition_bound():
    report = checked("、".join(["白发"] * 17))
    assert report["status"] == "unsupported" and report["constraint"] is None
    assert "16" in report["unparsed"][-1]["reason"]


def test_emoji_offsets_count_unicode_code_points_and_keep_original_spacing():
    text = "😀 白发\n🧑🏽‍🚀 红色外套"
    report = checked(text)
    assert report["status"] == "needs_review"
    white = next(item for item in report["spans"] if item["text"] == "白发")
    assert white["start"] == 2 and white["end"] == 4
    assert report["spans"][0]["text"] == "😀" and report["spans"][0]["end"] == 1


@pytest.mark.parametrize("text", ["", " ", "\t\n", "，。"])
def test_empty_and_nonsemantic_input_never_become_ready(text):
    report = checked(text)
    assert report["status"] in ("unsupported", "needs_review") and report["constraint"] is None


def test_full_input_limit_is_preserved_and_overlimit_or_invalid_input_is_rejected():
    text = "白发" + " " * 2046
    assert checked(text)["originalText"] == text
    for invalid in (text + " ", "😀" * 2049, None, 1, "\ud800"):
        with pytest.raises(ValueError):
            draft_detail_query(invalid)


def test_draft_is_deterministic_and_returned_mutations_do_not_change_a_subsequent_result():
    text = "白发，红色外套，未知名字"
    original = checked(text)
    expected = json.loads(json.dumps(original))
    original["constraint"]["actorAll"].clear()
    original["unparsed"][0]["text"] = "changed"
    assert checked(text) == expected
