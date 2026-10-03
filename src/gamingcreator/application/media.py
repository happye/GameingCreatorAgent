from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Protocol

from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.media import MediaAsset, MediaPreprocessingResult


@dataclass(frozen=True, slots=True)
class SamplingParameters:
    interval_seconds: Fraction = Fraction(1)
    max_width: int = 512
    max_frames: int = 1000

    def __post_init__(self) -> None:
        if (
            self.interval_seconds <= 0
            or type(self.max_width) is not int
            or self.max_width < 2
            or type(self.max_frames) is not int
            or self.max_frames <= 0
        ):
            raise ValueError("Invalid media sampling parameters.")


class MediaProcessor(Protocol):
    async def probe(self, source: Path, context: CancellationContext) -> MediaAsset: ...

    async def preprocess(
        self,
        source: Path,
        output: Path,
        parameters: SamplingParameters,
        context: CancellationContext,
    ) -> MediaPreprocessingResult: ...
