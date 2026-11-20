"""B01: preview selection uses a verified same-asset proxy, otherwise the original."""

from __future__ import annotations

import hashlib
import json
from urllib.parse import parse_qs, urlparse

import pytest

import gamingcreator.infrastructure.proxy_media as proxy_media
from gamingcreator.infrastructure.proxy_media import SETTINGS, choose_preview, proxy_directory

SHA = "a" * 64
OTHER = "b" * 64
VIDEO = "/api/media?project=artifacts/demo&run=run-1"


def plant(repo, sha=SHA, *, settings=SETTINGS, source_sha=None, corrupt=False):
    directory = proxy_directory(repo, sha)
    directory.mkdir(parents=True)
    body = b"proxy-bytes"
    (directory / "proxy.mp4").write_bytes(body)
    receipt = {
        "schemaVersion": "editing-proxy-receipt-v1",
        "sourceSha256": source_sha or sha,
        "settings": settings,
        "bytes": 0 if corrupt else len(body),
        "proxySha256": hashlib.sha256(body).hexdigest(),
    }
    (directory / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")


def query(url):
    return {key: values[0] for key, values in parse_qs(urlparse(url).query).items()}


def test_missing_proxy_uses_original_and_does_not_build(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("choose_preview must not build a proxy")

    monkeypatch.setattr(proxy_media, "make_proxy", forbidden)
    choice = choose_preview(VIDEO, repository=tmp_path, source_sha256=SHA, prefer_proxy=True)
    assert choice["source"] == "original"
    assert query(choice["url"]) == {"project": "artifacts/demo", "run": "run-1"}
    assert "proxy" not in query(choice["url"])


def test_valid_proxy_used_only_when_preferred(tmp_path):
    plant(tmp_path)
    skipped = choose_preview(VIDEO, repository=tmp_path, source_sha256=SHA, prefer_proxy=False)
    assert skipped["source"] == "original"
    assert "proxy" not in query(skipped["url"])
    chosen = choose_preview(VIDEO, repository=tmp_path, source_sha256=SHA, prefer_proxy=True)
    assert chosen["source"] == "proxy"
    assert query(chosen["url"]) == {"project": "artifacts/demo", "run": "run-1", "proxy": "1"}


def test_foreign_or_invalid_proxy_url_falls_back_to_original(tmp_path):
    plant(tmp_path)
    for bad in (
        "/api/media?project=artifacts/other&run=run-1&proxy=1",
        "/api/media?project=artifacts/demo&run=run-2&proxy=1",
        "/api/media?project=artifacts/demo&run=run-1",
        "http://example.com/api/media?project=artifacts/demo&run=run-1&proxy=1",
        "/api/other?project=artifacts/demo&run=run-1&proxy=1",
        r"G:\cache\proxy.mp4",
    ):
        choice = choose_preview(
            VIDEO, repository=tmp_path, source_sha256=SHA, prefer_proxy=True, proxy_url=bad
        )
        assert choice["source"] == "original", bad
        assert "proxy" not in query(choice["url"]), bad


def test_matching_proxy_url_is_accepted(tmp_path):
    plant(tmp_path)
    choice = choose_preview(
        VIDEO,
        repository=tmp_path,
        source_sha256=SHA,
        prefer_proxy=True,
        proxy_url="/api/media?project=artifacts/demo&run=run-1&proxy=1",
    )
    assert choice["source"] == "proxy"
    assert query(choice["url"])["proxy"] == "1"


def test_invalid_receipt_uses_original(tmp_path):
    plant(
        tmp_path,
        settings={"version": "tampered"},
    )
    # rewrite with bad settings already; also a bytes mismatch case
    choice = choose_preview(VIDEO, repository=tmp_path, source_sha256=SHA, prefer_proxy=True)
    assert choice["source"] == "original"
    plant(
        tmp_path / "other",
    )  # unused
    repo = tmp_path / "bytes"
    repo.mkdir()
    plant(repo, corrupt=True)
    assert (
        choose_preview(VIDEO, repository=repo, source_sha256=SHA, prefer_proxy=True)["source"]
        == "original"
    )
    # receipt for a different source hash stored under this folder
    repo2 = tmp_path / "sha"
    repo2.mkdir()
    plant(repo2, source_sha=OTHER)
    assert (
        choose_preview(VIDEO, repository=repo2, source_sha256=SHA, prefer_proxy=True)["source"]
        == "original"
    )


def test_rejects_non_media_video_url(tmp_path):
    plant(tmp_path)
    with pytest.raises(ValueError):
        choose_preview(
            "http://127.0.0.1/api/media?project=artifacts/demo&run=run-1",
            repository=tmp_path,
            source_sha256=SHA,
        )
    with pytest.raises(ValueError):
        choose_preview(
            "/api/evidence?project=artifacts/demo&run=run-1", repository=tmp_path, source_sha256=SHA
        )
