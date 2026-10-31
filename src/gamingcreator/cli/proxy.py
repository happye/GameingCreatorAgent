"""make-proxy: build (or reuse) one recording's low-resolution editing proxy."""

import json
import sys
from pathlib import Path

from gamingcreator.application.providers import CancellationContext
from gamingcreator.infrastructure.proxy_media import make_proxy
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


async def execute_make_proxy(project: Path, run_id: str, repository: Path) -> None:
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        asset = (await store.load_run(run_id)).asset
    finally:
        await store.close()
    receipt = await make_proxy(
        repository,
        asset.source_path,
        asset.sha256,
        asset.duration_us,
        CancellationContext(f"proxy-{run_id}", 6 * 3600),
    )
    sys.stdout.write(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
