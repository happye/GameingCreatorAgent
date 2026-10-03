from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Literal

from gamingcreator.domain.time import SourceInstant, SourceRange


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    evidence_id: str
    media_id: str
    kind: Literal["image", "audio"]
    source_time: SourceInstant | SourceRange
    artifact_path: Path
    sha256: str
    transform_version: str


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    media_id: str
    source_range: SourceRange
    text: str
    uncertainty: str | None = None


@dataclass(frozen=True, slots=True)
class SemanticEvent:
    event_id: str
    media_id: str
    run_id: str
    source_range: SourceRange
    observable_facts: tuple[str, ...]
    mechanic_tags: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    modality: Literal["visual", "audio", "combined"]
    uncertainty: str | None


@dataclass(frozen=True, slots=True)
class EmbeddingSpace:
    provider: str
    model: str
    revision_scope: str
    dimension: int
    normalization: Literal["none", "l2"]

    def __post_init__(self) -> None:
        if not self.provider or not self.model or not self.revision_scope:
            raise ValueError("Embedding space needs a complete model identity.")
        if type(self.dimension) is not int or self.dimension <= 0:
            raise ValueError("Embedding dimension must be a positive integer.")
        if self.normalization not in ("none", "l2"):
            raise ValueError("Unknown vector normalization.")


@dataclass(frozen=True, slots=True)
class Embedding:
    subject_id: str
    space: EmbeddingSpace
    vector: tuple[float, ...]
    text_hash: str

    def __post_init__(self) -> None:
        if len(self.vector) != self.space.dimension:
            raise ValueError("Vector dimension does not match its space.")
        if any(type(value) not in (int, float) or not isfinite(value) for value in self.vector):
            raise ValueError("Vectors must contain finite numeric values.")
