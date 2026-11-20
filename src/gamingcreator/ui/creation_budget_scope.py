"""Resolve creation budget identity from verified local request ancestry."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from gamingcreator.infrastructure.creation_work_store import CreationWorkStore

if TYPE_CHECKING:
    from gamingcreator.ui.creation_jobs import CreationJobs


def request_digest(kind: str, request: dict[str, Any]) -> str:
    canonical = json.dumps({"kind": kind, "request": request}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def resolve_budget_key(
    jobs: CreationJobs,
    job_id: str,
    project_id: str,
    read_prepared: Callable[[str], dict[str, Any]],
) -> str:
    jobs.project(project_id)
    store = CreationWorkStore(jobs.safe(jobs.root / "works"))
    return _resolve(jobs, store, job_id, project_id, read_prepared, set())


def _resolve(
    jobs: CreationJobs,
    store: CreationWorkStore,
    job_id: str,
    project_id: str,
    read_prepared: Callable[[str], dict[str, Any]],
    seen: set[str],
) -> str:
    if job_id in seen or len(seen) >= 100:
        raise ValueError("作品来源链循环或过长。")
    seen = seen | {job_id}
    if job_id.startswith("work:"):
        store.read(job_id[5:], project_id)
        return job_id
    directory = jobs.directory(job_id)
    state = jobs.read(directory / "status.json")
    document = jobs.read(directory / "request.json")
    request = document["request"]
    if (
        state["projectId"] != project_id
        or ("projectId" in request and request["projectId"] != project_id)
        or document["digest"] != request_digest(state["kind"], request)
    ):
        raise ValueError("作品来源请求校验或项目归属不匹配。")
    declared = None
    if "workId" in request:
        store.read(request["workId"], project_id)
        declared = "work:" + request["workId"]
    parents = [
        request[key] for key in ("planJobId", "revisionJobId", "parentJobId") if key in request
    ]
    if any(
        not isinstance(parent, str) or not re.fullmatch("[a-f0-9]{32}", parent)
        for parent in parents
    ):
        raise ValueError("派生任务必须引用真实任务身份。")
    prepared = None
    if "reasoningPreparedHash" in request:
        prepared = read_prepared(request["reasoningPreparedHash"])
        if prepared.get("purpose") != "plan" or prepared["projectId"] != project_id:
            raise ValueError("AI来源必须是同项目的方案准备记录。")
        parents.append(prepared["jobId"])
    if not parents:
        if state["kind"] != "plan" or request.get("projectId") != project_id:
            raise ValueError("作品来源缺少根方案。")
        return declared or job_id
    scopes = [_resolve(jobs, store, parent, project_id, read_prepared, seen) for parent in parents]
    scope = scopes[0]
    if (
        any(value != scope for value in scopes)
        or (declared is not None and declared != scope)
        or (prepared is not None and "budgetKey" in prepared and prepared["budgetKey"] != scope)
    ):
        raise ValueError("作品来源身份冲突。")
    return scope
