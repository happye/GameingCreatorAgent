"""Offline projection of non-200 provider bodies stays bounded and credential-free."""

from __future__ import annotations

import hashlib
import json

from gamingcreator.infrastructure.deepseek_vision import _http_error_projection


def test_empty_body_projection():
    assert _http_error_projection(b"")["bodyKind"] == "empty"


def test_json_error_message_is_truncated():
    message = "x" * 800
    body = json.dumps({"error": {"message": message, "type": "invalid_request_error"}}).encode()
    projection = _http_error_projection(body)
    assert projection["bodyKind"] == "json_object"
    assert projection["errorMessage"] == ("x" * 500)
    assert projection["errorType"] == "invalid_request_error"
    assert projection["responseSha256"] == hashlib.sha256(body).hexdigest()


def test_non_json_body_marked():
    body = b"not-json<"
    projection = _http_error_projection(body)
    assert projection["bodyKind"] == "non_json"
    assert "errorMessage" not in projection
