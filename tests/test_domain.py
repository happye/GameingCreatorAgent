import pytest

from gamingcreator.domain.models import Embedding, EmbeddingSpace
from gamingcreator.domain.time import INT64_MAX, SourceInstant, SourceRange


@pytest.mark.parametrize(
    ("start", "end", "duration"),
    [(True, 2, 3), (0, 1.5, 3), (-1, 2, 3), (0, 0, 3), (2, 1, 3), (0, 4, 3), (0, 1, INT64_MAX + 1)],
)
def test_source_interval_rejects_invalid_time(start: int, end: int, duration: int) -> None:
    with pytest.raises(ValueError):
        SourceRange(start, end, duration)


def test_source_interval_allows_exact_end_without_rounding() -> None:
    assert SourceRange(1, INT64_MAX, INT64_MAX).end_us == INT64_MAX
    assert SourceInstant(0, 10).time_us == 0
    with pytest.raises(ValueError):
        SourceInstant(10, 10)


def test_embedding_spaces_keep_provider_revision_and_normalization_distinct() -> None:
    original = EmbeddingSpace("provider-a", "model", "run:one", 2, "none")
    other_provider = EmbeddingSpace("provider-b", "model", "run:one", 2, "none")
    other_revision = EmbeddingSpace("provider-a", "model", "run:two", 2, "none")
    normalized = EmbeddingSpace("provider-a", "model", "run:one", 2, "l2")
    assert len({original, other_provider, other_revision, normalized}) == 4


@pytest.mark.parametrize("vector", [(1.0,), (float("nan"), 0.0), (float("inf"), 0.0), (True, 0.0)])
def test_embedding_rejects_wrong_dimensions_or_invalid_numeric_values(
    vector: tuple[float, ...],
) -> None:
    space = EmbeddingSpace("provider", "model", "run:one", 2, "none")
    with pytest.raises(ValueError):
        Embedding("subject", space, vector, "text-hash")
