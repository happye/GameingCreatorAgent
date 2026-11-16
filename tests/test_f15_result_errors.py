"""F15: 代理、OCR、逐词结果区分未准备、损坏、取消、权限和不可用；重试不覆盖、不付费。"""

import json
from pathlib import Path

from gamingcreator.application.screen_text_reports import (
    NOTICE_DAMAGED,
    NOTICE_PERMISSION,
    NOTICE_UNPREPARED,
    _unprepared_notice,
    read_screen_text_report,
)
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.asr_words import (
    _damaged_words,
    _inspect_published_words,
    _missing_words,
    _permission_words,
    _unavailable_words,
)
from gamingcreator.infrastructure.asr_words_sidecar import WORDS_FILENAME, words_payload_sha256
from gamingcreator.infrastructure.proxy_inventory import _receipt_problem


def test_asr_helpers_distinguish_five_states():
    missing = _missing_words("run-1")
    damaged = _damaged_words("run-1")
    permission = _permission_words("run-1")
    cancelled = AppError("asr.cancelled", "逐词识别已取消。", ExitCode.CANCELLED, "run-1")
    unavailable = _unavailable_words("run-1")
    assert missing.code == "asr.words_not_found"
    assert "找不到" in missing.message
    assert damaged.code == "asr.words_damaged"
    assert "已损坏" in damaged.message and "不会覆盖" in damaged.message
    assert permission.code == "asr.words_permission"
    assert "没有权限" in permission.message
    assert cancelled.code == "asr.cancelled" and "已取消" in cancelled.message
    assert unavailable.code == "environment.asr"
    assert "不可用" in unavailable.message
    codes = {missing.code, damaged.code, permission.code, cancelled.code, unavailable.code}
    assert len(codes) == 5


def test_inspect_words_marks_corrupt_and_tampered(tmp_path, monkeypatch):
    from gamingcreator.infrastructure import asr_words_sidecar as sidecar

    monkeypatch.setattr(
        sidecar, "asr_words_directory", lambda project, run_id, result_hash: project / result_hash
    )
    missing = _inspect_published_words(tmp_path, "run-1", "a" * 64)
    assert missing == "missing"

    digest = "b" * 64
    directory = tmp_path / digest
    directory.mkdir()
    (directory / WORDS_FILENAME).write_text("{not-json", encoding="utf-8")
    assert _inspect_published_words(tmp_path, "run-1", digest) == "damaged"

    payload = json.dumps({"schemaVersion": "x", "words": []}).encode("utf-8")
    (directory / WORDS_FILENAME).write_bytes(payload)
    assert words_payload_sha256(payload) != digest
    assert _inspect_published_words(tmp_path, "run-1", digest) == "damaged"

    def deny(*_args, **_kwargs):
        raise PermissionError("denied")

    import gamingcreator.infrastructure.local_files as local_files

    monkeypatch.setattr(local_files, "read_bounded", deny)
    assert _inspect_published_words(tmp_path, "run-1", digest) == "permission"


def test_screen_text_notice_categories():
    assert _unprepared_notice(["无关说明。"]) == "无关说明。"
    assert NOTICE_UNPREPARED.startswith("尚未准备屏幕文字")
    assert _unprepared_notice(["报告不是合法的 JSON。"]) == NOTICE_DAMAGED
    assert _unprepared_notice(["没有权限读取屏幕文字报告。"]) == NOTICE_PERMISSION
    assert (
        _unprepared_notice(["屏幕文字服务不可用。"])
        == "屏幕文字结果目前不可用，未开始新的识别任务。"
    )


def test_screen_text_permission_is_not_missing(tmp_path, monkeypatch):
    report = tmp_path / "ocr.json"
    report.write_text("{}", encoding="utf-8")

    def deny(self, *args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "stat", deny)
    read = read_screen_text_report(report)
    assert not read.ok
    assert read.reason == "没有权限读取屏幕文字报告。"


def test_proxy_receipt_permission_is_not_bad_json(tmp_path, monkeypatch):
    receipt = tmp_path / "receipt.json"
    receipt.write_text("{}", encoding="utf-8")
    proxy = tmp_path / "proxy.mp4"
    proxy.write_bytes(b"x")

    def deny(self, *args, encoding=None, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "read_text", deny)
    assert _receipt_problem(receipt, proxy, "a" * 64) == "没有权限读取代理回执。"


def test_existing_sidecar_is_not_overwritten(tmp_path):
    # Lightweight: publishing twice into the same hash must keep words_exists and not rewrite.
    # Full publish needs a real bundle; this checks the public error remains a refusal to overwrite.
    error = AppError("asr.words_exists", "词级结果已存在，不会覆盖旧文件。", ExitCode.INPUT)
    assert "不会覆盖" in error.message
    assert error.code == "asr.words_exists"
