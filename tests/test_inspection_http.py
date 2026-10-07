import asyncio
import hashlib
import json
import os
import secrets
import threading
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import ProxyHandler, Request, build_opener

import pytest
from test_sqlite_store import CONFIG, bundle_fixture, event_fixture

from gamingcreator.application.providers import CostStatus, InvocationMetadata, ProviderUsage
from gamingcreator.application.storage import InvocationStatus, StoredInvocation
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.ui.media import MediaResource, VerifiedMediaCache, byte_range
from gamingcreator.ui.server import create_server, error_status
from gamingcreator.ui.service import cost_payload, registered_media


@contextmanager
def workspace(repository):
    # Windows may allocate a low port (e.g. 1723) that Chromium blocks.
    # Reserve the listening socket directly in a browser-safe high range.
    for _ in range(32):
        try:
            server = create_server("127.0.0.1", 20000 + secrets.randbelow(40000), repository)
            break
        except OSError:
            continue
    else:
        raise RuntimeError("No free browser-safe test port.")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(5)
        server.server_close()
        assert not thread.is_alive()


def get(base, path, **kwargs):
    request = Request(base + path, **kwargs)
    # The process proxy must not intercept the loopback inspection server.
    opener = build_opener(ProxyHandler({}))
    try:
        response = opener.open(request, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        return response.status, dict(response.headers), response.read()


def stored_project(root):
    source_root = root / "artifacts" / "fixture"
    source_root.mkdir(parents=True)
    bundle = bundle_fixture(source_root)
    project = source_root / "project"

    async def build():
        store = await SqliteTimelineStore.open(project)
        try:
            await store.create_run("run-1", bundle.asset, CONFIG)
            await store.begin_stage("run-1", "media", bundle.asset.sha256)
            await store.persist_media_bundle("run-1", bundle)
            await store.begin_stage("run-1", "vision", "a" * 64)
            event = event_fixture(bundle)
            await store.persist_timeline("run-1", "vision", (event,), (), "b" * 64)
            await store.complete_run("run-1")
        finally:
            await store.close()

    asyncio.run(build())
    return project, bundle


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, (0, 10, False)),
        ("bytes=2-5", (2, 4, True)),
        ("bytes=7-", (7, 3, True)),
        ("bytes=-3", (7, 3, True)),
        ("bytes=0-100", (0, 10, True)),
        ("bytes=-100", (0, 10, True)),
    ],
)
def test_single_range_contract(value, expected):
    assert byte_range(value, 10) == expected


@pytest.mark.parametrize(
    "value", ["bytes=10-", "bytes=5-2", "bytes=-0", "bytes=-", "bytes=0-1,3-4", "items=0-2"]
)
def test_invalid_ranges_are_rejected(value):
    with pytest.raises(ValueError):
        byte_range(value, 10)


def test_valid_http_errors_and_local_access_boundary(tmp_path):
    with workspace(tmp_path) as base:
        status, _, body = get(base, "/api/runs?project=missing")
        assert status == 400
        assert json.loads(body)["exitCode"] == 2
        assert get(base, "/api/runs?project=../outside")[0] == 400
        assert get(base, "/api/projects", headers={"Host": "attacker.invalid"})[0] == 403
        assert get(base, "/api/projects", headers={"Origin": "https://attacker.invalid"})[0] == 403
        assert get(base, "/api/projects", headers={"Sec-Fetch-Site": "cross-site"})[0] == 403
        assert get(base, "/missing")[0] == 404
    assert error_status(AppError("environment.model", "safe", ExitCode.ENVIRONMENT)) == 503
    assert error_status(AppError("storage.busy", "safe", ExitCode.STORAGE)) == 409


def test_health_identifies_repository_and_pid_without_model_or_storage(tmp_path):
    with workspace(tmp_path) as base:
        status, headers, body = get(base, "/api/health")
        assert status == 200 and headers["Cache-Control"] == "no-store"
        assert json.loads(body) == {
            "application": "gamingcreator-workspace",
            "apiVersion": 1,
            "capabilities": ["media-preparation-v1", "benchmark-workflow-v1"],
            "repository": str(tmp_path.resolve()),
            "pid": os.getpid(),
            "parentPid": os.getppid(),
        }
        assert get(base, "/api/health", headers={"Host": "external.invalid"})[0] == 403
        assert get(base, "/api/health", headers={"Origin": "https://external.invalid"})[0] == 403
        status, head_headers, body = get(base, "/api/health", method="HEAD")
        assert status == 200 and body == b"" and int(head_headers["Content-Length"]) > 0


def test_registered_media_range_head_and_evidence(tmp_path):
    project, bundle = stored_project(tmp_path)
    query = urlencode({"project": str(project), "run": "run-1"})
    expected = bundle.asset.source_path.read_bytes()
    with workspace(tmp_path) as base:
        status, headers, body = get(base, "/api/media?" + query, headers={"Range": "bytes=2-8"})
        assert (status, body) == (206, expected[2:9])
        assert headers["Content-Range"] == f"bytes 2-8/{len(expected)}"
        assert headers["Accept-Ranges"] == "bytes"
        assert headers["X-Content-Type-Options"] == "nosniff"
        status, headers, body = get(base, "/api/media?" + query, method="HEAD")
        assert status == 200 and body == b""
        assert int(headers["Content-Length"]) == len(expected)
        status, headers, _ = get(base, "/api/media?" + query, headers={"Range": "bytes=9000-"})
        assert status == 416 and headers["Content-Range"] == f"bytes */{len(expected)}"
        evidence_query = query + "&" + urlencode({"id": bundle.images[0].evidence_id})
        assert get(base, "/api/evidence?" + evidence_query)[2] == bundle.images[0].path.read_bytes()
        assert get(base, "/api/evidence?" + query + "&id=other-run:image")[0] == 404
        assert get(base, "/api/media?" + query + "&path=toolchain.json")[2] == expected
        assert get(base, "/api/media?" + query + "&run=other-run")[0] == 400
        bundle.asset.source_path.write_bytes(b"changed source")
        status, _, body = get(base, "/api/media?" + query)
        assert status == 409 and json.loads(body)["code"] == "storage.integrity"


def test_inspect_empty_query_is_a_read_with_metadata(tmp_path):
    project, _ = stored_project(tmp_path)
    reference = project.relative_to(tmp_path).as_posix()
    query = urlencode({"project": reference, "run": "run-1", "query": "", "mode": "lexical"})
    with workspace(tmp_path) as base:
        status, _, body = get(base, "/api/inspect?" + query)
        payload = json.loads(body)
        assert status == 200 and payload["candidates"] == []
        assert payload["media"]["durationUs"] == 2_000_000
        assert payload["analysisKind"] == "frame_observations"
        assert payload["timeline"][0]["mechanicTags"] == ["fixture-mechanic"]
        assert payload["evidence"][0]["startUs"] == 100_000
        assert payload["stages"][0]["status"] == "completed"
        assert payload["retrievalVersion"] and payload["configHash"]
        for media_url in (payload["media"]["videoUrl"], payload["evidence"][0]["url"]):
            identity = parse_qs(urlparse(media_url).query)
            assert identity["project"] == [reference] and identity["run"] == ["run-1"]
            assert get(base, media_url)[0] == 200
        assert get(base, "/api/inspect?" + query + "&top=101")[0] == 400
        status, _, runs = get(base, "/api/runs?" + urlencode({"project": str(project)}))
        assert status == 200 and json.loads(runs)["runs"][0]["sourceName"] == "source.fixture"


def test_verified_media_invalidates_cached_stat(tmp_path):
    path = tmp_path / "source.mp4"
    path.write_bytes(b"original")
    resource = MediaResource(path, hashlib.sha256(b"original").hexdigest(), "video/mp4")
    cache = VerifiedMediaCache()
    with cache.open(resource) as stream:
        assert stream.read() == b"original"
    before = path.stat()
    path.write_bytes(b"mutation")
    # Coarse filesystem clocks can preserve mtime for two immediate equal-size writes.
    # This test checks invalidation when the registered stat identity changes.
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns + 2_000_000_000))
    with pytest.raises(AppError, match="媒体已更改"):
        with cache.open(resource):
            pass


def test_workspace_cannot_bind_public_interface(tmp_path):
    with pytest.raises(ValueError, match="127.0.0.1"):
        create_server("0.0.0.0", 0, tmp_path)


def test_workspace_cannot_share_a_live_port_with_another_preview(tmp_path):
    first = create_server("127.0.0.1", 0, tmp_path)
    try:
        with pytest.raises(OSError):
            create_server("127.0.0.1", first.server_port, tmp_path)
    finally:
        first.server_close()


def test_project_database_link_cannot_escape_repository(tmp_path):
    repository = tmp_path / "repository"
    project = repository / "artifacts" / "linked"
    project.mkdir(parents=True)
    outside = tmp_path / "outside.sqlite3"
    outside.write_bytes(b"outside repository")
    try:
        os.symlink(outside, project / "timeline.sqlite3")
    except OSError:
        pytest.skip("File symlinks are not permitted in this environment")
    with workspace(repository) as base:
        assert get(base, "/api/runs?project=artifacts/linked")[0] == 400
        assert json.loads(get(base, "/api/projects")[2])["projects"] == []


def test_single_evidence_lookup_does_not_hash_the_source(tmp_path, monkeypatch):
    project, bundle = stored_project(tmp_path)

    def no_full_hash(path):
        raise AssertionError("A thumbnail lookup must not scan the whole timeline")

    monkeypatch.setattr("gamingcreator.infrastructure.sqlite_store._hash", no_full_hash)
    resource = asyncio.run(registered_media(project, "run-1", bundle.images[0].evidence_id))
    assert resource.path == bundle.images[0].path
    with VerifiedMediaCache().open(resource) as stream:
        assert stream.read() == resource.path.read_bytes()


def test_missing_price_and_unverified_amount_are_not_known_cost():
    usage = ProviderUsage(
        original_cost=Decimal("9"),
        currency="CNY",
        cost_cny=Decimal("9"),
        cost_status=CostStatus.ESTIMATED,
    )
    metadata = InvocationMetadata(
        "deepseek",
        "model",
        "model",
        "revision",
        "prompt",
        "schema",
        1,
        usage,
    )
    invocation = StoredInvocation(
        "inv", "run", "vision", "request", InvocationStatus.COMPLETED, metadata, None
    )
    assert cost_payload((invocation,)) == {
        "knownCny": "0",
        "unknownAttempts": 1,
        "status": "unverified",
    }
    priced = replace(invocation, metadata=replace(metadata, price_version="fixed-price"))
    assert cost_payload((priced,))["knownCny"] == "9"
    uncertain = replace(
        priced,
        metadata=replace(priced.metadata, usage=replace(usage, cost_status=CostStatus.UNVERIFIED)),
    )
    assert cost_payload((priced, uncertain)) == {
        "knownCny": "9",
        "unknownAttempts": 1,
        "status": "unverified",
    }


def test_canonical_database_path_is_checked_even_on_hosts_without_symlink_privilege(
    tmp_path, monkeypatch
):
    repository = tmp_path / "repository"
    project = repository / "artifacts" / "linked"
    project.mkdir(parents=True)
    database = project / "timeline.sqlite3"
    database.write_bytes(b"database fixture")
    original = type(database).resolve

    def linked_resolve(path, *args, **kwargs):
        if path == database:
            return tmp_path / "outside.sqlite3"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(type(database), "resolve", linked_resolve)
    with workspace(repository) as base:
        assert get(base, "/api/runs?project=artifacts/linked")[0] == 400
        assert json.loads(get(base, "/api/projects")[2])["projects"] == []
