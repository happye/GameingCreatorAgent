"""Public, local-only template planning entry point."""

import json
from pathlib import Path

from gamingcreator.application.creative_planner import candidates, plan_creation
from gamingcreator.application.edit_decision import select_edit_decision
from gamingcreator.domain.creation import CreativeBrief
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.creation_files import write_creation
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore


async def execute_plan_creation(
    project: Path,
    runs: list[str],
    brief_path: Path,
    output: Path,
    events: list[str],
    fps: int,
    selection: str | None,
) -> dict[str, object]:
    try:
        if not runs or len(runs) != len(set(runs)):
            raise ValueError("Select unique Completed run IDs.")
        if brief_path.stat().st_size > 1_000_000:
            raise ValueError("Brief exceeds 1 MB.")
        raw = json.loads(brief_path.read_text(encoding="utf-8-sig"))
        brief = CreativeBrief.from_json(raw)
        store = await SqliteTimelineStore.open(project, read_only=True)
        try:
            timelines = tuple([await store.load_completed_timeline(run) for run in runs])
        finally:
            await store.close()
        report = plan_creation(brief, candidates(timelines, tuple(events)), fps)
        report["brief"] = raw
        documents: dict[str, object] = {"plans.json": report}
        if selection is not None:
            documents["edit-decision.json"] = select_edit_decision(report, selection)
        result = write_creation(
            output, documents, (project, brief_path, *(t.run.asset.source_path for t in timelines))
        )
        return {**result, "planner": "offline-template-v1", "selected": selection}
    except (ValueError, OSError) as error:
        raise AppError("creation.invalid_input", str(error), ExitCode.INPUT) from error
