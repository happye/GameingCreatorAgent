"""Offline STATUS / progress numbers from repo docs. No network."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def feature_list_counts(path: Path) -> dict[str, int | list[str]]:
    data = json.loads(_read(path))
    features = data.get("features") or []
    passed = [f["id"] for f in features if f.get("passes") is True]
    failed = [f["id"] for f in features if f.get("passes") is False]
    other = [f["id"] for f in features if f.get("passes") not in (True, False)]
    return {
        "total": len(features),
        "passes_true": len(passed),
        "passes_false": len(failed),
        "passes_other": len(other),
        "true_ids": passed,
        "false_ids": failed,
    }


def progress_board_summary(path: Path) -> dict[str, str | int | None]:
    text = _read(path)
    out: dict[str, str | int | None] = {
        "header_line": None,
        "delivered": None,
        "partial": None,
        "not_started": None,
        "planned_total": None,
        "overall_pct_note": None,
        "tech_debt_line": None,
    }
    # e.g. 全部计划功能 **51 项：已交付 10 · 部分 41 · 未开始 0**
    m = re.search(
        r"全部计划功能\s*\*?\*?(\d+)\s*项[：:]\s*已交付\s*(\d+)\s*[·•]\s*部分\s*(\d+)\s*[·•]\s*未开始\s*(\d+)",
        text,
    )
    if m:
        out["planned_total"] = int(m.group(1))
        out["delivered"] = int(m.group(2))
        out["partial"] = int(m.group(3))
        out["not_started"] = int(m.group(4))
        out["header_line"] = m.group(0)
    pct = re.search(r"整体约\s*(\d+%)", text)
    if pct:
        out["overall_pct_note"] = pct.group(1)
    td = re.search(r"技术债[^\n]{0,80}", text)
    if td:
        out["tech_debt_line"] = td.group(0).strip()
    return out


def tech_debt_counts(path: Path) -> dict[str, int | list[str]]:
    text = _read(path)
    rows = re.findall(r"^\|\s*(TD\d+)\s*\|([^|\n]*)\|([^|\n]*)\|([^|\n]*)\|", text, re.M)
    resolved: list[str] = []
    partial: list[str] = []
    open_ids: list[str] = []
    for tid, _a, _b, status in rows:
        blob = status.lower()
        # Chinese / English cues in the status/notes cell
        cell = status
        if re.search(r"已解决|resolved|fixed|已修复|已关闭", cell, re.I):
            resolved.append(tid)
        elif re.search(r"部分|partial", cell, re.I) and not re.search(
            r"未解决|open|仍开", cell, re.I
        ):
            partial.append(tid)
        else:
            # default: treat as still open unless clearly done earlier in cell
            if re.search(r"已交付|已完成|关闭", cell) and not re.search(
                r"未|仍|待", cell
            ):
                resolved.append(tid)
            else:
                open_ids.append(tid)
    # Prefer board headline if present in same file intro
    return {
        "table_rows": len(rows),
        "classified_resolved": len(resolved),
        "classified_partial": len(partial),
        "classified_open": len(open_ids),
        "open_ids": open_ids,
        "partial_ids": partial,
        "resolved_ids": resolved,
    }


def human_inputs_open(path: Path) -> dict[str, int | list[str]]:
    text = _read(path)
    # Count rows in the "仍待真实输入" markdown table (skip header/separator)
    section = re.search(
        r"##\s*仍待真实输入[\s\S]*?(?=\n##\s|\Z)", text
    )
    pending: list[str] = []
    if section:
        for line in section.group(0).splitlines():
            if not line.startswith("|"):
                continue
            if re.match(r"^\|\s*---", line) or "事项" in line and "怎么做" in line:
                continue
            cols = [c.strip() for c in line.strip("|").split("|")]
            if cols and cols[0] and cols[0] != "事项":
                pending.append(cols[0][:60])
    # "当前必做人工仍为 0" style
    must = None
    m = re.search(r"当前必做人工仍为\s*(\d+)|当前必须做\s*(\d+)\s*项|当前必做\s*(\d+)\s*项", text)
    if m:
        must = int(next(g for g in m.groups() if g is not None))
    return {
        "pending_table_rows": len(pending),
        "pending_titles": pending,
        "must_do_declared": must,
    }


def status_md_excerpt(path: Path) -> str:
    text = _read(path)
    # Keep it short for terminal
    lines = []
    for line in text.splitlines():
        if line.startswith("#") or line.startswith("-") or line.startswith(">"):
            lines.append(line)
        if len(lines) >= 40:
            break
    return "\n".join(lines)


def main() -> int:
    status_path = ROOT / "STATUS.md"
    fl_path = ROOT / "feature_list.json"
    board_path = ROOT / "docs" / "exec-plans" / "progress-board.md"
    td_path = ROOT / "docs" / "exec-plans" / "tech-debt.md"
    hi_path = ROOT / "docs" / "exec-plans" / "human-inputs.md"

    print("=== STATUS.md (excerpt) ===")
    if status_path.is_file():
        print(status_md_excerpt(status_path))
        print(f"(bytes={status_path.stat().st_size})")
    else:
        print("MISSING STATUS.md", file=sys.stderr)
        return 2

    print("\n=== feature_list.json (Phase 0 F-ids) ===")
    fl = feature_list_counts(fl_path)
    print(
        f"total={fl['total']} passes_true={fl['passes_true']} "
        f"passes_false={fl['passes_false']} other={fl['passes_other']}"
    )
    print(f"true: {', '.join(fl['true_ids'])}")  # type: ignore[arg-type]
    print(f"false: {', '.join(fl['false_ids'])}")  # type: ignore[arg-type]

    print("\n=== progress-board.md (planned 51-item口径) ===")
    board = progress_board_summary(board_path)
    print(
        f"planned={board['planned_total']} delivered={board['delivered']} "
        f"partial={board['partial']} not_started={board['not_started']} "
        f"pct_note={board['overall_pct_note']}"
    )
    if board["header_line"]:
        print(board["header_line"])
    if board["tech_debt_line"]:
        print(board["tech_debt_line"])

    print("\n=== tech-debt (board口径 preferred; table lists ids) ===")
    td = tech_debt_counts(td_path)
    # Prefer explicit board summary numbers when present
    mtd = re.search(
        r"技术债[^\n]*?(\d+)\s*项[，,]\s*已解决\s*(\d+)\s*[·•]\s*部分\s*(\d+)\s*[·•]\s*未解决\s*(\d+)",
        _read(board_path),
    )
    if mtd:
        print(
            f"board: total={mtd.group(1)} resolved={mtd.group(2)} "
            f"partial={mtd.group(3)} open={mtd.group(4)}"
        )
    ids = re.findall(r"^\|\s*(TD\d+)\s*\|", _read(td_path), re.M)
    print(f"table_ids({len(ids)}): {', '.join(ids)}")
    print(
        f"(heuristic open~={td['classified_open']} — descriptions are free text; use board counts)"
    )

    print("\n=== human-inputs.md ===")
    hi = human_inputs_open(hi_path)
    print(
        f"must_do_declared={hi['must_do_declared']} "
        f"pending_table_rows={hi['pending_table_rows']}"
    )
    for title in hi["pending_titles"]:  # type: ignore[union-attr]
        print(f"  - {title}")

    print("\n=== tip ===")
    # local only — do not shell out if git missing; best-effort
    git_head = ROOT / ".git" / "HEAD"
    if git_head.is_file():
        head = _read(git_head).strip()
        if head.startswith("ref:"):
            ref = head.split(" ", 1)[1].strip()
            ref_path = ROOT / ".git" / ref
            if ref_path.is_file():
                print(f"{ref} {_read(ref_path).strip()[:12]}")
            else:
                print(head)
        else:
            print(head[:12])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
