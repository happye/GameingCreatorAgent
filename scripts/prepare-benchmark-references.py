"""Prepare a raw-footage editor or verify its record and export a plan; no inference."""

import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from gamingcreator.application.benchmark_preparation import canonical_json, loads_plan
from gamingcreator.application.benchmark_reference_review import (
    MAX_RECORD_BYTES,
    build_reference_context,
    validate_reference_record,
)
from gamingcreator.application.benchmark_review import decode_object
from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.errors import AppError
from gamingcreator.domain.media import MediaAsset
from gamingcreator.infrastructure.benchmark_preparation_files import read_bounded
from gamingcreator.infrastructure.benchmark_review_files import publish_review_bundle
from gamingcreator.infrastructure.ffmpeg_media import FfmpegMediaProcessor, hash_file
from gamingcreator.ui.benchmark_reference_review import render_reference_review

ROOT = Path(__file__).resolve().parents[1]


async def probe_plan(document: dict[str, object], base: Path) -> dict[str, MediaAsset]:
    plan = loads_plan(canonical_json(document).decode())
    processor = FfmpegMediaProcessor(ROOT)
    assets = {}
    for source in plan.sources:
        path = Path(source.path)
        assets[source.source_id] = await processor.probe(
            (path if path.is_absolute() else base / path).resolve(),
            CancellationContext("reference-probe", 120),
        )
    return assets


def read_editor(directory: Path) -> tuple[dict[str, object], dict[str, bytes]]:
    if (directory / "receipt.json").is_symlink() or (directory / "receipt.json").is_junction():
        raise ValueError("原片标注回执不能通过链接替换。")
    receipt = decode_object(read_bounded(directory / "receipt.json"))
    names = {"plan-input.json", "context.json", "record-template.json", "review.html"}
    if (
        set(receipt) != {"schemaVersion", "files", "qualityGate", "paidRequestsSent"}
        or receipt["schemaVersion"] != "benchmark-review-receipt-v1"
        or type(receipt["files"]) is not dict
        or set(receipt["files"]) != names
        or receipt["qualityGate"] is not None
        or receipt["paidRequestsSent"] != 0
    ):
        raise ValueError("原片标注包不完整。")
    files = {}
    for name in names:
        path = directory / name
        if path.is_symlink() or path.is_junction():
            raise ValueError("原片标注包不能通过链接替换。")
        data = read_bounded(path, 16_777_216)
        if hashlib.sha256(data).hexdigest() != cast(dict[str, object], receipt["files"])[name]:
            raise ValueError("原片标注资料已经改变。")
        files[name] = data
    return decode_object(files["context.json"]), files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="准备分析前原片标注，或核对记录后导出待冻结计划。")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path)
    source.add_argument("--review-directory", type=Path)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if bool(args.review_directory) != bool(args.record):
        parser.error("导入需要同时填写--review-directory和--record。")
    try:
        if args.input is not None:
            input_path = args.input.resolve()
            original = read_bounded(input_path)
            plan = loads_plan(original.decode("utf-8-sig"))
            assets = asyncio.run(probe_plan(plan.document, input_path.parent))
            context, template = build_reference_context(plan, assets, datetime.now(UTC).isoformat())
            outputs = {
                "plan-input.json": original,
                "context.json": canonical_json(context),
                "record-template.json": canonical_json(template),
                "review.html": render_reference_review(context, template).encode(),
            }
            protected = [input_path]
            if read_bounded(input_path) != original:
                raise ValueError("准备期间计划已改变。")
        else:
            directory = args.review_directory.resolve()
            context, inputs = read_editor(directory)
            assets = asyncio.run(probe_plan(cast(dict[str, object], context["plan"]), directory))
            data = read_bounded(args.record, MAX_RECORD_BYTES)
            record = validate_reference_record(data, context, assets)
            outputs = {
                "context.json": inputs["context.json"],
                "record-input.json": data,
                "reference-record.json": canonical_json(record),
                "benchmark-plan.json": canonical_json(record["plan"]),
            }
            protected = [directory, args.record]
            if (
                read_editor(directory)[1] != inputs
                or read_bounded(args.record, MAX_RECORD_BYTES) != data
            ):
                raise ValueError("导入期间原资料已改变。")
        for asset in assets.values():
            if hash_file(asset.source_path) != asset.sha256:
                raise ValueError("保存期间原录像已改变。")
            protected.append(asset.source_path)
        hashes = publish_review_bundle(args.output.resolve(), outputs, protected)
        print(
            json.dumps(
                {
                    "schemaVersion": "benchmark-reference-result-v1",
                    "output": str(args.output.resolve()),
                    "files": hashes,
                    "isFrozen": False,
                    "qualityGate": None,
                    "paidRequestsSent": 0,
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (
        OSError,
        ValueError,
        UnicodeError,
        TypeError,
        KeyError,
        OverflowError,
        RecursionError,
        AppError,
    ):
        print(
            json.dumps(
                {
                    "code": "input.benchmark_references",
                    "message": "原片、事前计划或标注记录不符，请保留资料并使用新输出目录。",
                    "qualityGate": None,
                },
                ensure_ascii=False,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
