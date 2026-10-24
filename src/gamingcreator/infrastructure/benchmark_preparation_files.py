"""Bounded local freeze/binding bundles; exclusive outputs and no project writes."""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import cast

from gamingcreator.application.benchmark import loads_manifest
from gamingcreator.application.benchmark_inventory_binding import (
    INVENTORY_FILE,
    MAX_INVENTORY_BYTES,
    derive_source_inventory,
)
from gamingcreator.application.benchmark_preparation import (
    FREEZE_VERSION,
    FREEZE_VERSION_V2,
    MAX_PLAN_BYTES,
    canonical_json,
    freeze_preparation,
    loads_plan,
)
from gamingcreator.infrastructure.ffmpeg_media import hash_file

MAX_BUNDLE_BYTES = 4_194_304


def read_bounded(path: Path, limit: int = MAX_PLAN_BYTES) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("验收资料超过允许大小。")
    return data


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("冻结资料含重复字段。")
        result[key] = value
    return result


def _json(data: bytes) -> dict[str, object]:
    value = json.loads(data.decode("utf-8-sig"), object_pairs_hook=_pairs)
    if type(value) is not dict:
        raise ValueError("验收资料不是JSON对象。")
    canonical_json(value)
    return cast(dict[str, object], value)


def _publish(output: Path, files: dict[str, bytes], protected: list[Path]) -> dict[str, str]:
    output = output.resolve()
    if any(
        path.resolve().is_relative_to(output) or output.is_relative_to(path.resolve())
        for path in protected
    ):
        raise ValueError("新输出目录不能覆盖或位于原输入／项目／冻结目录内。")
    if any(len(data) > MAX_BUNDLE_BYTES for data in files.values()):
        raise ValueError("生成的验收资料超过允许大小。")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    hashes = {name: _sha(data) for name, data in files.items()}
    for name, data in files.items():
        with (output / name).open("xb") as stream:
            stream.write(data)
    with (output / "receipt.json").open("xb") as stream:
        stream.write(
            canonical_json({"schemaVersion": "benchmark-bundle-receipt-v1", "files": hashes})
        )
    return hashes


def write_freeze(
    input_path: Path,
    input_bytes: bytes,
    frozen: dict[str, object],
    output: Path,
    inventory: tuple[Path, bytes] | None = None,
) -> dict[str, str]:
    if read_bounded(input_path) != input_bytes:
        raise ValueError("冻结期间输入计划已改变。")
    files = {"plan-input.json": input_bytes, "freeze.json": canonical_json(frozen)}
    protected = [input_path]
    derived = frozen.get("sourceInventory")
    if (
        frozen["schemaVersion"] not in (FREEZE_VERSION, FREEZE_VERSION_V2)
        or (frozen["schemaVersion"] == FREEZE_VERSION and inventory is not None)
        or (frozen["schemaVersion"] == FREEZE_VERSION_V2 and "sourceInventory" not in frozen)
        or (derived is None) != (inventory is None)
    ):
        raise ValueError("冻结版本与素材盘点报告不匹配。")
    if inventory is not None:
        inventory_path, inventory_bytes = inventory
        if read_bounded(inventory_path, MAX_INVENTORY_BYTES) != inventory_bytes:
            raise ValueError("冻结期间素材盘点报告已改变。")
        if cast(dict[str, object], derived)["reportSha256"] != _sha(inventory_bytes):
            raise ValueError("冻结的素材盘点与报告字节不符。")
        files[INVENTORY_FILE] = inventory_bytes
        protected.append(inventory_path)
    sources = cast(list[dict[str, object]], frozen["sources"])
    for source in sources:
        if hash_file(Path(cast(str, source["path"]))) != source["sha256"]:
            raise ValueError("冻结期间原录像已改变。")
    return _publish(output, files, [*protected, *(Path(cast(str, row["path"])) for row in sources)])


def read_freeze(directory: Path) -> tuple[dict[str, object], str]:
    directory = directory.resolve()
    if any(
        (directory / name).is_symlink() or (directory / name).is_junction()
        for name in ("receipt.json", "freeze.json", "plan-input.json", INVENTORY_FILE)
    ):
        raise ValueError("冻结文件不能是链接。")
    receipt = _json(read_bounded(directory / "receipt.json", MAX_BUNDLE_BYTES))
    if (
        set(receipt) != {"schemaVersion", "files"}
        or receipt["schemaVersion"] != "benchmark-bundle-receipt-v1"
    ):
        raise ValueError("未知冻结回执。")
    hashes = receipt["files"]
    base = {"plan-input.json", "freeze.json"}
    if type(hashes) is not dict or set(hashes) not in (base, {*base, INVENTORY_FILE}):
        raise ValueError("冻结回执资料不完整。")
    data = read_bounded(directory / "freeze.json", MAX_BUNDLE_BYTES)
    original = read_bounded(directory / "plan-input.json")
    if _sha(data) != hashes["freeze.json"] or _sha(original) != hashes["plan-input.json"]:
        raise ValueError("冻结资料已改变。")
    frozen = _json(data)
    fields = {"schemaVersion", "frozenAt", "plan", "sources", "preparation"}
    if frozen.get("schemaVersion") == FREEZE_VERSION:
        if set(hashes) != base or set(frozen) != fields:
            raise ValueError("未知冻结版本／字段。")
    elif frozen.get("schemaVersion") != FREEZE_VERSION_V2 or set(frozen) != {
        *fields,
        "sourceInventory",
    }:
        raise ValueError("未知冻结版本／字段。")
    elif (frozen["sourceInventory"] is None) != (INVENTORY_FILE not in hashes):
        raise ValueError("冻结素材盘点与回执不一致。")
    plan = loads_plan(original.decode("utf-8-sig"))
    if frozen["plan"] != plan.document:
        raise ValueError("冻结计划与原输入不同。")
    timestamp = datetime.fromisoformat(cast(str, frozen["frozenAt"]))
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("冻结时间缺时区。")
    sources = frozen["sources"]
    if type(sources) is not list or len(sources) != len(plan.sources):
        raise ValueError("冻结来源不完整。")
    for source in sources:
        if type(source) is not dict or set(source) != {
            "id",
            "path",
            "sha256",
            "durationUs",
            "probeVersion",
        }:
            raise ValueError("冻结来源字段无效。")
        if any(
            type(source[key]) is not str or not source[key].strip()
            for key in ("id", "path", "sha256", "probeVersion")
        ):
            raise ValueError("冻结来源文字无效。")
        if type(source["durationUs"]) is not int or not 0 < source["durationUs"] < 2**63:
            raise ValueError("冻结来源时长无效。")
    if {row["id"] for row in sources} != {row.source_id for row in plan.sources}:
        raise ValueError("冻结来源身份不同。")
    if INVENTORY_FILE in hashes:
        report = read_bounded(directory / INVENTORY_FILE, MAX_INVENTORY_BYTES)
        if _sha(report) != hashes[INVENTORY_FILE]:
            raise ValueError("冻结资料已改变。")
        if frozen["sourceInventory"] != derive_source_inventory(report, sources):
            raise ValueError("冻结素材盘点与报告不同。")
    if frozen["preparation"] != freeze_preparation(plan, frozen, sources):
        raise ValueError("冻结准备状态不同。")
    return frozen, _sha(data)


def write_binding(
    *,
    directory: Path,
    freeze_sha256: str,
    output: Path,
    project: Path,
    manifest: dict[str, object],
    provenance: dict[str, object],
) -> dict[str, str]:
    _, current_sha = read_freeze(directory)
    if current_sha != freeze_sha256:
        raise ValueError("绑定期间冻结资料已改变。")
    data = canonical_json(manifest)
    loads_manifest(data.decode("utf-8"))
    return _publish(
        output,
        {"benchmark.json": data, "binding.json": canonical_json(provenance)},
        [directory, project],
    )


def validate_bound_manifest(directory: Path, input_bytes: bytes) -> None:
    """Only candidate labels and subsequent human review may change the bound template."""
    receipt = _json(read_bounded(directory / "receipt.json", MAX_BUNDLE_BYTES))
    if receipt.get("schemaVersion") != "benchmark-bundle-receipt-v1":
        raise ValueError("未知绑定回执。")
    hashes = receipt.get("files")
    if type(hashes) is not dict or set(hashes) != {"benchmark.json", "binding.json"}:
        raise ValueError("绑定回执不完整。")
    data = read_bounded(directory / "benchmark.json", MAX_BUNDLE_BYTES)
    provenance = read_bounded(directory / "binding.json", MAX_BUNDLE_BYTES)
    if _sha(data) != hashes["benchmark.json"] or _sha(provenance) != hashes["binding.json"]:
        raise ValueError("绑定资料已改变。")
    if _json(provenance).get("schemaVersion") != "benchmark-binding-v1":
        raise ValueError("未知绑定版本。")
    base, actual = _json(data), _json(input_bytes)
    loads_manifest(data.decode("utf-8"))
    loads_manifest(input_bytes.decode("utf-8-sig"))
    human = cast(dict[str, object], actual["humanLabels"])
    human["reviewed"] = cast(dict[str, object], base["humanLabels"])["reviewed"]
    for query in cast(list[dict[str, object]], actual["queries"]):
        query["candidateLabels"] = []
    if actual != base:
        raise ValueError("查询／来源／人工参考或原确认声明已改变，不能沿用冻结评测。")
