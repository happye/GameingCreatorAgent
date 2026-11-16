"""F 组共用的隔离混合源：24/30/60fps、可变帧率、非零起点、有声/无声、中文文件名。

只在临时目录里生成短素材，不下载、也不分析用户录像。产物有字节和空间上限。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from fractions import Fraction
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from test_sqlite_store import CONFIG, HASH

from gamingcreator.application.media import SamplingParameters
from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.models import SemanticEvent
from gamingcreator.domain.time import SourceRange
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.ui.server import create_server

ROOT = Path(__file__).resolve().parents[1]
ROOT = next(
    (path for path in (ROOT, *ROOT.parents) if (path / ".tools/ffmpeg/bin/ffmpeg.exe").is_file()),
    ROOT,
)
FFMPEG = ROOT / ".tools/ffmpeg/bin/ffmpeg.exe"
FFPROBE = ROOT / ".tools/ffmpeg/bin/ffprobe.exe"

MIN_FREE_BYTES = 200 * 1024 * 1024
MAX_PRODUCT_BYTES = 40 * 1024 * 1024
MAX_PRODUCT_FILES = 80

# 五个短镜头：颜色可从成片里核对其实际次序。
SOURCE_SPECS = (
    {
        "name": "24帧 红.mp4",
        "color": "red",
        "rate": 24,
        "audio_hz": 440,
        "vfr": False,
        "offset": 0,
        "facts": ("开门",),
    },
    {
        "name": "30帧 绿.mp4",
        "color": "green",
        "rate": 30,
        "audio_hz": 880,
        "vfr": False,
        "offset": 0,
        "facts": ("角色跳跃", "空中旋转", "落地特效"),
    },
    {
        "name": "60帧 蓝.mp4",
        "color": "blue",
        "rate": 60,
        "audio_hz": None,
        "vfr": False,
        "offset": 0,
        "facts": ("拾取道具",),
    },
    {
        "name": "可变帧率 黄.mp4",
        "color": "yellow",
        "rate": 30,
        "audio_hz": 660,
        "vfr": True,
        "offset": 0,
        "facts": ("角色奔跑",),
    },
    {
        "name": "非零起点 品红.mp4",
        "color": "magenta",
        "rate": 30,
        "audio_hz": 550,
        "vfr": False,
        "offset": 2,
        "facts": ("结算画面",),
    },
)

# 活动投稿要凑满规则里的最短时长时，官方计划每镜最多4秒（开场6秒），五个镜头只有22秒。
EXTRA_SOURCE_SPECS = (
    {
        "name": "30帧 青.mp4",
        "color": "cyan",
        "rate": 30,
        "audio_hz": 770,
        "vfr": False,
        "offset": 0,
        "facts": ("技能连招",),
    },
    {
        "name": "24帧 紫.mp4",
        "color": "purple",
        "rate": 24,
        "audio_hz": 990,
        "vfr": False,
        "offset": 0,
        "facts": ("地图互动",),
    },
)

RGB = {
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "magenta": (255, 0, 255),
    "cyan": (0, 255, 255),
    "purple": (128, 0, 255),
}


def require_space(path: Path) -> None:
    if not FFMPEG.is_file() or not FFPROBE.is_file():
        raise RuntimeError("本机未准备项目内的 FFmpeg。")
    free = shutil.disk_usage(path).free
    if free < MIN_FREE_BYTES:
        raise RuntimeError(f"可用空间不足 {MIN_FREE_BYTES} 字节，停止以免占满磁盘。")


def _is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def enforce_product_caps(directory: Path, skip: tuple[str, ...] = (".tools",)) -> int:
    # 不跟随工具目录的联接，只统计这次隔离任务自己写出的文件。
    total = 0
    files = 0
    if directory.exists():
        for root, names, files_in_dir in os.walk(directory, followlinks=False):
            current = Path(root)
            names[:] = [name for name in names if name not in skip and not _is_link(current / name)]
            for name in files_in_dir:
                item = current / name
                if item.is_file() and not _is_link(item):
                    files += 1
                    total += item.stat().st_size
    if files > MAX_PRODUCT_FILES or total > MAX_PRODUCT_BYTES:
        raise RuntimeError(f"隔离产物超过上限（{files} 个文件，{total} 字节）。")
    return total


def link_tools(repository: Path) -> None:
    target = repository / ".tools"
    source = ROOT / ".tools"
    if target.exists():
        return
    subprocess.run(["cmd", "/c", "mklink", "/J", str(target), str(source)], check=True)


def run_ffmpeg(arguments: list[str]) -> None:
    subprocess.run(
        [str(FFMPEG), "-hide_banner", "-nostdin", "-v", "error", *arguments],
        check=True,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


def write_mixed_sources(
    footage: Path, duration: float = 1, *, extras: bool = False
) -> list[dict[str, object]]:
    specs = SOURCE_SPECS + (EXTRA_SOURCE_SPECS if extras else ())
    footage.mkdir(parents=True, exist_ok=True)
    written = []
    for spec in specs:
        path = footage / spec["name"]
        command = [
            "-f",
            "lavfi",
            "-i",
            f"color=c={spec['color']}:s=160x90:r={spec['rate']}:d={duration}",
        ]
        if spec["audio_hz"]:
            command += [
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={spec['audio_hz']}:sample_rate=48000:duration={duration}",
                "-c:a",
                "aac",
            ]
        if spec["vfr"]:
            command += ["-vf", "select='lt(n,8)+not(mod(n,2))'", "-fps_mode", "vfr"]
        if spec["offset"]:
            command += ["-output_ts_offset", str(spec["offset"])]
        command += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
        run_ffmpeg(command)
        written.append({**spec, "path": path})
    return written


async def plant_completed_runs(
    project: Path, sources: list[dict[str, object]]
) -> list[dict[str, object]]:
    processor = FfmpegMediaProcessor(ROOT)
    parameters = SamplingParameters(interval_seconds=Fraction(1), max_width=160, max_frames=24)
    planted = []
    store = await SqliteTimelineStore.open(project)
    try:
        for index, source in enumerate(sources):
            run_id = f"run-{index}"
            media_dir = project / "runs" / run_id / "media"
            bundle = await processor.preprocess(
                source["path"],
                media_dir,
                parameters,
                CancellationContext(run_id, 60),
            )
            await store.create_run(run_id, bundle.asset, CONFIG)
            await store.begin_stage(run_id, "media", HASH)
            await store.persist_media_bundle(run_id, bundle)
            await store.begin_stage(run_id, "vision", HASH)
            duration = bundle.asset.duration_us
            if duration < 200_000:
                raise RuntimeError(f"{source['name']} 没有可用的时间范围。")
            start_us = 0
            end_us = duration
            event = SemanticEvent(
                f"e{index}",
                bundle.asset.media_id,
                run_id,
                SourceRange(start_us, end_us, duration),
                source["facts"],
                ("玩法",),
                (bundle.images[0].evidence_id,),
                "visual",
                None,
            )
            await store.persist_timeline(run_id, "vision", (event,), (), HASH)
            await store.complete_run(run_id)
            planted.append(
                {
                    **source,
                    "runId": run_id,
                    "eventId": event.event_id,
                    "mediaId": bundle.asset.media_id,
                    "durationUs": duration,
                }
            )
    finally:
        await store.close()
    return planted


def start_http(repository: Path):
    server = create_server("127.0.0.1", 0, repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_port}"


def stop_http(server, thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=10)


def http_json(base: str, path: str, payload: dict | None = None, timeout: int = 30) -> dict:
    if payload is None:
        with urlopen(base + path, timeout=timeout) as response:
            return json.load(response)
    request = Request(
        base + path,
        json.dumps(payload).encode("utf-8"),
        {"Content-Type": "application/json", "Origin": base},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            return json.loads(body) if body else {"status": response.status}
    except HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        error.close()
        raise RuntimeError(f"HTTP {error.code} {path}: {detail}") from error


def wait_job(base: str, job_id: str, timeout: float = 180) -> dict:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        last = http_json(base, f"/api/creation/jobs/{job_id}")
        if last.get("status") not in {"pending", "running"}:
            return last
        time.sleep(0.2)
    raise RuntimeError(f"任务 {job_id} 超时未结束：{last}")


def shrink_profile(profile: dict) -> dict:
    for kind in ("video", "cover"):
        profile["Fields"][kind]["width"] //= 8
        profile["Fields"][kind]["height"] //= 8
        for key in ("width", "height"):
            profile["Fields"][kind][key] += profile["Fields"][kind][key] % 2
    return profile


def probe_media(path: Path) -> dict:
    result = subprocess.run(
        [
            str(FFPROBE),
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def frame_rgb(path: Path, frame: int) -> tuple[int, int, int]:
    # 取中心一小块再平均，避免 yuv420 缩到 1 像素时把相邻颜色认错。
    pixels = subprocess.run(
        [
            str(FFMPEG),
            "-hide_banner",
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(path),
            "-vf",
            "select=eq(n\\," + str(frame) + "),crop=16:16",
            "-frames:v",
            "1",
            "-pix_fmt",
            "rgb24",
            "-f",
            "rawvideo",
            "-",
        ],
        check=True,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    ).stdout
    if len(pixels) != 16 * 16 * 3:
        raise RuntimeError(f"读不到第 {frame} 帧的颜色（得到 {len(pixels)} 字节）。")
    reds = pixels[0::3]
    greens = pixels[1::3]
    blues = pixels[2::3]
    return (
        sum(reds) // len(reds),
        sum(greens) // len(greens),
        sum(blues) // len(blues),
    )


def nearest_color(rgb: tuple[int, int, int]) -> str:
    return min(RGB, key=lambda name: sum(abs(rgb[i] - RGB[name][i]) for i in range(3)))


def pcm_energy(path: Path) -> float:
    pcm = subprocess.run(
        [
            str(FFMPEG),
            "-hide_banner",
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(path),
            "-vn",
            "-ar",
            "48000",
            "-ac",
            "1",
            "-f",
            "s16le",
            "-",
        ],
        check=True,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    ).stdout
    import array

    samples = array.array("h", pcm)
    if not samples:
        return 0.0
    return sum(abs(value) for value in samples) / len(samples)
