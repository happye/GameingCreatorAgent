"""Build the progress dashboard data (docs/progress/data.js) from the project's sources.

Usage (repo root, after `. ./scripts/env.ps1` or any Python 3.11+):
  python -B scripts/progress_ui.py          # regenerate docs/progress/data.js
  python -B scripts/progress_ui.py --check  # exit 1 if data.js is stale or a node is missing

Open docs/progress/index.html in a browser (works from file://, no server).
Sources (no other copies): feature_list.json, docs/exec-plans/journeys.json, tech-debt.md,
human-inputs.md, sprint-*.md, STATUS.md, git log, and docs/progress/nodes.json (hand-kept
notes for features, roadmap, stages, quality steps, J1 fixes, release gates, last gate).
The gitignored live.js holds volatile data (time, branch, recent commits); data.js is stable.
Update guide: docs/references/progress-dashboard.md. Offline, stdlib only.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PLANS = ROOT / "docs" / "exec-plans"
OUT_DIR = ROOT / "docs" / "progress"
NODES = OUT_DIR / "nodes.json"
DATA_JS = OUT_DIR / "data.js"
LIVE_JS = OUT_DIR / "live.js"  # gitignored: generation time, branch, recent commits
PREFIX = "window.PROGRESS_DATA = "
LIVE_PREFIX = "window.PROGRESS_LIVE = "
GROUPS = {
    "A": "基础架构与本地处理",
    "B": "视频理解与检索",
    "C": "创作规划",
    "D": "成片制作",
    "E": "多平台与发布",
    "F": "产品形态与交互",
    "G": "内容模式",
    "H": "商业化",
}
NODE_STATUS = {"done", "active", "partial", "todo", "blocked"}
ID_RE = re.compile(r"\b(P0\d\d|F0\d\d|TD0\d\d|R\d(?:-[A-Z])?|J\d)\b")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _json(path: Path) -> Any:
    return json.loads(_read(path))


def _git(*args: str) -> str:
    try:
        done = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.decode("utf-8", errors="replace")


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def features(nodes: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    data = _json(ROOT / "feature_list.json")
    notes = nodes.get("features", {})
    rows = []
    for x in data.get("product_features") or []:
        note = notes.get(x["id"], {})
        rows.append(
            {
                "id": x["id"],
                "group": x.get("group"),
                "name": x.get("name"),
                "first": bool(x.get("first_product")),
                "delivery": x.get("delivery_status"),
                "impl": x.get("implementation_status"),
                "quality": x.get("quality_status"),
                "release": x.get("release_status"),
                "remaining": x.get("remaining"),
                "evidence": x.get("implementation_evidence") or [],
                "done": note.get("done", ""),
                "todo": note.get("todo") or x.get("remaining") or "",
                "updated": note.get("updated", ""),
                "sprints": note.get("sprints", []),
            }
        )
    phase0 = [
        {
            "id": f["id"],
            "name": f.get("name"),
            "description": f.get("description", ""),
            "passes": f.get("passes") is True,
            "criteria": f.get("test_criteria", ""),
        }
        for f in data.get("features") or []
    ]
    return rows, phase0


def tech_debt() -> list[dict[str, str]]:
    rows = []
    for line in _read(PLANS / "tech-debt.md").splitlines():
        if not line.startswith("| TD"):
            continue
        c = _cells(line)
        status = c[-1]
        low = status.lower()
        state = (
            "resolved"
            if low.startswith("resolved")
            else "partial"
            if low.startswith("partial")
            else "open"
        )
        rows.append(
            {
                "id": c[0],
                "found": c[1] if len(c) > 1 else "",
                "severity": c[2] if len(c) > 2 else "",
                "impact": c[3] if len(c) > 3 else "",
                "fix": c[4] if len(c) > 5 else "",
                "status": status,
                "state": state,
            }
        )
    return sorted(rows, key=lambda r: r["id"])


def human_inputs() -> list[dict[str, str]]:
    text = _read(PLANS / "human-inputs.md")
    section = re.search(r"##\s*仍待真实输入[\s\S]*?(?=\n##\s|\Z)", text)
    rows = []
    for line in section.group(0).splitlines() if section else []:
        c = _cells(line)
        if not line.startswith("|") or c[0] in ("事项", "") or c[0].startswith("---"):
            continue
        c += [""] * (4 - len(c))
        rows.append({"item": c[0], "how": c[1], "when": c[2], "state": c[3]})
    return rows


def sprint_dates() -> dict[str, str]:
    log = _git("log", "--format=@%ad", "--date=short", "--name-only", "--", "docs/exec-plans")
    dates: dict[str, str] = {}
    current = ""
    for line in log.splitlines():
        if line.startswith("@"):
            current = line[1:]
        elif line.strip():
            dates.setdefault(Path(line.strip()).stem, current)
    return dates


def sprints() -> list[dict[str, Any]]:
    dates = sprint_dates()
    rows = []
    paths = [*PLANS.glob("sprint-*.md"), *PLANS.glob("grok-*.md")]
    for path in sorted(paths):
        if path.stem == "sprint-template":
            continue
        text = _read(path)
        title = next((ln[2:].strip() for ln in text.splitlines() if ln.startswith("# ")), path.stem)
        head = "\n".join(text.splitlines()[:6])
        rows.append(
            {
                "file": path.stem,
                "title": title,
                "ids": sorted(set(ID_RE.findall(head))),
                "date": dates.get(path.stem, ""),
                "bytes": path.stat().st_size,
            }
        )
    return rows


def _status_section(title: str) -> str:
    text = _read(ROOT / "STATUS.md")
    section = re.search(r"##\s*" + title + r"[^\n]*\n([\s\S]*?)(?=\n##\s|\Z)", text)
    return section.group(1).strip() if section else ""


def status_now() -> list[str]:
    items = re.split(r"\n(?=\d+\.\s)", _status_section("当前交付与下一步"))
    return [re.sub(r"^\d+\.\s*", "", it).strip() for it in items if it.strip()]


def status_fees() -> list[str]:
    lines = _status_section("费用与授权").splitlines()
    return [ln.lstrip("- ").strip() for ln in lines if ln.strip()]


def commits(limit: int = 150) -> list[dict[str, str]]:
    log = _git("log", f"-{limit}", "--format=%h\x1f%ad\x1f%s", "--date=short")
    rows = []
    for line in log.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 3:
            kind = parts[2].split(":", 1)[0] if ":" in parts[2][:12] else "other"
            rows.append({"sha": parts[0], "date": parts[1], "subject": parts[2], "kind": kind})
    return rows


def summary(
    feats: list[dict[str, Any]],
    phase0: list[dict[str, Any]],
    td: list[dict[str, str]],
    human: list[dict[str, str]],
    journeys: list[dict[str, Any]],
) -> dict[str, Any]:
    d = Counter(f["delivery"] for f in feats)
    first = [f for f in feats if f["first"]]
    fd = Counter(f["delivery"] for f in first)

    def pct(c: Counter[Any], n: int) -> float:
        return round((c["delivered"] + 0.5 * c["partial"]) / n * 100, 1) if n else 0.0

    return {
        "planned": len(feats),
        "delivery": dict(d),
        "pct": pct(d, len(feats)),
        "first": len(first),
        "firstDelivery": dict(fd),
        "firstPct": pct(fd, len(first)),
        "qualityAccepted": sum(1 for f in feats if f["quality"] == "accepted"),
        "released": sum(1 for f in feats if f["release"] not in (None, "not_released")),
        "phase0Pass": sum(1 for f in phase0 if f["passes"]),
        "phase0Total": len(phase0),
        "td": dict(Counter(t["state"] for t in td)),
        "tdTotal": len(td),
        "humanPending": len(human),
        "journeyAgentPass": sum(1 for j in journeys if j["agent_run"]["result"] == "pass"),
        "journeyHumanUsable": sum(
            1 for j in journeys if j["human_check"]["verdict"] in ("usable", "usable_draft")
        ),
        "journeyTotal": len(journeys),
    }


def build() -> dict[str, Any]:
    nodes = _json(NODES)
    feats, phase0 = features(nodes)
    td, human = tech_debt(), human_inputs()
    journeys = _json(PLANS / "journeys.json")["journeys"]
    return {
        "schemaVersion": 1,
        "nodesUpdated": nodes.get("updated", ""),
        "groups": GROUPS,
        "summary": summary(feats, phase0, td, human, journeys),
        "journeys": journeys,
        "features": feats,
        "phase0": phase0,
        "roadmap": nodes.get("roadmap", []),
        "stages": nodes.get("stages", []),
        "qualitySteps": nodes.get("qualitySteps", []),
        "journeyFixes": nodes.get("journeyFixes", {}),
        "releaseGates": nodes.get("releaseGates", []),
        "gate": nodes.get("gate", {}),
        "fees": status_fees(),
        "now": status_now(),
        "sprints": sprints(),
        "techDebt": td,
        "human": human,
    }


def live() -> dict[str, Any]:
    return {
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD").strip(),
        "head": _git("rev-parse", "--short", "HEAD").strip(),
        "commits": commits(),
    }


def node_problems(data: dict[str, Any]) -> list[str]:
    out = []
    for f in data["features"]:
        if not f["done"]:
            out.append(f"nodes.json: feature {f['id']} has no done note")
    known = {s["file"] for s in data["sprints"]}
    placed: set[str] = set()
    for batch in data["roadmap"]:
        for sl in batch.get("slices", []):
            if sl.get("sprint") and sl["sprint"] not in known:
                out.append(f"nodes.json: {batch['id']} slice {sl['id']} -> missing {sl['sprint']}")
            placed.add(sl.get("sprint", ""))
            if sl.get("status") not in NODE_STATUS:
                out.append(f"nodes.json: {batch['id']}/{sl['id']} bad status {sl.get('status')}")
        if batch.get("status") not in NODE_STATUS:
            out.append(f"nodes.json: {batch['id']} bad status {batch.get('status')}")
    for name in sorted(known - placed):
        out.append(f"nodes.json: sprint {name} is not placed under any roadmap slice")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if data.js is stale")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    data = build()
    problems = node_problems(data)
    if args.check:
        try:
            old = json.loads(_read(DATA_JS).removeprefix(PREFIX).rstrip().rstrip(";"))
        except (OSError, ValueError):
            old = {}
        if old != json.loads(json.dumps(data, ensure_ascii=False)):
            problems.append("docs/progress/data.js is stale: run python -B scripts/progress_ui.py")
    else:
        text = PREFIX + json.dumps(data, ensure_ascii=False, indent=1) + ";\n"
        DATA_JS.write_text(text, encoding="utf-8", newline="\n")
        live_text = LIVE_PREFIX + json.dumps(live(), ensure_ascii=False) + ";\n"
        LIVE_JS.write_text(live_text, encoding="utf-8", newline="\n")
        s = data["summary"]
        print(
            f"wrote {DATA_JS.relative_to(ROOT)}: {s['planned']} features {s['pct']}%,"
            f" first {s['firstPct']}%, journeys {s['journeyHumanUsable']}/{s['journeyTotal']}"
            f" human-usable, TD {s['tdTotal']}, sprints {len(data['sprints'])}"
        )
    for p in problems:
        print(f"WARN {p}")
    return 1 if args.check and problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
