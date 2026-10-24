"""Production CLI assembly for one-frame static-observation generation."""

from __future__ import annotations

import os
from pathlib import Path

from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004
from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.retrieval import load_searchable_timeline
from gamingcreator.application.static_observation_generation import (
    MAX_STATIC_GENERATION_AUTHORIZATION_BYTES,
    MAX_STATIC_GENERATION_PROPOSAL_BYTES,
    StaticGenerationAuthorization,
    StaticGenerationProposal,
    build_prepare_report,
    build_static_generation_proposal,
    execute_static_observation_generation,
    generation_paths,
    loads_static_generation_authorization,
    loads_static_generation_proposal,
    proposal_file_bytes,
)
from gamingcreator.application.static_observations import (
    PublishStatus,
    StaticCollectionArtifact,
)
from gamingcreator.application.storage import StoredTimeline
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.deepseek_static_observations import (
    DeepSeekStaticObservationProvider,
)
from gamingcreator.infrastructure.http_transport import HttpxVisionTransport, VisionTransport
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.infrastructure.static_observation_attempts import (
    SqliteStaticGenerationLedger,
)
from gamingcreator.infrastructure.static_observation_store import (
    SqliteStaticObservationStore,
)


def build_vision_transport() -> VisionTransport:
    """The only network seam; offline tests replace this factory, never the store."""
    return HttpxVisionTransport()


def _input_error(message: str) -> AppError:
    return AppError("input.static_generation", message, ExitCode.INPUT)


def _scope_error() -> AppError:
    return AppError(
        "static_generation.scope",
        "命令行项目、数据库或固定账本根与冻结身份不一致。",
        ExitCode.INPUT,
    )


def _read_bounded(path: Path, limit: int, label: str) -> bytes:
    try:
        if path.is_symlink() or not path.is_file():
            raise _input_error(f"找不到静态生成{label}文件。")
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
    except OSError as error:
        raise _input_error(f"无法读取静态生成{label}文件。") from error
    if len(data) > limit:
        raise _input_error(f"静态生成{label}文件超过有界大小。")
    return data


def _verify_scope(
    proposal: StaticGenerationProposal,
    project_root: Path,
    database: Path,
    ledger_root: Path,
) -> None:
    if (
        proposal.project_root != str(project_root)
        or proposal.database_path != str(database)
        or proposal.ledger_root != str(ledger_root)
    ):
        raise _scope_error()


async def _timeline(project: Path, run_id: str) -> StoredTimeline:
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        return await load_searchable_timeline(store, run_id)
    finally:
        await store.close()


def _publish(project: Path, artifact: StaticCollectionArtifact) -> PublishStatus:
    store = SqliteStaticObservationStore.open(project, read_only=False)
    try:
        return store.publish(artifact)
    finally:
        store.close()


def _write_frozen_proposal(path: Path, data: bytes) -> str:
    """Create the frozen proposal once; identical bytes are unchanged, anything else fails."""
    try:
        if path.is_symlink() or path.is_junction():
            raise _input_error("静态生成提案输出不能是符号链接或目录联接。")
        if not path.parent.is_dir():
            raise _input_error("静态生成提案输出目录必须已存在。")
        if path.exists():
            if not path.is_file():
                raise _input_error("静态生成提案输出必须是普通文件。")
            existing = _read_bounded(path, MAX_STATIC_GENERATION_PROPOSAL_BYTES, "提案")
            if existing != data:
                raise _input_error("该路径已保存不同内容的冻结提案；不会覆盖。")
            return "unchanged"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise
    except FileExistsError:
        existing = _read_bounded(path, MAX_STATIC_GENERATION_PROPOSAL_BYTES, "提案")
        if existing != data:
            raise _input_error("该路径已保存不同内容的冻结提案；不会覆盖。") from None
        return "unchanged"
    except OSError as error:
        raise _input_error("无法写入静态生成冻结提案。") from error
    return "created"


async def execute_prepare_static_observation_generation(
    project: Path,
    run_id: str,
    collection_id: str,
    evidence_id: str,
    output: Path,
) -> dict[str, object]:
    """Freeze one registered Completed frame locally; no provider, network, or ledger write."""
    generation_paths(project)
    timeline = await _timeline(project, run_id)
    proposal = build_static_generation_proposal(
        project,
        timeline,
        run_id=run_id,
        collection_id=collection_id,
        evidence_id=evidence_id,
    )
    status = _write_frozen_proposal(output, proposal_file_bytes(proposal))
    return build_prepare_report(
        proposal,
        status="prepared" if status == "created" else "unchanged",
        proposal_path=output,
    )


def _load_dispatch_inputs(
    project: Path, proposal_path: Path, authorization_path: Path
) -> tuple[
    StaticGenerationProposal,
    StaticGenerationAuthorization,
    Path,
]:
    project_root, database, ledger_root = generation_paths(project)
    proposal = loads_static_generation_proposal(
        _read_bounded(proposal_path, MAX_STATIC_GENERATION_PROPOSAL_BYTES, "提案")
    )
    _verify_scope(proposal, project_root, database, ledger_root)
    authorization = loads_static_generation_authorization(
        _read_bounded(
            authorization_path,
            MAX_STATIC_GENERATION_AUTHORIZATION_BYTES,
            "人类授权",
        )
    )
    return proposal, authorization, project_root


async def execute_dispatch_static_observation_generation(
    project: Path, proposal_path: Path, authorization_path: Path
) -> dict[str, object]:
    """Explicitly dispatch at most one provider request under the frozen human declaration."""
    proposal, authorization, project_root = _load_dispatch_inputs(
        project, proposal_path, authorization_path
    )
    timeline = await _timeline(project_root, proposal.run_id)
    ledger = SqliteStaticGenerationLedger(project_root)
    try:
        provider = DeepSeekStaticObservationProvider(
            build_vision_transport(), price_snapshot=DEEPSEEK_FLASH_20261004
        )
        context = CancellationContext(
            proposal.run_id, float(proposal.parameters.timeout_seconds + 5)
        )
        return await execute_static_observation_generation(
            proposal=proposal,
            authorization=authorization,
            timeline=timeline,
            ledger=ledger,
            publisher=lambda artifact: _publish(project_root, artifact),
            provider=provider,
            context=context,
            operation="dispatch",
        )
    finally:
        ledger.close()


async def execute_resume_static_observation_generation(
    project: Path, proposal_path: Path, authorization_path: Path
) -> dict[str, object]:
    """Recover only settlement and local publish for an existing attempt; never send."""
    proposal, authorization, project_root = _load_dispatch_inputs(
        project, proposal_path, authorization_path
    )
    timeline = await _timeline(project_root, proposal.run_id)
    ledger = SqliteStaticGenerationLedger(project_root)
    try:
        return await execute_static_observation_generation(
            proposal=proposal,
            authorization=authorization,
            timeline=timeline,
            ledger=ledger,
            publisher=lambda artifact: _publish(project_root, artifact),
            provider=None,
            context=None,
            operation="resume",
        )
    finally:
        ledger.close()
