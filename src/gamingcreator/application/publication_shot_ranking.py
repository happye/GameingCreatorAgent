"""Rank the evidence-bearing shots of one finished video with a local embedding provider."""

from hashlib import sha256
from typing import Any

from gamingcreator.application.providers import (
    CancellationContext,
    EmbeddingProvider,
    EmbeddingRequest,
    ProviderStatus,
)
from gamingcreator.application.retrieval import _cosine
from gamingcreator.domain.errors import AppError, ExitCode


async def rank_shots(
    provider: EmbeddingProvider, publication_id: str, theme: str, shots: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not shots:
        return []
    texts = (f"query: {theme}", *(f"passage: {shot['description']}" for shot in shots))
    result = await provider.embed(
        EmbeddingRequest(publication_id, texts, "embedding-v1"),
        CancellationContext(publication_id, 120),
    )
    embeddings = result.output
    if result.status != ProviderStatus.COMPLETED or embeddings is None:
        raise AppError(
            "publication.theme_embedding",
            "本机语义模型暂未完成主题选段。",
            ExitCode.PROVIDER,
        )
    if len(embeddings) != len(texts) or any(
        item.space != embeddings[0].space
        or item.subject_id != f"{publication_id}:{index}"
        or item.text_hash != sha256(text.encode("utf-8")).hexdigest()
        for index, (item, text) in enumerate(zip(embeddings, texts, strict=True))
    ):
        raise AppError(
            "publication.theme_identity",
            "主题向量与成片镜头不匹配。",
            ExitCode.PROVIDER,
        )
    scored = [
        (_cosine(embeddings[0], item), shot)
        for item, shot in zip(embeddings[1:], shots, strict=True)
    ]
    scored.sort(key=lambda item: (-item[0], item[1]["startFrame"], item[1]["endFrame"]))
    return [shot for _, shot in scored[:8]]
