"""Synthetic OCR hard-case stills: small PNGs, byte-capped, deleted by the caller.

Accuracy on these images is not human-reviewed. Fixtures exist so regressions can
exercise stylized titles and low-contrast text without claiming quality acceptance.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = Path(__file__).resolve().parent / "fixtures" / "ocr-hard-cases" / "catalog.json"
FFMPEG = ROOT / ".tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
DIFFICULTIES = frozenset({"plain_control", "low_contrast", "stylized_title"})


def load_catalog(path: Path = CATALOG_PATH) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schemaVersion") != "ocr-hard-case-catalog-v1":
        raise ValueError("Unexpected OCR hard-case catalog schema.")
    max_bytes = document.get("maxImageBytes")
    if type(max_bytes) is not int or not 1024 <= max_bytes <= 512 * 1024:
        raise ValueError("Catalog maxImageBytes must be a modest positive byte cap.")
    cases = document.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Catalog needs a non-empty cases list.")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Each catalog case must be an object.")
        case_id = case.get("id")
        difficulty = case.get("difficulty")
        if type(case_id) is not str or not case_id or case_id in seen:
            raise ValueError("Catalog case ids must be unique non-empty strings.")
        if difficulty not in DIFFICULTIES:
            raise ValueError(f"Unknown difficulty tag: {difficulty!r}")
        seen.add(case_id)
    return document


def _escape_drawtext(text: str) -> str:
    # lavfi drawtext: escape \ and : and '
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _drawtext_filter(font: Path, item: dict[str, Any]) -> str:
    parts = [
        f"fontfile='{_escape_drawtext(font.as_posix())}'",
        f"text='{_escape_drawtext(str(item['text']))}'",
        f"fontsize={int(item['fontsize'])}",
        f"x={int(item['x'])}",
        f"y={int(item['y'])}",
        f"fontcolor={item['fontcolor']}",
    ]
    for key in ("borderw", "bordercolor", "shadowx", "shadowy", "shadowcolor"):
        if key in item:
            parts.append(f"{key}={item[key]}")
    return "drawtext=" + ":".join(parts)


def render_case(case: dict[str, Any], destination: Path, *, font: Path, ffmpeg: Path = FFMPEG) -> Path:
    """Render one catalog case to a PNG at destination; caller must enforce size and delete."""
    if destination.exists():
        raise FileExistsError(destination)
    width, height = int(case["width"]), int(case["height"])
    background = str(case["background"])
    chain = [f"color=c={background}:s={width}x{height}:d=1"]
    for item in case["draw"]:
        chain.append(_drawtext_filter(font, item))
    graph = ",".join(chain)
    subprocess.run(
        [
            str(ffmpeg),
            "-hide_banner",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            graph,
            "-frames:v",
            "1",
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
    font = Path(str(document["fontFile"]))
    if not font.is_file():
        raise FileNotFoundError(font)
    directory.mkdir(parents=True, exist_ok=True)
    rendered: list[tuple[dict[str, Any], Path]] = []
    for case in document["cases"]:
        path = directory / f"{case['id']}.png"
        render_case(case, path, font=font, ffmpeg=ffmpeg)
        size = path.stat().st_size
        if size > int(document["maxImageBytes"]):
            path.unlink(missing_ok=True)
            raise ValueError(
                f"Fixture {case['id']} is {size} bytes; cap is {document['maxImageBytes']}."
            )
        rendered.append((case, path))
    return rendered