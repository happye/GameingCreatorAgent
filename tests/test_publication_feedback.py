import pytest

from gamingcreator.application.creation_feedback import CreatorStructureChoice
from gamingcreator.domain.errors import AppError
from gamingcreator.ui import publication_feedback
from gamingcreator.ui.creation_jobs import CreationJobs


@pytest.fixture
def target(tmp_path, monkeypatch):
    scope = {
        "projectId": "artifacts/local",
        "publicationJobId": "a" * 32,
        "packageJobId": "b" * 32,
        "packageVideoSha256": "c" * 64,
    }

    def verified_package(self, job_id):
        assert job_id == scope["packageJobId"]
        return {
            "kind": "package",
            "status": "completed",
            "projectId": scope["projectId"],
            "package": {
                "publicationJobId": scope["publicationJobId"],
                "expectedPublicationReceiptSha256": "d" * 64,
                "profile": {"Platform": "bilibili"},
                "artifacts": {
                    "video.mp4": {"sha256": "c" * 64},
                    "package.zip": {"sha256": "e" * 64},
                },
            },
        }

    monkeypatch.setattr(CreationJobs, "get", verified_package)
    body = {
        **scope,
        "source": "test",
        "observedOn": "2026-11-19",
        "postUrl": None,
        "metrics": {"ctrBps": 0, "retention3sBps": None, "completionBps": 1025},
    }
    return CreationJobs(tmp_path), scope, body


def test_feedback_appends_replays_and_recovers_zero_unknown_and_source(target):
    jobs, scope, body = target
    assert publication_feedback.history(jobs, scope)["records"] == []
    assert not (jobs.root / "publication-feedback").exists()
    first = publication_feedback.record(jobs, body)
    assert first["target"] == {
        **scope,
        "publicationReceiptSha256": "d" * 64,
        "packageZipSha256": "e" * 64,
        "platform": "bilibili",
    }
    assert publication_feedback.record(jobs, body) == first
    second = publication_feedback.record(
        jobs,
        {
            **body,
            "source": "creator",
            "observedOn": "2026-11-20",
            "postUrl": "https://video.example/post",
        },
    )
    reopened = CreationJobs(jobs.repository)
    records = publication_feedback.history(reopened, scope)["records"]
    assert records == [second, first] and records[1]["metrics"] == body["metrics"]


def test_feedback_rejects_foreign_identity_invalid_fields_and_altered_history(target):
    jobs, scope, body = target
    for invalid in (
        {"projectId": "artifacts/other"},
        {"publicationJobId": "f" * 32},
        {"packageVideoSha256": "f" * 64},
        {"source": "platform-api"},
        {"observedOn": "2026-02-30"},
        {"postUrl": "javascript:alert(1)"},
        {"metrics": {**body["metrics"], "ctrBps": True}},
        {"metrics": {**body["metrics"], "ctrBps": 10_001}},
    ):
        with pytest.raises(AppError):
            publication_feedback.record(jobs, {**body, **invalid})
    assert not (jobs.root / "publication-feedback").exists()
    saved = publication_feedback.record(jobs, body)
    path = (
        jobs.root
        / "publication-feedback"
        / scope["packageJobId"]
        / (saved["observationId"] + ".json")
    )
    jobs.save(path, {**saved, "source": "creator"})
    with pytest.raises(AppError, match="成效记录校验失败"):
        publication_feedback.history(jobs, scope)


def test_only_known_creator_outcomes_bind_the_next_plan_reference(target, monkeypatch):
    jobs, scope, sample = target
    lineage = {
        "title": "已发布版本",
        "workId": "a" * 32,
        "contentType": "guide",
        "label": "倒序",
        "sourceJobId": "d" * 32,
        "sourcePlanId": "reverse",
        "sourceReceiptSha256": "0" * 64,
    }
    monkeypatch.setattr(publication_feedback, "_lineage", lambda *_: lineage)
    monkeypatch.setattr(
        publication_feedback,
        "_receipt_target",
        lambda service, identity: (
            publication_feedback._package_target(service, identity),
            {"Fields": {}},
        ),
    )
    test = publication_feedback.record(jobs, sample)
    entered = publication_feedback.record(jobs, {**sample, "source": "creator"})
    compared = publication_feedback.compare(jobs, {**scope, "metric": "ctrBps"})
    assert [row["source"] for row in compared["rows"]] == ["creator", "test"]
    assert compared["rows"][1]["choice"] is None
    choice = compared["rows"][0]["choice"]
    assert (
        choice["outcome"]["valueBps"] == 0
        and choice["outcome"]["observationId"] == entered["observationId"]
    )
    query = {
        "projectId": scope["projectId"],
        "workId": lineage["workId"],
        "brief": {"contentType": "guide", "platforms": ["bilibili"]},
    }
    publication_feedback.verify_reference(jobs, query, CreatorStructureChoice.from_json(choice))
    with pytest.raises(ValueError, match="no longer matches"):
        publication_feedback.verify_reference(
            jobs, {**query, "workId": "b" * 32}, CreatorStructureChoice.from_json(choice)
        )
    with pytest.raises(ValueError, match="no longer matches"):
        publication_feedback.verify_reference(
            jobs,
            query,
            CreatorStructureChoice.from_json(
                {
                    **choice,
                    "outcome": {
                        **choice["outcome"],
                        "observationId": test["observationId"],
                        "documentSha256": test["documentSha256"],
                    },
                }
            ),
        )
    for row in publication_feedback.compare(jobs, {**scope, "metric": "retention3sBps"})["rows"]:
        assert row["metrics"]["retention3sBps"] is None and row["choice"] is None
