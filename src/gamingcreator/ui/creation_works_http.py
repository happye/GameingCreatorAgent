"""Persistent work identities and their editable display names."""

import json
import unicodedata
from pathlib import Path
from typing import cast

from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.creation_work_store import CreationWorkStore, work_document_digest
from gamingcreator.infrastructure.local_files import read_bounded
from gamingcreator.ui.creation_jobs import CreationJobs, fail

WORK_NAME_SCHEMA = "creation-work-name-v1"
WORK_NAME_LIMIT = 100


def _named_work(jobs: CreationJobs, root: Path, work: dict[str, object]) -> dict[str, object]:
    path = root / f"{work['workId']}.name.json"
    try:
        value: object = json.loads(read_bounded(jobs.safe(path), 4096).decode("utf-8"))
        if isinstance(value, dict):
            digest = value.pop("documentSha256", None)
            name = value.get("name")
            if (
                value.get("schemaVersion") == WORK_NAME_SCHEMA
                and value.get("workId") == work["workId"]
                and value.get("projectId") == work["projectId"]
                and isinstance(name, str)
                and digest == work_document_digest(value)
            ):
                return {**work, "workName": name}
    except (OSError, ValueError, RecursionError, AppError):
        pass
    return work


def works_get(jobs: CreationJobs, project_id: object, work_id: object = None) -> dict[str, object]:
    jobs.project(project_id)
    project = cast(str, project_id)
    store = CreationWorkStore(jobs.safe(jobs.root / "works"))
    if work_id is not None:
        if not isinstance(work_id, str):
            raise ValueError("无效作品标识。")
        return {"work": _named_work(jobs, store.root, store.read(work_id, project))}
    return {"works": [_named_work(jobs, store.root, work) for work in store.catalog(project)]}


def works_post(jobs: CreationJobs, value: object) -> dict[str, object]:
    if (
        not isinstance(value, dict)
        or set(value) != {"projectId", "requestId"}
        or any(not isinstance(item, str) or not item.strip() for item in value.values())
    ):
        raise ValueError("无效作品请求字段。")
    jobs.project(value["projectId"])
    store = CreationWorkStore(jobs.safe(jobs.root / "works"))
    return {"work": store.create(value["projectId"], value["requestId"])}


def work_name_post(jobs: CreationJobs, value: object) -> dict[str, object]:
    if (
        not isinstance(value, dict)
        or set(value) != {"projectId", "workId", "name"}
        or any(not isinstance(item, str) for item in value.values())
    ):
        raise ValueError("无效作品命名请求。")
    project_id, work_id = value["projectId"], value["workId"]
    name = value["name"].strip()
    if not 1 <= len(name) <= WORK_NAME_LIMIT or any(
        unicodedata.category(char) in {"Cc", "Cs"} for char in name
    ):
        raise fail("input.work_name", f"请输入 1–{WORK_NAME_LIMIT} 个字的单行作品名称。")
    jobs.project(project_id)
    store = CreationWorkStore(jobs.safe(jobs.root / "works"))
    work = store.read(work_id, project_id)
    # The label is replaced atomically and never enters the identity used by jobs or billing.
    document = {
        "schemaVersion": WORK_NAME_SCHEMA,
        "workId": work_id,
        "projectId": project_id,
        "name": name,
    }
    jobs.save(
        store.root / f"{work_id}.name.json",
        {**document, "documentSha256": work_document_digest(document)},
    )
    return {"work": {**work, "workName": name}}
