"""Match an exact published refinement key without provider calls or source mutation."""

import json
from pathlib import Path

from gamingcreator.application.detail_query import MAX_MANIFEST_BYTES, match_report
from gamingcreator.application.detail_refinement import (
    DetailRefinementRequest,
    RefinementIdentity,
    RefinementSettings,
    default_refinement_identity,
)
from gamingcreator.application.detail_retrieval import SavedDetailCorpus, build_saved_detail_corpus
from gamingcreator.application.storage import RunStatus, StoredTimeline
from gamingcreator.domain.actor_details import (
    MATCHER_VERSION,
    TEMPORAL_MATCHER_VERSION,
    CandidateDetail,
    QueryConstraint,
    constraint_hash,
)
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.deepseek_detail_parts import provider_parts_identity
from gamingcreator.infrastructure.deepseek_detail_refinement import provider_refinement_identity
from gamingcreator.infrastructure.deepseek_detail_temporal import (
    provider_temporal_identity,
    temporal_refinement_settings,
)
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
    if profile == "v3":
        return provider_parts_identity()
    if profile == "v4":
        return provider_temporal_identity()
    raise AppError("input.detail_profile", "精分析版本只能为v1、v2、v3或v4。", ExitCode.INPUT)


def refinement_settings_for_profile(profile: str) -> RefinementSettings:
    refinement_identity_for_profile(profile)
    return temporal_refinement_settings() if profile == "v4" else RefinementSettings()


def read_saved_detail_corpus(
    project: Path, timelines: tuple[StoredTimeline, ...], profile: str
) -> SavedDetailCorpus:
    identity = refinement_identity_for_profile(profile)
    settings = refinement_settings_for_profile(profile)

    def read(
        timeline: StoredTimeline, event_id: str
    ) -> tuple[DetailRefinementRequest | None, CandidateDetail | None]:
        outcome = reuse_or_refuse(project, timeline, event_id, identity=identity, settings=settings)
        return outcome.request, outcome.detail

    return build_saved_detail_corpus(
        timelines, read, profile=profile, identity=identity, settings=settings
    )


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
    settings = refinement_settings_for_profile(profile)
    outcome = reuse_or_refuse(project, timeline, event_id, identity=identity, settings=settings)

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
        outcome = reuse_or_refuse(project, timeline, event_id, identity=identity, settings=settings)
        if outcome.detail is None or outcome.request_hash is None:
            raise AppError(
                "refinement.source_mismatch",
                "保存前精分析结果已变化。",
                ExitCode.STORAGE,
                timeline.run.run_id,
            )
        document = report()
        directory = sidecar_directory(project, timeline.run.run_id, outcome.request_hash)
        matcher_version = TEMPORAL_MATCHER_VERSION if profile == "v4" else MATCHER_VERSION
        target = directory / "matches" / f"{constraint_hash(constraint)}-{matcher_version}.json"
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
