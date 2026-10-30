"""Explicit local music registration; no downloads or licensing assertions."""

from pathlib import Path
from typing import Any

from gamingcreator.application.providers import CancellationContext
from gamingcreator.infrastructure.music_library import MusicLibrary


async def execute_register_music(
    repository: Path,
    source: Path,
    title: str,
    source_description: str,
    license_status: str,
    license_evidence: Path | None,
) -> dict[str, Any]:
    track = await MusicLibrary(repository).register(
        source,
        title,
        source_description,
        license_status,
        license_evidence,
        CancellationContext("register-music", 600),
    )
    return track.public()
