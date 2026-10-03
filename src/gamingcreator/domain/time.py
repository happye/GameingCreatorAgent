from dataclasses import dataclass

INT64_MAX = 2**63 - 1


def require_microseconds(value: int) -> None:
    if type(value) is not int or not 0 <= value <= INT64_MAX:
        raise ValueError("Time must be an integer in the nonnegative Int64 range.")


@dataclass(frozen=True, slots=True)
class SourceRange:
    """Half-open source interval, validated against its media duration."""

    start_us: int
    end_us: int
    duration_us: int

    def __post_init__(self) -> None:
        for value in (self.start_us, self.end_us, self.duration_us):
            require_microseconds(value)
        if not self.start_us < self.end_us <= self.duration_us:
            raise ValueError("Source interval must be nonempty and inside the media.")


@dataclass(frozen=True, slots=True)
class SourceInstant:
    """A frame instant is not represented as a zero-length clip."""

    time_us: int
    duration_us: int

    def __post_init__(self) -> None:
        require_microseconds(self.time_us)
        require_microseconds(self.duration_us)
        if self.time_us >= self.duration_us:
            raise ValueError("Source instant must precede the end of the media.")
