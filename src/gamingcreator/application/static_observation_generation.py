"""Frozen single-frame static-observation generation proposals and local execution."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal, Protocol, cast

from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004, PriceSnapshot
from gamingcreator.application.providers import (
    CancellationContext,
    InvocationMetadata,
    ProviderResult,
    ProviderStatus,
)
from gamingcreator.application.retrieval import refuse_unsearchable_run
from gamingcreator.application.static_observation_budget import (
    StaticAttemptResult,
    StaticAttemptState,
    StaticGenerationLedger,
)
from gamingcreator.application.static_observations import (
    PublishStatus,
    StaticCollectionArtifact,
    build_static_collection_artifact,
)
from gamingcreator.application.storage import RunStatus, StoredTimeline
from gamingcreator.domain.actor_details import DETAIL_VOCABULARY_VERSION, AttributeKind
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.models import EvidenceReference
from gamingcreator.domain.static_observations import (
    MAX_STATIC_OBSERVATION_ACTORS,
    StaticActor,
    StaticObservation,
    StaticObservationPackage,
    StaticObservationProvenance,
)
from gamingcreator.domain.time import SourceInstant

STATIC_GENERATION_PROFILE = "static-frame-profile-v2"
STATIC_GENERATION_PROPOSAL_SCHEMA_VERSION = "static-observation-generation-proposal-v1"
STATIC_GENERATION_AUTHORIZATION_SCHEMA_VERSION = "static-observation-generation-authorization-v1"
STATIC_GENERATION_RESULT_SCHEMA_VERSION = "static-observation-generation-result-v1"
STATIC_GENERATION_PREPARE_SCHEMA_VERSION = "static-observation-generation-prepare-v1"
STATIC_GENERATION_SCHEMA_VERSION = "static-observation-generation-schema-v2"
STATIC_GENERATION_PROMPT_VERSION = "static-frame-observation-prompt-v2"
STATIC_GENERATION_PROVIDER = "deepseek"
STATIC_GENERATION_MODEL = "deepseek-flash"
STATIC_GENERATION_VOCABULARY_VERSION = DETAIL_VOCABULARY_VERSION
STATIC_GENERATION_CLAIM = "generated_static_draft_only_not_visually_verified"
STATIC_GENERATION_DECLARATION = "human_declared_local_authorization_not_cryptographic"
MAX_STATIC_GENERATION_PROPOSAL_BYTES = 65_536
MAX_STATIC_GENERATION_AUTHORIZATION_BYTES = 65_536
MAX_STATIC_GENERATION_RESPONSE_CONTENT_BYTES = 65_536
MAX_FRAME_PARTS_PER_ACTOR = 7
MAX_FRAME_PARTS_PER_GROUP = {"hair": 1, "clothing": 3, "held": 3}
STATIC_PART_GROUP_KINDS: dict[str, frozenset[AttributeKind]] = {
    "hair": frozenset({AttributeKind.HAIR_COLOR}),
    "clothing": frozenset({AttributeKind.CLOTHING_COLOR, AttributeKind.CLOTHING_SHAPE}),
    "held": frozenset({AttributeKind.HELD_SHAPE, AttributeKind.HELD_CLASS}),
}
GENERATED_ATTRIBUTE_KINDS: tuple[AttributeKind, ...] = (
    AttributeKind.HAIR_COLOR,
    AttributeKind.CLOTHING_COLOR,
    AttributeKind.CLOTHING_SHAPE,
    AttributeKind.HELD_SHAPE,
    AttributeKind.HELD_CLASS,
)
MAX_AUTHORIZATION_COST_CNY = Decimal("10")
MAX_HUMAN_AUTHORIZATION_REF = 500
LEDGER_DIRECTORY_NAME = ".static-observation-generation"
LEDGER_SUBDIRECTORY_NAME = "ledger"
TIMELINE_FILE_NAME = "timeline.sqlite3"

STATIC_GENERATION_PROMPT = """Observe exactly one supplied registered game frame.
Return one JSON object with exactly the key actors and no other keys.
actors is an array of at most 8 objects; each object has exactly actorIndex and parts.
actorIndex is a distinct integer from 1 to 8 assigned by left-to-right visible order.
parts is a nonempty array of at most 7 objects; each object has exactly partGroup,
partIndex, and attributes.
partGroup is exactly one of hair, clothing, held.
hair has at most 1 part: partIndex 1 and only the attribute hair_color.
clothing has at most 3 parts: distinct partIndex 1 to 3 and only clothing_color
and/or clothing_shape.
held has at most 3 parts: distinct partIndex 1 to 3 and only held_shape and/or
held_class.
attributes is a nonempty object using only the kinds allowed for that partGroup.
Each value is exactly one lowercase string from this frozen vocabulary:
hair_color and clothing_color: white, black, red, blue, brown, orange, gray, green, yellow,
purple, light, dark.
clothing_shape: upper_garment, coat, scarf, shorts, trousers, armor, gloves.
held_shape: flat_object, blue_flat_object, long_rod, curved_object.
held_class: weapon, staff, tool; a shape alone never establishes a class.
Use one clothing part per distinct visible garment; never merge two garments.
Use one held part per distinct visible held object; never merge two held objects.
Never move a value between parts and never repeat a partGroup and partIndex in one actor.
Omit every part you cannot see; never guess from game context.
Do not report actor names, actions, effects, environment, source time, frame IDs, run IDs,
paths, or any other field, and never describe another frame.
If no person is visible, return {"actors":[]}. Return JSON only, with no prose.
"""

STATIC_GENERATION_PROMPT_HASH = hashlib.sha256(STATIC_GENERATION_PROMPT.encode("utf-8")).hexdigest()

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]{0,6})(?:\.[0-9]{1,8})?\Z")
_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|\+00:00)\Z"
)
_DIAGNOSTIC = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
_EVIDENCE_IMAGE = re.compile(r".+:image:[0-9]{6}\Z")


def _error(code: str, message: str, exit_code: ExitCode) -> AppError:
    return AppError(code, message, exit_code)


def _input_error(message: str) -> AppError:
    return _error("static_generation.input", message, ExitCode.INPUT)


def _identity_error() -> AppError:
    return _error(
        "static_generation.identity",
        "生成提案与当前已完成任务、注册证据、文件或版本不一致。",
        ExitCode.INPUT,
    )


def _authorization_error(code: str, message: str) -> AppError:
    return _error(code, message, ExitCode.BUDGET)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def decimal_text(value: Decimal) -> str:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError("Static generation amounts must be finite nonnegative decimals.")
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "0E-8") else text


def _decimal(value: object, label: str, *, positive: bool = False) -> Decimal:
    if type(value) is not str or not _DECIMAL.fullmatch(value):
        raise _input_error(f"静态生成{label}金额格式无效。")
    try:
        amount = Decimal(value)
    except InvalidOperation:
        raise _input_error(f"静态生成{label}金额格式无效。") from None
    if not amount.is_finite() or amount < 0 or (positive and amount == 0):
        raise _input_error(f"静态生成{label}金额超出允许范围。")
    if decimal_text(amount) != value:
        raise _input_error(f"静态生成{label}金额不是规范小数文本。")
    return amount


def _hash_text(value: object, label: str) -> str:
    if type(value) is not str or not _HASH.fullmatch(value):
        raise _input_error(f"静态生成{label} SHA-256 无效。")
    return value


def _identifier(value: object, label: str) -> str:
    if type(value) is not str or not _IDENTIFIER.fullmatch(value):
        raise _input_error(f"静态生成{label}标识无效。")
    return value


def _integer(value: object, label: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise _input_error(f"静态生成{label}整数超出允许范围。")
    return value


def _timestamp(value: object, label: str) -> str:
    if type(value) is not str or not _TIMESTAMP.fullmatch(value):
        raise _input_error(f"静态生成{label}时间文本无效。")
    return value


def _absolute_path(value: object, label: str) -> str:
    if type(value) is not str or not value or "\x00" in value:
        raise _input_error(f"静态生成{label}路径无效。")
    path = Path(value)
    if not path.is_absolute() or str(path) != value:
        raise _input_error(f"静态生成{label}路径必须是规范绝对路径。")
    return value


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise _input_error("静态生成 JSON 包含重复字段。")
        result[key] = value
    return result


def _invalid_constant(value: str) -> object:
    del value
    raise _input_error("静态生成 JSON 不允许非有限数字。")


def _decode_document(data: bytes, limit: int) -> dict[str, object]:
    if type(data) is not bytes or not data or len(data) > limit:
        raise _input_error("静态生成文件为空或超过有界大小。")
    if data.startswith(b"\xef\xbb\xbf"):
        raise _input_error("静态生成文件必须是无 BOM 的 UTF-8 JSON。")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise _input_error("静态生成文件不是有效 UTF-8。") from None
    try:
        decoded: object = json.loads(
            text, object_pairs_hook=_pairs, parse_constant=_invalid_constant
        )
    except (json.JSONDecodeError, RecursionError):
        raise _input_error("静态生成文件不是有效有界 JSON。") from None
    if type(decoded) is not dict:
        raise _input_error("静态生成文件必须是 JSON 对象。")
    return cast(dict[str, object], decoded)


def _object(
    value: object,
    fields: frozenset[str],
    label: str,
    *,
    optional: frozenset[str] = frozenset(),
) -> dict[str, object]:
    if type(value) is not dict:
        raise _input_error(f"静态生成{label}必须是 JSON 对象。")
    result = cast(dict[str, object], value)
    keys = set(result)
    if not fields <= keys or keys - fields - optional:
        raise _input_error(f"静态生成{label}字段缺失或多余。")
    return result


def _array(value: object, label: str, maximum: int, *, minimum: int = 0) -> list[object]:
    if type(value) is not list:
        raise _input_error(f"静态生成{label}必须是 JSON 数组。")
    result = cast(list[object], value)
    if not minimum <= len(result) <= maximum:
        raise _input_error(f"静态生成{label}超出有界数量。")
    return result


def _file_sha256(path: Path, maximum: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > maximum:
                    raise _identity_error()
                digest.update(chunk)
    except OSError:
        raise _identity_error() from None
    return digest.hexdigest(), size


def _plain_directory(path: Path, label: str) -> Path:
    try:
        if path.is_symlink() or path.is_junction():
            raise _input_error(f"静态生成{label}不能是符号链接或目录联接。")
        resolved = path.resolve()
    except OSError:
        raise _input_error(f"无法解析静态生成{label}。") from None
    if not resolved.is_dir():
        raise _input_error(f"静态生成{label}必须是已存在的目录。")
    return resolved


def _plain_database(path: Path) -> Path:
    try:
        if path.is_symlink() or path.is_junction() or not path.is_file():
            raise _input_error("静态生成数据库必须是普通文件。")
        stat = path.lstat()
    except OSError:
        raise _input_error("无法核对静态生成数据库文件。") from None
    if stat.st_nlink != 1:
        raise _input_error("静态生成数据库不能是硬链接。")
    return path.resolve()


def generation_paths(project: Path) -> tuple[Path, Path, Path]:
    """Return canonical project, timeline database, and fixed ledger root paths."""
    project_root = _plain_directory(project, "项目目录")
    database = _plain_database(project_root / TIMELINE_FILE_NAME)
    if database.parent != project_root:
        raise _input_error("静态生成数据库必须位于项目根目录。")
    ledger_root = project_root / LEDGER_DIRECTORY_NAME / LEDGER_SUBDIRECTORY_NAME
    candidate = project_root
    for part in (LEDGER_DIRECTORY_NAME, LEDGER_SUBDIRECTORY_NAME):
        candidate = candidate / part
        try:
            if candidate.is_symlink() or candidate.is_junction():
                raise _input_error("静态生成账本根不能是符号链接或目录联接。")
        except OSError:
            raise _input_error("无法核对静态生成账本根。") from None
    return project_root, database, ledger_root.resolve()


@dataclass(frozen=True, slots=True)
class StaticGenerationParameters:
    max_output_tokens: int = 2_000
    max_input_token_ceiling: int = 200_000
    max_image_bytes: int = 4_194_304
    image_detail: str = "high"
    timeout_seconds: int = 60
    max_requests: int = 1
    max_input_frames: int = 1

    def __post_init__(self) -> None:
        _integer(self.max_output_tokens, "maxOutputTokens", 1, 65_536)
        _integer(self.max_input_token_ceiling, "maxInputTokenCeiling", 1, 1_000_000)
        _integer(self.max_image_bytes, "maxImageBytes", 1, 16_777_216)
        if self.image_detail not in ("low", "high"):
            raise _input_error("静态生成 imageDetail 只能是 low 或 high。")
        _integer(self.timeout_seconds, "timeoutSeconds", 1, 600)
        if self.max_requests != 1:
            raise _authorization_error(
                "static_generation.authorization_limit", "静态生成授权必须限定 maxRequests=1。"
            )
        if self.max_input_frames != 1:
            raise _authorization_error(
                "static_generation.authorization_limit",
                "静态生成授权必须限定 maxInputFrames=1。",
            )


def _parameters_document(parameters: StaticGenerationParameters) -> dict[str, object]:
    return {
        "maxOutputTokens": parameters.max_output_tokens,
        "maxInputTokenCeiling": parameters.max_input_token_ceiling,
        "maxImageBytes": parameters.max_image_bytes,
        "imageDetail": parameters.image_detail,
        "timeoutSeconds": parameters.timeout_seconds,
        "maxRequests": parameters.max_requests,
        "maxInputFrames": parameters.max_input_frames,
    }


def _load_parameters(value: object) -> StaticGenerationParameters:
    fields = frozenset(_parameters_document(StaticGenerationParameters()))
    item = _object(value, fields, "参数")
    return StaticGenerationParameters(
        _integer(item["maxOutputTokens"], "maxOutputTokens", 1, 65_536),
        _integer(item["maxInputTokenCeiling"], "maxInputTokenCeiling", 1, 1_000_000),
        _integer(item["maxImageBytes"], "maxImageBytes", 1, 16_777_216),
        cast(str, item["imageDetail"]),
        _integer(item["timeoutSeconds"], "timeoutSeconds", 1, 600),
        _integer(item["maxRequests"], "maxRequests", 1, 1),
        _integer(item["maxInputFrames"], "maxInputFrames", 1, 1),
    )


@dataclass(frozen=True, slots=True)
class StaticGenerationIdentity:
    provider: str
    model: str
    prompt_version: str
    prompt_hash: str
    schema_version: str
    vocabulary_version: str

    def __post_init__(self) -> None:
        expected = (
            (self.provider, STATIC_GENERATION_PROVIDER),
            (self.model, STATIC_GENERATION_MODEL),
            (self.prompt_version, STATIC_GENERATION_PROMPT_VERSION),
            (self.prompt_hash, STATIC_GENERATION_PROMPT_HASH),
            (self.schema_version, STATIC_GENERATION_SCHEMA_VERSION),
            (self.vocabulary_version, STATIC_GENERATION_VOCABULARY_VERSION),
        )
        if any(value != expected_value for value, expected_value in expected):
            raise _identity_error()


def static_generation_identity() -> StaticGenerationIdentity:
    return StaticGenerationIdentity(
        STATIC_GENERATION_PROVIDER,
        STATIC_GENERATION_MODEL,
        STATIC_GENERATION_PROMPT_VERSION,
        STATIC_GENERATION_PROMPT_HASH,
        STATIC_GENERATION_SCHEMA_VERSION,
        STATIC_GENERATION_VOCABULARY_VERSION,
    )


def generation_reservation_cny(
    parameters: StaticGenerationParameters,
    price_snapshot: PriceSnapshot = DEEPSEEK_FLASH_20261004,
) -> Decimal:
    return price_snapshot.reservation_cny(
        parameters.max_input_token_ceiling, parameters.max_output_tokens
    )


@dataclass(frozen=True, slots=True)
class StaticGenerationProposal:
    project_root: str
    database_path: str
    ledger_root: str
    run_id: str
    collection_id: str
    profile: str
    media_id: str
    source_path: str
    source_sha256: str
    config_hash: str
    pipeline_version: str
    pipeline_hash: str
    evidence_id: str
    image_path: str
    image_sha256: str
    image_bytes: int
    source_time_us: int
    duration_us: int
    identity: StaticGenerationIdentity
    parameters: StaticGenerationParameters
    currency: str
    reservation_cny: Decimal
    price_version: str
    price_model_version: str
    proposal_sha256: str

    def __post_init__(self) -> None:
        for value, label in (
            (self.project_root, "项目根"),
            (self.database_path, "数据库"),
            (self.ledger_root, "账本根"),
            (self.source_path, "源路径"),
            (self.image_path, "图片路径"),
        ):
            _absolute_path(value, label)
        _identifier(self.run_id, "run")
        _identifier(self.collection_id, "collection")
        if self.profile != STATIC_GENERATION_PROFILE:
            raise _identity_error()
        _identifier(self.media_id, "media")
        _hash_text(self.source_sha256, "源")
        _hash_text(self.config_hash, "配置")
        _identifier(self.pipeline_version, "pipeline 版本")
        _hash_text(self.pipeline_hash, "pipeline")
        if (
            type(self.evidence_id) is not str
            or not _EVIDENCE_IMAGE.fullmatch(self.evidence_id)
            or not self.evidence_id.startswith(f"{self.run_id}:{self.media_id}:image:")
        ):
            raise _identity_error()
        _hash_text(self.image_sha256, "注册图片")
        _integer(self.image_bytes, "注册图片字节数", 1, self.parameters.max_image_bytes)
        _integer(self.source_time_us, "源时钟", 0, 2**63 - 1)
        _integer(self.duration_us, "源时长", 1, 2**63 - 1)
        if self.source_time_us >= self.duration_us:
            raise _identity_error()
        if type(self.identity) is not StaticGenerationIdentity:
            raise _identity_error()
        if type(self.parameters) is not StaticGenerationParameters:
            raise _input_error("静态生成参数必须是 typed 参数。")
        if self.currency != "CNY":
            raise _input_error("静态生成货币必须是 CNY。")
        reservation = _decimal(str(self.reservation_cny), "预留", positive=True)
        if reservation != self.reservation_cny:
            raise _input_error("静态生成预留金额无效。")
        if self.price_version != DEEPSEEK_FLASH_20261004.version:
            raise _identity_error()
        if self.price_model_version != DEEPSEEK_FLASH_20261004.model_version:
            raise _identity_error()
        _hash_text(self.proposal_sha256, "提案")


@dataclass(frozen=True, slots=True)
class StaticGenerationAuthorization:
    authorization_id: str
    proposal_sha256: str
    project_root: str
    database_path: str
    ledger_root: str
    identity: StaticGenerationIdentity
    parameters: StaticGenerationParameters
    currency: str
    max_cost_cny: Decimal
    max_requests: int
    max_input_frames: int
    human_authorization_ref: str
    allow_model: bool
    declaration: str
    authorization_sha256: str

    def __post_init__(self) -> None:
        _identifier(self.authorization_id, "授权")
        _hash_text(self.proposal_sha256, "提案")
        for value, label in (
            (self.project_root, "项目根"),
            (self.database_path, "数据库"),
            (self.ledger_root, "账本根"),
        ):
            _absolute_path(value, label)
        if type(self.identity) is not StaticGenerationIdentity:
            raise _input_error("静态生成授权必须先冻结提供方身份。")
        if type(self.parameters) is not StaticGenerationParameters:
            raise _input_error("静态生成授权必须先冻结参数。")
        if self.currency != "CNY":
            raise _authorization_error(
                "static_generation.authorization_limit", "静态生成授权货币必须是 CNY。"
            )
        amount = _decimal(str(self.max_cost_cny), "授权上限", positive=True)
        if amount != self.max_cost_cny or amount > MAX_AUTHORIZATION_COST_CNY:
            raise _authorization_error(
                "static_generation.authorization_limit", "静态生成授权金额上限无效。"
            )
        if self.max_requests != 1 or self.max_input_frames != 1:
            raise _authorization_error(
                "static_generation.authorization_limit",
                "静态生成授权必须固定 maxRequests=1 与 maxInputFrames=1。",
            )
        if not self.allow_model:
            raise _authorization_error(
                "static_generation.authorization_not_allowed",
                "人类授权文件没有显式 allow-model。",
            )
        if self.declaration != STATIC_GENERATION_DECLARATION:
            raise _authorization_error(
                "static_generation.authorization_not_allowed",
                "人类授权声明文本不受支持。",
            )
        if (
            type(self.human_authorization_ref) is not str
            or not self.human_authorization_ref.strip()
            or len(self.human_authorization_ref) > MAX_HUMAN_AUTHORIZATION_REF
        ):
            raise _authorization_error(
                "static_generation.authorization_not_allowed",
                "人类授权文件必须包含有界的人类授权引用。",
            )
        _hash_text(self.authorization_sha256, "授权内容")


def _identity_document(identity: StaticGenerationIdentity) -> dict[str, object]:
    return {
        "provider": identity.provider,
        "model": identity.model,
        "promptVersion": identity.prompt_version,
        "promptHash": identity.prompt_hash,
        "generationSchemaVersion": identity.schema_version,
        "vocabularyVersion": identity.vocabulary_version,
    }


def _load_identity(item: dict[str, object]) -> StaticGenerationIdentity:
    return StaticGenerationIdentity(
        cast(str, item["provider"]),
        cast(str, item["model"]),
        cast(str, item["promptVersion"]),
        _hash_text(item["promptHash"], "prompt"),
        cast(str, item["generationSchemaVersion"]),
        cast(str, item["vocabularyVersion"]),
    )


def _proposal_document(proposal: StaticGenerationProposal) -> dict[str, object]:
    return {
        "schemaVersion": STATIC_GENERATION_PROPOSAL_SCHEMA_VERSION,
        "projectRoot": proposal.project_root,
        "databasePath": proposal.database_path,
        "ledgerRoot": proposal.ledger_root,
        "runId": proposal.run_id,
        "collectionId": proposal.collection_id,
        "profile": proposal.profile,
        "mediaId": proposal.media_id,
        "sourcePath": proposal.source_path,
        "sourceSha256": proposal.source_sha256,
        "configHash": proposal.config_hash,
        "pipelineVersion": proposal.pipeline_version,
        "pipelineHash": proposal.pipeline_hash,
        "evidenceId": proposal.evidence_id,
        "imagePath": proposal.image_path,
        "imageSha256": proposal.image_sha256,
        "imageBytes": proposal.image_bytes,
        "sourceTimeUs": proposal.source_time_us,
        "durationUs": proposal.duration_us,
        **_identity_document(proposal.identity),
        "parameters": _parameters_document(proposal.parameters),
        "currency": proposal.currency,
        "reservationCny": decimal_text(proposal.reservation_cny),
        "priceVersion": proposal.price_version,
        "priceModelVersion": proposal.price_model_version,
    }


def canonical_proposal_json(proposal: StaticGenerationProposal) -> str:
    return _canonical_json(_proposal_document(proposal))


def proposal_sha256(proposal: StaticGenerationProposal) -> str:
    return hashlib.sha256(canonical_proposal_json(proposal).encode("utf-8")).hexdigest()


def proposal_file_bytes(proposal: StaticGenerationProposal) -> bytes:
    document = _proposal_document(proposal)
    document["proposalSha256"] = proposal.proposal_sha256
    return _canonical_json(document).encode("utf-8")


def _placeholder_path(*parts: str) -> str:
    root = Path("C:/placeholder") if os.name == "nt" else Path("/placeholder")
    return str(root.joinpath(*parts))


def _placeholder_proposal() -> StaticGenerationProposal:
    identity = static_generation_identity()
    parameters = StaticGenerationParameters()
    reservation = generation_reservation_cny(parameters)
    return StaticGenerationProposal(
        _placeholder_path("project"),
        _placeholder_path("project", TIMELINE_FILE_NAME),
        _placeholder_path("project", LEDGER_DIRECTORY_NAME, LEDGER_SUBDIRECTORY_NAME),
        "run-1",
        "look-1",
        STATIC_GENERATION_PROFILE,
        "media-1",
        _placeholder_path("project", "source.fixture"),
        "0" * 64,
        "0" * 64,
        "pipeline-v1",
        "0" * 64,
        "run-1:media-1:image:000000",
        _placeholder_path("project", "frame-0.png"),
        "0" * 64,
        1,
        0,
        1,
        identity,
        parameters,
        "CNY",
        reservation,
        DEEPSEEK_FLASH_20261004.version,
        DEEPSEEK_FLASH_20261004.model_version,
        "0" * 64,
    )


def loads_static_generation_proposal(data: bytes) -> StaticGenerationProposal:
    base_fields = frozenset(_proposal_document(_placeholder_proposal()))
    document = _decode_document(data, MAX_STATIC_GENERATION_PROPOSAL_BYTES)
    item = _object(document, base_fields | {"proposalSha256"}, "提案")
    stored_hash = _hash_text(item["proposalSha256"], "提案")
    proposal = StaticGenerationProposal(
        cast(str, item["projectRoot"]),
        cast(str, item["databasePath"]),
        cast(str, item["ledgerRoot"]),
        cast(str, item["runId"]),
        cast(str, item["collectionId"]),
        cast(str, item["profile"]),
        cast(str, item["mediaId"]),
        cast(str, item["sourcePath"]),
        _hash_text(item["sourceSha256"], "源"),
        _hash_text(item["configHash"], "配置"),
        cast(str, item["pipelineVersion"]),
        _hash_text(item["pipelineHash"], "pipeline"),
        cast(str, item["evidenceId"]),
        cast(str, item["imagePath"]),
        _hash_text(item["imageSha256"], "注册图片"),
        _integer(item["imageBytes"], "注册图片字节数", 1, 16_777_216),
        _integer(item["sourceTimeUs"], "源时钟", 0, 2**63 - 1),
        _integer(item["durationUs"], "源时长", 1, 2**63 - 1),
        _load_identity(item),
        _load_parameters(item["parameters"]),
        cast(str, item["currency"]),
        _decimal(item["reservationCny"], "预留", positive=True),
        cast(str, item["priceVersion"]),
        cast(str, item["priceModelVersion"]),
        stored_hash,
    )
    if proposal_sha256(proposal) != stored_hash:
        raise _input_error("静态生成提案内容与冻结哈希不一致。")
    return proposal


def _authorization_document(
    authorization: StaticGenerationAuthorization,
) -> dict[str, object]:
    return {
        "schemaVersion": STATIC_GENERATION_AUTHORIZATION_SCHEMA_VERSION,
        "authorizationId": authorization.authorization_id,
        "proposalHash": authorization.proposal_sha256,
        "projectRoot": authorization.project_root,
        "databasePath": authorization.database_path,
        "ledgerRoot": authorization.ledger_root,
        **_identity_document(authorization.identity),
        "parameters": _parameters_document(authorization.parameters),
        "currency": authorization.currency,
        "maxCostCny": decimal_text(authorization.max_cost_cny),
        "maxRequests": authorization.max_requests,
        "maxInputFrames": authorization.max_input_frames,
        "humanAuthorizationRef": authorization.human_authorization_ref,
        "allowModel": authorization.allow_model,
        "declaration": authorization.declaration,
    }


def canonical_authorization_json(authorization: StaticGenerationAuthorization) -> str:
    return _canonical_json(_authorization_document(authorization))


def authorization_sha256(authorization: StaticGenerationAuthorization) -> str:
    return hashlib.sha256(canonical_authorization_json(authorization).encode("utf-8")).hexdigest()


def authorization_file_bytes(authorization: StaticGenerationAuthorization) -> bytes:
    document = _authorization_document(authorization)
    document["authorizationSha256"] = authorization.authorization_sha256
    return _canonical_json(document).encode("utf-8")


def _placeholder_authorization() -> StaticGenerationAuthorization:
    proposal = _placeholder_proposal()
    return StaticGenerationAuthorization(
        "authorization-1",
        proposal.proposal_sha256,
        proposal.project_root,
        proposal.database_path,
        proposal.ledger_root,
        proposal.identity,
        proposal.parameters,
        "CNY",
        Decimal("0.5"),
        1,
        1,
        "placeholder human authorization reference",
        True,
        STATIC_GENERATION_DECLARATION,
        "0" * 64,
    )


def loads_static_generation_authorization(data: bytes) -> StaticGenerationAuthorization:
    base_fields = frozenset(_authorization_document(_placeholder_authorization()))
    document = _decode_document(data, MAX_STATIC_GENERATION_AUTHORIZATION_BYTES)
    item = _object(document, base_fields | {"authorizationSha256"}, "人类授权")
    stored_hash = _hash_text(item["authorizationSha256"], "授权内容")
    authorization = StaticGenerationAuthorization(
        cast(str, item["authorizationId"]),
        _hash_text(item["proposalHash"], "提案"),
        cast(str, item["projectRoot"]),
        cast(str, item["databasePath"]),
        cast(str, item["ledgerRoot"]),
        _load_identity(item),
        _load_parameters(item["parameters"]),
        cast(str, item["currency"]),
        _decimal(item["maxCostCny"], "授权上限", positive=True),
        _integer(item["maxRequests"], "maxRequests", 1, 1),
        _integer(item["maxInputFrames"], "maxInputFrames", 1, 1),
        cast(str, item["humanAuthorizationRef"]),
        item["allowModel"] is True,
        cast(str, item["declaration"]),
        stored_hash,
    )
    if authorization_sha256(authorization) != stored_hash:
        raise _authorization_error(
            "static_generation.authorization_hash", "人类授权内容与冻结哈希不一致。"
        )
    return authorization


def verify_authorization_against_proposal(
    proposal: StaticGenerationProposal, authorization: StaticGenerationAuthorization
) -> None:
    """Validate a human declaration as data; this never proves a human wrote it."""
    if authorization.proposal_sha256 != proposal.proposal_sha256:
        raise _authorization_error(
            "static_generation.authorization_mismatch", "人类授权绑定了另一份冻结提案。"
        )
    if (
        authorization.project_root != proposal.project_root
        or authorization.database_path != proposal.database_path
        or authorization.ledger_root != proposal.ledger_root
    ):
        raise _authorization_error(
            "static_generation.authorization_scope",
            "人类授权的项目、数据库或固定账本根与提案不一致。",
        )
    if authorization.identity != proposal.identity:
        raise _authorization_error(
            "static_generation.authorization_mismatch", "人类授权的提供方身份与提案不一致。"
        )
    if authorization.parameters != proposal.parameters:
        raise _authorization_error(
            "static_generation.authorization_mismatch", "人类授权的调用参数与提案不一致。"
        )
    if authorization.currency != proposal.currency:
        raise _authorization_error(
            "static_generation.authorization_mismatch", "人类授权货币与提案不一致。"
        )
    if authorization.max_cost_cny < proposal.reservation_cny:
        raise _authorization_error(
            "static_generation.authorization_limit", "人类授权金额上限低于保守预留。"
        )


@dataclass(frozen=True, slots=True)
class VerifiedGenerationFrame:
    evidence: EvidenceReference
    instant: SourceInstant


def verify_proposal_against_timeline(
    proposal: StaticGenerationProposal, timeline: StoredTimeline
) -> VerifiedGenerationFrame:
    """Recheck current Completed/coverage eligibility and the exact registered frame."""
    run = timeline.run
    refuse_unsearchable_run(run)
    if run.status is not RunStatus.COMPLETED:
        raise _identity_error()
    if generation_reservation_cny(proposal.parameters) != proposal.reservation_cny:
        raise _identity_error()
    if (
        proposal.run_id != run.run_id
        or proposal.media_id != run.asset.media_id
        or proposal.source_path != str(run.asset.source_path)
        or proposal.source_sha256 != run.asset.sha256
        or proposal.duration_us != run.asset.duration_us
        or proposal.config_hash != run.config_hash
        or proposal.pipeline_version != run.configuration.pipeline_version
        or proposal.pipeline_hash != run.configuration.pipeline_hash
    ):
        raise _identity_error()
    try:
        if not run.asset.source_path.is_file():
            raise _identity_error()
    except OSError:
        raise _identity_error() from None
    matches = tuple(
        evidence for evidence in timeline.evidence if evidence.evidence_id == proposal.evidence_id
    )
    if len(matches) != 1:
        raise _identity_error()
    evidence = matches[0]
    if (
        evidence.kind != "image"
        or type(evidence.source_time) is not SourceInstant
        or evidence.media_id != proposal.media_id
        or evidence.source_time.time_us != proposal.source_time_us
        or evidence.source_time.duration_us != proposal.duration_us
        or evidence.sha256 != proposal.image_sha256
        or str(evidence.artifact_path) != proposal.image_path
        or not proposal.evidence_id.startswith(f"{proposal.run_id}:{proposal.media_id}:image:")
    ):
        raise _identity_error()
    try:
        if evidence.artifact_path.is_symlink() or not evidence.artifact_path.is_file():
            raise _identity_error()
    except OSError:
        raise _identity_error() from None
    digest, size = _file_sha256(evidence.artifact_path, proposal.parameters.max_image_bytes)
    if digest != proposal.image_sha256 or size != proposal.image_bytes:
        raise _identity_error()
    return VerifiedGenerationFrame(evidence, evidence.source_time)


@dataclass(frozen=True, slots=True)
class StaticObservationRequest:
    run_id: str
    collection_id: str
    proposal_sha256: str
    evidence: EvidenceReference
    image_path: Path
    identity: StaticGenerationIdentity
    parameters: StaticGenerationParameters

    def __post_init__(self) -> None:
        if self.evidence.kind != "image" or type(self.evidence.source_time) is not SourceInstant:
            raise ValueError("Static observation request needs one registered image frame.")
        if self.identity != static_generation_identity():
            raise ValueError("Unsupported static observation provider identity.")
        _hash_text(self.proposal_sha256, "提案")


@dataclass(frozen=True, slots=True)
class StaticObservationOutput:
    actors: tuple[StaticActor, ...]

    def __post_init__(self) -> None:
        if type(self.actors) is not tuple or len(self.actors) > MAX_STATIC_OBSERVATION_ACTORS:
            raise ValueError("Static observation actors are not bounded.")
        if any(type(actor) is not StaticActor for actor in self.actors):
            raise ValueError("Static observation output requires typed actors.")
        if len({actor.actor_id for actor in self.actors}) != len(self.actors):
            raise ValueError("Static observation output actors must be unique.")


class StaticObservationProvider(Protocol):
    async def observe(
        self, request: StaticObservationRequest, context: CancellationContext
    ) -> ProviderResult[StaticObservationOutput]: ...


def build_static_generation_proposal(
    project: Path,
    timeline: StoredTimeline,
    *,
    run_id: str,
    collection_id: str,
    evidence_id: str,
    parameters: StaticGenerationParameters | None = None,
    price_snapshot: PriceSnapshot = DEEPSEEK_FLASH_20261004,
) -> StaticGenerationProposal:
    """Freeze one explicit Completed registered image frame; no provider or network."""
    project_root, database, ledger_root = generation_paths(project)
    _identifier(run_id, "run")
    _identifier(collection_id, "collection")
    if run_id != timeline.run.run_id:
        raise _identity_error()
    settings = parameters if parameters is not None else StaticGenerationParameters()
    reservation = generation_reservation_cny(settings, price_snapshot)
    proposal = _draft_proposal(
        project_root,
        database,
        ledger_root,
        timeline,
        run_id,
        collection_id,
        evidence_id,
        settings,
        reservation,
        price_snapshot,
    )
    frozen = replace(proposal, proposal_sha256=proposal_sha256(proposal))
    verify_proposal_against_timeline(frozen, timeline)
    return frozen


def _draft_proposal(
    project_root: Path,
    database: Path,
    ledger_root: Path,
    timeline: StoredTimeline,
    run_id: str,
    collection_id: str,
    evidence_id: str,
    parameters: StaticGenerationParameters,
    reservation: Decimal,
    price_snapshot: PriceSnapshot,
) -> StaticGenerationProposal:
    evidence = tuple(item for item in timeline.evidence if item.evidence_id == evidence_id)
    if len(evidence) != 1:
        raise _identity_error()
    frame = evidence[0]
    if frame.kind != "image" or type(frame.source_time) is not SourceInstant:
        raise _identity_error()
    digest, size = _file_sha256(frame.artifact_path, parameters.max_image_bytes)
    if digest != frame.sha256:
        raise _identity_error()
    if size > parameters.max_image_bytes:
        raise _input_error("注册图片超过冻结的字节上限。")
    return StaticGenerationProposal(
        str(project_root),
        str(database),
        str(ledger_root),
        run_id,
        collection_id,
        STATIC_GENERATION_PROFILE,
        timeline.run.asset.media_id,
        str(timeline.run.asset.source_path),
        timeline.run.asset.sha256,
        timeline.run.config_hash,
        timeline.run.configuration.pipeline_version,
        timeline.run.configuration.pipeline_hash,
        evidence_id,
        str(frame.artifact_path),
        frame.sha256,
        size,
        frame.source_time.time_us,
        timeline.run.asset.duration_us,
        static_generation_identity(),
        parameters,
        "CNY",
        reservation,
        price_snapshot.version,
        price_snapshot.model_version,
        "0" * 64,
    )


def static_observation_request(
    proposal: StaticGenerationProposal, frame: VerifiedGenerationFrame
) -> StaticObservationRequest:
    return StaticObservationRequest(
        proposal.run_id,
        proposal.collection_id,
        proposal.proposal_sha256,
        frame.evidence,
        Path(proposal.image_path),
        proposal.identity,
        proposal.parameters,
    )


def _execution_detail(metadata: InvocationMetadata) -> dict[str, object]:
    if metadata.execution_details is None:
        return {}
    try:
        value = json.loads(metadata.execution_details)
    except (json.JSONDecodeError, RecursionError):
        return {}
    return cast(dict[str, object], value) if type(value) is dict else {}


def _provider_request_attempted(metadata: InvocationMetadata) -> bool:
    return _execution_detail(metadata).get("dispatchAttempted") is True


def attempt_result_from_provider(
    result: ProviderResult[StaticObservationOutput], *, recorded_at: str
) -> StaticAttemptResult:
    """Persist only typed output, real invocation metadata, and whitelisted digests."""
    details = _execution_detail(result.metadata)
    response_hash = details.get("responseSha256")
    response_sha256 = response_hash if type(response_hash) is str else None
    if response_sha256 is not None and not _HASH.fullmatch(response_sha256):
        response_sha256 = None
    response_bytes = details.get("responseBytes")
    content_bytes = details.get("contentBytes")
    http_status = details.get("httpStatus")
    if result.status is ProviderStatus.COMPLETED:
        if result.output is None or response_sha256 is None:
            raise _error(
                "static_generation.metadata",
                "提供方结果缺少可持久化的响应摘要。",
                ExitCode.PROVIDER,
            )
        status: Literal["observed", "no_observations", "failed", "cancelled"] = (
            "no_observations" if not result.output.actors else "observed"
        )
        actors = result.output.actors
    else:
        status = "cancelled" if result.status is ProviderStatus.CANCELLED else "failed"
        actors = ()
    diagnostics = () if result.error is None else (result.error.code,)
    if any(not _DIAGNOSTIC.fullmatch(item) for item in diagnostics):
        raise _error("static_generation.metadata", "提供方诊断码不在白名单内。", ExitCode.PROVIDER)
    return StaticAttemptResult(
        status,
        actors,
        result.metadata,
        response_sha256,
        response_bytes if type(response_bytes) is int and response_bytes >= 0 else 0,
        content_bytes if type(content_bytes) is int and content_bytes >= 0 else None,
        http_status if type(http_status) is int and 100 <= http_status <= 599 else None,
        diagnostics,
        recorded_at,
    )


def _provenance(result: StaticAttemptResult) -> StaticObservationProvenance:
    if result.response_sha256 is None:
        raise _identity_error()
    return StaticObservationProvenance(
        "自动静态草案：仅由单张已注册Completed帧生成五类冻结静态属性；"
        "真实外观未独立验证，不是人评或验收结论。",
        result.response_sha256,
        f"{STATIC_GENERATION_SCHEMA_VERSION}.{STATIC_GENERATION_PROMPT_VERSION}",
    )


def package_from_attempt(
    proposal: StaticGenerationProposal, result: StaticAttemptResult
) -> StaticObservationPackage:
    if result.status not in ("observed", "no_observations"):
        raise _identity_error()
    return StaticObservationPackage(
        proposal.run_id,
        proposal.collection_id,
        proposal.media_id,
        proposal.source_sha256,
        proposal.config_hash,
        proposal.pipeline_version,
        _provenance(result),
        (
            StaticObservation(
                "gen-" + proposal.proposal_sha256[:40],
                proposal.evidence_id,
                result.actors,
            ),
        ),
        proposal.pipeline_hash,
    )


def _local_flags() -> dict[str, object]:
    return {
        "claim": STATIC_GENERATION_CLAIM,
        "claimMeaning": (
            "由单帧生成的静态草案；只保存冻结词表的typed属性，真实外观、人评与验收均未验证。"
        ),
        "visualVerified": None,
        "humanLabels": None,
        "qualityGate": None,
        "f006Passed": False,
        "f009Passed": False,
        "f010Passed": False,
        "providerVerified": False,
        "billingVerified": False,
        "automaticRetry": False,
    }


def build_prepare_report(
    proposal: StaticGenerationProposal, *, status: str, proposal_path: Path
) -> dict[str, object]:
    document: dict[str, object] = {
        "schemaVersion": STATIC_GENERATION_PREPARE_SCHEMA_VERSION,
        "status": status,
        "proposalHash": proposal.proposal_sha256,
        "proposalPath": str(proposal_path),
        "runId": proposal.run_id,
        "collectionId": proposal.collection_id,
        "mediaId": proposal.media_id,
        "evidenceId": proposal.evidence_id,
        "sourceTimeUs": proposal.source_time_us,
        "durationUs": proposal.duration_us,
        "reservationCny": decimal_text(proposal.reservation_cny),
        "currency": proposal.currency,
        "priceVersion": proposal.price_version,
        "parameters": _parameters_document(proposal.parameters),
        "authorizationRequired": True,
        "authorizationCreated": False,
        "providerRequestsSent": 0,
        "modelInvocations": 0,
    }
    document.update(_local_flags())
    return document


def build_generation_report(
    proposal: StaticGenerationProposal,
    authorization: StaticGenerationAuthorization,
    *,
    operation: Literal["dispatch", "resume"],
    status: str,
    exit_code: ExitCode,
    state: StaticAttemptState | None,
    provider_requests_sent: int,
    publish_status: PublishStatus | None,
    collection_sha256: str | None,
    next_action: str,
) -> dict[str, object]:
    result = None if state is None else state.result
    charge = None
    charge_status = "unknown"
    reservation = None
    attempt_status = "none"
    if state is not None:
        attempt_status = "planned" if state.result is None else "recorded"
        reservation = decimal_text(state.reservation_cny)
        charge_status = state.charge_status
        if state.charge_cny is not None:
            charge = decimal_text(state.charge_cny)
    document: dict[str, object] = {
        "schemaVersion": STATIC_GENERATION_RESULT_SCHEMA_VERSION,
        "operation": operation,
        "status": status,
        "exitCode": int(exit_code),
        "proposalHash": proposal.proposal_sha256,
        "authorizationId": authorization.authorization_id,
        "authorizationSha256": authorization.authorization_sha256,
        "runId": proposal.run_id,
        "collectionId": proposal.collection_id,
        "mediaId": proposal.media_id,
        "evidenceId": proposal.evidence_id,
        "sourceTimeUs": proposal.source_time_us,
        "attemptId": None if state is None else state.attempt_id,
        "attemptStatus": attempt_status,
        "generationStatus": None if result is None else result.status,
        "providerRequestsSent": provider_requests_sent,
        "providerRequestsSentScope": "this_operation_only",
        "published": bool(state is not None and state.published),
        "publishStatus": publish_status,
        "collectionSha256": collection_sha256,
        "observationCount": 1 if collection_sha256 is not None else 0,
        "actorCount": 0 if result is None else len(result.actors),
        "reservationCny": reservation,
        "chargeCny": charge,
        "chargeStatus": charge_status,
        "currency": proposal.currency,
        "overAuthorizationLimit": bool(
            state is not None
            and state.charge_cny is not None
            and state.charge_cny > authorization.max_cost_cny
        ),
        "responseSha256": None if result is None else result.response_sha256,
        "responseBytes": 0 if result is None else result.response_bytes,
        "contentBytes": None if result is None else result.content_bytes,
        "httpStatus": None if result is None else result.http_status,
        "diagnostics": [] if result is None else list(result.diagnostics),
        "nextAction": next_action,
    }
    document.update(_local_flags())
    return document


async def execute_static_observation_generation(
    *,
    proposal: StaticGenerationProposal,
    authorization: StaticGenerationAuthorization,
    timeline: StoredTimeline,
    ledger: StaticGenerationLedger,
    publisher: Callable[[StaticCollectionArtifact], PublishStatus],
    provider: StaticObservationProvider | None,
    context: CancellationContext | None,
    operation: Literal["dispatch", "resume"],
) -> dict[str, object]:
    """Send at most once, or resume only the provable local publish; never auto-retry."""
    if Path(str(ledger.root)).resolve() != Path(proposal.ledger_root):
        raise _authorization_error(
            "static_generation.authorization_scope", "静态生成账本根与冻结提案不一致。"
        )
    if Path(str(ledger.database)).resolve() != Path(proposal.database_path):
        raise _authorization_error(
            "static_generation.authorization_scope", "静态生成数据库与冻结提案不一致。"
        )
    verify_authorization_against_proposal(proposal, authorization)
    verify_proposal_against_timeline(proposal, timeline)
    with ledger.request_guard(proposal.proposal_sha256):
        frame = verify_proposal_against_timeline(proposal, timeline)
        ledger.bind_authorization(authorization)
        state = ledger.load_attempt(proposal.proposal_sha256)
        if state is not None and (
            state.authorization_id != authorization.authorization_id
            or state.authorization_sha256 != authorization.authorization_sha256
        ):
            raise _authorization_error(
                "static_generation.authorization_conflict",
                "同一冻结提案已有另一种人类授权的执行记录；失败关闭且不新发送。",
            )
        sent = 0
        if state is None:
            if operation == "resume":
                return build_generation_report(
                    proposal,
                    authorization,
                    operation=operation,
                    status="nothing_to_resume",
                    exit_code=ExitCode.SUCCESS,
                    state=None,
                    provider_requests_sent=0,
                    publish_status=None,
                    collection_sha256=None,
                    next_action="没有已知发送尝试；恢复不会新建请求。",
                )
            if provider is None or context is None:
                raise _error(
                    "static_generation.provider_missing",
                    "显式派发需要生产提供方与取消上下文。",
                    ExitCode.PROVIDER,
                )
            planned_at = datetime.now(UTC).isoformat()
            state, created = ledger.plan_attempt(proposal, authorization, planned_at=planned_at)
            if created:
                result = await provider.observe(
                    static_observation_request(proposal, frame), context
                )
                if _provider_request_attempted(result.metadata):
                    sent = 1
                attempt = attempt_result_from_provider(
                    result, recorded_at=datetime.now(UTC).isoformat()
                )
                state = ledger.record_result(request_key=proposal.proposal_sha256, result=attempt)
            else:
                sent = 0
        if state.result is None:
            return build_generation_report(
                proposal,
                authorization,
                operation=operation,
                status="unknown",
                exit_code=ExitCode.BUDGET,
                state=state,
                provider_requests_sent=sent,
                publish_status=None,
                collection_sha256=None,
                next_action="已有未结算发送尝试；保留预留与次数，不自动重发。",
            )
        result_state = state.result
        if result_state.status in ("failed", "cancelled"):
            cancelled = result_state.status == "cancelled"
            return build_generation_report(
                proposal,
                authorization,
                operation=operation,
                status="cancelled" if cancelled else "failed",
                exit_code=ExitCode.CANCELLED if cancelled else ExitCode.PROVIDER,
                state=state,
                provider_requests_sent=sent,
                publish_status=None,
                collection_sha256=None,
                next_action="该尝试已结束且不会重试；请人工决定是否另行授权。",
            )
        package = package_from_attempt(proposal, result_state)
        artifact = build_static_collection_artifact(package, timeline)
        publish_status = await asyncio.to_thread(publisher, artifact)
        state = ledger.mark_published(proposal.proposal_sha256)
        status = "no_observations" if result_state.status == "no_observations" else "published"
        return build_generation_report(
            proposal,
            authorization,
            operation=operation,
            status=status,
            exit_code=ExitCode.SUCCESS,
            state=state,
            provider_requests_sent=sent,
            publish_status=publish_status,
            collection_sha256=artifact.package_sha256,
            next_action="已按冻结内容发布到现有静态集合；不声明视觉或人评通过。",
        )
