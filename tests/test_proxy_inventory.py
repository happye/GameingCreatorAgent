"""B13/B14: read-only proxy-space inventory with classified statuses."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_preview_clock_align_browser import plant_playable_proxy

from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.local_paths import is_link
from gamingcreator.infrastructure.proxy_inventory import SCHEMA, list_proxy_space, proxy_space_root
from gamingcreator.infrastructure.proxy_media import SETTINGS


def _write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def _sha(prefix: str) -> str:
    return (prefix * 64)[:64]


def test_missing_root_is_empty_and_does_not_create_the_directory(tmp_path):
    inventory = list_proxy_space(tmp_path)
    assert inventory["schemaVersion"] == SCHEMA
    assert inventory["items"] == ()
    assert inventory["totalCount"] == 0
    assert inventory["totalBytes"] == 0
    assert inventory["counts"] == {
        "valid": 0,
        "missing": 0,
        "bad_receipt": 0,
        "building": 0,
        "other": 0,
    }
    assert not proxy_space_root(tmp_path).exists()


def test_lists_only_the_official_proxy_root(tmp_path):
    first = tmp_path / "one.mp4"
    second = tmp_path / "two.mp4"
    first.write_bytes(b"original-one")
    second.write_bytes(b"original-two-bytes")
    plant_playable_proxy(tmp_path, first, _sha("a"), 1_000_000, body=b"proxy-one-body!!")
    plant_playable_proxy(tmp_path, second, _sha("b"), 2_000_000, body=b"proxy-two-body!!!!")
    building = proxy_space_root(tmp_path) / ".building-in-progress"
    _write(building / "proxy.mp4", b"partial-proxy-bytes")
    _write(tmp_path / ".cache" / "models" / "weights.bin", b"not-a-proxy")
    _write(tmp_path / "footage" / "original.mp4", b"original-footage")
    _write(tmp_path / ".cache" / "workspace" / "creations" / "out.mp4", b"user-render")
    _write(
        tmp_path / ".cache" / "workspace" / "proxies-not" / _sha("c") / "proxy.mp4", b"wrong-root"
    )

    inventory = list_proxy_space(tmp_path)
    items = {item["sourceSha256"]: item for item in inventory["items"]}
    assert inventory["schemaVersion"] == SCHEMA
    assert inventory["totalCount"] == 3
    assert items[_sha("a")]["status"] == "valid"
    assert items[_sha("a")]["bytes"] == len(b"proxy-one-body!!")
    assert items[_sha("a")]["cleanable"] is True
    assert items[_sha("b")]["status"] == "valid"
    assert items[_sha("b")]["bytes"] == len(b"proxy-two-body!!!!")
    assert items[""]["status"] == "building"
    assert items[""]["bytes"] == len(b"partial-proxy-bytes")
    assert items[""]["cleanable"] is False
    assert "可清理" not in items[""]["reason"] or "不能当作可清理" in items[""]["reason"]
    assert inventory["totalBytes"] == (
        len(b"proxy-one-body!!") + len(b"proxy-two-body!!!!") + len(b"partial-proxy-bytes")
    )
    assert inventory["counts"] == {
        "valid": 2,
        "missing": 0,
        "bad_receipt": 0,
        "building": 1,
        "other": 0,
    }
    listed = {item["sourceSha256"] for item in inventory["items"] if item["sourceSha256"]}
    assert _sha("c") not in listed


def test_inventory_does_not_write_or_rebuild(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"keep-me")
    digest = _sha("d")
    plant_playable_proxy(tmp_path, source, digest, 1_000_000, body=b"planted-proxy")
    root = proxy_space_root(tmp_path)
    receipt = root / digest / "receipt.json"
    before = receipt.read_bytes()
    mtime = receipt.stat().st_mtime_ns
    proxy_mtime = (root / digest / "proxy.mp4").stat().st_mtime_ns
    names_before = sorted(path.name for path in root.iterdir())

    inventory = list_proxy_space(tmp_path)

    assert inventory["totalCount"] == 1 and inventory["items"][0]["status"] == "valid"
    assert receipt.read_bytes() == before
    assert receipt.stat().st_mtime_ns == mtime
    assert (root / digest / "proxy.mp4").stat().st_mtime_ns == proxy_mtime
    assert sorted(path.name for path in root.iterdir()) == names_before


def test_classifies_missing_bad_receipt_and_active_builds(tmp_path):
    valid_source = tmp_path / "valid.mp4"
    valid_source.write_bytes(b"valid-original")
    plant_playable_proxy(tmp_path, valid_source, _sha("1"), 1_000_000, body=b"valid-proxy-bytes")
    root = proxy_space_root(tmp_path)

    missing_proxy = root / _sha("2")
    _write(missing_proxy / "receipt.json", json.dumps({"note": "no proxy file"}).encode())
    missing_receipt = root / _sha("3")
    _write(missing_receipt / "proxy.mp4", b"orphan-proxy")
    empty_dir = root / _sha("4")
    empty_dir.mkdir(parents=True)

    bad_bytes = root / _sha("5")
    plant_playable_proxy(tmp_path, valid_source, _sha("5"), 1_000_000, body=b"size-mismatch")
    receipt = json.loads((bad_bytes / "receipt.json").read_text(encoding="utf-8"))
    receipt["bytes"] = 1
    (bad_bytes / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")

    bad_json = root / _sha("6")
    _write(bad_json / "proxy.mp4", b"json-bad")
    _write(bad_json / "receipt.json", b"{not-json")

    bad_settings = root / _sha("7")
    plant_playable_proxy(tmp_path, valid_source, _sha("7"), 1_000_000, body=b"settings-bad")
    receipt = json.loads((bad_settings / "receipt.json").read_text(encoding="utf-8"))
    receipt["settings"] = {**SETTINGS, "version": "not-the-current-settings"}
    (bad_settings / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")

    building = root / ".building-live"
    _write(building / "proxy.mp4", b"building-bytes")
    _write(building / "receipt.json", b"{}")

    inventory = list_proxy_space(tmp_path)
    items = {item["sourceSha256"] or item["status"]: item for item in inventory["items"]}
    assert items[_sha("1")]["status"] == "valid"
    assert items[_sha("1")]["reason"] == "回执和代理文件齐全，结构检查通过。"
    assert items[_sha("1")]["cleanable"] is True
    assert (
        items[_sha("2")]["status"] == "missing" and items[_sha("2")]["reason"] == "缺少代理文件。"
    )
    assert items[_sha("3")]["status"] == "missing" and items[_sha("3")]["reason"] == "缺少回执。"
    assert (
        items[_sha("4")]["status"] == "missing"
        and items[_sha("4")]["reason"] == "缺少回执和代理文件。"
    )
    assert items[_sha("5")]["status"] == "bad_receipt"
    assert items[_sha("5")]["reason"] == "回执记录的字节数与代理文件大小不一致。"
    assert (
        items[_sha("6")]["status"] == "bad_receipt"
        and items[_sha("6")]["reason"] == "回执不是合法的 JSON。"
    )
    assert items[_sha("7")]["status"] == "bad_receipt"
    assert items[_sha("7")]["reason"] == "回执里的编码设置与当前代理规格不一致。"
    assert items["building"]["status"] == "building"
    assert items["building"]["cleanable"] is False
    assert items["building"]["reason"] == "正在生成代理，不能当作可清理项。"
    assert inventory["counts"]["valid"] == 1
    assert inventory["counts"]["missing"] == 3
    assert inventory["counts"]["bad_receipt"] == 3
    assert inventory["counts"]["building"] == 1
    for item in inventory["items"]:
        if item["status"] == "building":
            assert item["cleanable"] is False


def test_does_not_rebuild_or_modify_bad_or_missing_records(tmp_path):
    root = proxy_space_root(tmp_path)
    missing = root / _sha("8")
    _write(missing / "receipt.json", b'{"keep": true}')
    bad = root / _sha("9")
    _write(bad / "proxy.mp4", b"bad-body")
    _write(bad / "receipt.json", b"{not-json")
    snapshot = {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in (missing / "receipt.json", bad / "proxy.mp4", bad / "receipt.json")
    }
    names_before = sorted(path.name for path in root.rglob("*"))

    inventory = list_proxy_space(tmp_path)

    assert {item["status"] for item in inventory["items"]} == {"missing", "bad_receipt"}
    assert not (missing / "proxy.mp4").exists()
    for path, (body, mtime) in snapshot.items():
        assert path.read_bytes() == body
        assert path.stat().st_mtime_ns == mtime
    assert sorted(path.name for path in root.rglob("*")) == names_before


def _snapshot(path: Path) -> tuple[bytes, int]:
    return path.read_bytes(), path.stat().st_mtime_ns


def _make_junction(link: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    link.parent.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
    )
    if completed.returncode:
        pytest.skip("Windows junction unavailable")


def test_unknown_directory_is_rejected_and_not_counted(tmp_path):
    root = proxy_space_root(tmp_path)
    source = tmp_path / "ok.mp4"
    source.write_bytes(b"ok")
    plant_playable_proxy(tmp_path, source, _sha("a"), 1_000_000, body=b"valid-proxy")
    _write(root / "misc" / "proxy.mp4", b"should-not-be-counted")
    with pytest.raises(AppError, match="不明目录"):
        list_proxy_space(tmp_path)
    assert (root / "misc" / "proxy.mp4").read_bytes() == b"should-not-be-counted"


def test_loose_file_in_proxy_root_is_rejected(tmp_path):
    root = proxy_space_root(tmp_path)
    _write(root / "readme.txt", b"not-a-record")
    with pytest.raises(AppError, match="不明目录"):
        list_proxy_space(tmp_path)
    assert (root / "readme.txt").read_bytes() == b"not-a-record"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows junction boundary")
def test_child_junction_is_rejected_and_outside_is_untouched(tmp_path):
    source = tmp_path / "ok.mp4"
    source.write_bytes(b"ok")
    plant_playable_proxy(tmp_path, source, _sha("a"), 1_000_000, body=b"valid-proxy")
    outside = tmp_path / "outside-tree" / "payload.bin"
    _write(outside, b"external-payload")
    before = _snapshot(outside)
    _make_junction(proxy_space_root(tmp_path) / _sha("b"), outside.parent)
    with pytest.raises(AppError, match="链接"):
        list_proxy_space(tmp_path)
    assert _snapshot(outside) == before


@pytest.mark.skipif(sys.platform != "win32", reason="Windows junction boundary")
def test_proxy_root_junction_is_rejected_and_outside_is_untouched(tmp_path):
    workspace = tmp_path / ".cache" / "workspace"
    workspace.mkdir(parents=True)
    outside = tmp_path / "external-proxies"
    _write(outside / _sha("e") / "proxy.mp4", b"escaped-bytes")
    before = _snapshot(outside / _sha("e") / "proxy.mp4")
    _make_junction(workspace / "proxies", outside)
    with pytest.raises(AppError, match="链接"):
        list_proxy_space(tmp_path)
    assert _snapshot(outside / _sha("e") / "proxy.mp4") == before


def test_hard_linked_proxy_is_rejected_and_outside_is_untouched(tmp_path):
    source = tmp_path / "ok.mp4"
    source.write_bytes(b"ok")
    digest = _sha("a")
    plant_playable_proxy(tmp_path, source, digest, 1_000_000, body=b"will-be-replaced")
    outside = tmp_path / "outside" / "shared.bin"
    _write(outside, b"external-hardlink-bytes")
    proxy = proxy_space_root(tmp_path) / digest / "proxy.mp4"
    proxy.unlink()
    os.link(outside, proxy)
    before = _snapshot(outside)
    with pytest.raises(AppError, match="硬链接"):
        list_proxy_space(tmp_path)
    assert _snapshot(outside) == before
    assert proxy.exists()


def test_file_symlink_proxy_is_rejected_and_outside_is_untouched(tmp_path):
    source = tmp_path / "ok.mp4"
    source.write_bytes(b"ok")
    digest = _sha("a")
    plant_playable_proxy(tmp_path, source, digest, 1_000_000, body=b"will-be-replaced")
    outside = tmp_path / "outside" / "target.bin"
    _write(outside, b"external-symlink-bytes")
    proxy = proxy_space_root(tmp_path) / digest / "proxy.mp4"
    proxy.unlink()
    try:
        proxy.symlink_to(outside)
    except OSError:
        pytest.skip("File symlink privilege unavailable")
    if not is_link(proxy):
        pytest.skip("symlink not reported as link")
    before = _snapshot(outside)
    with pytest.raises(AppError, match="链接"):
        list_proxy_space(tmp_path)
    assert _snapshot(outside) == before
