"""只读盘点项目里的编辑代理目录。

只枚举官方代理根 `.cache/workspace/proxies`，返回每条记录的来源哈希、字节、状态和原因，以及条数和总字节。
不扫描模型、原片或用户成片，也不创建、修改或删除任何文件。活动构建不会标成可清理。
遇到链接、硬链接、越界路径或不明目录时直接拒绝，不跟随到代理根外面统计。
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from collections.abc import Mapping
from io import StringIO
from pathlib import Path
from typing import Any

from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.local_paths import is_link
from gamingcreator.infrastructure.proxy_lease import checked_directory, is_sha256, proxy_lease
from gamingcreator.infrastructure.proxy_media import (
    PROXY_CACHE_ROOT,
    SETTINGS,
    proxy_directory,
    proxy_record,
    proxy_stat_identity,
    read_proxy,
    unlink_proxy_record,
)

SCHEMA = "proxy-space-inventory-v1"
_EMPTY_COUNTS = {"valid": 0, "missing": 0, "bad_receipt": 0, "building": 0, "other": 0}


def proxy_space_root(repository: Path) -> Path:
    """Official editing-proxy root for one project repository."""
    return repository.absolute() / PROXY_CACHE_ROOT


def list_proxy_space(repository: Path) -> dict[str, Any]:
    """Read-only inventory of the official proxy root only."""
    root = proxy_space_root(repository)
    try:
        if not checked_directory(root):
            return _empty()
    except OSError:
        _reject("代理空间根目录或其上级是链接或不可读取。")
    items = tuple(
        _list_child(root, child) for child in sorted(root.iterdir(), key=lambda path: path.name)
    )
    counts = dict(_EMPTY_COUNTS)
    for item in items:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return {
        "schemaVersion": SCHEMA,
        "items": items,
        "totalCount": len(items),
        "totalBytes": sum(item["bytes"] for item in items),
        "counts": counts,
    }


def _empty() -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA,
        "items": (),
        "totalCount": 0,
        "totalBytes": 0,
        "counts": dict(_EMPTY_COUNTS),
    }


def _reject(message: str) -> None:
    raise AppError("storage.proxy_inventory", message, ExitCode.INPUT)


def _hard_linked(path: Path) -> bool:
    """True when the entry has another name, or the link count cannot be read."""
    try:
        return os.lstat(path).st_nlink > 1
    except FileNotFoundError:
        return False
    except OSError:
        return True


def _item(source: str, size: int, status: str, reason: str, cleanable: bool) -> dict[str, Any]:
    return {
        "sourceSha256": source,
        "bytes": size,
        "status": status,
        "reason": reason,
        "cleanable": cleanable,
    }


def _list_child(root: Path, child: Path) -> dict[str, Any]:
    if is_link(child):
        _reject("代理空间里有链接，已拒绝盘点，以免跟到目录外。")
    name = child.name
    if not child.is_dir() or not (name.startswith(".building-") or is_sha256(name)):
        _reject("代理空间里有不明目录，已拒绝盘点。")
    try:
        child.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        _reject("代理空间里有越界路径，已拒绝盘点。")
    _guard_record_files(child)
    if name.startswith(".building-"):
        return _item("", _proxy_bytes(child), "building", "正在生成代理，不能当作可清理项。", False)
    try:
        before = proxy_record(child)
        item = _classify_record(child, name)
        after = proxy_record(child)
    except OSError:
        return _item(
            name, _proxy_bytes(child), "other", "目录已变化，或含不明或不安全的条目。", False
        )
    if (
        before is None
        or after is None
        or _reclaim_token(child, *before) != _reclaim_token(child, *after)
    ):
        return _item(name, item["bytes"], "other", "目录已变化，请刷新盘点。", False)
    if item["status"] != "valid":
        return {**item, "cleanable": False}
    return {**item, "reclaimToken": _reclaim_token(child, *after)}


def _guard_record_files(directory: Path) -> None:
    for path in (directory / "receipt.json", directory / "proxy.mp4"):
        if is_link(path):
            _reject("代理空间里有链接，已拒绝盘点，以免跟到目录外。")
        if _hard_linked(path):
            _reject("代理空间里有硬链接，已拒绝盘点，以免跟到目录外。")


def _classify_record(directory: Path, source: str) -> dict[str, Any]:
    receipt_path, proxy = directory / "receipt.json", directory / "proxy.mp4"
    has_receipt = receipt_path.is_file() and not is_link(receipt_path)
    has_proxy = proxy.is_file() and not is_link(proxy)
    size = _proxy_bytes(directory)
    if not has_receipt or not has_proxy:
        missing = []
        if not has_receipt:
            missing.append("回执")
        if not has_proxy:
            missing.append("代理文件")
        return _item(source, size, "missing", "缺少" + "和".join(missing) + "。", True)
    problem = _receipt_problem(receipt_path, proxy, source)
    if problem is None:
        return _item(source, size, "valid", "回执和代理文件齐全，结构检查通过。", True)
    return _item(source, size, "bad_receipt", problem, True)


def _receipt_problem(receipt_path: Path, proxy: Path, source_sha256: str) -> str | None:
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except PermissionError:
        return "没有权限读取代理回执。"
    except (OSError, ValueError):
        return "回执不是合法的 JSON。"
    if not isinstance(receipt, dict):
        return "回执格式无效。"
    if not is_sha256(receipt.get("proxySha256")):
        return "回执里的代理哈希无效。"
    if receipt.get("schemaVersion") != "editing-proxy-receipt-v1":
        return "回执格式版本无效。"
    if receipt.get("sourceSha256") != source_sha256:
        return "回执里的来源哈希与目录不一致。"
    if receipt.get("settings") != SETTINGS:
        return "回执里的编码设置与当前代理规格不一致。"
    try:
        size = proxy.stat().st_size
    except PermissionError:
        return "没有权限读取代理文件。"
    except OSError:
        return "无法读取代理文件大小。"
    if receipt.get("bytes") != size:
        return "回执记录的字节数与代理文件大小不一致。"
    return None


def _reclaim_token(directory: Path, info: os.stat_result, files: dict[str, os.stat_result]) -> str:
    identity = [
        str(directory),
        proxy_stat_identity(info),
        [(name, proxy_stat_identity(files[name])) for name in sorted(files)],
    ]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=True).encode("ascii")).hexdigest()


def reclaim_proxy(repository: Path, source_sha256: str, reclaim_token: str) -> dict[str, Any]:
    """Remove the single proxy record that still matches the user's inventory snapshot."""
    if not is_sha256(source_sha256) or not is_sha256(reclaim_token):
        raise AppError("input.proxy_reclaim", "代理哈希或回收凭据无效。", ExitCode.INPUT)
    directory = proxy_directory(repository, source_sha256)
    with proxy_lease(repository, source_sha256, write=True):
        try:
            record = proxy_record(directory)
        except OSError:
            raise AppError(
                "storage.proxy_unsafe", "代理目录或文件不安全，未回收。", ExitCode.STORAGE
            ) from None
        if record is None:
            return {"sourceSha256": source_sha256, "removed": False, "releasedProxyBytes": 0}
        directory_stat, files = record
        if _reclaim_token(directory, directory_stat, files) != reclaim_token:
            raise AppError(
                "storage.proxy_stale", "代理目录已变化，请刷新盘点后重新确认。", ExitCode.STORAGE
            )
        receipt = read_proxy(repository, source_sha256)
        if receipt is None or receipt.get("schemaVersion") != "editing-proxy-receipt-v1":
            raise AppError(
                "storage.proxy_unsafe", "代理文件与有效回执无法核对，未回收。", ExitCode.STORAGE
            )
        try:
            unlink_proxy_record(directory, record)
        except OSError:
            raise AppError(
                "storage.proxy_reclaim_failed",
                "回收未完成，部分文件可能已移除，请刷新盘点。",
                ExitCode.STORAGE,
            ) from None
        size = files["proxy.mp4"].st_size if "proxy.mp4" in files else 0
        return {"sourceSha256": source_sha256, "removed": True, "releasedProxyBytes": size}


def _proxy_bytes(directory: Path) -> int:
    if is_link(directory) or not directory.is_dir():
        return 0
    proxy = directory / "proxy.mp4"
    if is_link(proxy) or not proxy.is_file():
        return 0
    try:
        return proxy.stat().st_size
    except OSError:
        return 0


NOTICE = "只读盘点，未删除。"


def proxy_space_document(repository: Path) -> dict[str, Any]:
    """JSON payload for the inventory page and downloads; still read-only."""
    inventory = list_proxy_space(repository)
    return {
        "schemaVersion": inventory["schemaVersion"],
        "notice": NOTICE,
        "readOnly": True,
        "items": inventory["items"],
        "totalCount": inventory["totalCount"],
        "totalBytes": inventory["totalBytes"],
        "counts": inventory["counts"],
    }


def proxy_space_csv(document: Mapping[str, Any]) -> str:
    """Spreadsheet of one inventory document; callers add a BOM if Excel needs it."""
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["sourceSha256", "bytes", "status", "reason", "cleanable"])
    for item in document["items"]:
        writer.writerow(
            [
                item["sourceSha256"],
                item["bytes"],
                item["status"],
                item["reason"],
                "true" if item["cleanable"] else "false",
            ]
        )
    return buffer.getvalue()
