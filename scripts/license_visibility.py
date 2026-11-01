"""Post-build/install reminder to read bundled third-party notices and gaps (no downloads)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def format_license_visibility(root: Path) -> str:
    """Return a Chinese reminder pointing at notices and gaps under root/licenses."""
    base = Path(root).resolve()
    licenses = base / "licenses"
    notices = licenses / "THIRD-PARTY-NOTICES.md"
    gaps = licenses / "gaps.json"
    lines = [
        "请阅读本机已随包装入的第三方许可材料（不会联网下载补许可）：",
        f"  - {notices}",
        f"  - {gaps}",
    ]
    if not notices.is_file():
        lines.append("警告：未找到 licenses/THIRD-PARTY-NOTICES.md。")
    if not gaps.is_file():
        lines.append("警告：未找到 licenses/gaps.json。")
    else:
        try:
            payload = json.loads(gaps.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            lines.append("警告：licenses/gaps.json 无法读取或不是合法 JSON。")
        else:
            if isinstance(payload, list):
                lines.append(
                    f"  gaps.json 当前记录 {len(payload)} 项待确认缺口（分发前需人工审阅）。"
                )
            else:
                lines.append("警告：licenses/gaps.json 应为缺口对象数组。")
    lines.append("分发前请自行确认 gaps；本程序不会自动补齐许可证文件。")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print a reminder to read bundled THIRD-PARTY-NOTICES.md and gaps.json."
    )
    parser.add_argument("--root", type=Path, required=True, help="Portable app or install root")
    args = parser.parse_args(argv)
    sys.stdout.write(format_license_visibility(args.root) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
