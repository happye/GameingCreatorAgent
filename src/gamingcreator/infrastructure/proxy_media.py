"""Low-resolution editing proxies for long recordings, with hard size limits.

A proxy is only for smooth preview; renders always read the original source. Every proxy is
built in a private temporary directory with a byte budget enforced twice (FFmpeg -fs and the
shared MediaOutputLimit watcher), checked against the source duration, and only then moved into
place. Any failure removes the temporary directory: no partial proxy is ever kept.
"""

import json
import shutil
import time
from contextlib import suppress
from fractions import Fraction
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse
from uuid import uuid4

from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.errors import AppError, ExitCode
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


STALE_BUILD_SECONDS = 12 * 3600


def _is_sha(value: object) -> bool:
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )


def proxy_directory(repository: Path, source_sha256: str) -> Path:
    if not _is_sha(source_sha256):
        raise ValueError("Invalid source SHA256.")
    return repository.resolve() / ".cache/workspace/proxies" / source_sha256


def is_editing_proxy_file(path: Path) -> bool:
    """True when path is a kept editing-proxy file (proxy.mp4 next to its receipt)."""
    resolved = Path(path).resolve()
    return resolved.name == "proxy.mp4" and (resolved.parent / "receipt.json").is_file()


def reject_editing_proxy_source(path: Path) -> None:
    """Frame grabs, shot detection and renders must read the original recording."""
    if is_editing_proxy_file(path):
        raise AppError(
            "media.proxy_not_source",
            "取帧和成片必须使用原片，不能使用编辑代理。",
            ExitCode.INPUT,
        )


_proxy_bytes = None


def _proxy_cache(cache: Any = None) -> Any:
    """Reuse the caller's media cache when given, otherwise one process-wide verifier."""
    global _proxy_bytes
    if cache is not None:
        return cache
    if _proxy_bytes is None:
        from gamingcreator.infrastructure.verified_media import VerifiedMediaCache

        _proxy_bytes = VerifiedMediaCache()
    return _proxy_bytes


def load_proxy_receipt(repository: Path, source_sha256: str) -> dict[str, Any] | None:
    """Structural receipt and file, without hashing. Same-size tampers still look intact here."""
    directory = proxy_directory(repository, source_sha256)
    receipt_path, proxy = directory / "receipt.json", directory / "proxy.mp4"
    if not receipt_path.is_file() or not proxy.is_file() or is_link(proxy) or is_link(directory):
        return None
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(receipt, dict) or not _is_sha(receipt.get("proxySha256")):
        return None
    if (
        receipt.get("sourceSha256") != source_sha256
        or receipt.get("settings") != SETTINGS
        or receipt.get("bytes") != proxy.stat().st_size
    ):
        return None
    return {**receipt, "path": str(proxy)}


def read_proxy(repository: Path, source_sha256: str, *, cache: Any = None) -> dict[str, Any] | None:
    """The saved proxy receipt if its bytes still match, else None (never rebuilt here)."""
    receipt = load_proxy_receipt(repository, source_sha256)
    if receipt is None:
        return None
    from gamingcreator.domain.errors import AppError
    from gamingcreator.infrastructure.verified_media import MediaResource

    try:
        with _proxy_cache(cache).open(
            MediaResource(Path(receipt["path"]), receipt["proxySha256"], "video/mp4")
        ):
            pass
    except AppError:
        return None
    return receipt


async def _duration_us(ffprobe: Path, path: Path, context: CancellationContext) -> int:
    result = await run_media_process(
        [str(ffprobe), "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        context,
    )
    return int(Fraction(json.loads(result.stdout)["format"]["duration"]) * 1_000_000)


async def _has_audio_stream(ffprobe: Path, path: Path, context: CancellationContext) -> bool:
    """Whether the file already has an audio stream. Never invents one."""
    result = await run_media_process(
        [
            str(ffprobe),
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(path),
        ],
        context,
    )
    return bool(result.stdout.strip())


def _proxy_command(
    ffmpeg: Path, source: Path, output: Path, budget: int, include_audio: bool
) -> list[str]:
    """Build the preview proxy. Video only when the original has no audio track."""
    command = [
        str(ffmpeg),
        "-nostdin",
        "-v",
        "error",
        "-i",
        str(source),
        "-map",
        "0:v:0",
    ]
    if include_audio:
        command.extend(["-map", "0:a:0?", "-c:a", "aac", "-b:a", str(AUDIO_RATE), "-ac", "1"])
    else:
        command.extend(["-an"])
    command.extend(
        [
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
            "-movflags",
            "+faststart",
            "-fs",
            str(budget),
            str(output),
        ]
    )
    return command


def _place_proxy(temporary: Path, final: Path) -> None:
    """Move the finished proxy into place. Windows may briefly hold a handle after FFmpeg exits."""
    if final.exists():
        shutil.rmtree(final)
    delay = 0.05
    for attempt in range(5):
        try:
            temporary.rename(final)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(delay)
            delay *= 2


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
    # A file replaced at the registered path must never be served as that recording's preview.
    if await hash_source(source, context) != source_sha256:
        raise ValueError("Source bytes do not match the registered recording.")
    root = final.parent
    root.mkdir(parents=True, exist_ok=True)
    if any(is_link(p) for p in (root, *root.parents)):
        raise ValueError("Proxy directory cannot use links.")
    budget = proxy_budget(source_duration_us)
    # A build killed outright leaves its folder; any older than the 6 h build limit is stale.
    cutoff = time.time() - STALE_BUILD_SECONDS
    for stale in root.glob(".building-*"):
        with suppress(OSError):
            if stale.is_dir() and not is_link(stale) and stale.stat().st_mtime < cutoff:
                shutil.rmtree(stale, ignore_errors=True)
    temporary = root / f".building-{uuid4().hex}"
    temporary.mkdir()
    try:
        output = temporary / "proxy.mp4"
        tools = tools or repository.resolve() / ".tools/ffmpeg/bin"
        include_audio = await _has_audio_stream(tools / "ffprobe.exe", source, context)
        await run_media_process(
            _proxy_command(tools / "ffmpeg.exe", source, output, budget, include_audio),
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
            "sourceHasAudio": include_audio,
            "proxyHasAudio": include_audio,
            "use": "preview-only; renders read the original source",
        }
        (temporary / "receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        _place_proxy(temporary, final)
        return {**receipt, "path": str(final / "proxy.mp4"), "reused": False}
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)


def _media_query(url: str) -> dict[str, str] | None:
    """只接受相对路径的 /api/media，避免把外站或任意文件路径当成预览地址。"""
    parsed = urlparse(url)
    if parsed.scheme or parsed.netloc or parsed.path != "/api/media":
        return None
    raw = parse_qs(parsed.query, keep_blank_values=True)
    if any(len(values) != 1 for values in raw.values()):
        return None
    query = {key: values[0] for key, values in raw.items()}
    if not query.get("project") or not query.get("run"):
        return None
    return query


def choose_preview(
    video_url: str,
    *,
    repository: Path,
    source_sha256: str,
    prefer_proxy: bool = False,
    proxy_url: str | None = None,
) -> dict[str, str | None]:
    """在原片和已核代理之间选预览地址。不建代理；回执无效或不是同一条素材时用原片。"""
    query = _media_query(video_url)
    if query is None:
        raise ValueError("Preview URL must be a same-origin /api/media address for one recording.")
    original = "/api/media?" + urlencode(
        {key: value for key, value in query.items() if key != "proxy"}
    )
    receipt = read_proxy(repository, source_sha256)
    if not prefer_proxy or receipt is None:
        return {
            "url": original,
            "source": "original",
            "reason": None if receipt is None else "preference",
        }
    if proxy_url is not None:
        offered = _media_query(proxy_url)
        if (
            offered is None
            or offered.get("project") != query["project"]
            or offered.get("run") != query["run"]
            or offered.get("proxy") != "1"
        ):
            return {"url": original, "source": "original", "reason": "mismatched-proxy-url"}
    return {
        "url": "/api/media?"
        + urlencode(
            {**{key: value for key, value in query.items() if key != "proxy"}, "proxy": "1"}
        ),
        "source": "proxy",
        "reason": None,
    }
