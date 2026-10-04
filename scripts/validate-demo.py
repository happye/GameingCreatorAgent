"""Validate an existing completed demo offline; never analyze or call a remote API."""

import argparse
import asyncio
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from gamingcreator.application.analysis import _write_export
from gamingcreator.cli.main import execute_benchmark, execute_search
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


async def validate(
    project: Path, run_id: str, repository: Path, earlier_runs: list[str]
) -> dict[str, Any]:
    store = await SqliteTimelineStore.open(project)
    try:
        timeline = await store.load_completed_timeline(run_id)
        _write_export(project, timeline)
        asset = timeline.run.asset
        attempts = timeline.invocations
        known = all(item.metadata.usage.cost_cny is not None for item in attempts)
        cost = sum((item.metadata.usage.cost_cny or Decimal(0) for item in attempts), Decimal(0))
        earlier_attempts = []
        for historical in earlier_runs:
            old = await store.load_timeline(historical, require_completed=False)
            if old.run.asset.sha256 != asset.sha256:
                raise ValueError("Earlier experiment must refer to the same source.")
            earlier_attempts += [
                {
                    "runId": historical,
                    "status": old.run.status,
                    "eventCount": len(old.events),
                    "unknownCosts": sum(
                        item.metadata.usage.cost_cny is None for item in old.invocations
                    ),
                    "knownCostCny": str(
                        sum(
                            (
                                item.metadata.usage.cost_cny or Decimal(0)
                                for item in old.invocations
                            ),
                            Decimal(0),
                        )
                    ),
                }
            ]
    finally:
        await store.close()
    report: dict[str, Any] = {
        "schemaVersion": 1,
        "evidenceType": "real-development-video",
        "runId": run_id,
        "sourceSha256": asset.sha256,
        "sourceDurationUs": asset.duration_us,
        "eventCount": len(timeline.events),
        "transcriptCount": len(timeline.transcripts),
        "visionWindows": sum(row.stage_id.startswith("vision-") for row in timeline.checkpoints),
        "knownApiCostCny": str(cost),
        "totalApiCostCny": str(cost) if known else None,
        "billingConfirmed": False,
        "earlierExperimentRuns": earlier_attempts,
        "queries": [],
        "humanQualityGate": None,
    }
    queries = (
        ("attack-zh", "寻找角色打斗和攻击的片段", "main"),
        ("attack-en", "Find clips of fighters attacking each other in the arena", "main"),
        ("vehicle-development-negative", "汽车修理工拆卸发动机维修车辆", "negative"),
    )
    retrieval_id = None
    for query_id, query, _ in queries:
        comparisons: dict[str, Any] = {}
        for mode in ("lexical", "semantic", "hybrid"):
            first = await execute_search(project, run_id, query, repository, mode=mode)
            second = await execute_search(project, run_id, query, repository, mode=mode)
            stable = first["candidates"] == second["candidates"]
            if not stable:
                raise ValueError("Repeated retrieval candidates changed.")
            comparisons[mode] = {
                "firstMs": first["elapsedMs"],
                "repeatMs": second["elapsedMs"],
                "stable": stable,
                "candidates": second["candidates"],
                "embedding": second["embedding"],
                "abstentionReason": second["abstentionReason"],
            }
            retrieval_id = second["retrievalId"]
        report["queries"].append({"id": query_id, "query": query, "modes": comparisons})
    manifest = {
        "schemaVersion": 1,
        "datasetId": "demo-development-unlabelled",
        "labelVersion": None,
        "humanLabels": {
            "confirmed": False,
            "annotators": [],
            "reviewed": False,
            "frozenAt": None,
            "independentTestSet": False,
        },
        "media": [
            {
                "mediaId": asset.media_id,
                "runId": run_id,
                "sha256": asset.sha256,
                "durationUs": asset.duration_us,
            }
        ],
        "queries": [
            {
                "id": query_id,
                "text": query,
                "kind": kind,
                "mediaId": asset.media_id,
                "runId": run_id,
                "referenceEvents": [],
                "candidateLabels": [],
            }
            for query_id, query, kind in queries
        ],
    }
    manifest_path = project / "demo-benchmark-input.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    benchmark = await execute_benchmark(
        project, manifest_path, project / "demo-benchmark-report.json", repository
    )
    if benchmark["qualityGate"] is not None or not benchmark["mediaVerified"]:
        raise ValueError("Unlabelled demo must remain unverified with verified media.")
    report["benchmark"] = benchmark
    child = await asyncio.to_thread(
        subprocess.run,
        [
            sys.executable,
            "-B",
            str(Path(__file__).resolve()),
            "--project",
            str(project),
            "--run",
            run_id,
            "--reader",
            str(retrieval_id),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=30,
    )
    if child.returncode != 0:
        raise ValueError("Second process could not read the stored search.")
    report["secondProcessRead"] = json.loads(child.stdout)
    report["limitations"] = [
        "These are development queries, with no frozen independent human labels.",
        "First/repeat retrieval times reuse existing model/document caches, not a cold full analysis.",
        "Scores and semantic thresholds are uncalibrated; negative-query misses must remain visible.",
        "No hour-long performance gate or UI was tested.",
    ]
    destination = project / "demo-validation.json"
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return {
        "report": str(destination),
        "runId": run_id,
        "eventCount": len(timeline.events),
        "apiCostEstimateCny": str(cost),
        "stableQueries": 9,
        "humanQualityGate": None,
    }


async def read(project: Path, run_id: str, retrieval_id: str) -> dict[str, Any]:
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        timeline = await store.load_completed_timeline(run_id)
        result = await store.load_retrieval(retrieval_id)
        if result["runId"] != run_id:
            raise ValueError("Search does not belong to the requested run.")
        hits = result["hits"]
        if not isinstance(hits, list):
            raise ValueError("Stored search has invalid hits.")
        return {
            "status": "completed",
            "runId": run_id,
            "eventCount": len(timeline.events),
            "retrievalId": retrieval_id,
            "hitCount": len(hits),
        }
    finally:
        await store.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--reader")
    parser.add_argument("--earlier-run", action="append", default=[])
    args = parser.parse_args()
    try:
        result = (
            asyncio.run(read(args.project.resolve(), args.run, args.reader))
            if args.reader
            else asyncio.run(
                validate(
                    args.project.resolve(),
                    args.run,
                    Path(__file__).resolve().parents[1],
                    args.earlier_run,
                )
            )
        )
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except Exception:
        print(
            "demo.validation_failed: inspect the preserved project and source files",
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
