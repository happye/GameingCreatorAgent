"""Print the project's current numbers, computed from their sources. Offline, stdlib only.

Primary metric: end-to-end journeys (docs/exec-plans/journeys.json).
Secondary counts: feature_list.json, tech-debt.md status column, human-inputs.md pending table.
`--check` also fails when progress-board.md's hand-written headline drifts from these
counts, when STATUS.md / AGENTS.md / HANDOFF.md exceed their size budgets, or when HANDOFF.md
is older than STATUS.md (used by CI).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLANS = ROOT / "docs" / "exec-plans"
# Unfrozen 2026-11-03 by the user; list items here if a feature is frozen again.
FREEZE_IDS: tuple[str, ...] = ()
SIZE_BUDGETS = {"STATUS.md": 5120, "AGENTS.md": 8192, "HANDOFF.md": 5120}
TIER = {"usable": "✅", "usable_draft": "🟡", "not_usable": "❌", "not_done": "⬜"}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def journeys() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = json.loads(_read(PLANS / "journeys.json"))["journeys"]
    return rows


def feature_counts() -> dict[str, Any]:
    data = json.loads(_read(ROOT / "feature_list.json"))
    items = data.get("product_features") or []
    phase0 = data.get("features") or []
    first = [x for x in items if x.get("first_product")]
    return {
        "planned": len(items),
        "delivery": Counter(x.get("delivery_status") for x in items),
        "first": len(first),
        "first_delivery": Counter(x.get("delivery_status") for x in first),
        "quality": Counter(x.get("quality_status") for x in items),
        "phase0_true": [f["id"] for f in phase0 if f.get("passes") is True],
        "phase0_false": [f["id"] for f in phase0 if f.get("passes") is False],
        "frozen": [x["id"] for x in items if x.get("id") in FREEZE_IDS],
    }


def tech_debt_counts() -> Counter[str]:
    counts: Counter[str] = Counter()
    for line in _read(PLANS / "tech-debt.md").splitlines():
        if not line.startswith("| TD"):
            continue
        status = line.strip().strip("|").split("|")[-1].strip().lower()
        if status.startswith("resolved"):
            counts["resolved"] += 1
        elif status.startswith("partial"):
            counts["partial"] += 1
        else:
            counts["open"] += 1
    return counts


def human_pending() -> list[str]:
    text = _read(PLANS / "human-inputs.md")
    section = re.search(r"##\s*仍待真实输入[\s\S]*?(?=\n##\s|\Z)", text)
    rows = []
    for line in section.group(0).splitlines() if section else []:
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and cols[0] not in ("事项", "") and not cols[0].startswith("---"):
            rows.append(cols[0][:40])
    return rows


def board_drift(features: dict[str, Any]) -> list[str]:
    """Compare progress-board.md's hand-written headline with the computed counts."""
    text = _read(PLANS / "progress-board.md")
    m = re.search(r"(\d+)\s*项：已交付\s*(\d+)\s*·\s*部分\s*(\d+)\s*·\s*未开始\s*(\d+)", text)
    if not m:
        return ["progress-board.md: headline '51 项：已交付 · 部分 · 未开始' not found"]
    board = tuple(int(g) for g in m.groups())
    d = features["delivery"]
    computed = (features["planned"], d["delivered"], d["partial"], d["not_started"])
    if board != computed:
        return [f"progress-board.md headline {board} != feature_list {computed}"]
    return []


def size_problems() -> list[str]:
    out = []
    for name, limit in SIZE_BUDGETS.items():
        size = (ROOT / name).stat().st_size
        if size > limit:
            out.append(f"{name} is {size} bytes (budget {limit})")
    return out


CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def control_char_problems() -> list[str]:
    """PowerShell double-quoted writes turn backtick escapes into control characters."""
    try:
        listed = subprocess.run(
            ["git", "ls-files", "-z", "*.md", "*.toml", "*.json"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8")
    except (OSError, subprocess.CalledProcessError):
        return []
    out = []
    for name in filter(None, listed.split("\0")):
        path = ROOT / name
        if path.is_file() and CONTROL.search(path.read_text(encoding="utf-8", errors="replace")):
            out.append(f"{name} contains control characters")
    return out


DATE = re.compile(r"20\d\d-\d\d-\d\d")


def handoff_problems(status: str, handoff: str) -> list[str]:
    """HANDOFF.md must be overwritten when the state moves on: its session date may not be
    older than the newest date STATUS.md mentions (content only, so it also works in CI)."""
    session = re.search(r"最近一次会话[^\n]*?(20\d\d-\d\d-\d\d)", handoff)
    if session is None:
        return ["HANDOFF.md has no '最近一次会话（YYYY-MM-DD…' line"]
    newest = max(DATE.findall(status), default="")
    if newest > session.group(1):
        return [
            f"HANDOFF.md is stale (session {session.group(1)}, STATUS.md mentions {newest});"
            " overwrite it at session end"
        ]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 on drift or size budget")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("== 主指标：端到端流程（agent 跑通 / 你亲自试过）==")
    for j in journeys():
        run, check = j["agent_run"], j["human_check"]
        agent = f"agent {run['result']} {run['date'] or '-'}"
        human = f"{TIER.get(check['verdict'], '?')} 人评 {check['verdict']} {check['date'] or ''}"
        print(f"  {j['id']} {j['name']}: {agent} | {human}".rstrip())

    f = feature_counts()
    d, fd, td = f["delivery"], f["first_delivery"], tech_debt_counts()
    pending = human_pending()
    print("== 次要计数（由源文件计算）==")
    print(
        f"  计划功能 {f['planned']}: 已交付 {d['delivered']} · 部分 {d['partial']}"
        f" · 未开始 {d['not_started']}"
    )
    print(
        f"  首产品 {f['first']}: 已交付 {fd['delivered']} · 部分 {fd['partial']}"
        f" · 未开始 {fd['not_started']}"
    )
    print(
        f"  质量已验收: {f['quality'].get('accepted', 0)} / {f['planned']}"
        f"（其余 {dict(f['quality'])}）"
    )
    print(
        f"  Phase0 F: passes {len(f['phase0_true'])} · false {len(f['phase0_false'])}"
        f"（{', '.join(f['phase0_false'])}）"
    )
    print(
        f"  技术债 {sum(td.values())}: 已解决 {td['resolved']} · 部分 {td['partial']}"
        f" · 未解决 {td['open']}"
    )
    print(f"  人工待办（human-inputs 表）{len(pending)} 项")
    if f["frozen"]:
        print(f"  冻结中: {', '.join(f['frozen'])}（解冻条件见 STATUS.md）")

    problems = (
        board_drift(f)
        + size_problems()
        + control_char_problems()
        + handoff_problems(_read(ROOT / "STATUS.md"), _read(ROOT / "HANDOFF.md"))
    )
    for problem in problems:
        print(f"WARN {problem}")
    return 1 if args.check and problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
