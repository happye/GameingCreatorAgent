"""Contracts for a single explicitly selected local narration asset."""

import unicodedata
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LocalVoice:
    voice_id: str
    description: str
    language: str
    engine: str = "windows-sapi"


@dataclass(frozen=True, slots=True)
class NarrationRequest:
    request_id: str
    project_id: str
    text: str
    voice_id: str

    def __post_init__(self) -> None:
        for value in (self.request_id, self.project_id, self.voice_id):
            if not isinstance(value, str) or not value.strip() or len(value) > 2048:
                raise ValueError(
                    "Narration identities must be nonempty strings of at most 2048 characters."
                )
            if any(unicodedata.category(char).startswith("C") for char in value):
                raise ValueError("Narration identities contain control characters.")
        if not isinstance(self.text, str) or not self.text.strip() or len(self.text) > 10000:
            raise ValueError("Narration text must contain 1..10000 characters.")
        if any(
            unicodedata.category(char).startswith("C") and char not in "\n\r\t"
            for char in self.text
        ):
            raise ValueError("Narration text contains unsupported control characters.")


@dataclass(frozen=True, slots=True)
class NarrationArtifact:
    directory: Path
    wav_path: Path
    text_path: Path
    receipt_path: Path
    receipt_sha256: str
    voice: LocalVoice
    sample_rate: int
    channels: int
    sample_width: int
    sample_count: int
    wav_sha256: str
    text_sha256: str

    @property
    def duration_seconds(self) -> float:
        return self.sample_count / self.sample_rate
