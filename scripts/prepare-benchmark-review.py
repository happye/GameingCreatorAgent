"""Prepare/import manual review against an actual saved benchmark ranking; no search."""

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import cast

from gamingcreator.application.benchmark import loads_manifest
from gamingcreator.application.benchmark_preparation import canonical_json
from gamingcreator.application.benchmark_review import (
    MAX_REVIEW_BYTES,
    build_review_context,
    decode_object,
    judged_manifest,
    validate_review,
)
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.benchmark_preparation_files import (
    read_bounded,
    validate_bound_manifest,
)
from gamingcreator.infrastructure.benchmark_review_files import publish_review_bundle
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.ui.benchmark_review import render_benchmark_review


async def prepare(
    project: Path, report_path: Path, binding: Path
) -> tuple[dict[str, object], dict[str, object], bytes, bytes]:
    base_bytes = read_bounded(binding / "benchmark.json")
    validate_bound_manifest(binding, base_bytes)
    manifest = loads_manifest(base_bytes.decode("utf-8-sig"))
    report_bytes = read_bounded(report_path, MAX_REVIEW_BYTES)
    report = decode_object(report_bytes)
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        timelines = {
            source.run_id: await store.load_completed_timeline(source.run_id)
            for source in manifest.media
        }
        queries = cast(list[dict[str, object]], report["queries"])
        identifiers = {row["retrievalId"] for row in queries if row.get("retrievalId") is not None}
        if any(type(value) is not str or not value for value in identifiers):
            raise ValueError("报告检索身份无效。")
        retrievals = {
            identifier: await store.load_retrieval(identifier)
            for identifier in cast(set[str], identifiers)
        }
        context, template = build_review_context(
            decode_object(base_bytes),
            report,
            report_sha256=hashlib.sha256(report_bytes).hexdigest(),
            binding_sha256=hashlib.sha256(base_bytes).hexdigest(),
            timelines=timelines,
            retrievals=retrievals,
        )
        return context, template, base_bytes, report_bytes
    finally:
        await store.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="只读准备固定十位人工判分，或核对下载记录后生成评测文件。"
    )
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--record", type=Path)
    args = parser.parse_args(argv)
    try:
        project, report_path, binding = (
            args.project.resolve(),
            args.report.resolve(),
            args.binding.resolve(),
        )
        context, template, base_bytes, report_bytes = asyncio.run(
            prepare(project, report_path, binding)
        )
        outputs = {
            "review.html": render_benchmark_review(context, template).encode("utf-8"),
            "context.json": canonical_json(context),
            "record-template.json": canonical_json(template),
            "report-input.json": report_bytes,
        }
        protected = [project, report_path, binding]
        judged = 0
        if args.record is not None:
            record_path = args.record.resolve()
            data = read_bounded(record_path, MAX_REVIEW_BYTES)
            record = validate_review(data, template, context)
            manifest = judged_manifest(context, record)
            validate_bound_manifest(binding, canonical_json(manifest))
            outputs.update(
                {
                    "review-input.json": data,
                    "review-record.json": canonical_json(record),
                    "benchmark-judged.json": canonical_json(manifest),
                }
            )
            protected.append(record_path)
            judged = sum(
                slot["grade"] is not None
                for row in cast(list[dict[str, object]], record["queries"])
                for slot in cast(list[dict[str, object]], row["slots"])
            )
            if read_bounded(record_path, MAX_REVIEW_BYTES) != data:
                raise ValueError("保存期间人工记录已改变。")
        if (
            read_bounded(report_path, MAX_REVIEW_BYTES) != report_bytes
            or read_bounded(binding / "benchmark.json") != base_bytes
        ):
            raise ValueError("准备期间原报告或绑定已改变。")
        files = publish_review_bundle(args.output.resolve(), outputs, protected)
        print(
            json.dumps(
                {
                    "schemaVersion": "benchmark-review-result-v1",
                    "output": str(args.output.resolve()),
                    "files": files,
                    "judgedPositions": judged,
                    "qualityGate": None,
                    "paidRequestsSent": 0,
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (OSError, ValueError, UnicodeError, TypeError, KeyError, RecursionError, AppError):
        print(
            json.dumps(
                {
                    "code": "input.benchmark_review",
                    "message": "原报告／绑定／保存检索／来源或人工记录不符，请使用对应的新目录和资料。",
                    "qualityGate": None,
                },
                ensure_ascii=False,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
