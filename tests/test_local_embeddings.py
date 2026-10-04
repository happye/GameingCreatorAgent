import asyncio
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from gamingcreator.application.asr import ModelFile
from gamingcreator.application.providers import (
    CancellationContext,
    EmbeddingRequest,
    ProviderStatus,
)
from gamingcreator.infrastructure.local_embeddings import (
    REQUIRED_FILES,
    WORKER_SCHEMA,
    LocalEmbeddingProvider,
    LocalEmbeddingSettings,
)
from gamingcreator.infrastructure.media_process import ProcessOutput


@pytest.fixture
def provider(tmp_path, monkeypatch):
    directory = tmp_path / ".cache/models/e5"
    files = []
    for name in sorted(REQUIRED_FILES):
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        content = f"fixture-only {name}".encode()
        path.write_bytes(content)
        files.append(ModelFile(name, len(content), hashlib.sha256(content).hexdigest()))
    interpreter = tmp_path / ".venv/Scripts/python.exe"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_bytes(b"fake interpreter; never executed")
    monkeypatch.setattr(
        "gamingcreator.infrastructure.local_embeddings.verify_native", lambda *args: None
    )
    return LocalEmbeddingProvider(
        tmp_path,
        LocalEmbeddingSettings(
            directory, tuple(files), "fixture-e5", "a" * 40, native_library_directory=tmp_path
        ),
    )


def request(texts=("query: 建造房屋", "passage: player assembles shelter")):
    return EmbeddingRequest("run", texts, "embedding-v1")


def embed(provider, value=None, timeout=10):
    return asyncio.run(provider.embed(value or request(), CancellationContext("run", timeout)))


def install_fake(monkeypatch, calls, *, malformed=None):
    async def run(arguments, context, **kwargs):
        value = json.loads(Path(arguments[-1]).read_text())
        calls.append(value)
        vector = [1.0] + [0.0] * 383
        response = {
            "schema": WORKER_SCHEMA,
            "vectors": [vector for _ in value["texts"]],
            "nativeLibraries": [],
        }
        if malformed is not None:
            malformed(response)
        assert arguments[1:3] == ["-I", "-B"]
        assert kwargs["max_stdout_bytes"] == 16 * 1024 * 1024
        return ProcessOutput(json.dumps(response).encode(), b"")

    monkeypatch.setattr("gamingcreator.infrastructure.local_embeddings.run_media_process", run)


def test_offline_worker_preserves_full_space_and_text_identity(provider, monkeypatch):
    calls = []
    install_fake(monkeypatch, calls)
    result = embed(provider)
    assert result.status == ProviderStatus.COMPLETED
    assert len(result.output) == 2
    assert result.output[0].space.dimension == 384
    assert result.output[0].space.revision_scope.startswith("a" * 40 + ":")
    assert result.output[0].text_hash == hashlib.sha256(request().texts[0].encode()).hexdigest()
    details = json.loads(result.metadata.execution_details)
    assert details["cachedTexts"] == 0 and details["hardwareCostMeasured"] is False
    assert result.metadata.usage.cost_cny == 0
    assert list((provider.repository / ".cache/embedding-requests").iterdir()) == []


def test_warm_cache_skips_inference_but_still_verifies_assets(provider, monkeypatch):
    calls = []
    install_fake(monkeypatch, calls)
    first = embed(provider)
    second = embed(provider)
    assert first.output == second.output
    assert len(calls) == 1
    assert json.loads(second.metadata.execution_details)["cachedTexts"] == 2
    (provider.settings.model_directory / "tokenizer.json").write_bytes(b"modified")
    broken = embed(provider)
    assert broken.status == ProviderStatus.FAILED
    assert broken.error.code == "embedding.model_integrity"
    assert len(calls) == 1


def test_explicit_cold_mode_does_not_read_or_write_shared_vector_cache(provider, monkeypatch):
    calls = []
    install_fake(monkeypatch, calls)
    cold = LocalEmbeddingProvider(provider.repository, provider.settings, use_cache=False)
    assert embed(cold).status == ProviderStatus.COMPLETED
    assert embed(cold).status == ProviderStatus.COMPLETED
    assert len(calls) == 2
    assert not (provider.repository / ".cache/embeddings").exists()


def test_model_revision_change_cannot_reuse_cache(provider, monkeypatch):
    calls = []
    install_fake(monkeypatch, calls)
    first = embed(provider)
    second_provider = LocalEmbeddingProvider(
        provider.repository, replace(provider.settings, revision="b" * 40)
    )
    second = embed(second_provider)
    assert len(calls) == 2
    assert first.output[0].space != second.output[0].space


def test_manifest_file_order_does_not_change_vector_space(provider):
    reordered = LocalEmbeddingProvider(
        provider.repository,
        replace(provider.settings, model_files=tuple(reversed(provider.settings.model_files))),
    )
    assert reordered.space == provider.space


def test_asset_modified_during_worker_result_is_not_cached(provider, monkeypatch):
    async def modifying_worker(arguments, context, **kwargs):
        value = json.loads(Path(arguments[-1]).read_text())
        (provider.settings.model_directory / "tokenizer.json").write_bytes(
            b"changed during inference"
        )
        return ProcessOutput(
            json.dumps(
                {
                    "schema": WORKER_SCHEMA,
                    "vectors": [[1.0] + [0.0] * 383 for _ in value["texts"]],
                    "nativeLibraries": [],
                }
            ).encode(),
            b"",
        )

    monkeypatch.setattr(
        "gamingcreator.infrastructure.local_embeddings.run_media_process", modifying_worker
    )
    result = embed(provider)
    assert (
        result.status == ProviderStatus.FAILED and result.error.code == "embedding.model_integrity"
    )
    assert not (provider.repository / ".cache/embeddings").exists()


def test_invalid_later_vector_does_not_cache_earlier_vector(provider, monkeypatch):
    def invalidate_last(response):
        response["vectors"][-1] = [0.0] * 384

    install_fake(monkeypatch, [], malformed=invalidate_last)
    assert embed(provider).status == ProviderStatus.FAILED
    assert not (provider.repository / ".cache/embeddings").exists()


def test_text_change_reuses_only_matching_vectors(provider, monkeypatch):
    calls = []
    install_fake(monkeypatch, calls)
    embed(provider)
    embed(provider, request(("query: 跳跃", request().texts[1])))
    assert calls[1]["texts"] == ["query: 跳跃"]


def test_corrupted_cache_is_recomputed(provider, monkeypatch):
    calls = []
    install_fake(monkeypatch, calls)
    embed(provider)
    provider._cache_path(request().texts[0]).write_text('{"payload":{},"sha256":"bad"}')
    assert embed(provider).status == ProviderStatus.COMPLETED
    assert len(calls) == 2 and calls[1]["texts"] == [request().texts[0]]


def test_missing_model_never_network_falls_back(provider, monkeypatch):
    calls = []
    install_fake(monkeypatch, calls)
    (provider.settings.model_directory / "tokenizer.json").unlink()
    result = embed(provider)
    assert (
        result.status == ProviderStatus.FAILED and result.error.code == "embedding.model_integrity"
    )
    assert not calls


@pytest.mark.parametrize(
    "transform",
    [
        lambda value: value.update(schema="bad"),
        lambda value: value.update(vectors=[]),
        lambda value: value["vectors"][0].pop(),
        lambda value: value["vectors"][0].__setitem__(0, float("nan")),
        lambda value: value["vectors"][0].__setitem__(0, 0),
    ],
)
def test_invalid_worker_vectors_are_rejected(provider, monkeypatch, transform):
    install_fake(monkeypatch, [], malformed=transform)
    result = embed(provider)
    assert result.status == ProviderStatus.FAILED
    assert result.error.code == "embedding.response_invalid"


def test_cancelled_context_returns_typed_cancelled(provider):
    context = CancellationContext("run", 10)
    context.cancelled.set()
    result = asyncio.run(provider.embed(request(), context))
    assert result.status == ProviderStatus.CANCELLED
    assert result.error.code == "embedding.cancelled"


def test_timeout_covers_worker_and_cleans_request_directory(provider, monkeypatch):
    async def slow(*args, **kwargs):
        await asyncio.sleep(1)
        raise AssertionError("worker was not cancelled")

    monkeypatch.setattr("gamingcreator.infrastructure.local_embeddings.run_media_process", slow)
    result = embed(provider, timeout=0.05)
    assert result.status == ProviderStatus.FAILED and result.error.code == "embedding.timeout"
    assert list((provider.repository / ".cache/embedding-requests").iterdir()) == []


@pytest.mark.parametrize("texts", [("no prefix",), (), ("query: " + "a" * 9000,)])
def test_invalid_request_does_not_start_worker(provider, monkeypatch, texts):
    calls = []
    install_fake(monkeypatch, calls)
    result = embed(provider, request(texts))
    assert (
        result.status == ProviderStatus.FAILED and result.error.code == "embedding.request_invalid"
    )
    assert not calls


def test_external_model_path_is_refused(provider, monkeypatch, tmp_path):
    calls = []
    install_fake(monkeypatch, calls)
    restricted = LocalEmbeddingProvider(tmp_path / "other-root", provider.settings)
    result = embed(restricted)
    assert (
        result.status == ProviderStatus.FAILED and result.error.code == "embedding.assets_invalid"
    )
    assert not calls
