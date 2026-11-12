"""Topic suggestions cite frozen observations and follow retained segments."""

from dataclasses import replace

import pytest
from test_creation_planner import brief
from test_plan_proposals import output, timelines

from gamingcreator.application.plan_proposals import (
    compile_plan_proposal,
    create_plan_snapshot,
    proposal_version,
    validate_plan_proposal,
    with_knowledge,
)
from gamingcreator.application.plan_topics import with_topics


def snapshot_with_topics(**changes):
    fields = {"mandatory_topics": ("教学", "fact 1"), **changes}
    return with_topics(create_plan_snapshot(replace(brief(), **fields), timelines(), 30))


def topic_output(snapshot, orders=((1, 2, 3),)):
    value = output(snapshot, orders)
    value["schemaVersion"] = proposal_version(snapshot)
    for plan in value["plans"]:
        for shot in plan["shots"]:
            shot["topicUses"] = []
    return value


def use(topic="教学", quote="fact 0"):
    return {"topic": topic, "rationale": "从操作画面说明玩法", "observationQuote": quote}


def compile_value(snapshot, value):
    return compile_plan_proposal(snapshot, validate_plan_proposal(snapshot, value))["plans"][0]


def test_topic_snapshot_version_and_final_coverage():
    snapshot = snapshot_with_topics()
    assert snapshot.payload["schemaVersion"] == "plan-snapshot-v3"
    assert snapshot.payload["topicMapping"] == {
        "schemaVersion": "plan-topics-v1",
        "topics": ["教学", "fact 1"],
    }
    value = topic_output(snapshot, ((2, 1),))
    value["plans"][0]["shots"][1]["topicUses"] = [use()]
    plan = compile_value(snapshot, value)
    assert plan["topicCoverage"] == [
        {"topic": "教学", "status": "ai-suggested", "shotIndexes": [2]},
        {"topic": "fact 1", "status": "missing", "shotIndexes": []},
    ]
    assert plan["segments"][1]["topicUses"] == [use()]
    assert plan["ready"]
    assert len(plan["advisories"]) == 1
    assert "缺少主题映射：fact 1" in plan["advisories"][0]


@pytest.mark.parametrize(
    "fault",
    [
        "unknown",
        "quote",
        "other-candidate",
        "duplicate",
        "long",
        "blank",
        "extra",
        "missing",
    ],
)
def test_reject_invalid_topic_references(fault):
    snapshot = snapshot_with_topics()
    value = topic_output(snapshot)
    shot = value["plans"][0]["shots"][0]
    reference = use()
    shot["topicUses"] = [reference]
    if fault == "unknown":
        reference["topic"] = "未知"
    elif fault == "quote":
        reference["observationQuote"] = "模型编造画面"
    elif fault == "other-candidate":
        reference["observationQuote"] = "fact 1"
    elif fault == "duplicate":
        shot["topicUses"].append(reference.copy())
    elif fault == "long":
        reference["rationale"] = "字" * 501
    elif fault == "blank":
        reference["observationQuote"] = " "
    elif fault == "extra":
        reference["evidenceId"] = "forged"
    else:
        del shot["topicUses"]
    with pytest.raises(ValueError):
        validate_plan_proposal(snapshot, value)


def test_dropped_shot_does_not_count_as_topic_coverage(monkeypatch):
    # Force a valid candidate to receive no output budget: its mapping must disappear.
    monkeypatch.setattr("gamingcreator.application.plan_proposals._budgets", lambda *args: [90, 0])
    snapshot = snapshot_with_topics()
    value = topic_output(snapshot, ((1, 2),))
    value["plans"][0]["shots"][1]["topicUses"] = [use(quote="fact 1")]
    plan = compile_value(snapshot, value)
    assert len(plan["segments"]) == 1
    assert plan["topicCoverage"][0]["status"] == "missing"
    assert plan["topicCoverage"][0]["shotIndexes"] == []


def test_tag_substring_is_accepted_as_verbatim_observation():
    sources = timelines()
    sources[0].events = (
        replace(sources[0].events[0], mechanic_tags=("连续闪避操作",)),
        *sources[0].events[1:],
    )
    snapshot = with_topics(
        create_plan_snapshot(replace(brief(), mandatory_topics=("教学",)), sources, 30)
    )
    value = topic_output(snapshot, ((1,),))
    value["plans"][0]["shots"][0]["topicUses"] = [use(quote="闪避")]
    assert compile_value(snapshot, value)["topicCoverage"][0]["status"] == "ai-suggested"


def test_duplicate_final_interval_does_not_count_mapping():
    snapshot = snapshot_with_topics()
    # Distinct trusted candidate identities can resolve to the same final interval.
    snapshot = replace(snapshot, clips=(snapshot.clips[0], snapshot.clips[0], snapshot.clips[2]))
    value = topic_output(snapshot, ((1, 2),))
    value["plans"][0]["shots"][1]["topicUses"] = [use(quote="fact 1")]
    plan = compile_value(snapshot, value)
    assert len(plan["segments"]) == 1
    assert plan["topicCoverage"][0]["status"] == "missing"


def test_knowledge_composes_in_either_order_without_downgrade():
    base = create_plan_snapshot(replace(brief(), mandatory_topics=("教学",)), timelines(), 30)
    knowledge = [{"entryId": "entry-1"}]
    first = with_knowledge(with_topics(base), knowledge)
    second = with_topics(with_knowledge(base, knowledge))
    assert first.fingerprint == second.fingerprint
    assert first.payload["schemaVersion"] == "plan-snapshot-v3"
    value = topic_output(first)
    value["plans"][0]["knowledgeUses"] = [{"entryId": "entry-1", "structureQuote": "先展示"}]
    plan = compile_value(first, value)
    assert plan["knowledgeUses"][0]["entryId"] == "entry-1"
    assert plan["topicCoverage"][0]["status"] == "missing"


@pytest.mark.parametrize("knowledge", [False, True])
def test_old_versions_and_no_topic_snapshot_remain_unchanged(knowledge):
    snapshot = create_plan_snapshot(brief(), timelines(), 30)
    if knowledge:
        snapshot = with_knowledge(snapshot, [{"entryId": "entry-1"}])
    assert with_topics(snapshot) is snapshot
    value = output(snapshot)
    value["schemaVersion"] = proposal_version(snapshot)
    if knowledge:
        value["plans"][0]["knowledgeUses"] = []
    plan = compile_value(snapshot, value)
    assert "topicCoverage" not in plan
    assert all("topicUses" not in segment for segment in plan["segments"])
    assert value["schemaVersion"] == f"plan-proposal-v{2 if knowledge else 1}"
