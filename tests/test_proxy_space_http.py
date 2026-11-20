"""B16: read-only proxy-space page plus JSON and CSV downloads."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from urllib.request import ProxyHandler, Request, build_opener

from test_inspection_http import get, workspace
from test_preview_clock_align_browser import plant_playable_proxy

from gamingcreator.infrastructure.proxy_inventory import (
    NOTICE,
    list_proxy_space,
    proxy_space_document,
    proxy_space_root,
)


def _sha(prefix: str) -> str:
    return (prefix * 64)[:64]


def _write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)


def _plant(tmp_path: Path) -> None:
    first = tmp_path / "one.mp4"
    second = tmp_path / "two.mp4"
    first.write_bytes(b"original-one")
    second.write_bytes(b"original-two-bytes")
    plant_playable_proxy(tmp_path, first, _sha("a"), 1_000_000, body=b"proxy-one-body!!")
    plant_playable_proxy(tmp_path, second, _sha("b"), 2_000_000, body=b"proxy-two-body!!!!")
    building = proxy_space_root(tmp_path) / ".building-in-progress"
    _write(building / "proxy.mp4", b"partial-proxy-bytes")
    missing = proxy_space_root(tmp_path) / _sha("c")
    _write(missing / "receipt.json", json.dumps({"note": "no proxy file"}).encode())


def _snapshot(root: Path) -> dict[Path, tuple[bytes, int]]:
    return {
        path: (path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_document_matches_inventory_and_states_read_only(tmp_path):
    _plant(tmp_path)
    inventory = list_proxy_space(tmp_path)
    document = proxy_space_document(tmp_path)
    assert document["notice"] == NOTICE == "只读盘点，未删除。"
    assert document["readOnly"] is True
    assert document["schemaVersion"] == inventory["schemaVersion"]
    assert document["items"] == inventory["items"]
    assert document["totalCount"] == inventory["totalCount"] == 4
    assert document["totalBytes"] == inventory["totalBytes"]
    assert document["counts"] == inventory["counts"]


def test_json_and_csv_match_inventory_and_page_is_read_only(tmp_path):
    _plant(tmp_path)
    inventory = list_proxy_space(tmp_path)
    root = proxy_space_root(tmp_path)
    before = _snapshot(root)
    names_before = sorted(path.name for path in root.iterdir())

    with workspace(tmp_path) as base:
        status, headers, body = get(base, "/api/proxy-space")
        assert status == 200
        payload = json.loads(body.decode())
        assert payload["notice"] == "只读盘点，未删除。"
        assert payload["readOnly"] is True
        assert payload["totalCount"] == inventory["totalCount"]
        assert payload["totalBytes"] == inventory["totalBytes"]
        assert payload["counts"] == inventory["counts"]
        assert [item["sourceSha256"] for item in payload["items"]] == [
            item["sourceSha256"] for item in inventory["items"]
        ]
        assert [item["bytes"] for item in payload["items"]] == [
            item["bytes"] for item in inventory["items"]
        ]

        json_status, json_headers, json_body = get(base, "/api/proxy-space.json")
        assert json_status == 200
        assert "attachment" in json_headers.get("Content-Disposition", "")
        assert "proxy-space.json" in json_headers.get("Content-Disposition", "")
        assert json.loads(json_body.decode()) == payload

        csv_status, csv_headers, csv_body = get(base, "/api/proxy-space.csv")
        assert csv_status == 200
        assert csv_headers.get("Content-Type", "").startswith("text/csv")
        assert "attachment" in csv_headers.get("Content-Disposition", "")
        assert "proxy-space.csv" in csv_headers.get("Content-Disposition", "")
        text = csv_body.decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(text)))
        assert len(rows) == inventory["totalCount"]
        assert sum(int(row["bytes"]) for row in rows) == inventory["totalBytes"]
        assert [row["sourceSha256"] for row in rows] == [
            item["sourceSha256"] for item in inventory["items"]
        ]
        assert [row["status"] for row in rows] == [item["status"] for item in inventory["items"]]
        assert [row["cleanable"] for row in rows] == [
            "true" if item["cleanable"] else "false" for item in inventory["items"]
        ]

        page_status, _, page = get(base, "/proxy-space")
        assert page_status == 200
        html = page.decode()
        assert "只读盘点，未删除。" in html
        assert "不会删除任何文件" in html
        assert "/api/proxy-space.json" in html
        assert "/api/proxy-space.csv" in html
        assert "回收" not in html
        lower = html.lower()
        assert 'type="submit"' not in lower
        assert "<button" not in lower
        assert "<form" not in lower
        assert "delete" not in lower
        script_status, _, script = get(base, "/assets/proxy-space.js")
        assert script_status == 200
        script_text = script.decode()
        assert "只读盘点，未删除。" in script_text
        assert "回收" not in script_text
        assert "fetch(" not in script_text.replace('fetch("/api/proxy-space")', "")
        assert "/delete" not in script_text
        assert "/api/proxy-space" in script_text

        home_status, _, home = get(base, "/")
        assert home_status == 200
        assert 'href="/proxy-space"' in home.decode()

        bad_status, _, bad_body = get(base, "/api/proxy-space?project=oops")
        assert bad_status == 400
        assert json.loads(bad_body.decode())["code"] == "input.request"

        opener = build_opener(ProxyHandler({}))
        try:
            response = opener.open(
                Request(base + "/api/proxy-space", data=b"{}", method="POST"), timeout=10
            )
            posted = response.status
            post_body = response.read()
        except Exception as error:
            posted = getattr(error, "status", getattr(error, "code", 0))
            post_body = getattr(error, "read", lambda: b"")()
        assert posted in {400, 404, 405}
        assert b"deleted" not in post_body.lower()
        assert "已删除".encode() not in post_body

    assert _snapshot(root) == before
    assert sorted(path.name for path in root.iterdir()) == names_before


def test_json_reports_inventory_rejection_without_changing_files(tmp_path):
    _plant(tmp_path)
    loose = proxy_space_root(tmp_path) / "README.txt"
    loose.write_bytes(b"not-a-record")
    before = loose.read_bytes()
    mtime = loose.stat().st_mtime_ns
    with workspace(tmp_path) as base:
        status, _, body = get(base, "/api/proxy-space")
        assert status == 400
        payload = json.loads(body.decode())
        assert payload["code"] == "storage.proxy_inventory"
        assert "不明目录" in payload["message"]
    assert loose.read_bytes() == before
    assert loose.stat().st_mtime_ns == mtime
