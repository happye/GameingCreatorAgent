import asyncio
import json
import math
import shutil
import struct
import wave
from pathlib import Path

import pytest

from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.ffmpeg_media import hash_file
from gamingcreator.infrastructure.music_library import MusicLibrary

TOOLS = Path("G:/Tools/ChatGPTRepo/GameingCreatorAgent/.tools/ffmpeg/bin")


@pytest.fixture
def library(tmp_path):
    # Fixed tools are copied read-only from the existing pinned installation; no downloads.
    target = tmp_path / ".tools/ffmpeg/bin"
    target.mkdir(parents=True)
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        shutil.copyfile(TOOLS / name, target / name)
    return MusicLibrary(tmp_path)


def tone(path):
    with wave.open(str(path), "wb") as writer:
        writer.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        writer.writeframes(
            b"".join(
                struct.pack("<h", int(5000 * math.sin(i * 880 * math.tau / 48000)))
                for i in range(4800)
            )
        )
    return path


def register(library, source, evidence=None):
    return asyncio.run(
        library.register(
            source,
            "测试音调",
            "本地生成仅测试",
            "test_only",
            evidence,
            CancellationContext("test", 60),
        )
    )


def test_real_decode_register_resolve_catalog_and_immutable_sources(library, tmp_path):
    source = tone(tmp_path / "tone.wav")
    evidence = tmp_path / "license.txt"
    evidence.write_text("test-only declaration", encoding="utf-8")
    before = hash_file(source), hash_file(evidence)
    track = register(library, source, evidence)
    assert track.duration_us == 100_000
    assert track.sha256 == before[0]
    assert library.resolve(track.track_id, track.receipt_sha256) == track
    catalog = library.catalog()
    assert catalog["issues"] == [] and len(catalog["tracks"]) == 1
    public = json.dumps(catalog)
    assert str(source) not in public and "test-only declaration" not in public
    assert track.public()["licenseStatus"] == "test_only"
    assert before == (hash_file(source), hash_file(evidence))
    second = register(library, source)
    assert second.track_id != track.track_id
    assert library.resolve(track.track_id, track.receipt_sha256) == track


@pytest.mark.parametrize("target", ["audio", "receipt", "evidence"])
def test_tampered_registration_rejected(library, tmp_path, target):
    source = tone(tmp_path / "tone.wav")
    evidence = tmp_path / "evidence.txt"
    evidence.write_text("declaration")
    track = register(library, source, evidence)
    path = {
        "audio": track.path,
        "receipt": track.path.parent / "receipt.json",
        "evidence": track.path.parent / "license-evidence",
    }[target]
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError):
        library.resolve(track.track_id, track.receipt_sha256)
    assert library.catalog()["issues"]


@pytest.mark.parametrize("suffix", [".m3u", ".wav"])
def test_playlist_or_invalid_audio_has_no_receipt(library, tmp_path, suffix):
    source = tmp_path / ("invalid" + suffix)
    source.write_text("https://example.com/audio.mp3")
    with pytest.raises((ValueError, AppError)):
        register(library, source)
    assert not list(library.root.glob("*/receipt.json"))


def test_link_root_and_unknown_identity_rejected(library, tmp_path):
    with pytest.raises(ValueError):
        library.resolve("../foreign", "a" * 64)
    source = tone(tmp_path / "tone.wav")
    linked = tmp_path / "linked.wav"
    try:
        linked.symlink_to(source)
    except OSError:
        pytest.skip("Windows symbolic link permission unavailable")
    with pytest.raises(ValueError):
        register(library, linked)


def test_cli_register_dispatch_and_no_arbitrary_library(library, tmp_path, monkeypatch):
    from gamingcreator.cli.main import _dispatch, _parser

    source = tone(tmp_path / "tone.wav")
    monkeypatch.chdir(tmp_path)
    args = _parser().parse_args(
        [
            "register-music",
            "--input",
            str(source),
            "--title",
            "test tone",
            "--source-description",
            "generated locally",
            "--license-status",
            "test_only",
        ]
    )
    result = _dispatch(args)
    assert result["licenseStatus"] == "test_only"
    assert result["trackReceiptSha256"]
    assert not hasattr(args, "library")


def test_cancelled_register_no_receipt(library, tmp_path):
    source = tone(tmp_path / "tone.wav")
    context = CancellationContext("cancelled", 60)
    context.cancelled.set()
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(library.register(source, "test", "generated", "unknown", None, context))
    assert not list(library.root.glob("*/receipt.json"))


def test_limits_and_source_change_during_decode(library, tmp_path, monkeypatch):
    import gamingcreator.infrastructure.music_library as implementation

    source = tone(tmp_path / "tone.wav")
    before = hash_file(source)
    real = implementation.run_media_process

    async def mutate(arguments, context):
        result = await real(arguments, context)
        if "-xerror" in arguments:
            source.write_bytes(source.read_bytes() + b"mutated")
        return result

    monkeypatch.setattr(implementation, "run_media_process", mutate)
    with pytest.raises(ValueError, match="changed"):
        register(library, source)
    assert hash_file(source) != before
    assert not list(library.root.glob("*/receipt.json"))
    monkeypatch.setattr(implementation, "MAX_AUDIO_BYTES", 1)
    with pytest.raises(ValueError, match="bounded"):
        register(library, source)
