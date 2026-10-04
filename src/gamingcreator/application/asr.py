from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ModelFile:
    name: str
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class LocalAsrSettings:
    model_directory: Path
    model_name: str
    model_revision: str
    model_files: tuple[ModelFile, ...]
    native_library_directory: Path | None = None
    compute_type: str = "int8"
    cpu_threads: int = 2
    beam_size: int = 5
    vad_filter: bool = True
    native_library_files: tuple[ModelFile, ...] = ()
