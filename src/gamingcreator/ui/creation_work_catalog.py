"""Project existing creation rows onto a verified work without loading media."""

from collections.abc import Callable
from functools import cache
from typing import TYPE_CHECKING, Any

from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.creation_work_store import CreationWorkStore

if TYPE_CHECKING:
    from gamingcreator.ui.creation_jobs import CreationJobs


def jobs_in_work(
    jobs: "CreationJobs", project_id: str, work_id: str, states: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    store = CreationWorkStore(jobs.safe(jobs.root / "works"))
    store.read(work_id, project_id)
    by_id = {state["jobId"]: state for state in states}
    visiting: set[str] = set()
    package_platforms: dict[str, str] = {}

    @cache
    def belongs(job_id: str) -> bool:
        if job_id in visiting or len(visiting) >= 100:
            return False
        state = by_id.get(job_id)
        if state is None or state["projectId"] != project_id:
            return False
        kind = state["kind"]
        if kind not in {"plan", "revision", "render", "publication", "package"}:
            return False
        visiting.add(job_id)
        try:
            stored = jobs._projection_identity(jobs.directory(job_id), state)
            request = stored["request"]
            if kind == "plan":
                # Adopted plans and local duration completions preserve the root request's workId.
                return (request.get("projectId"), request.get("workId")) == (project_id, work_id)
            owned = _belongs_to_parent(state, stored, by_id, belongs)
            if owned and kind == "package":
                profile = request.get("profile")
                if isinstance(profile, dict) and isinstance(profile.get("Platform"), str):
                    package_platforms[job_id] = profile["Platform"]
            return owned
        except (AppError, OSError, ValueError, TypeError, KeyError, RecursionError):
            return False
        finally:
            visiting.remove(job_id)

    matched = [state for state in states if belongs(state["jobId"])]
    return [
        {**state, "platform": package_platforms[state["jobId"]]}
        if state["jobId"] in package_platforms
        else state
        for state in matched
    ]


def _belongs_to_parent(
    state: dict[str, Any],
    stored: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    belongs: Callable[[str], bool],
) -> bool:
    request = stored["request"]
    kind = state["kind"]
    parent_field, parent_kinds, expected_field = {
        "revision": ("parentJobId", ("plan", "revision"), "expectedParentReceiptSha256"),
        "publication": ("renderJobId", ("render",), "expectedRenderReceiptSha256"),
        "package": ("publicationJobId", ("publication",), "expectedPublicationReceiptSha256"),
        "render": ("planJobId", ("plan",), None),
    }[kind]
    if kind == "render" and "revisionJobId" in request:
        parent_field, parent_kinds = "revisionJobId", ("revision",)
    parent_id = request[parent_field]
    parent = by_id.get(parent_id)
    if parent is None or state.get("parentJobId") != parent_id:
        return False
    digest = parent.get("resultReceiptSha256")
    return (
        parent.get("kind") in parent_kinds
        and parent.get("status") == "completed"
        and isinstance(digest, str)
        and stored.get("parentReceiptSha256") == digest
        and (expected_field is None or request.get(expected_field) == digest)
        and belongs(parent_id)
    )
