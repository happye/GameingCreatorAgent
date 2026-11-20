# ruff: noqa: F811 -- pytest fixtures are imported for discovery, then injected by name.

from typing import Any

import pytest
from test_creation_jobs import service  # noqa: F401

from gamingcreator.infrastructure.creation_work_store import CreationWorkStore
from gamingcreator.infrastructure.ffmpeg_media import hash_file
from gamingcreator.ui.creation_budget_scope import request_digest
from gamingcreator.ui.creation_jobs import CreationJobs

PROJECT = "artifacts/project"
WORK = "a" * 32


def _save_task(
    jobs: CreationJobs,
    number: int,
    kind: str,
    request: dict[str, Any],
    parent: str | None = None,
    *,
    receipt_schema: str | None = None,
) -> str:
    job_id = f"{number:032x}"
    directory = jobs.jobs / job_id
    result = directory / "result"
    result.mkdir(parents=True)
    digest = request_digest(kind, request)
    parent_receipt = hash_file(jobs.jobs / parent / "result/receipt.json") if parent else None
    jobs.save(
        directory / "request.json",
        {"request": request, "digest": digest, "parentReceiptSha256": parent_receipt},
    )
    receipt = {
        "schemaVersion": receipt_schema
        or ("creation-receipt-v1" if kind == "plan" else f"creation-{kind}-receipt-v1"),
        "jobId": job_id,
        "requestDigest": digest,
    }
    if kind not in {"plan", "revision"}:
        receipt["status"] = "completed"
    if kind == "publication":
        receipt["parentRenderReceiptSha256"] = parent_receipt
    if kind == "package":
        receipt["parentPublicationReceiptSha256"] = parent_receipt
    jobs.save(result / "receipt.json", receipt)
    jobs.save(
        directory / "status.json",
        {
            "projectId": PROJECT,
            "kind": kind,
            "jobId": job_id,
            "status": "completed",
            "parentJobId": parent,
            "resultReceiptSha256": hash_file(result / "receipt.json"),
            "createdAt": f"{number:04d}",
        },
    )
    return job_id


def test_named_work_catalog_resolves_outputs_before_project_cap(
    service: CreationJobs, monkeypatch: pytest.MonkeyPatch
) -> None:
    def receipt(job_id: str) -> str:
        return hash_file(service.jobs / job_id / "result/receipt.json")

    store = CreationWorkStore(service.root / "works")
    store.create(PROJECT, WORK)
    store.create(PROJECT, "b" * 32)
    root = _save_task(service, 1, "plan", {"projectId": PROJECT, "workId": WORK})
    revision = _save_task(
        service,
        2,
        "revision",
        {"parentJobId": root, "expectedParentReceiptSha256": receipt(root)},
        root,
    )
    replacement = _save_task(
        service,
        3,
        "revision",
        {
            "parentJobId": revision,
            "expectedParentReceiptSha256": receipt(revision),
            "candidateManifestSha256": "c" * 64,
        },
        revision,
        receipt_schema="creation-revision-receipt-v2",
    )
    insertion = _save_task(
        service,
        4,
        "revision",
        {
            "parentJobId": replacement,
            "expectedParentReceiptSha256": receipt(replacement),
            "insertions": [{}],
        },
        replacement,
        receipt_schema="creation-revision-receipt-v3",
    )
    render = _save_task(service, 5, "render", {"revisionJobId": insertion}, insertion)
    publication = _save_task(
        service,
        6,
        "publication",
        {"renderJobId": render, "expectedRenderReceiptSha256": receipt(render)},
        render,
    )
    package = _save_task(
        service,
        7,
        "package",
        {
            "publicationJobId": publication,
            "expectedPublicationReceiptSha256": receipt(publication),
            "profile": {"Platform": "bilibili"},
        },
        publication,
    )
    _save_task(
        service,
        8,
        "package",
        {"publicationJobId": publication, "expectedPublicationReceiptSha256": "0" * 64},
        publication,
    )
    for number in range(100, 201):
        path = service.jobs / f"{number:032x}"
        path.mkdir()
        service.save(
            path / "status.json",
            {
                "projectId": PROJECT,
                "kind": "narration",
                "jobId": path.name,
                "status": "completed",
                "createdAt": f"{number:04d}",
            },
        )

    def fail_verify(*args: object) -> None:
        pytest.fail("listing completed jobs must avoid full artifact verification")

    monkeypatch.setattr(service, "verify", fail_verify)
    assert service.catalog(PROJECT)["truncated"] is True
    filtered = service.catalog(PROJECT, WORK)
    assert filtered["truncated"] is False
    assert [row["jobId"] for row in filtered["jobs"]] == [
        package,
        publication,
        render,
        insertion,
        replacement,
        revision,
        root,
    ]
    assert filtered["jobs"][0]["platform"] == "bilibili"
    assert service.catalog(PROJECT, "b" * 32) == {"jobs": [], "truncated": False}
    with pytest.raises(ValueError):
        service.catalog(PROJECT, "f" * 32)
