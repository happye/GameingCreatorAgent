"""Project brand copy used as optional input to the existing publication form."""

import hashlib
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from gamingcreator.application.enterprise import (
    PERMISSIONS,
    project_team_key,
    role_of,
    validate_team,
)
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.publication import validate_copy
from gamingcreator.infrastructure.local_files import read_bounded

if TYPE_CHECKING:
    from gamingcreator.ui.creation_jobs import CreationJobs

_SCHEMA = "brand-copy-template-v1"
_DIGEST = re.compile(r"[a-f0-9]{64}")


def _normalize(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"title", "description", "tags"}:
        raise ValueError("模板需要标题、简介和标签三个字段。")
    validate_copy(value, title_optional=True)
    tags = [tag.strip() for tag in value["tags"]]
    if any("," in tag or "，" in tag for tag in tags) or len(set(tags)) != len(tags):
        raise ValueError("模板标签须以逗号分隔，且不能重复。")
    return {
        "title": value["title"].strip(),
        "description": value["description"].strip(),
        "tags": tags,
    }


def _template_sha256(content: dict[str, Any]) -> str:
    payload = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _path(jobs: "CreationJobs", project_id: str) -> Path:
    jobs.project(project_id)
    return jobs.safe(
        jobs.root / "enterprise" / "brand-copy" / f"{project_team_key(project_id)}.json"
    )


def _snapshot(template: dict[str, Any], digest: str) -> dict[str, Any]:
    return {
        "template": {**template, "templateSha256": digest} if any(template.values()) else None,
        "revisionSha256": digest,
    }


def _read(path: Path, project_id: str) -> dict[str, Any]:
    if not path.exists():
        return {"template": None, "revisionSha256": None}
    try:
        stored = json.loads(read_bounded(path, 32_768))
        if not isinstance(stored, dict) or set(stored) != {
            "schemaVersion",
            "projectId",
            "revision",
            "template",
            "sha256",
        }:
            raise ValueError
        digest = stored.pop("sha256")
        if (
            stored["schemaVersion"] != _SCHEMA
            or stored["projectId"] != project_id
            or digest != _template_sha256(stored)
        ):
            raise ValueError
        return _snapshot(_normalize(stored["template"]), digest)
    except (ValueError, RecursionError) as error:
        raise AppError(
            "enterprise.template_damaged", "品牌文案模板已损坏。", ExitCode.STORAGE
        ) from error


def get_template(jobs: "CreationJobs", project_id: str) -> dict[str, Any]:
    return _read(_path(jobs, project_id), project_id)


def save_template(jobs: "CreationJobs", request: dict[str, Any]) -> dict[str, Any]:
    if set(request) != {"projectId", "actor", "expectedTemplateSha256", "template"}:
        raise ValueError("品牌文案模板请求字段无效。")
    project_id, actor, expected = (
        request[key] for key in ("projectId", "actor", "expectedTemplateSha256")
    )
    if (
        not isinstance(project_id, str)
        or not isinstance(actor, str)
        or not actor.strip()
        or len(actor) > 50
        or (
            expected is not None
            and (not isinstance(expected, str) or _DIGEST.fullmatch(expected) is None)
        )
    ):
        raise ValueError("品牌文案模板需要当前项目、负责人姓名和有效校对码。")
    template = _normalize(request["template"])
    path = _path(jobs, project_id)
    with jobs.root_writer():
        try:
            saved_team = jobs.team(project_id)
            team = validate_team(saved_team) if saved_team is not None else None
        except (ValueError, TypeError, RecursionError) as error:
            raise AppError(
                "enterprise.team_damaged",
                "项目团队设置已损坏，暂时无法保存品牌文案模板。",
                ExitCode.STORAGE,
            ) from error
        try:
            if team is None or role_of(team, actor.strip()) not in PERMISSIONS["edit_team"]:
                raise PermissionError
        except PermissionError as error:
            raise AppError(
                "enterprise.template_owner",
                "只有项目团队负责人可以保存品牌文案模板。",
                ExitCode.INPUT,
            ) from error
        current = _read(path, project_id)
        current_template = current["template"]
        if (not current_template and not any(template.values())) or (
            current_template
            and all(current_template[key] == value for key, value in template.items())
        ):
            return current
        if current["revisionSha256"] != expected:
            raise AppError(
                "enterprise.template_conflict",
                "品牌文案模板已更新。请刷新后再保存。",
                ExitCode.STORAGE,
            )
        content = {
            "schemaVersion": _SCHEMA,
            "projectId": project_id,
            "revision": uuid4().hex,
            "template": template,
        }
        digest = _template_sha256(content)
        path.parent.mkdir(parents=True, exist_ok=True)
        jobs.save(path, {**content, "sha256": digest})
        return _snapshot(template, digest)
