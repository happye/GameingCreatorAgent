"""Offline Windows SAPI synthesis in a cancellable, job-isolated subprocess."""

import hashlib
import json
import os
import sys
import tempfile
import wave
from contextlib import suppress
from pathlib import Path

from gamingcreator.application.narration import LocalVoice, NarrationArtifact, NarrationRequest
from gamingcreator.application.providers import CancellationContext
from gamingcreator.infrastructure.local_paths import is_link
from gamingcreator.infrastructure.media_process import run_media_process

_HELPER = Path(__file__).resolve().parents[3] / "scripts" / "sapi-narration.ps1"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def _invoke(mode: str, request_path: Path, context: CancellationContext) -> bytes:
    if sys.platform != "win32":
        raise ValueError("Local narration requires Windows SAPI.")
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    result = await run_media_process(
        [
            str(powershell),
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(_HELPER),
            "-Mode",
            mode,
            "-RequestPath",
            str(request_path),
        ],
        context,
        max_stdout_bytes=1024 * 1024,
        max_stderr_bytes=65536,
    )
    return result.stdout


async def list_local_voices(context: CancellationContext | None = None) -> tuple[LocalVoice, ...]:
    context = context or CancellationContext("local-voices", 30)
    cache = _HELPER.parent.parent / ".cache" / "narration"
    cache.mkdir(parents=True, exist_ok=True)
    if any(is_link(p) for p in (cache, *cache.parents)):
        raise ValueError("Narration scratch directory cannot use links.")
    with tempfile.TemporaryDirectory(prefix="voices-", dir=cache) as temporary:
        request_path = Path(temporary) / "request.json"
        request_path.write_text("{}", encoding="utf-8")
        records = json.loads((await _invoke("list", request_path, context)).decode("utf-8-sig"))
    voices = tuple(
        LocalVoice(item["voiceId"], item["description"], item["language"]) for item in records
    )
    if len({voice.voice_id for voice in voices}) != len(voices):
        raise ValueError("Duplicate installed voice identities.")
    return tuple(sorted(voices, key=lambda voice: voice.voice_id))


def _pcm(path: Path) -> tuple[int, int, int, int]:
    with wave.open(str(path), "rb") as audio:
        rate, channels, width, count = (
            audio.getframerate(),
            audio.getnchannels(),
            audio.getsampwidth(),
            audio.getnframes(),
        )
        if audio.getcomptype() != "NONE" or count <= 0 or rate <= 0 or channels <= 0:
            raise ValueError("Narration must be nonempty PCM WAV.")
        data = audio.readframes(count)
        if len(data) != count * channels * width or not any(data):
            raise ValueError("Narration PCM is truncated or silent.")
    return rate, channels, width, count


def read_narration_artifact(
    directory: Path, expected_receipt_sha256: str | None = None
) -> NarrationArtifact:
    directory = Path(directory)
    wav_path, text_path, receipt_path = (
        directory / "narration.wav",
        directory / "narration.txt",
        directory / "receipt.json",
    )
    for path in (wav_path, text_path, receipt_path, directory, *directory.parents):
        if is_link(path):
            raise ValueError("Narration assets cannot be symbolic links.")
    if expected_receipt_sha256 is not None and _sha(receipt_path) != expected_receipt_sha256:
        raise ValueError("Narration receipt content differs from expected SHA256.")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt["schemaVersion"] != "creation-narration-receipt-v1":
        raise ValueError("Unsupported narration receipt.")
    if receipt["engine"] != "windows-sapi" or receipt["licenseStatus"] != "unknown":
        raise ValueError("Invalid narration engine or license declaration.")
    voice_record = receipt["voice"]
    voice = LocalVoice(
        voice_record["voiceId"], voice_record["description"], voice_record["language"]
    )
    request = NarrationRequest(
        receipt["requestId"],
        receipt["projectId"],
        text_path.read_bytes().decode("utf-8"),
        voice.voice_id,
    )
    if not receipt["jobId"] or request.voice_id != voice.voice_id:
        raise ValueError("Invalid narration identity.")
    rate, channels, width, count = _pcm(wav_path)
    actual = {
        "sampleRate": rate,
        "channels": channels,
        "sampleWidth": width,
        "sampleCount": count,
        "durationSeconds": count / rate,
    }
    if receipt["audio"] != actual:
        raise ValueError("Narration WAV format differs from receipt.")
    wav_sha, text_sha = _sha(wav_path), _sha(text_path)
    if receipt["wavSha256"] != wav_sha or receipt["textSha256"] != text_sha:
        raise ValueError("Narration asset content differs from receipt.")
    return NarrationArtifact(
        directory,
        wav_path,
        text_path,
        receipt_path,
        _sha(receipt_path),
        voice,
        rate,
        channels,
        width,
        count,
        wav_sha,
        text_sha,
    )


async def synthesize_local_narration(
    request: NarrationRequest, output_directory: Path, context: CancellationContext
) -> NarrationArtifact:
    context.check_cancelled()
    voices = await list_local_voices(context)
    voice = next((item for item in voices if item.voice_id == request.voice_id), None)
    if voice is None:
        raise ValueError("Requested local voice is not installed.")
    directory = Path(output_directory).absolute()
    if any(is_link(p) for p in (directory, *directory.parents)):
        raise ValueError("Narration output cannot use links.")
    # Exclusive directory ownership: never merge into or erase another job's assets.
    directory.mkdir(parents=False, exist_ok=False)
    request_path = directory / "request.json"
    wav_path, text_path, receipt_path = (
        directory / "narration.wav",
        directory / "narration.txt",
        directory / "receipt.json",
    )
    try:
        request_path.write_text(
            json.dumps(
                {"text": request.text, "voiceId": voice.voice_id, "wavPath": str(wav_path)},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        await _invoke("synthesize", request_path, context)
        context.check_cancelled()
        rate, channels, width, count = _pcm(wav_path)
        with text_path.open("xb") as stream:
            stream.write(request.text.encode("utf-8"))
        receipt = {
            "schemaVersion": "creation-narration-receipt-v1",
            "jobId": context.run_id,
            "requestId": request.request_id,
            "projectId": request.project_id,
            "engine": "windows-sapi",
            "licenseStatus": "unknown",
            "voice": {
                "voiceId": voice.voice_id,
                "description": voice.description,
                "language": voice.language,
            },
            "audio": {
                "sampleRate": rate,
                "channels": channels,
                "sampleWidth": width,
                "sampleCount": count,
                "durationSeconds": count / rate,
            },
            "wavSha256": _sha(wav_path),
            "textSha256": _sha(text_path),
        }
        request_path.unlink()
        context.check_cancelled()
        with receipt_path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        return read_narration_artifact(directory)
    except BaseException:
        for path in (receipt_path, text_path, wav_path, request_path):
            with suppress(OSError):
                path.unlink(missing_ok=True)
        with suppress(OSError):
            directory.rmdir()
        raise
