"""Persistence contracts; no database or filesystem implementation dependencies."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from gamingcreator.application.inputs import AnalysisConfig
from gamingcreator.application.providers import InvocationMetadata
from gamingcreator.domain.media import MediaAsset, MediaPreprocessingResult
from gamingcreator.domain.models import EvidenceReference, SemanticEvent, TranscriptSegment


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class StageStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class InvocationStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    NO_AUDIO = "no_audio"
    NO_SPEECH = "no_speech"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True, slots=True)
class RunConfiguration:
    analysis: AnalysisConfig
    max_cost_cny: Decimal
    pipeline_version: str
    pipeline_hash: str
    required_stages: tuple[str, ...] = ("media", "vision")


@dataclass(frozen=True, slots=True)
class StoredRun:
    run_id: str
    asset: MediaAsset
    configuration: RunConfiguration
    config_hash: str
    status: RunStatus
    error_code: str | None


@dataclass(frozen=True, slots=True)
class StageCheckpoint:
    run_id: str
    stage_id: str
    status: StageStatus
    input_hash: str
    output_hash: str | None
    attempt: int
    error_code: str | None


@dataclass(frozen=True, slots=True)
class StoredInvocation:
    invocation_id: str
    run_id: str
    stage_id: str
    logical_request_id: str
    status: InvocationStatus
    metadata: InvocationMetadata
    error_code: str | None


@dataclass(frozen=True, slots=True)
class StoredTimeline:
    run: StoredRun
    checkpoints: tuple[StageCheckpoint, ...]
    evidence: tuple[EvidenceReference, ...]
    transcripts: tuple[TranscriptSegment, ...]
    events: tuple[SemanticEvent, ...]
    invocations: tuple[StoredInvocation, ...]


@dataclass(frozen=True, slots=True)
class IntegrityIssue:
    run_id: str
    code: str
    path: Path


@dataclass(frozen=True, slots=True)
class RecoveryReport:
    interrupted_runs: tuple[str, ...]
    interrupted_stages: tuple[tuple[str, str], ...]
    interrupted_invocations: tuple[str, ...]
    integrity_issues: tuple[IntegrityIssue, ...]
    orphan_files: tuple[Path, ...]
    temporary_files: tuple[Path, ...]


class TimelineStore(Protocol):
    async def create_run(
        self, run_id: str, asset: MediaAsset, configuration: RunConfiguration
    ) -> StoredRun: ...

    async def load_run(self, run_id: str) -> StoredRun: ...

    async def list_runs(self) -> tuple[tuple[str, str], ...]: ...

    async def load_evidence_reference(
        self, run_id: str, evidence_id: str
    ) -> EvidenceReference | None: ...

    async def load_checkpoints(self, run_id: str) -> tuple[StageCheckpoint, ...]: ...

    async def begin_stage(self, run_id: str, stage_id: str, input_hash: str) -> None: ...

    async def persist_media_bundle(
        self, run_id: str, bundle: MediaPreprocessingResult, stage_id: str = "media"
    ) -> None: ...

    async def load_media_bundle(
        self, run_id: str, stage_id: str = "media"
    ) -> MediaPreprocessingResult: ...

    async def persist_timeline(
        self,
        run_id: str,
        stage_id: str,
        events: tuple[SemanticEvent, ...],
        transcripts: tuple[TranscriptSegment, ...],
        output_hash: str,
    ) -> None: ...

    async def finish_stage(
        self,
        run_id: str,
        stage_id: str,
        status: StageStatus,
        output_hash: str | None = None,
        error_code: str | None = None,
    ) -> None: ...

    async def begin_invocation(
        self,
        invocation_id: str,
        run_id: str,
        stage_id: str,
        logical_request_id: str,
        metadata: InvocationMetadata,
    ) -> None: ...

    async def finish_invocation(
        self,
        invocation_id: str,
        status: InvocationStatus,
        metadata: InvocationMetadata,
        error_code: str | None = None,
    ) -> None: ...

    async def load_invocations(self, run_id: str) -> tuple[StoredInvocation, ...]: ...

    async def complete_run(self, run_id: str) -> None: ...

    async def stop_run(self, run_id: str, status: RunStatus, error_code: str | None) -> None: ...

    async def load_completed_timeline(self, run_id: str) -> StoredTimeline: ...

    async def load_timeline(
        self, run_id: str, *, require_completed: bool = True
    ) -> StoredTimeline: ...

    async def prepare_resume(self, run_id: str) -> None: ...

    async def recover(self) -> RecoveryReport: ...

    async def close(self) -> None: ...
