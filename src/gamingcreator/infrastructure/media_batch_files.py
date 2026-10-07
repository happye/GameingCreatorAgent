"""Project-local immutable batch plans and replaceable state snapshots."""

import hashlib
import json
import os
import re
from contextlib import suppress
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import uuid4

from gamingcreator.application.media_batch import (
    MAX_BATCH_INPUT_BYTES,
    MediaBatchItem,
    MediaBatchPlan,
    initial_batch_state,
    loads_batch_input,
    validate_batch_state,
)
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.local_files import LocalInputReader
from gamingcreator.infrastructure.writer_lock import ProjectWriterLock


def read_batch_bytes(path: Path) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(MAX_BATCH_INPUT_BYTES + 1)
    if len(data) > MAX_BATCH_INPUT_BYTES:
        raise ValueError("批次资料不能超过1MiB。")
    return data


def _json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode(
        "utf-8"
    )


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _decode(data: bytes) -> dict[str, object]:
    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in items:
            if key in value:
                raise ValueError("批次资料含重复字段。")
            value[key] = item
        return value

    raw = json.loads(data.decode("utf-8-sig"), object_pairs_hook=pairs)
    if type(raw) is not dict:
        raise ValueError("批次资料须为对象。")
    return cast(dict[str, object], raw)


class MediaBatchFiles:
    def __init__(self, project: Path, batch_id: str) -> None:
        if not re.fullmatch(r"[a-f0-9]{32}", batch_id):
            raise ValueError("批次身份无效。")
        self.project = project.resolve()
        self.directory = self.project / "media-batches" / batch_id
        if not self.directory.resolve().is_relative_to(self.project):
            raise ValueError("批次目录超出项目。")
        self.batch_id = batch_id
        self._lock: ProjectWriterLock | None = None

    def create(
        self, plan: MediaBatchPlan, input_directory: Path, input_bytes: bytes, config_bytes: bytes
    ) -> None:
        if plan.project != self.project or plan.batch_id != self.batch_id:
            raise ValueError("批次项目身份不同。")
        loads_batch_input(input_bytes)
        self.directory.mkdir(parents=True)
        files = {"source-input.json": input_bytes, "analysis-config.json": config_bytes}
        files["plan.json"] = _json(
            {
                "schemaVersion": "media-batch-plan-v1",
                "batchId": plan.batch_id,
                "project": str(plan.project),
                "inputDirectory": str(input_directory),
                "createdAt": datetime.now(UTC).isoformat(),
                "maxCostCnyPerTask": str(plan.max_cost_cny),
                "timeoutSeconds": plan.timeout_seconds,
                "configuration": asdict(plan.config),
                "items": [
                    {"id": item.item_id, "path": str(item.video), "runId": item.run_id}
                    for item in plan.items
                ],
            }
        )
        for name, data in files.items():
            with (self.directory / name).open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        with (self.directory / "receipt.json").open("xb") as stream:
            stream.write(
                _json(
                    {
                        "schemaVersion": "media-batch-plan-receipt-v1",
                        "files": {name: _sha(data) for name, data in files.items()},
                        "modelInvocations": 0,
                        "newReservations": 0,
                    }
                )
            )
            stream.flush()
            os.fsync(stream.fileno())

    def acquire(self) -> None:
        self._lock = ProjectWriterLock(self.directory)
        self._lock.acquire()

    def close(self) -> None:
        if self._lock is not None:
            self._lock.close()
            self._lock = None

    def load(self) -> tuple[MediaBatchPlan, dict[str, object], str]:
        receipt = _decode(read_batch_bytes(self.directory / "receipt.json"))
        hashes = receipt.get("files")
        if (
            set(receipt) != {"schemaVersion", "files", "modelInvocations", "newReservations"}
            or receipt["schemaVersion"] != "media-batch-plan-receipt-v1"
            or receipt["modelInvocations"] != 0
            or receipt["newReservations"] != 0
            or type(hashes) is not dict
            or set(hashes) != {"source-input.json", "analysis-config.json", "plan.json"}
        ):
            raise ValueError("批次冻结回执无效。")
        files = {
            name: read_batch_bytes(self.directory / name)
            for name in cast(dict[str, object], hashes)
        }
        if any(_sha(data) != cast(dict[str, object], hashes)[name] for name, data in files.items()):
            raise ValueError("批次原清单／配置／身份改变。")
        raw = _decode(files["plan.json"])
        if (
            set(raw)
            != {
                "schemaVersion",
                "batchId",
                "project",
                "inputDirectory",
                "createdAt",
                "maxCostCnyPerTask",
                "timeoutSeconds",
                "configuration",
                "items",
            }
            or raw["schemaVersion"] != "media-batch-plan-v1"
            or raw["batchId"] != self.batch_id
            or raw["project"] != str(self.project)
        ):
            raise ValueError("批次计划身份不同。")
        config = LocalInputReader().load_config(self.directory / "analysis-config.json")
        if raw["configuration"] != asdict(config):
            raise ValueError("批次配置快照不同。")
        budget = Decimal(cast(str, raw["maxCostCnyPerTask"]))
        if not budget.is_finite() or budget <= 0:
            raise ValueError("批次后续限额无效。")
        expected = loads_batch_input(files["source-input.json"])
        rows = raw["items"]
        if type(rows) is not list or len(rows) != len(expected):
            raise ValueError("批次素材不完整。")
        items = []
        for row, (identifier, source) in zip(rows, expected, strict=True):
            if (
                type(row) is not dict
                or set(row) != {"id", "path", "runId"}
                or row["id"] != identifier
                or type(row["path"]) is not str
                or type(row["runId"]) is not str
                or not re.fullmatch(r"[a-f0-9]{32}", row["runId"])
            ):
                raise ValueError("批次素材运行身份无效。")
            relative = Path(source)
            path = (
                relative
                if relative.is_absolute()
                else Path(cast(str, raw["inputDirectory"])) / relative
            ).resolve()
            if str(path) != row["path"]:
                raise ValueError("批次素材路径改变。")
            items.append(MediaBatchItem(identifier, path, row["runId"]))
        if len({item.run_id for item in items}) != len(items) or len(
            {item.video for item in items}
        ) != len(items):
            raise ValueError("批次任务／原路径不能重复。")
        timeout = raw["timeoutSeconds"]
        if type(timeout) not in (int, float):
            raise ValueError("批次期限无效。")
        plan = MediaBatchPlan(
            self.batch_id, self.project, config, budget, cast(float, timeout), tuple(items)
        )
        digest = _sha(files["plan.json"])
        state_path = self.directory / "state.json"
        state = (
            _decode(read_batch_bytes(state_path))
            if state_path.exists()
            else initial_batch_state(plan, digest)
        )
        validate_batch_state(state, plan, digest)
        return plan, state, digest

    def save(self, state: dict[str, object], plan: MediaBatchPlan, digest: str) -> None:
        if self._lock is None:
            raise AppError("storage.batch_lock", "更新批次状态须持有批次锁。", ExitCode.STORAGE)
        validate_batch_state(state, plan, digest)
        temporary = self.directory / (".state-" + uuid4().hex + ".tmp")
        try:
            data = _json(state)
            if len(data) > MAX_BATCH_INPUT_BYTES:
                raise ValueError("批次状态超过1MiB。")
            with temporary.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.directory / "state.json")
        except (OSError, ValueError, UnicodeError):
            raise AppError(
                "storage.batch_checkpoint",
                "批次状态保存失败，请保留原任务后续跑。",
                ExitCode.STORAGE,
            ) from None
        finally:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
