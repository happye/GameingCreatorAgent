"""Low-resolution editing proxies for long recordings, with hard size limits.

A proxy is only for smooth preview; renders always read the original source. Every proxy is
built in a private temporary directory with a byte budget enforced twice (FFmpeg -fs and the
shared MediaOutputLimit watcher), checked against the source duration, and only then moved into
place. Any failure removes the temporary directory: no partial proxy is ever kept.
"""

import json
import shutil
from fractions import Fraction
from pathlib import Path
from typing import Any
from uuid import uuid4

from gamingcreator.application.providers import CancellationContext
from gamingcreator.infrastructure.ffmpeg_media import hash_source
from gamingcreator.infrastructure.local_paths import is_link
from gamingcreator.infrastructure.media_process import MediaOutputLimit, run_media_process

HEIGHT = 360
VIDEO_MAX_RATE = 600_000
AUDIO_RATE = 64_000
SETTINGS: dict[str, object] = {
    "version": "editing-proxy-v1",
    "height": HEIGHT,
    "videoMaxRate": VIDEO_MAX_RATE,
    "audioRate": AUDIO_RATE,
    "codec": "h264+aac",
}
HARD_CAP_BYTES = 1024**3
DURATION_TOLERANCE = Fraction(1, 2)


def proxy_budget(duration_us: int) -> int:
    """Bytes allowed for one proxy: 1.5× the capped bitrate plus container room, ≤1 GiB."""
    if type(duration_us) is not int or duration_us <= 0:
        raise ValueError("Proxy needs a positive source duration.")
    rate = (VIDEO_MAX_RATE + AUDIO_RATE) // 8  # bytes per second
    return min(HARD_CAP_BYTES, int(Fraction(duration_us, 1_000_000) * rate * 3 / 2) + 8 * 1024**2)


def proxy_directory(repository: Path, source_sha256: str) -> Path:
    if len(source_sha256) != 64 or any(c not in "0123456789abcdef" for c in source_sha256):
        raise ValueError("Invalid source SHA256.")
    return repository.resolve() / ".cache/workspace/proxies" / source_sha256


def read_proxy(repository: Path, source_sha256: str) -> dict[str, Any] | None:
    """The saved proxy receipt if its file still matches, else None (never rebuilt here)."""
    directory = proxy_directory(repository, source_sha256)
    receipt_path, proxy = directory / "receipt.json", directory / "proxy.mp4"
    if not receipt_path.is_file() or not proxy.is_file() or is_link(proxy) or is_link(directory):
        return None
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (
        receipt.get("sourceSha256") != source_sha256
        or receipt.get("settings") != SETTINGS
        or receipt.get("bytes") != proxy.stat().st_size
    ):
        return None
    return {**receipt, "path": str(proxy)}


async def _duration_us(ffprobe: Path, path: Path, context: CancellationContext) -> int:
    result = await run_media_process(
        [str(ffprobe), "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        context,
    )
    return int(Fraction(json.loads(result.stdout)["format"]["duration"]) * 1_000_000)


async def make_proxy(
    repository: Path,
    source: Path,
    source_sha256: str,
    source_duration_us: int,
    context: CancellationContext,
    tools: Path | None = None,
) -> dict[str, Any]:
    existing = read_proxy(repository, source_sha256)
    if existing is not None:
        return {**existing, "reused": True}
    final = proxy_directory(repository, source_sha256)
    root = final.parent
    root.mkdir(parents=True, exist_ok=True)
    if any(is_link(p) for p in (root, *root.parents)):
        raise ValueError("Proxy directory cannot use links.")
    budget = proxy_budget(source_duration_us)
    temporary = root / f".building-{uuid4().hex}"
    temporary.mkdir()
    try:
        output = temporary / "proxy.mp4"
        tools = tools or repository.resolve() / ".tools/ffmpeg/bin"
        await run_media_process(
            [
                str(tools / "ffmpeg.exe"),
                "-nostdin",
                "-v",
                "error",
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-vf",
                f"scale=-2:{HEIGHT}:flags=bicubic,format=yuv420p",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "30",
                "-maxrate",
                str(VIDEO_MAX_RATE),
                "-bufsize",
                str(2 * VIDEO_MAX_RATE),
                "-c:a",
                "aac",
                "-b:a",
                str(AUDIO_RATE),
                "-ac",
                "1",
                "-movflags",
                "+faststart",
                "-fs",
                str(budget),
                str(output),
            ],
            context,
            output_limit=MediaOutputLimit(output, budget),
        )
        size = output.stat().st_size
        if size >= budget:
            raise ValueError("Proxy reached its byte budget; a truncated proxy is never kept.")
        duration = await _duration_us(tools / "ffprobe.exe", output, context)
        if abs(Fraction(duration - source_duration_us, 1_000_000)) > DURATION_TOLERANCE:
            raise ValueError("Proxy duration differs from the source.")
        receipt = {
            "schemaVersion": "editing-proxy-receipt-v1",
            "sourceSha256": source_sha256,
            "sourceDurationUs": source_duration_us,
            "settings": SETTINGS,
            "bytes": size,
            "budgetBytes": budget,
            "durationUs": duration,
            "proxySha256": await hash_source(output, context),
            "use": "preview-only; renders read the original source",
        }
        (temporary / "receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if final.exists():
            shutil.rmtree(final)
        temporary.rename(final)
        return {**receipt, "path": str(final / "proxy.mp4"), "reused": False}
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
