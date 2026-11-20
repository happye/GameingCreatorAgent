"""Durable local exports for combinations of evidenced advertising plans."""

from pathlib import Path
from time import sleep
from typing import Any
from uuid import uuid4

from gamingcreator.application.ad_cut import AD_ACTIONS
from gamingcreator.domain.creation_presentation import SUBTITLE_STYLES
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.platform_profile import validate_profile
from gamingcreator.ui.creation_budget_scope import request_digest
from gamingcreator.ui.package_batches import PackageBatches, identity, locked
from gamingcreator.ui.revision_jobs import Chain, load_chain, revision_subtitles

STAGES = ("render", "publication", "package")
VERSION_LABELS = {"ad-evidence-hook": "卖点版", "ad-evidence-demo": "演示版"}
STYLE_LABELS = {"none": "无字幕", "standard": "标准字幕", "large": "大字字幕", "boxed": "底框字幕"}


def new_stage() -> dict[str, Any]:
    return {
        "childRequestId": uuid4().hex,
        "jobId": None,
        "status": "pending",
        "error": None,
        "attempt": 1,
    }


class AdBatches(PackageBatches):
    schema = "ad-batch-v1"
    root_name = "ad-batches"
    scope_key = "planJobId"
    retry_failed_items = True

    def validate(self, value: dict[str, Any]) -> None:
        if not isinstance(value, dict) or set(value) != {
            "requestId",
            "projectId",
            "planJobId",
            "expectedPlanReceiptSha256",
            "profile",
            "variants",
        }:
            raise ValueError("请提供广告方案、成片选项和本机平台配置。")
        identity(value["requestId"])
        root_id = identity(value["planJobId"])
        self.jobs.project(value["projectId"])
        profile = validate_profile(value["profile"])
        if profile["Fields"].keys() & {"variant", "publicationText"}:
            raise ValueError("广告批量使用完整成片的平台配置。")
        if profile["Fields"]["video"]["fit"] != "pad":
            raise ValueError("广告批量的平台画幅需要保留原画比例并补边。")
        plan = self.jobs.get(root_id)
        if (
            plan["kind"] != "plan"
            or plan["status"] != "completed"
            or plan["projectId"] != value["projectId"]
            or plan["brief"]["contentType"] != "ad"
            or plan["resultReceiptSha256"] != value["expectedPlanReceiptSha256"]
        ):
            raise ValueError("广告方案与项目或已保存回执不匹配。")
        ready = {p["id"] for p in plan["plans"] if p["ready"] and p["id"] in AD_ACTIONS}
        variants = value["variants"]
        if not isinstance(variants, list) or not 1 <= len(variants) <= 6:
            raise ValueError("请选择一到六个广告版本。")
        seen = set()
        revisions: dict[str, Chain] = {}
        for row in variants:
            if not isinstance(row, dict) or set(row) not in (
                {"planId", "subtitleStyle"},
                {"planId", "subtitleStyle", "revisionJobId", "revisionReceiptSha256"},
            ):
                raise ValueError("广告版本字段无效。")
            plan_id = row["planId"]
            if not isinstance(plan_id, str) or plan_id not in ready:
                raise ValueError("请选择有原片依据的可用广告方案。")
            if row["subtitleStyle"] not in ("none", *SUBTITLE_STYLES):
                raise ValueError("广告版本的字幕样式无效。")
            revision = identity(row["revisionJobId"]) if "revisionJobId" in row else None
            key = (plan_id, row["subtitleStyle"], revision)
            if key in seen:
                raise ValueError("广告版本组合重复。")
            seen.add(key)
            if revision is not None:
                self.validate_revision(revision, root_id, row, revisions)

    def validate_revision(
        self, revision: str, root_id: str, row: dict[str, Any], revisions: dict[str, Chain]
    ) -> None:
        if revision not in revisions:
            state = self.jobs.read(self.jobs.directory(revision) / "status.json")
            if state["kind"] != "revision" or state["status"] != "completed":
                raise ValueError("请选择已保存剪辑版本。")
            revisions[revision] = load_chain(self.jobs, revision, read_only=True)
        chain = revisions[revision]
        if (chain.root_id, chain.plan_id, chain.digest) != (
            root_id,
            row["planId"],
            row["revisionReceiptSha256"],
        ):
            raise ValueError("已保存剪辑与广告方案或回执不匹配。")
        if row["subtitleStyle"] != "none" and chain.subtitle_overrides:
            revision_subtitles(chain, "burn", ad_fallback=True)

    def initial_state(self, value: dict[str, Any]) -> dict[str, Any]:
        return {
            "planJobId": value["planJobId"],
            "profile": value["profile"],
            "items": [
                {
                    **variant,
                    "status": "pending",
                    "error": None,
                    "stages": {kind: {**new_stage(), "history": []} for kind in STAGES},
                }
                for variant in value["variants"]
            ],
        }

    def stage_payload(
        self,
        kind: str,
        request: dict[str, Any],
        item: dict[str, Any],
        parent: dict[str, Any],
    ) -> dict[str, Any]:
        if kind == "render":
            video = request["profile"]["Fields"]["video"]
            style = item["subtitleStyle"]
            return {
                **(
                    {"revisionJobId": item["revisionJobId"]}
                    if "revisionJobId" in item
                    else {"planJobId": request["planJobId"], "planId": item["planId"]}
                ),
                "expectedParentReceiptSha256": item.get(
                    "revisionReceiptSha256", request["expectedPlanReceiptSha256"]
                ),
                "width": video["width"],
                "height": video["height"],
                **(
                    {"subtitleMode": "burn", "subtitleStyle": style, "adCaptionFallback": True}
                    if style != "none"
                    else {}
                ),
            }
        if kind == "publication":
            draft = self.jobs.publication(parent["jobId"])
            return {
                **{
                    field: draft[field]
                    for field in (
                        "renderJobId",
                        "expectedRenderReceiptSha256",
                        "coverFrame",
                        "description",
                        "tags",
                    )
                },
                "title": f"{draft['title']}｜{VERSION_LABELS[item['planId']]} · {STYLE_LABELS[item['subtitleStyle']]}",
            }
        return {
            "profile": request["profile"],
            "publicationJobId": parent["jobId"],
            "expectedPublicationReceiptSha256": parent["resultReceiptSha256"],
        }

    def bind_stage(
        self,
        directory: Path,
        index: int,
        kind: str,
        request: dict[str, Any],
        parent: dict[str, Any],
    ) -> dict[str, Any] | None:
        with locked(directory / "state-lock"):
            state = self.read(directory)
            if state["cancelRequested"]:
                return None
            item = state["items"][index]
            stage = item["stages"][kind]
            payload = stage.get("payload")
            if payload is None:
                payload = self.stage_payload(kind, request, request["variants"][index], parent)
                stage["payload"] = payload
            child_request = {"requestId": stage["childRequestId"], **payload}
            registration = self.jobs.safe(
                self.jobs.root / (identity(stage["childRequestId"]) + ".json")
            )
            if registration.exists():
                registered = self.jobs.read(registration)
                if registered["digest"] != request_digest(kind, child_request):
                    raise ValueError("广告子任务请求已变化。")
                job_id = registered["jobId"]
                if stage["jobId"] not in (None, job_id):
                    raise ValueError("广告子任务与请求标识不匹配。")
                prior_status = stage["status"]
                child = self.bound_child(kind, child_request, job_id, state["projectId"])
                stage.update(jobId=job_id, status=child["status"], error=child.get("error"))
                retry = child["status"] == "interrupted" or (
                    prior_status == child["status"] == "failed"
                    and (child.get("error") or {}).get("code") != "creation.artifact_invalid"
                )
                if not retry:
                    self.save(directory, state)
                    return dict(child)
                stage["history"].append(
                    {key: value for key, value in stage.items() if key != "history"}
                )
                stage.update({**new_stage(), "attempt": stage["attempt"] + 1})
                child_request["requestId"] = stage["childRequestId"]
            elif stage["jobId"] is not None:
                raise ValueError("广告子任务的请求登记已缺失。")
            item.update(status="running", error=None)
            self.save(directory, state)
            accepted = self.jobs.submit(kind, child_request)
            stage.update(jobId=accepted["jobId"], status=accepted["status"])
            self.save(directory, state)
            return self.bound_child(kind, child_request, accepted["jobId"], state["projectId"])

    def bound_child(
        self, kind: str, request: dict[str, Any], job_id: str, project_id: str
    ) -> dict[str, Any]:
        stored = self.jobs.read(self.jobs.directory(job_id) / "request.json")
        parents = {
            "render": (
                request.get("revisionJobId", request.get("planJobId")),
                "expectedParentReceiptSha256",
            ),
            "publication": (request.get("renderJobId"), "expectedRenderReceiptSha256"),
            "package": (request.get("publicationJobId"), "expectedPublicationReceiptSha256"),
        }
        parent_id, receipt_key = parents[kind]
        if (
            stored["request"] != request
            or stored["digest"] != request_digest(kind, request)
            or stored["parentReceiptSha256"] != request[receipt_key]
        ):
            raise ValueError("广告子任务的请求或父回执不匹配。")
        child = self.jobs.get(job_id, include_receipt=True)
        if (child["kind"], child["projectId"], child["parentJobId"]) != (
            kind,
            project_id,
            parent_id,
        ):
            raise ValueError("广告子任务的类型、项目或父任务不匹配。")
        return dict(child)

    def finish_stage(
        self,
        directory: Path,
        index: int,
        kind: str,
        status: str,
        error: object,
    ) -> None:
        with locked(directory / "state-lock"):
            state = self.read(directory)
            item = state["items"][index]
            item["stages"][kind].update(status=status, error=error)
            item.update(
                status="running" if status == "completed" and kind != "package" else status,
                error=error,
            )
            self.save(directory, state)

    def run_item(self, directory: Path, index: int) -> bool:
        request = self.request(directory)
        parent: dict[str, Any] = {}
        for kind in STAGES:
            try:
                child = self.bind_stage(directory, index, kind, request, parent)
            except AppError as error:
                if error.code == "entitlement.denied":
                    self.finish_stage(
                        directory, index, kind, "interrupted", {"message": error.message}
                    )
                    raise
                if error.exit_code != ExitCode.INPUT:
                    raise
                self.finish_stage(directory, index, kind, "failed", {"message": error.message})
                return True
            if child is None:
                return False
            while child["status"] in {"pending", "running"}:
                sleep(0.25)
                child = self.jobs.get(child["jobId"], include_receipt=True)
            status = child["status"]
            self.finish_stage(directory, index, kind, status, child.get("error"))
            if status != "completed":
                return True
            parent = child
        return True
