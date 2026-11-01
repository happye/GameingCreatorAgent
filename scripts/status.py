"""Offline primary e2e metrics + STATUS/progress numbers. No network."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Content modes / commercial items frozen until first mode is human-evaluated.
# Documented only — this script never flips feature_list states.
FREEZE_IDS = ("P038", "P046", "P047", "P048", "P049", "P050", "P051")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def feature_list_phase0(path: Path) -> dict:
    data = json.loads(_read(path))
    features = data.get("features") or []
    passed = [f["id"] for f in features if f.get("passes") is True]
    failed = [f["id"] for f in features if f.get("passes") is False]
    return {
        "total": len(features),
        "passes_true": len(passed),
        "passes_false": len(failed),
        "true_ids": passed,
        "false_ids": failed,
    }


def product_features_metrics(path: Path) -> dict:
    data = json.loads(_read(path))
    items = data.get("product_features") or []
    delivery = Counter(x.get("delivery_status") or "unknown" for x in items)
    quality = Counter(x.get("quality_status") or "unknown" for x in items)
    release = Counter(x.get("release_status") or "unknown" for x in items)
    first = [x for x in items if x.get("first_product")]
    first_delivery = Counter(x.get("delivery_status") or "unknown" for x in first)
    freeze = []
    for x in items:
        if x.get("id") in FREEZE_IDS:
            freeze.append(
                {
                    "id": x["id"],
                    "name": x.get("name"),
                    "delivery_status": x.get("delivery_status"),
                    "quality_status": x.get("quality_status"),
                    "release_status": x.get("release_status"),
                }
            )
    return {
        "total": len(items),
        "delivery": dict(delivery),
        "quality": dict(quality),
        "release": dict(release),
        "first_product_n": len(first),
        "first_delivery": dict(first_delivery),
        "freeze": freeze,
    }


def progress_board_metrics(path: Path) -> dict:
    text = _read(path)
    out: dict = {
        "planned_total": None,
        "delivered": None,
        "partial": None,
        "not_started": None,
        "overall_pct_note": None,
        "first_total": None,
        "first_delivered": None,
        "first_partial": None,
        "first_not_started": None,
        "first_pct_note": None,
        "quality_real_done": None,
        "quality_real_total": None,
        "tech_debt_line": None,
        "tech_debt": None,
        "human_must": None,
        "human_pending": None,
        "header_line": None,
    }
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
    # ★ first-product line variants
    fp = re.search(
        r"22\s*项中已交付\s*(\d+)\s*[·•]\s*部分\s*(\d+)\s*[·•]\s*未开始\s*(\d+).*?约\s*(\d+%)",
        text,
    )
    if not fp:
        fp = re.search(
            r"★\s*范围\s*(\d+)\s*项[：:]\s*.*?(\d+)\s*[·•].*?(\d+).*?(\d+)",
            text,
        )
        if fp:
            out["first_total"] = int(fp.group(1))
    else:
        out["first_total"] = 22
        out["first_delivered"] = int(fp.group(1))
        out["first_partial"] = int(fp.group(2))
        out["first_not_started"] = int(fp.group(3))
        out["first_pct_note"] = fp.group(4)
    # Board summary line often: 首产品0/22/0≈50%
    fp2 = re.search(r"首产品\s*(\d+)\s*/\s*(\d+)\s*/\s*(\d+)\s*≈?\s*(\d+%)?", text)
    if fp2:
        out["first_delivered"] = int(fp2.group(1))
        out["first_total"] = int(fp2.group(2))
        out["first_partial"] = out.get("first_partial")
        if out["first_partial"] is None and out["first_total"] is not None:
            # if form is delivered/total/not_started
            out["first_not_started"] = int(fp2.group(3))
            if out["first_delivered"] is not None and out["first_total"] is not None:
                out["first_partial"] = (
                    out["first_total"] - out["first_delivered"] - out["first_not_started"]
                )
        if fp2.group(4):
            out["first_pct_note"] = fp2.group(4)
    # Quality gate: 质量验收 0/8 步
    q = re.search(r"质量验收\s*(\d+)\s*/\s*(\d+)\s*步", text)
    if q:
        out["quality_real_done"] = int(q.group(1))
        out["quality_real_total"] = int(q.group(2))
    td = re.search(
        r"技术债[^\n]*?(\d+)\s*项[，,]\s*已解决\s*(\d+)\s*[·•]\s*部分\s*(\d+)\s*[·•]\s*未解决\s*(\d+)",
        text,
    )
    if td:
        out["tech_debt"] = {
            "total": int(td.group(1)),
            "resolved": int(td.group(2)),
            "partial": int(td.group(3)),
            "open": int(td.group(4)),
        }
        out["tech_debt_line"] = td.group(0)
    # human: 现在必须人工操作0项，未来9项 / 人工0／未来8
    hm = re.search(r"现在必须人工操作\s*(\d+)\s*项，未来\s*(\d+)\s*项", text)
    if not hm:
        hm = re.search(r"人工\s*(\d+)\s*／未来\s*(\d+)", text)
    if not hm:
        hm = re.search(r"当前必做\s*(\d+)\s*项；未来\s*(\d+)\s*项", text)
    if hm:
        out["human_must"] = int(hm.group(1))
        out["human_pending"] = int(hm.group(2))
    return out


def human_inputs_open(path: Path) -> dict:
    text = _read(path)
    section = re.search(r"##\s*仍待真实输入[\s\S]*?(?=\n##\s|\Z)", text)
    pending: list[str] = []
    if section:
        for line in section.group(0).splitlines():
            if not line.startswith("|"):
                continue
            if re.match(r"^\|\s*---", line) or ("事项" in line and "怎么做" in line):
                continue
            cols = [c.strip() for c in line.strip("|").split("|")]
            if cols and cols[0] and cols[0] != "事项":
                pending.append(cols[0][:60])
    must = None
    m = re.search(
        r"当前必做人工仍为\s*(\d+)|当前必须做\s*(\d+)\s*项|当前必做\s*(\d+)\s*项",
        text,
    )
    if m:
        must = int(next(g for g in m.groups() if g is not None))
    return {
        "pending_table_rows": len(pending),
        "pending_titles": pending,
        "must_do_declared": must,
    }


def status_md_excerpt(path: Path) -> str:
    text = _read(path)
    lines = []
    for line in text.splitlines():
        if line.startswith("#") or line.startswith("-") or line.startswith(">"):
            lines.append(line)
        if len(lines) >= 45:
            break
    return "\n".join(lines)


def print_primary(board: dict, phase0: dict, product: dict, human: dict) -> None:
    """Primary e2e metrics — report to user only when these change."""
    print("=== PRIMARY e2e metrics (report only when these change) ===")
    print(
        "tier: delivered=✅ / partial=🟡 / not_started=⬜ ; "
        "quality/release stay separate (feature_list.product_features)"
    )
    print(
        f"1. planned51: {board['delivered']}/{board['partial']}/{board['not_started']} "
        f"of {board['planned_total']} (~{board['overall_pct_note']}) "
        f"[board]; json delivery={product['delivery']}"
    )
    print(
        f"2. first_product★: delivered={board['first_delivered']} "
        f"partial≈{board['first_partial']} not_started={board['first_not_started']} "
        f"of {board['first_total']} (~{board['first_pct_note']}); "
        f"json first_n={product['first_product_n']} first_delivery={product['first_delivery']}"
    )
    print(
        f"3. phase0_F: passes_true={phase0['passes_true']} "
        f"passes_false={phase0['passes_false']} "
        f"false_ids={', '.join(phase0['false_ids'])} "
        f"(F006/F009/F010 must stay false until human evidence)"
    )
    print(
        f"4. quality_gate_steps_real: "
        f"{board['quality_real_done']}/{board['quality_real_total']} "
        f"(board §3; tools may be ready — real human steps still count)"
    )
    td = board.get("tech_debt") or {}
    print(
        f"5. tech_debt: {td.get('resolved')}/{td.get('partial')}/{td.get('open')} "
        f"of {td.get('total')} (resolved/partial/open)"
    )
    print(
        f"6. human_inputs: must={board['human_must']} "
        f"future={board['human_pending']} "
        f"(human-inputs table rows={human['pending_table_rows']}, "
        f"declared_must={human['must_do_declared']})"
    )
    freeze_ids = ", ".join(x["id"] for x in product["freeze"])
    print(
        f"7. freeze_until_first_mode_human_eval: {freeze_ids} "
        f"(no new scope; statuses unchanged by this script)"
    )
    print(
        "milestone report rule: ≤150 Chinese chars + one openable artifact path; "
        "only when a primary metric above changes."
    )


def main() -> int:
    status_path = ROOT / "STATUS.md"
    fl_path = ROOT / "feature_list.json"
    board_path = ROOT / "docs" / "exec-plans" / "progress-board.md"
    hi_path = ROOT / "docs" / "exec-plans" / "human-inputs.md"

    if not status_path.is_file():
        print("MISSING STATUS.md", file=sys.stderr)
        return 2

    phase0 = feature_list_phase0(fl_path)
    product = product_features_metrics(fl_path)
    board = progress_board_metrics(board_path)
    human = human_inputs_open(hi_path)

    print_primary(board, phase0, product, human)

    print("\n=== STATUS.md (excerpt) ===")
    print(status_md_excerpt(status_path))
    print(f"(bytes={status_path.stat().st_size})")

    print("\n=== freeze detail (read-only) ===")
    for row in product["freeze"]:
        print(
            f"  {row['id']} {row['name']}: delivery={row['delivery_status']} "
            f"quality={row['quality_status']} release={row['release_status']}"
        )

    print("\n=== offline primary-path commands (no paid calls) ===")
    print("  python -B scripts/status.py")
    print(
        "  python -B scripts/validate-demo.py "
        "--project artifacts/demo-phase0 "
        "--run f76f5d6495314c04ae04083614d4afd6"
    )
    print(
        "  python -B scripts/validate-inspection-ui.py "
        "--project artifacts/demo-phase0 "
        "--run f76f5d6495314c04ae04083614d4afd6"
    )
    print(
        "  # full offline gate (long): ./scripts/verify.ps1 "
        "# format/lint/types/pytest/wheels — not required every session"
    )

    print("\n=== tip ===")
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
