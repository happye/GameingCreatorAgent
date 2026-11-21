"""Checked per-project brand presets copied into the existing Studio drafts."""

import hashlib
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

from gamingcreator.application.enterprise import (
    PERMISSIONS,
    project_team_key,
    role_of,
    validate_team,
)
from gamingcreator.domain.creation_overlays import CreationOverlays
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.publication import validate_copy
from gamingcreator.infrastructure.local_files import read_bounded
from gamingcreator.infrastructure.overlay_assets import OverlayAssetLibrary, resolve_overlay_assets
from gamingcreator.ui.overlay_jobs import public_asset

if TYPE_CHECKING:
    from gamingcreator.ui.creation_jobs import CreationJobs

_DIGEST = re.compile(r"[a-f0-9]{64}")
TemplateKind = Literal["copy", "visual"]


def _copy_fields(value: object) -> dict[str, Any]:
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


def _normalize(kind: TemplateKind, value: object) -> dict[str, Any] | None:
    if kind == "copy":
        return _copy_fields(value)
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"timelineFrames", "overlays"}:
        raise ValueError("品牌图层模板需要原成片帧数及选中的图层。")
    frames = value["timelineFrames"]
    if type(frames) is not int or not 1 <= frames <= (1 << 53) - 1:
        raise ValueError("品牌图层模板的成片帧数无效。")
    overlays = CreationOverlays.from_json(value["overlays"])
    if not overlays.items:
        raise ValueError("请至少选择一个品牌图层。")
    overlays.validate_duration(frames)
    return {"timelineFrames": frames, "overlays": overlays.to_json()}


def _template_sha256(content: dict[str, Any]) -> str:
    payload = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _path(jobs: "CreationJobs", project_id: str, kind: TemplateKind) -> Path:
    jobs.project(project_id)
    return jobs.safe(
        jobs.root / "enterprise" / f"brand-{kind}" / f"{project_team_key(project_id)}.json"
    )


def _snapshot(template: dict[str, Any] | None, digest: str) -> dict[str, Any]:
    return {
        "template": {**template, "templateSha256": digest}
        if template and any(template.values())
        else None,
        "revisionSha256": digest,
    }


def _read(path: Path, project_id: str, kind: TemplateKind) -> dict[str, Any]:
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
            stored["schemaVersion"] != f"brand-{kind}-template-v1"
            or stored["projectId"] != project_id
            or digest != _template_sha256(stored)
        ):
            raise ValueError
        return _snapshot(_normalize(kind, stored["template"]), digest)
    except (ValueError, RecursionError) as error:
        raise AppError(
            "enterprise.template_damaged", "品牌模板已损坏。", ExitCode.STORAGE
        ) from error


def _visual_assets(jobs: "CreationJobs", template: dict[str, Any]) -> list[dict[str, Any]]:
    overlays = CreationOverlays.from_json(template["overlays"])
    by_id = {
        asset.asset_id: asset
        for asset in resolve_overlay_assets(OverlayAssetLibrary(jobs.repository), overlays)
    }
    return [public_asset(asset) for asset in by_id.values()]


def get_template(
    jobs: "CreationJobs", project_id: str, kind: TemplateKind = "copy"
) -> dict[str, Any]:
    snapshot = _read(_path(jobs, project_id, kind), project_id, kind)
    if kind == "visual" and snapshot["template"]:
        template = snapshot["template"]
        try:
            template["assets"] = _visual_assets(jobs, template)
        except (OSError, ValueError):
            template["assets"] = []
            template["assetIssue"] = "品牌图层素材或登记回执不可用，请重新登记后更新模板。"
    return snapshot


def _check_owner(jobs: "CreationJobs", project_id: str, actor: str) -> None:
    try:
        saved_team = jobs.team(project_id)
        team = validate_team(saved_team) if saved_team is not None else None
    except (ValueError, TypeError, RecursionError) as error:
        raise AppError(
            "enterprise.team_damaged",
            "项目团队设置已损坏，暂时无法保存品牌模板。",
            ExitCode.STORAGE,
        ) from error
    try:
        if team is None or role_of(team, actor.strip()) not in PERMISSIONS["edit_team"]:
            raise PermissionError
    except PermissionError as error:
        raise AppError(
            "enterprise.template_owner",
            "只有项目团队负责人可以保存品牌模板。",
            ExitCode.INPUT,
        ) from error


def save_template(
    jobs: "CreationJobs", request: dict[str, Any], kind: TemplateKind = "copy"
) -> dict[str, Any]:
    if set(request) != {"projectId", "actor", "expectedTemplateSha256", "template"}:
        raise ValueError("品牌模板请求字段无效。")
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
        raise ValueError("品牌模板需要当前项目、负责人姓名和有效校对码。")
    template = _normalize(kind, request["template"])
    path = _path(jobs, project_id, kind)
    with jobs.root_writer():
        _check_owner(jobs, project_id, actor)
        current = _read(path, project_id, kind)
        current_template = current["template"]
        current_fields = (
            {key: value for key, value in current_template.items() if key != "templateSha256"}
            if current_template
            else None
        )
        same = current_fields == (template if template and any(template.values()) else None)
        if not same and current["revisionSha256"] != expected:
            raise AppError(
                "enterprise.template_conflict",
                "品牌模板已更新。请刷新后再保存。",
                ExitCode.STORAGE,
            )
        assets = _visual_assets(jobs, template) if kind == "visual" and template else None
        if not same:
            content = {
                "schemaVersion": f"brand-{kind}-template-v1",
                "projectId": project_id,
                "revision": uuid4().hex,
                "template": template,
            }
            digest = _template_sha256(content)
            path.parent.mkdir(parents=True, exist_ok=True)
            jobs.save(path, {**content, "sha256": digest})
            current = _snapshot(template, digest)
        if assets is not None:
            current["template"]["assets"] = assets
        return current
