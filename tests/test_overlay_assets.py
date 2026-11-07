import asyncio
import shutil
import struct
import zlib
from pathlib import Path

import pytest

from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.media_process import run_media_process
from gamingcreator.infrastructure.overlay_assets import OverlayAssetLibrary


def chunk(kind, content):
    return (
        struct.pack(">I", len(content))
        + kind
        + content
        + struct.pack(">I", zlib.crc32(kind + content))
    )


def png(width=2, height=2, extra=b""):
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + extra
        + chunk(b"IDAT", zlib.compress((b"\0" + b"\xff\0\0\xff" * width) * height))
        + chunk(b"IEND", b"")
    )


@pytest.fixture
def library(tmp_path):
    tools = tmp_path / ".tools/ffmpeg/bin"
    tools.mkdir(parents=True)
    shutil.copyfile(Path(".tools/ffmpeg/bin/ffmpeg.exe"), tools / "ffmpeg.exe")
    return OverlayAssetLibrary(tmp_path)


def test_real_png_reopen_and_tamper(library):
    asset = asyncio.run(library.register_png(png(), "../../unsafe.png"))
    assert asset.public()["kind"] == "image"
    assert "path" not in asset.public()
    assert asset.path.read_bytes() == png()
    assert (
        OverlayAssetLibrary(library.repository).resolve(asset.asset_id, asset.receipt_sha256)
        == asset
    )
    asset.path.write_bytes(png(3, 2))
    with pytest.raises(ValueError, match="changed"):
        library.resolve(asset.asset_id, asset.receipt_sha256)


def test_real_cjk_sprite_alpha_and_full_length(library):
    async def run():
        asset = await library.register_text("中文测试" * 30)
        assert asset.text == "中文测试" * 30
        assert 100 < asset.width <= 4096
        assert asset.height < 128
        result = await run_media_process(
            [
                library._tool(),
                "-v",
                "error",
                "-i",
                str(asset.path),
                "-vf",
                "alphaextract",
                "-f",
                "rawvideo",
                "-",
            ],
            CancellationContext("alpha", 30),
        )
        assert min(result.stdout) == 0
        assert max(result.stdout) == 255
        return asset

    asset = asyncio.run(run())
    assert library.resolve(asset.asset_id, asset.receipt_sha256).public() == asset.public()


@pytest.mark.parametrize(
    "raw",
    [
        b"fake.png",
        png(extra=chunk(b"acTL", struct.pack(">II", 1, 0))),
        png(4097, 1),
        png() + b"trailing",
        b"x" * (8 * 1024**2 + 1),
    ],
    ids=["fake", "apng", "dimensions", "trailing", "bytes"],
)
def test_reject_invalid_bounded_png(library, raw):
    with pytest.raises(ValueError):
        asyncio.run(library.register_png(raw))


def test_fake_compressed_png_and_identity(library):
    raw = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", b"not zlib")
        + chunk(b"IEND", b"")
    )
    with pytest.raises(AppError):
        asyncio.run(library.register_png(raw))
    with pytest.raises(ValueError):
        library.resolve("../outside", "a" * 64)
    asset = asyncio.run(library.register_png(png()))
    with pytest.raises(ValueError):
        library.resolve(asset.asset_id, "0" * 64)


def test_concurrent_registration_preserves_both_records(library):
    async def run():
        return await asyncio.gather(library.register_png(png()), library.register_png(png()))

    assets = asyncio.run(run())
    assert assets[0].asset_id != assets[1].asset_id
    for asset in assets:
        assert library.resolve(asset.asset_id, asset.receipt_sha256) == asset


@pytest.mark.parametrize(
    "text", ["", "x" * 121, "line\nline", "{\\pos(1,1)}", "a\u2028b", "1 < 2", "A\u200bB"]
)
def test_plain_single_line_text(library, text):
    with pytest.raises(ValueError):
        asyncio.run(library.register_text(text))
    assert not library.root.exists()


def test_text_sprite_repository_with_apostrophe(tmp_path):
    repository = tmp_path / "Creator's repo"
    tools = repository / ".tools/ffmpeg/bin"
    tools.mkdir(parents=True)
    shutil.copyfile(Path(".tools/ffmpeg/bin/ffmpeg.exe"), tools / "ffmpeg.exe")
    library = OverlayAssetLibrary(repository)
    asset = asyncio.run(library.register_text("中文标题"))
    assert asset.kind == "text" and asset.text == "中文标题"
    assert library.resolve(asset.asset_id, asset.receipt_sha256) == asset
