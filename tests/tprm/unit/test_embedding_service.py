"""Unit tests for EmbeddingService protocol and FakeEmbeddingService."""
from __future__ import annotations

import pytest

from orchestra_tprm.embedding.service import EmbeddingService, FakeEmbeddingService


@pytest.fixture
def svc() -> FakeEmbeddingService:
    return FakeEmbeddingService()


@pytest.mark.asyncio
async def test_fake_embedding_returns_768_floats(svc: FakeEmbeddingService) -> None:
    vec = await svc.embed("hello world")
    assert len(vec) == 768
    assert all(isinstance(v, float) for v in vec)


@pytest.mark.asyncio
async def test_fake_embedding_deterministic_for_same_text(svc: FakeEmbeddingService) -> None:
    a = await svc.embed("same text")
    b = await svc.embed("same text")
    assert a == b


@pytest.mark.asyncio
async def test_fake_embedding_different_for_different_text(svc: FakeEmbeddingService) -> None:
    a = await svc.embed("text one")
    b = await svc.embed("text two")
    # At minimum index 0 should differ (hash-derived)
    assert a != b


@pytest.mark.asyncio
async def test_fake_embed_batch_returns_one_per_text(svc: FakeEmbeddingService) -> None:
    texts = ["alpha", "beta", "gamma"]
    results = await svc.embed_batch(texts)
    assert len(results) == 3
    for vec in results:
        assert len(vec) == 768


def test_fake_embedding_service_satisfies_protocol() -> None:
    svc = FakeEmbeddingService()
    assert isinstance(svc, EmbeddingService), (
        "FakeEmbeddingService must satisfy the EmbeddingService runtime_checkable Protocol"
    )
