"""Immutable local audio registration with receipts, bounded copies and no network."""

import json
import os
import stat
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any
from uuid import uuid4

from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.creation_audio import _hex
from gamingcreator.infrastructure.ffmpeg_media import hash_file
from gamingcreator.infrastructure.media_process import run_media_process

MAX_AUDIO_BYTES = 500 * 1024 * 1024
MAX_EVIDENCE_BYTES = 10 * 1024 * 1024
_FORMATS = {
    ".wav": "wav",
    ".mp3": "mp3",
    ".flac": "flac",
    ".ogg": "ogg",
    ".m4a": "mov",
    ".mp4": "mov",
    ".aac": "aac",
}
_LICENSES = {"unknown", "user_declared", "test_only"}


@dataclass(frozen=True, slots=True)
class MusicTrack:
    track_id: str
    title: str
    path: Path
    sha256: str
    receipt_sha256: str
    duration_us: int
    license_status: str
    source_description: str

    def public(self) -> dict[str, Any]:
        return {
            "trackId": self.track_id,
            "title": self.title,
            "trackReceiptSha256": self.receipt_sha256,
            "mediaSha256": self.sha256,
            "durationUs": self.duration_us,
            "licenseStatus": self.license_status,
            "bpm": None,
            "mood": None,
            "drop": None,
        }


def _safe(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    if str(path).startswith("\\\\"):
        raise ValueError("Music inputs must be local files.")
    for candidate in (path, *path.parents):
        if candidate.exists() or candidate.is_symlink():
            info = candidate.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("Music paths cannot contain links or reparse points.")
    return path


def _file(path: Path, maximum: int) -> Path:
    path = _safe(path)
    if not stat.S_ISREG(path.stat().st_mode) or not 0 < path.stat().st_size <= maximum:
        raise ValueError("Music input must be a bounded nonempty regular file.")
    return path


def _description(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 2000:
        raise ValueError("Music title and source description must be nonempty bounded text.")
    if any(ord(c) < 32 for c in value):
        raise ValueError("Music metadata contains control characters.")
    return value


class MusicLibrary:
    def __init__(self, repository: Path):
        self.repository = _safe(repository)
        self.root = self.repository / ".cache/workspace/music"

    async def register(
        self,
        source: Path,
        title: str,
        source_description: str,
        license_status: str,
        license_evidence: Path | None,
        context: CancellationContext,
    ) -> MusicTrack:
        title, source_description = _description(title), _description(source_description)
        if license_status not in _LICENSES:
            raise ValueError("Music license status is a declaration, never verified.")
        source = _file(source, MAX_AUDIO_BYTES)
        if source.suffix.lower() not in _FORMATS:
            raise ValueError("Unsupported ordinary audio container.")
        evidence = None if license_evidence is None else _file(license_evidence, MAX_EVIDENCE_BYTES)
        _safe(self.root).mkdir(parents=True, exist_ok=True)
        track_id = uuid4().hex
        directory = _safe(self.root / track_id)
        directory.mkdir()
        files: dict[str, Any] = {}
        for original, name, maximum in [
            (source, "audio" + source.suffix.lower(), MAX_AUDIO_BYTES),
            *([] if evidence is None else [(evidence, "license-evidence", MAX_EVIDENCE_BYTES)]),
        ]:
            before = hash_file(_file(original, maximum))
            target = _safe(directory / name)
            copied = 0
            with original.open("rb") as reader, target.open("xb") as writer:
                while chunk := reader.read(1024 * 1024):
                    context.check_cancelled()
                    copied += len(chunk)
                    if copied > maximum:
                        raise ValueError("Music input grew beyond its size limit.")
                    writer.write(chunk)
            if hash_file(_file(original, maximum)) != before or hash_file(target) != before:
                raise ValueError("Music input changed during registration.")
            files[name] = {"sha256": before, "size": copied}
        audio_name = "audio" + source.suffix.lower()
        audio = directory / audio_name
        tool = self.repository / ".tools/ffmpeg/bin"
        input_args = [
            "-protocol_whitelist",
            "file",
            "-f",
            _FORMATS[source.suffix.lower()],
            "-i",
            str(audio),
        ]
        probe = await run_media_process(
            [
                str(tool / "ffprobe.exe"),
                "-v",
                "error",
                *input_args,
                "-show_streams",
                "-show_format",
                "-of",
                "json",
            ],
            context,
        )
        info = json.loads(probe.stdout)
        if not any(s.get("codec_type") == "audio" for s in info.get("streams", [])):
            raise ValueError("Music file has no audio stream.")
        duration = Fraction(info["format"]["duration"])
        duration_us = (duration * 1_000_000).__ceil__()
        if duration_us <= 0:
            raise ValueError("Music duration must be positive.")
        await run_media_process(
            [
                str(tool / "ffmpeg.exe"),
                "-v",
                "error",
                "-xerror",
                "-nostdin",
                *input_args,
                "-map",
                "0:a:0",
                "-vn",
                "-f",
                "null",
                "-",
            ],
            context,
        )
        # Source and copied bytes remain fixed through the complete decode.
        if hash_file(_file(source, MAX_AUDIO_BYTES)) != files[audio_name]["sha256"]:
            raise ValueError("Music source changed while decoding.")
        if (
            evidence is not None
            and hash_file(_file(evidence, MAX_EVIDENCE_BYTES))
            != files["license-evidence"]["sha256"]
        ):
            raise ValueError("Music license evidence changed while decoding.")
        for name, entry in files.items():
            if hash_file(_file(directory / name, MAX_AUDIO_BYTES)) != entry["sha256"]:
                raise ValueError("Registered music bytes changed.")
        metadata = {
            "schemaVersion": "music-track-v1",
            "trackId": track_id,
            "title": title,
            "sourceDescription": source_description,
            "licenseStatus": license_status,
            "audioFile": audio_name,
            "durationUs": duration_us,
            "files": files,
        }
        context.check_cancelled()
        encoded = json.dumps(metadata, ensure_ascii=False, sort_keys=True).encode("utf-8")
        pending = _safe(directory / "receipt.partial.json")
        with pending.open("xb") as writer:
            writer.write(encoded)
        context.check_cancelled()
        pending.rename(_safe(directory / "receipt.json"))
        return self.resolve(track_id, hash_file(directory / "receipt.json"))

    def resolve(self, track_id: str, receipt_sha256: str) -> MusicTrack:
        _hex(track_id, 32)
        _hex(receipt_sha256, 64)
        directory = _safe(self.root / track_id)
        receipt = _file(directory / "receipt.json", 65536)
        if hash_file(receipt) != receipt_sha256:
            raise ValueError("Music receipt identity changed.")
        metadata = json.loads(receipt.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict) or set(metadata) != {
            "schemaVersion",
            "trackId",
            "title",
            "sourceDescription",
            "licenseStatus",
            "audioFile",
            "durationUs",
            "files",
        }:
            raise ValueError("Invalid music receipt fields.")
        audio = metadata.get("audioFile")
        if not isinstance(audio, str) or audio not in {"audio" + suffix for suffix in _FORMATS}:
            raise ValueError("Invalid registered music file.")
        files = metadata.get("files")
        if not isinstance(files, dict) or set(files) not in ({audio}, {audio, "license-evidence"}):
            raise ValueError("Invalid registered music attachments.")
        for name, entry in files.items():
            path = _file(directory / name, MAX_AUDIO_BYTES if name == audio else MAX_EVIDENCE_BYTES)
            if (
                not isinstance(entry, dict)
                or set(entry) != {"sha256", "size"}
                or type(entry["size"]) is not int
                or path.stat().st_size != entry["size"]
                or hash_file(path) != entry["sha256"]
            ):
                raise ValueError("Registered music file changed.")
        if (
            metadata.get("schemaVersion") != "music-track-v1"
            or metadata.get("trackId") != track_id
            or not isinstance(metadata.get("licenseStatus"), str)
            or metadata.get("licenseStatus") not in _LICENSES
            or type(metadata.get("durationUs")) is not int
            or metadata["durationUs"] <= 0
        ):
            raise ValueError("Invalid music registration metadata.")
        return MusicTrack(
            track_id,
            _description(metadata.get("title")),
            directory / audio,
            files[audio]["sha256"],
            receipt_sha256,
            metadata["durationUs"],
            metadata["licenseStatus"],
            _description(metadata.get("sourceDescription")),
        )

    def catalog(self) -> dict[str, Any]:
        tracks: list[dict[str, Any]] = []
        issues: list[dict[str, str]] = []
        root = _safe(self.root)
        if not root.exists():
            return {"tracks": tracks, "issues": issues}
        for directory in sorted(root.iterdir()):
            try:
                _hex(directory.name, 32)
                receipt = _file(directory / "receipt.json", 65536)
                tracks.append(self.resolve(directory.name, hash_file(receipt)).public())
            except (OSError, ValueError, KeyError, TypeError):
                issues.append(
                    {
                        "trackId": directory.name,
                        "message": "Music registration is incomplete or damaged.",
                    }
                )
        return {"tracks": tracks, "issues": issues}
