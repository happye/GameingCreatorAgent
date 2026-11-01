"""Queue editing-proxy builds for many prepared/analyzed runs.

Each item still calls make_proxy: same byte budget, duration check, and
temporary-directory cleanup on failure. The batch only orders work and reports
per-run outcomes; it never keeps a partial proxy directory of its own.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.proxy_media import make_proxy
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


def _valid_sha(value: object) -> bool:
    return (
        isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
    )


SCHEMA = "make-proxy-batch-v1"
_BUILD_TIMEOUT = 6 * 3600


def _summary(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"built": 0, "reused": 0, "shared": 0, "failed": 0}
    for item in items:
        status = item["status"]
        if status in counts:
            counts[status] += 1
    return counts


async def resolve_proxy_batch_runs(project: Path, run_ids: Sequence[str] | None) -> list[str]:
    """Explicit run ids, or every eligible run in the project (stable order)."""
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        listed = await store.list_runs()
        if run_ids is None:
            ordered: list[str] = []
            for run_id, _status in listed:
                try:
                    asset = (await store.load_run(run_id)).asset
                except Exception:
                    continue
                if (
                    type(asset.duration_us) is int
                    and asset.duration_us > 0
                    and _valid_sha(asset.sha256)
                ):
                    ordered.append(run_id)
            return ordered
        # Preserve caller order; duplicates kept so the report mirrors the request.
        return list(run_ids)
    finally:
        await store.close()


async def make_proxies_for_runs(
    project: Path,
    repository: Path,
    run_ids: Sequence[str] | None,
    *,
    tools: Path | None = None,
) -> dict[str, Any]:
    """Build or reuse proxies for the given runs (or all eligible), one after another."""
    project = project.resolve()
    repository = repository.resolve()
    selected = await resolve_proxy_batch_runs(project, run_ids)
    items: list[dict[str, Any]] = []
    by_sha: dict[str, dict[str, Any]] = {}
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        for run_id in selected:
            if type(run_id) is not str or not run_id:
                items.append(
                    {
                        "runId": run_id,
                        "status": "failed",
                        "error": "Run id must be a non-empty string.",
                    }
                )
                continue
            try:
                asset = (await store.load_run(run_id)).asset
            except Exception as error:
                items.append(
                    {
                        "runId": run_id,
                        "status": "failed",
                        "error": f"Cannot load run: {error}",
                    }
                )
                continue
            if (
                type(asset.duration_us) is not int
                or asset.duration_us <= 0
                or not _valid_sha(asset.sha256)
            ):
                items.append(
                    {
                        "runId": run_id,
                        "sourceSha256": getattr(asset, "sha256", None),
                        "status": "failed",
                        "error": "Run has no eligible media asset for a proxy.",
                    }
                )
                continue
            prior = by_sha.get(asset.sha256)
            if prior is not None:
                items.append(
                    {
                        "runId": run_id,
                        "sourceSha256": asset.sha256,
                        "status": "shared",
                        "sharedWithRunId": prior["runId"],
                        "receipt": prior.get("receipt"),
                    }
                )
                continue
            try:
                receipt = await make_proxy(
                    repository,
                    asset.source_path,
                    asset.sha256,
                    asset.duration_us,
                    CancellationContext(f"proxy-batch-{run_id}", _BUILD_TIMEOUT),
                    tools,
                )
            except (AppError, ValueError, OSError) as error:
                failed = {
                    "runId": run_id,
                    "sourceSha256": asset.sha256,
                    "status": "failed",
                    "error": str(error),
                }
                items.append(failed)
                by_sha[asset.sha256] = failed
                continue
            status = "reused" if receipt.get("reused") else "built"
            row = {
                "runId": run_id,
                "sourceSha256": asset.sha256,
                "status": status,
                "receipt": receipt,
            }
            items.append(row)
            by_sha[asset.sha256] = row
    finally:
        await store.close()
    return {
        "schemaVersion": SCHEMA,
        "project": str(project),
        "items": items,
        "summary": _summary(items),
    }
