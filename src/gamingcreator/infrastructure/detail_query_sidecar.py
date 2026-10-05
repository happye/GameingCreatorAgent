"""Match an exact published refinement key without provider calls or source mutation."""

import json
from pathlib import Path

from gamingcreator.application.detail_query import MAX_MANIFEST_BYTES, match_report
from gamingcreator.application.detail_refinement import (
    RefinementIdentity,
    default_refinement_identity,
)
from gamingcreator.application.storage import RunStatus, StoredTimeline
from gamingcreator.domain.actor_details import MATCHER_VERSION, QueryConstraint, constraint_hash
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.deepseek_detail_refinement import provider_refinement_identity
from gamingcreator.infrastructure.detail_refinement_sidecar import (
    RefinementWriterLock,
    _atomic,
    _confined,
    _loads,
    reuse_or_refuse,
    sidecar_directory,
)


def refinement_identity_for_profile(profile: str) -> RefinementIdentity:
    if profile == "v1":
        return default_refinement_identity()
    if profile == "v2":
        return provider_refinement_identity()
    raise AppError("input.detail_profile", "精分析版本只能为v1或v2。", ExitCode.INPUT)


def match_refinement(
    project: Path,
    timeline: StoredTimeline,
    event_id: str,
    constraint: QueryConstraint,
    *,
    profile: str = "v2",
    save: bool = False,
) -> dict[str, object]:
    if timeline.run.status != RunStatus.COMPLETED:
        raise AppError(
            "refinement.run_incomplete",
            "匹配仅接受已完成的源运行。",
            ExitCode.STORAGE,
            timeline.run.run_id,
        )
    identity = refinement_identity_for_profile(profile)
    outcome = reuse_or_refuse(project, timeline, event_id, identity=identity)

    def report() -> dict[str, object]:
        document = match_report(
            outcome.request,
            outcome.detail,
            constraint,
            run_id=timeline.run.run_id,
            event_id=event_id,
            request_digest=outcome.request_hash,
        )
        document["refinementProfile"] = profile
        if (
            len(json.dumps(document, ensure_ascii=False, allow_nan=False).encode())
            > MAX_MANIFEST_BYTES
        ):
            raise AppError(
                "refinement.too_large", "匹配报告超过1MiB。", ExitCode.STORAGE, timeline.run.run_id
            )
        return document

    if not save or outcome.detail is None or outcome.request is None:
        return report()
    with RefinementWriterLock(project, outcome.request):
        outcome = reuse_or_refuse(project, timeline, event_id, identity=identity)
        if outcome.detail is None or outcome.request_hash is None:
            raise AppError(
                "refinement.source_mismatch",
                "保存前精分析结果已变化。",
                ExitCode.STORAGE,
                timeline.run.run_id,
            )
        document = report()
        directory = sidecar_directory(project, timeline.run.run_id, outcome.request_hash)
        target = directory / "matches" / f"{constraint_hash(constraint)}-{MATCHER_VERSION}.json"
        _confined(project.resolve(), target)
        if target.exists():
            if _loads(target, project.resolve()) != document:
                raise AppError(
                    "refinement.immutable",
                    "已有匹配记录不符合当前冻结合同。",
                    ExitCode.STORAGE,
                    timeline.run.run_id,
                )
        else:
            _atomic(
                target,
                json.dumps(document, ensure_ascii=False, sort_keys=True, allow_nan=False).encode(),
            )
        return document
