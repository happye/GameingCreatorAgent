import asyncio
import hashlib
import json
import wave

import pytest

from gamingcreator.application.narration import LocalVoice, NarrationRequest
from gamingcreator.application.providers import CancellationContext
from gamingcreator.infrastructure import sapi_narration as sapi

VOICE = LocalVoice("installed-token", "Fixture voice", "804")


@pytest.fixture
def fake_engine(monkeypatch):
    async def invoke(mode, request_path, context):
        context.check_cancelled()
        if mode == "list":
            return json.dumps(
                [
                    {
                        "voiceId": VOICE.voice_id,
                        "description": VOICE.description,
                        "language": VOICE.language,
                    }
                ]
            ).encode()
        request = json.loads(request_path.read_text(encoding="utf-8"))
        with wave.open(request["wavPath"], "wb") as wav:
            wav.setparams((1, 2, 22050, 0, "NONE", "not compressed"))
            wav.writeframes(b"\x00\x01\x00\xff" * 1000)
        return b"{}"

    monkeypatch.setattr(sapi, "_invoke", invoke)


def test_roundtrip_plain_text_and_tamper(tmp_path, fake_engine):
    text = '<speak>中文 & "hello"</speak>\n$(`test`)'
    artifact = asyncio.run(
        sapi.synthesize_local_narration(
            NarrationRequest("r", "p", text, VOICE.voice_id),
            tmp_path / "output",
            CancellationContext("job", 30),
        )
    )
    assert artifact.text_path.read_bytes() == text.encode()
    assert artifact.wav_sha256 == hashlib.sha256(artifact.wav_path.read_bytes()).hexdigest()
    assert artifact.sample_count == 2000
    assert artifact.duration_seconds == 2000 / 22050
    receipt = json.loads(artifact.receipt_path.read_text(encoding="utf-8"))
    assert receipt["licenseStatus"] == "unknown"
    assert receipt["jobId"] == "job"
    assert set(path.name for path in artifact.directory.iterdir()) == {
        "narration.wav",
        "narration.txt",
        "receipt.json",
    }
    artifact.text_path.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="content differs"):
        sapi.read_narration_artifact(artifact.directory)


def test_fake_voice_and_output_conflict(tmp_path, fake_engine):
    request = NarrationRequest("r", "p", "中文", "missing")
    with pytest.raises(ValueError, match="not installed"):
        asyncio.run(
            sapi.synthesize_local_narration(request, tmp_path / "new", CancellationContext("j", 30))
        )
    assert not (tmp_path / "new").exists()
    existing = tmp_path / "existing"
    existing.mkdir()
    (existing / "original").write_bytes(b"preserve")
    with pytest.raises(FileExistsError):
        asyncio.run(
            sapi.synthesize_local_narration(
                NarrationRequest("r", "p", "中文", VOICE.voice_id),
                existing,
                CancellationContext("j", 30),
            )
        )
    assert (existing / "original").read_bytes() == b"preserve"


@pytest.mark.parametrize("failure", [asyncio.CancelledError, RuntimeError])
def test_failure_cleans_only_owned_directory(tmp_path, monkeypatch, fake_engine, failure):
    original = sapi._invoke

    async def fail(mode, request_path, context):
        if mode == "list":
            return await original(mode, request_path, context)
        (request_path.parent / "narration.wav").write_bytes(b"partial")
        raise failure()

    monkeypatch.setattr(sapi, "_invoke", fail)
    with pytest.raises(failure):
        asyncio.run(
            sapi.synthesize_local_narration(
                NarrationRequest("r", "p", "中文", VOICE.voice_id),
                tmp_path / "own",
                CancellationContext("j", 30),
            )
        )
    assert not (tmp_path / "own").exists()


@pytest.mark.parametrize("text", ["", " ", "x" * 10001, "x\x00", "x\x1b", "\ud800"])
def test_reject_invalid_text(text):
    with pytest.raises(ValueError):
        NarrationRequest("r", "p", text, VOICE.voice_id)


def test_real_chinese_sapi(tmp_path):
    voices = asyncio.run(sapi.list_local_voices())
    voice = next((voice for voice in voices if "804" in voice.language.split(";")), None)
    if voice is None:
        pytest.skip("No installed Simplified Chinese SAPI voice")
    artifact = asyncio.run(
        sapi.synthesize_local_narration(
            NarrationRequest(
                "real-request",
                "real-project",
                "这是一段本地中文旁白。<speak>文字与符号 & 都是纯文本。</speak>",
                voice.voice_id,
            ),
            tmp_path / "real",
            CancellationContext("real-job", 60),
        )
    )
    assert artifact.sample_count > 1000
    assert sapi.read_narration_artifact(artifact.directory) == artifact
    print(
        json.dumps(
            {
                "voiceId": voice.voice_id,
                "sampleRate": artifact.sample_rate,
                "channels": artifact.channels,
                "sampleCount": artifact.sample_count,
                "durationSeconds": artifact.duration_seconds,
                "wavSha256": artifact.wav_sha256,
                "receiptSha256": artifact.receipt_sha256,
            },
            ensure_ascii=False,
        )
    )


@pytest.mark.parametrize("target", ["narration.wav", "receipt.json"])
def test_changed_wave_or_receipt_is_rejected(tmp_path, fake_engine, target):
    artifact = asyncio.run(
        sapi.synthesize_local_narration(
            NarrationRequest("r", "p", "中文", VOICE.voice_id),
            tmp_path / "asset",
            CancellationContext("j", 30),
        )
    )
    path = artifact.directory / target
    if target == "receipt.json":
        receipt = json.loads(path.read_text(encoding="utf-8"))
        receipt["jobId"] = "different-job"
        path.write_text(json.dumps(receipt), encoding="utf-8")
    else:
        data = bytearray(path.read_bytes())
        data[-1] ^= 1
        path.write_bytes(data)
    with pytest.raises(ValueError):
        sapi.read_narration_artifact(artifact.directory, artifact.receipt_sha256)


def test_real_process_cancellation_and_timeout(tmp_path, monkeypatch):
    from gamingcreator.domain.errors import AppError

    original = sapi._invoke

    async def scenario():
        context = CancellationContext("cancel-job", 30)

        async def cancel_during_synthesis(mode, request_path, call_context):
            if mode == "list":
                return json.dumps(
                    [
                        {
                            "voiceId": VOICE.voice_id,
                            "description": VOICE.description,
                            "language": VOICE.language,
                        }
                    ]
                ).encode()
            # Exercise real job-isolated PowerShell, with cancellation before COM can finish.
            asyncio.get_running_loop().call_later(0.05, context.cancelled.set)
            return await original(mode, request_path, call_context)

        monkeypatch.setattr(sapi, "_invoke", cancel_during_synthesis)
        with pytest.raises(asyncio.CancelledError):
            await sapi.synthesize_local_narration(
                NarrationRequest("r", "p", "取消测试", VOICE.voice_id),
                tmp_path / "cancelled",
                context,
            )
        assert not (tmp_path / "cancelled").exists()
        request_path = tmp_path / "list.json"
        request_path.write_text("{}", encoding="utf-8")
        with pytest.raises(AppError) as captured:
            await original("list", request_path, CancellationContext("timeout-job", 0.001))
        assert captured.value.code == "media.timeout"

    asyncio.run(scenario())
