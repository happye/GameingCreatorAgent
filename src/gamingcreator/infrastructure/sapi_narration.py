"""Offline Windows SAPI synthesis in a cancellable, job-isolated subprocess."""

import asyncio
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
from gamingcreator.infrastructure.app_paths import scripts_directory
from gamingcreator.infrastructure.local_paths import is_link
from gamingcreator.infrastructure.media_process import run_media_process

_HELPER = scripts_directory() / "sapi-narration.ps1"
# Local Windows voices, and the paid cloud voices whose ids start with "cosyvoice:".
ENGINES = ("windows-sapi", "cosyvoice-v3-flash")


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        # Chunked: long narrations are checked without loading the whole file.
        read, audible = 0, False
        while read < count:
            data = audio.readframes(min(65536, count - read))
            if not data:
                break
            read += len(data) // (channels * width)
            audible = audible or any(data)
        if read != count or not audible:
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
    if receipt["engine"] not in ENGINES or receipt["licenseStatus"] != "unknown":
        raise ValueError("Invalid narration engine or license declaration.")
    voice_record = receipt["voice"]
    voice = LocalVoice(
        voice_record["voiceId"],
        voice_record["description"],
        voice_record["language"],
        receipt["engine"],
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
    wav_path = directory / "narration.wav"
    try:
        request_path.write_text(
            json.dumps(
                {"text": request.text, "voiceId": voice.voice_id, "wavPath": str(wav_path)},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        await _invoke("synthesize", request_path, context)
        request_path.unlink()
        return _seal(directory, request, voice, "windows-sapi", context)
    except BaseException:
        _discard(directory)
        raise


async def synthesize_cloud_narration(
    request: NarrationRequest, output_directory: Path, context: CancellationContext
) -> tuple[NarrationArtifact, int | None, str]:
    """One paid CosyVoice call; returns the asset, billed characters and provider request id."""
    from gamingcreator.infrastructure import cosyvoice_tts

    name = request.voice_id.removeprefix("cosyvoice:")
    if name not in cosyvoice_tts.VOICES or not request.voice_id.startswith("cosyvoice:"):
        raise ValueError("Requested cloud voice is not offered.")
    voice = LocalVoice(request.voice_id, cosyvoice_tts.VOICES[name], "zh-CN", "cosyvoice-v3-flash")
    directory = Path(output_directory).absolute()
    if any(is_link(p) for p in (directory, *directory.parents)):
        raise ValueError("Narration output cannot use links.")
    context.check_cancelled()
    directory.mkdir(parents=False, exist_ok=False)
    try:
        speech = await asyncio.to_thread(cosyvoice_tts.synthesize, request.text, name)
        with (directory / "narration.wav").open("xb") as stream:
            stream.write(speech.audio)
        artifact = _seal(directory, request, voice, "cosyvoice-v3-flash", context)
        return artifact, speech.billed_characters, speech.request_id
    except BaseException:
        _discard(directory)
        raise


def _discard(directory: Path) -> None:
    for name in ("receipt.json", "narration.txt", "narration.wav", "request.json"):
        with suppress(OSError):
            (directory / name).unlink(missing_ok=True)
    with suppress(OSError):
        directory.rmdir()


def _seal(
    directory: Path,
    request: NarrationRequest,
    voice: LocalVoice,
    engine: str,
    context: CancellationContext,
) -> NarrationArtifact:
    """Write the text and receipt next to a finished WAV, then read the asset back strictly."""
    wav_path, text_path, receipt_path = (
        directory / "narration.wav",
        directory / "narration.txt",
        directory / "receipt.json",
    )
    context.check_cancelled()
    rate, channels, width, count = _pcm(wav_path)
    with text_path.open("xb") as stream:
        stream.write(request.text.encode("utf-8"))
    receipt = {
        "schemaVersion": "creation-narration-receipt-v1",
        "jobId": context.run_id,
        "requestId": request.request_id,
        "projectId": request.project_id,
        "engine": engine,
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
    context.check_cancelled()
    with receipt_path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    return read_narration_artifact(directory)
