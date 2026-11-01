"""Synthetic shot-boundary hard cases: short concat clips, byte-capped, caller deletes.

Detection accuracy on these clips is not human-reviewed (抽检未人评). Fixtures expand
black-frame / hard-cut coverage for regression only — never F006 evidence.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = Path(__file__).resolve().parent / "fixtures" / "shot-hard-cases" / "catalog.json"
FFMPEG = ROOT / ".tools" / "ffmpeg" / "bin" / "ffmpeg.exe"


def load_catalog(path: Path = CATALOG_PATH) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schemaVersion") != "shot-hard-case-catalog-v1":
        raise ValueError("Unexpected shot hard-case catalog schema.")
    max_bytes = document.get("maxVideoBytes")
    if type(max_bytes) is not int or not 64 * 1024 <= max_bytes <= 8 * 1024 * 1024:
        raise ValueError("Catalog maxVideoBytes must be a modest byte cap.")
    cases = document.get("cases")
    if not isinstance(cases, list) or len(cases) < 3:
        raise ValueError("Catalog needs at least three synthetic cases.")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Each catalog case must be an object.")
        case_id = case.get("id")
        segments = case.get("segments")
        if type(case_id) is not str or not case_id or case_id in seen:
            raise ValueError("Catalog case ids must be unique non-empty strings.")
        if not isinstance(segments, list) or len(segments) < 2:
            raise ValueError(f"Case {case_id} needs at least two segments.")
        for segment in segments:
            if (
                not isinstance(segment, dict)
                or type(segment.get("color")) is not str
                or type(segment.get("seconds")) not in (int, float)
                or float(segment["seconds"]) <= 0
                or float(segment["seconds"]) > 5
            ):
                raise ValueError(f"Case {case_id} has an invalid segment.")
        seen.add(case_id)
    return document


def render_case(
    case: dict[str, Any],
    destination: Path,
    *,
    width: int,
    height: int,
    fps: int,
    ffmpeg: Path = FFMPEG,
) -> Path:
    if destination.exists():
        raise FileExistsError(destination)
    labels: list[str] = []
    parts: list[str] = []
    for index, segment in enumerate(case["segments"]):
        label = f"s{index}"
        labels.append(f"[{label}]")
        color = segment["color"]
        seconds = float(segment["seconds"])
        parts.append(f"color=c={color}:s={width}x{height}:r={fps}:d={seconds}[{label}]")
    graph = ";".join(parts) + f";{''.join(labels)}concat=n={len(labels)}:v=1:a=0[v]"
    subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-nostdin",
            "-v",
            "error",
            "-filter_complex",
            graph,
            "-map",
            "[v]",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-y",
            str(destination),
        ],
        check=True,
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )
    return destination


def render_all_cases(
    directory: Path,
    *,
    catalog: dict[str, Any] | None = None,
    ffmpeg: Path = FFMPEG,
) -> list[tuple[dict[str, Any], Path]]:
    document = catalog or load_catalog()
    directory.mkdir(parents=True, exist_ok=True)
    width, height, fps = int(document["width"]), int(document["height"]), int(document["fps"])
    rendered: list[tuple[dict[str, Any], Path]] = []
    for case in document["cases"]:
        path = directory / f"{case['id']}.mp4"
        render_case(case, path, width=width, height=height, fps=fps, ffmpeg=ffmpeg)
        size = path.stat().st_size
        if size > int(document["maxVideoBytes"]):
            path.unlink(missing_ok=True)
            raise ValueError(
                f"Fixture {case['id']} is {size} bytes; cap is {document['maxVideoBytes']}."
            )
        rendered.append((case, path))
    return rendered
