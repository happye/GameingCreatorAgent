"""Actual local overlay HTTP publication without model or voice calls."""

import base64
import json
import threading
from http.client import HTTPConnection

import pytest
from test_overlay_assets import library, png  # noqa: F401

from gamingcreator.domain.creation_overlays import CreationOverlays
from gamingcreator.ui.overlay_jobs import resolve_assets
from gamingcreator.ui.server import create_server


@pytest.fixture
def http(library):  # noqa: F811
    server = create_server("127.0.0.1", 0, library.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(value=None, path="/api/creation/overlay-assets", origin=None):
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=30)
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        connection.request(
            "GET" if value is None else "POST",
            path,
            json.dumps(value) if value is not None else None,
            headers,
        )
        response = connection.getresponse()
        data = response.read()
        result = response.status, response.getheader("Content-Type"), data
        connection.close()
        return result

    try:
        yield request, library
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_png_and_text_register_then_read_exact_asset(http):
    request, assets = http
    for value in (
        {
            "kind": "image",
            "fileName": "../../logo.png",
            "dataBase64": base64.b64encode(png()).decode(),
        },
        {"kind": "text", "text": "中文标题"},
    ):
        status, _, data = request(value)
        assert status == 200, data
        asset = json.loads(data)
        resolved = assets.resolve(asset["assetId"], asset["assetReceiptSha256"])
        status, content_type, image = request(path=asset["imageUrl"])
        assert status == 200 and content_type == "image/png"
        assert image == resolved.path.read_bytes()
        assert "sourcePath" not in asset and "path" not in asset
    status, _, _ = request(path=asset["imageUrl"] + "&extra=true")
    assert status == 400


@pytest.mark.parametrize(
    "value",
    [
        {"kind": "text", "text": "1 < 2"},
        {"kind": "text", "text": "title", "path": "C:/secret"},
        {"kind": "image", "fileName": "a.png", "dataBase64": "not base64!"},
        {"kind": "unknown"},
    ],
)
def test_bad_asset_requests_publish_nothing(http, value):
    request, assets = http
    assert request(value)[0] == 400
    assert not assets.root.exists()


def test_asset_origin_and_query_gate(http):
    request, assets = http
    assert request({"kind": "text", "text": "test"}, origin="https://example.com")[0] == 403
    assert (
        request({"kind": "text", "text": "test"}, path="/api/creation/overlay-assets?extra=1")[0]
        == 400
    )
    assert not assets.root.exists()


def test_layer_kind_and_text_cannot_borrow_other_asset_identity(library):  # noqa: F811
    from gamingcreator.ui.overlay_jobs import register_asset

    asset = register_asset(library, {"kind": "text", "text": "Original"})
    row = dict(
        overlayId="a" * 32,
        kind="text",
        text="Changed",
        startFrame=0,
        endFrame=30,
        x=0,
        y=0,
        width=1000,
        fadeInFrames=0,
        fadeOutFrames=0,
        assetId=asset["assetId"],
        assetReceiptSha256=asset["assetReceiptSha256"],
    )
    overlays = CreationOverlays.from_json({"schemaVersion": "creation-overlays-v1", "items": [row]})
    with pytest.raises(ValueError, match="text or kind"):
        resolve_assets(library, overlays)


def test_sprite_replaced_after_resolve_is_not_served(http, monkeypatch):
    from gamingcreator.infrastructure.overlay_assets import OverlayAssetLibrary

    request, assets = http
    status, _, data = request(
        {
            "kind": "image",
            "fileName": "logo.png",
            "dataBase64": base64.b64encode(png()).decode(),
        }
    )
    assert status == 200
    original = OverlayAssetLibrary.resolve

    def replaced(self, asset_id, receipt):
        asset = original(self, asset_id, receipt)
        asset.path.write_bytes(png(3, 2))
        return asset

    monkeypatch.setattr(OverlayAssetLibrary, "resolve", replaced)
    status, _, body = request(path=json.loads(data)["imageUrl"])
    assert status != 200
    assert body != png(3, 2)
