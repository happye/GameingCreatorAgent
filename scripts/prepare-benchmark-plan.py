"""Generate a local source/query form, preserving unknown declarations; no inference."""

import argparse
import json
from pathlib import Path
from typing import cast

from gamingcreator.application.benchmark_plan_draft import (
    DRAFT_VERSION,
    empty_draft,
    inventory_to_draft,
    plan_to_draft,
    validate_draft,
)
from gamingcreator.application.benchmark_preparation import canonical_json, loads_plan
from gamingcreator.application.benchmark_review import decode_object
from gamingcreator.infrastructure.benchmark_preparation_files import read_bounded
from gamingcreator.infrastructure.benchmark_review_files import publish_review_bundle
from gamingcreator.ui.benchmark_plan_editor import render_plan_editor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="生成事前录像／查询登记表单，不读取录像或分析项目。"
    )
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        draft = empty_draft()
        evidence: dict[str, object] | None = None
        outputs: dict[str, bytes] = {}
        protected = []
        if args.input is not None:
            input_path = args.input.resolve()
            original = read_bounded(input_path)
            document = decode_object(original)
            version = document.get("schemaVersion")
            if version == DRAFT_VERSION:
                draft = validate_draft(document)
            elif isinstance(version, str) and version.startswith("source-inventory-"):
                # Identity fields only; groups, purposes and declarations stay unknown.
                draft, evidence = inventory_to_draft(original)
            else:
                draft = plan_to_draft(loads_plan(original.decode("utf-8-sig")))
            for row in cast(list[dict[str, object]], draft["sources"]):
                if row["path"]:
                    path = Path(cast(str, row["path"]))
                    row["path"] = str(
                        (path if path.is_absolute() else input_path.parent / path).resolve()
                    )
            if read_bounded(input_path) != original:
                raise ValueError("登记期间原输入已改变。")
            outputs["plan-input.json"] = original
            protected.append(input_path)
        draft = validate_draft(draft)
        if evidence is not None:
            # Re-key by the final path so notes stay with a file even if its ID is edited.
            notes = cast(dict[str, object], evidence["sources"])
            evidence["sources"] = {
                row["path"]: notes[cast(str, row["id"])]
                for row in cast(list[dict[str, object]], draft["sources"])
                if row["id"] in notes
            }
        protected.extend(
            Path(cast(str, row["path"]))
            for row in cast(list[dict[str, object]], draft["sources"])
            if row["path"]
        )
        outputs.update(
            {
                "draft.json": canonical_json(draft),
                "edit.html": render_plan_editor(draft, evidence).encode(),
            }
        )
        hashes = publish_review_bundle(args.output.resolve(), outputs, protected)
        print(
            json.dumps(
                {
                    "schemaVersion": "benchmark-plan-editor-result-v1",
                    "output": str(args.output.resolve()),
                    "files": hashes,
                    "sourceMediaVerified": False,
                    "startedFromInventory": evidence is not None,
                    "humanFieldsFilled": False if evidence is not None else None,
                    "isFrozen": False,
                    "qualityGate": None,
                    "paidRequestsSent": 0,
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (OSError, ValueError, UnicodeError, TypeError, KeyError, OverflowError, RecursionError):
        print(
            json.dumps(
                {
                    "code": "input.benchmark_plan_draft",
                    "message": "登记资料不符，请保留原输入并使用新输出目录；已有人工参考请用原片标注继续。",
                    "qualityGate": None,
                },
                ensure_ascii=False,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
