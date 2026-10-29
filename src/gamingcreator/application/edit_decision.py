"""Explicit selection converts a ready template into a source-bound frame timeline."""

from typing import Any


def select_edit_decision(report: dict[str, Any], selection: str) -> dict[str, object]:
    selected = next((plan for plan in report["plans"] if plan["id"] == selection), None)
    if selected is None or not selected["ready"]:
        raise ValueError("Selected plan is unknown or has unresolved material/topic gaps.")
    return {
        "schemaVersion": "edit-decision-v1",
        "selectedPlan": selection,
        "fpsNumerator": report["fps"],
        "fpsDenominator": 1,
        "segments": selected["segments"],
        "rendered": False,
        "scriptStatus": selected["scriptStatus"],
    }
