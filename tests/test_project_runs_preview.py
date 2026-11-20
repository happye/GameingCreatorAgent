"""B04: 录像名单带上已核代理地址，没有代理时仍是原片。"""

from __future__ import annotations

import asyncio
import hashlib
import json
from urllib.parse import parse_qs, urlencode, urlparse

from test_detail_inspection import seed_project
from test_inspection_http import get, workspace

from gamingcreator.infrastructure.proxy_media import SETTINGS, proxy_directory
from gamingcreator.ui.service import project_runs_payload


def plant(repository, sha256):
    directory = proxy_directory(repository, sha256)
    directory.mkdir(parents=True)
    body = b"proxy-bytes"
    (directory / "proxy.mp4").write_bytes(body)
    (directory / "receipt.json").write_text(
        json.dumps(
            {
                "schemaVersion": "editing-proxy-receipt-v1",
                "sourceSha256": sha256,
                "settings": SETTINGS,
                "bytes": len(body),
                "proxySha256": hashlib.sha256(body).hexdigest(),
            }
        ),
        encoding="utf-8",
    )


def query(url):
    return {key: values[0] for key, values in parse_qs(urlparse(url).query).items()}


def test_runs_payload_includes_verified_proxy(tmp_path):
    project, bundle, _timeline = seed_project(tmp_path)
    plant(tmp_path, bundle.asset.sha256)
    payload = asyncio.run(
        project_runs_payload(project, tmp_path, project_reference="artifacts/project")
    )
    row = next(item for item in payload["runs"] if item["id"] == "run-1")
    assert urlparse(row["videoUrl"]).path == "/api/media"
    assert query(row["videoUrl"]) == {"project": "artifacts/project", "run": "run-1"}
    assert query(row["proxyUrl"]) == {
        "project": "artifacts/project",
        "run": "run-1",
        "proxy": "1",
    }


def test_runs_payload_without_proxy_keeps_original(tmp_path):
    project, _bundle, _timeline = seed_project(tmp_path)
    payload = asyncio.run(
        project_runs_payload(project, tmp_path, project_reference="artifacts/project")
    )
    row = next(item for item in payload["runs"] if item["id"] == "run-1")
    assert urlparse(row["videoUrl"]).path == "/api/media"
    assert query(row["videoUrl"]) == {"project": "artifacts/project", "run": "run-1"}
    assert row["proxyUrl"] is None


def test_http_runs_exposes_verified_proxy(tmp_path):
    _project, bundle, _timeline = seed_project(tmp_path)
    plant(tmp_path, bundle.asset.sha256)
    with workspace(tmp_path) as base:
        status, _headers, body = get(
            base, "/api/runs?" + urlencode({"project": "artifacts/project"})
        )
    assert status == 200
    payload = json.loads(body.decode("utf-8"))
    row = next(item for item in payload["runs"] if item["id"] == "run-1")
    assert query(row["videoUrl"]) == {"project": "artifacts/project", "run": "run-1"}
    assert query(row["proxyUrl"])["proxy"] == "1"
