"""Sandbox publishing: eligibility gates, persisted lifecycle, and no real platform access."""

import json

import pytest

from gamingcreator.infrastructure.sandbox_publisher import SandboxPublisher

PACKAGE = {
    "localChecks": "pass",
    "publicationEligibility": "unverified",
    "profile": {"Platform": "bilibili"},
}


def test_lifecycle_is_persisted_and_ends_published(tmp_path):
    publisher = SandboxPublisher(tmp_path)
    record = publisher.submit("a" * 32, PACKAGE, "sandbox")
    assert record["state"] == "submitted" and record["simulation"] is True
    assert record["remoteId"].startswith("sandbox-") and record["platform"] == "bilibili"
    states = [publisher.status(record["publishId"])["state"] for _ in range(4)]
    assert states == ["processing", "published", "published", "published"]
    saved = json.loads(
        (tmp_path / ".cache/workspace/publishing" / f"{record['publishId']}.json").read_text(
            "utf-8"
        )
    )
    assert [e["state"] for e in saved["events"]] == ["submitted", "processing", "published"]
    assert [r["publishId"] for r in publisher.history("a" * 32)] == [record["publishId"]]


@pytest.mark.parametrize(
    ("package", "target", "error"),
    [
        (PACKAGE, "bilibili", PermissionError),
        (PACKAGE, "ftp", ValueError),
        ({**PACKAGE, "localChecks": "fail"}, "sandbox", ValueError),
        ({**PACKAGE, "publicationEligibility": "blocked"}, "sandbox", ValueError),
    ],
)
def test_refusals_record_nothing(tmp_path, package, target, error):
    publisher = SandboxPublisher(tmp_path)
    with pytest.raises(error):
        publisher.submit("b" * 32, package, target)
    assert publisher.history("b" * 32) == []
    with pytest.raises(ValueError):
        publisher.status("../escape")
