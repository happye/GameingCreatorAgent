"""TD020 corpus: every sample has an expected value; unknowns stay 未识别 (None)."""

from __future__ import annotations

import pytest
from activity_rules_corpus import CORPUS

from gamingcreator.application.activity_rules import extract_activity_rules


def _field_value(result: dict, field: str):
    value = result["fields"][field]
    if value is None:
        return None
    if isinstance(value, list):
        return [item["value"] for item in value]
    return value["value"]


def test_corpus_has_at_least_sixty_unique_lines():
    texts = [text for text, _, _ in CORPUS]
    assert len(set(texts)) >= 60


@pytest.mark.parametrize(
    "text,field,expected", CORPUS, ids=[f"{i:02d}" for i in range(len(CORPUS))]
)
def test_corpus_line_expected_value(text, field, expected):
    actual = _field_value(extract_activity_rules(text), field)
    assert actual == expected


def test_unrecognized_deadline_only_does_not_invent_start():
    result = extract_activity_rules("投稿截止到2026年11月30日")
    assert result["fields"]["period"] is None
    assert result["knownFields"] == 0
