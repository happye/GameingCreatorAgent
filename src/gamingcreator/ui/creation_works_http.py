"""Explicit creation and read-only discovery of persistent work identities."""

from typing import cast

from gamingcreator.infrastructure.creation_work_store import CreationWorkStore
from gamingcreator.ui.creation_jobs import CreationJobs


def works_get(jobs: CreationJobs, project_id: object, work_id: object = None) -> dict[str, object]:
    jobs.project(project_id)
    project = cast(str, project_id)
    store = CreationWorkStore(jobs.safe(jobs.root / "works"))
    if work_id is not None:
        if not isinstance(work_id, str):
            raise ValueError("无效作品标识。")
        return {"work": store.read(work_id, project)}
    return {"works": store.catalog(project)}


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
