import pytest

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
