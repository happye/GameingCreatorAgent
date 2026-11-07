"""Immutable local PNG assets and fixed-font text sprites; no client paths."""

import hashlib
import json
import os
import re
import shutil
import struct
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.creation_overlays import (
    CreationOverlays,
    OverlayAssetMetadata,
    validate_asset_budget,
    validate_overlay_text,
)
from gamingcreator.infrastructure.ffmpeg_filters import filter_path
from gamingcreator.infrastructure.local_files import read_bounded
from gamingcreator.infrastructure.local_paths import is_link
from gamingcreator.infrastructure.media_process import MediaOutputLimit, run_media_process

MAX_PNG_BYTES = 8 * 1024**2


def _safe(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    if str(path).startswith("\\\\") or any(is_link(p) for p in (path, *path.parents)):
        raise ValueError("Overlay storage must be local and contain no links.")
    return path


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _png(data: bytes) -> tuple[int, int]:
    if not 0 < len(data) <= MAX_PNG_BYTES or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("A bounded PNG is required.")
    offset, dimensions, ended = 8, None, False
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("Incomplete PNG chunk.")
        size = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4 : offset + 8]
        end = offset + 12 + size
        if (
            end > len(data)
            or zlib.crc32(data[offset + 4 : end - 4]) != struct.unpack_from(">I", data, end - 4)[0]
        ):
            raise ValueError("Invalid PNG chunk.")
        if offset == 8:
            if kind != b"IHDR" or size != 13:
                raise ValueError("PNG must start with IHDR.")
            width, height = struct.unpack_from(">II", data, offset + 8)
            if not (0 < width <= 4096 and 0 < height <= 4096 and width * height <= 16_000_000):
                raise ValueError("PNG dimensions exceed the pixel budget.")
            dimensions = width, height
        elif kind == b"IHDR":
            raise ValueError("Duplicate PNG header.")
        if kind in {b"acTL", b"fcTL", b"fdAT"}:
            raise ValueError("Animated PNG is unsupported.")
        if kind == b"IEND":
            if size or end != len(data):
                raise ValueError("PNG has trailing data.")
            ended = True
        offset = end
    if dimensions is None or not ended:
        raise ValueError("Incomplete PNG.")
    return dimensions


def _ass(text: str) -> str:
    return (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 4096\nPlayResY: 128\nWrapStyle: 2\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, "
        "Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Microsoft YaHei,28,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,"
        "0,0,0,0,100,100,0,0,1,0,0,7,16,16,16,1\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        f"Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,{text}\n"
    )


def _glyph_bounds(pixels: bytes) -> tuple[int, int]:
    points = [i // 4 for i in range(3, len(pixels), 4) if pixels[i]]
    if not points:
        raise ValueError("Text has no visible glyphs.")
    xs, ys = [i % 4096 for i in points], [i // 4096 for i in points]
    if max(xs) >= 4094 or max(ys) >= 126 or min(xs) <= 1 or min(ys) <= 1:
        raise ValueError("Text exceeds the fixed sprite canvas.")
    return max(xs) + 3, max(ys) + 3


@dataclass(frozen=True, slots=True)
class OverlayAsset:
    asset_id: str
    receipt_sha256: str
    kind: str
    width: int
    height: int
    path: Path
    text: str | None = None
    sprite_sha256: str = ""

    def public(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "assetId": self.asset_id,
            "assetReceiptSha256": self.receipt_sha256,
            "kind": self.kind,
            "width": self.width,
            "height": self.height,
        }
        if self.kind == "text":
            result["text"] = self.text
        return result


class OverlayAssetLibrary:
    def __init__(self, repository: Path):
        self.repository = _safe(repository)
        self.root = self.repository / "artifacts/overlay-assets"

    def _tool(self) -> str:
        return str(self.repository / ".tools/ffmpeg/bin/ffmpeg.exe")

    async def _decode(self, path: Path, context: CancellationContext) -> None:
        await run_media_process(
            [
                self._tool(),
                "-v",
                "error",
                "-xerror",
                "-nostdin",
                "-protocol_whitelist",
                "file",
                "-f",
                "image2",
                "-c:v",
                "png",
                "-i",
                str(path),
                "-f",
                "null",
                "-",
            ],
            context,
        )

    async def register_png(
        self,
        raw_bytes: bytes,
        original_name: str | None = None,
        context: CancellationContext | None = None,
    ) -> OverlayAsset:
        context = context or CancellationContext("overlay-png", 30)
        context.check_cancelled()
        width, height = _png(raw_bytes)
        # The optional display name is never a path or part of persisted identity.
        if original_name is not None and (
            not isinstance(original_name, str) or len(original_name) > 255
        ):
            raise ValueError("Overlay filename is too long.")
        directory = self._directory()
        path = directory / "sprite.png"
        with path.open("xb") as stream:
            stream.write(raw_bytes)
        await self._decode(path, context)
        context.check_cancelled()
        return self._publish(directory, raw_bytes, width, height, None)

    def _directory(self) -> Path:
        _safe(self.root).mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(self.root).free < 256 * 1024**2:
            raise ValueError("Insufficient free space for overlay assets.")
        directory = _safe(self.root / uuid4().hex)
        directory.mkdir()
        return directory

    async def register_text(
        self,
        text: str,
        context: CancellationContext | None = None,
    ) -> OverlayAsset:
        text = validate_overlay_text(text)
        context = context or CancellationContext("overlay-text", 30)
        context.check_cancelled()
        scratch = _safe(self.repository / ".cache/scratch")
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="overlay-", dir=scratch) as temporary:
            work = Path(temporary)
            ass = work / "text.ass"
            ass.write_text(_ass(text), encoding="utf-8")
            target = work / "sprite.png"
            escaped = filter_path(ass)
            await run_media_process(
                [
                    self._tool(),
                    "-v",
                    "error",
                    "-nostdin",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=black@0:s=4096x128,format=rgba",
                    "-vf",
                    f"ass=filename={escaped}:alpha=1",
                    "-frames:v",
                    "1",
                    "-fs",
                    str(MAX_PNG_BYTES),
                    str(target),
                ],
                context,
                output_limit=MediaOutputLimit(target, MAX_PNG_BYTES, 256 * 1024**2, 16 * 1024**2),
            )
            # Measure actual glyph bounds: refuse clipping, then crop the shared sprite.
            result = await run_media_process(
                [
                    self._tool(),
                    "-v",
                    "error",
                    "-i",
                    str(target),
                    "-f",
                    "rawvideo",
                    "-pix_fmt",
                    "rgba",
                    "-",
                ],
                context,
                max_stdout_bytes=4096 * 128 * 4,
            )
            width, height = _glyph_bounds(result.stdout)
            cropped = work / "cropped.png"
            await run_media_process(
                [
                    self._tool(),
                    "-v",
                    "error",
                    "-i",
                    str(target),
                    "-vf",
                    f"crop={width}:{height}:0:0",
                    "-frames:v",
                    "1",
                    "-fs",
                    str(MAX_PNG_BYTES),
                    str(cropped),
                ],
                context,
                output_limit=MediaOutputLimit(cropped, MAX_PNG_BYTES, 256 * 1024**2, 16 * 1024**2),
            )
            raw = read_bounded(cropped, MAX_PNG_BYTES)
        context.check_cancelled()
        directory = self._directory()
        with (directory / "sprite.png").open("xb") as stream:
            stream.write(raw)
        return self._publish(directory, raw, width, height, text)

    def _publish(
        self,
        directory: Path,
        raw: bytes,
        width: int,
        height: int,
        text: str | None,
    ) -> OverlayAsset:
        receipt = {
            "schemaVersion": 1,
            "assetId": directory.name,
            "kind": "image" if text is None else "text",
            "width": width,
            "height": height,
            "spriteSha256": _sha(raw),
            "sourceSha256": _sha(raw if text is None else text.encode()),
            "text": text,
        }
        data = json.dumps(receipt, ensure_ascii=False, sort_keys=True).encode()
        with (directory / "receipt.json").open("xb") as stream:
            stream.write(data)
        return self.resolve(directory.name, _sha(data))

    def resolve(self, asset_id: str, receipt_sha256: str) -> OverlayAsset:
        if not isinstance(asset_id, str) or not re.fullmatch("[a-f0-9]{32}", asset_id):
            raise ValueError("Invalid overlay asset identity.")
        if not isinstance(receipt_sha256, str) or not re.fullmatch("[a-f0-9]{64}", receipt_sha256):
            raise ValueError("Invalid overlay receipt identity.")
        directory = _safe(self.root / asset_id)
        data = read_bounded(_safe(directory / "receipt.json"), 16384)
        if _sha(data) != receipt_sha256:
            raise ValueError("Overlay receipt changed.")
        receipt = json.loads(data)
        fields = {
            "schemaVersion",
            "assetId",
            "kind",
            "width",
            "height",
            "spriteSha256",
            "sourceSha256",
            "text",
        }
        if not isinstance(receipt, dict) or set(receipt) != fields or receipt["schemaVersion"] != 1:
            raise ValueError("Invalid overlay receipt schema.")
        path = _safe(directory / "sprite.png")
        raw = read_bounded(path, MAX_PNG_BYTES)
        dimensions = _png(raw)
        text = receipt["text"]
        if receipt["kind"] == "text":
            source = validate_overlay_text(text).encode()
        elif receipt["kind"] == "image" and text is None:
            source = raw
        else:
            raise ValueError("Invalid overlay kind.")
        if (
            receipt["assetId"] != asset_id
            or dimensions != (receipt["width"], receipt["height"])
            or _sha(raw) != receipt["spriteSha256"]
            or _sha(source) != receipt["sourceSha256"]
        ):
            raise ValueError("Overlay bytes or metadata changed.")
        return OverlayAsset(
            asset_id,
            receipt_sha256,
            receipt["kind"],
            *dimensions,
            path,
            text,
            receipt["spriteSha256"],
        )


def resolve_overlay_assets(
    library: OverlayAssetLibrary, overlays: CreationOverlays
) -> tuple[OverlayAsset, ...]:
    assets = tuple(library.resolve(i.asset_id, i.asset_receipt_sha256) for i in overlays.items)
    for item, asset in zip(overlays.items, assets, strict=True):
        if item.kind != asset.kind or item.text != asset.text:
            raise ValueError("Overlay text or kind differs from its asset receipt.")
    validate_asset_budget(
        overlays,
        tuple(
            OverlayAssetMetadata(
                a.asset_id, a.receipt_sha256, a.path.stat().st_size, a.width, a.height
            )
            for a in assets
        ),
    )
    return assets
