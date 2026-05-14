"""EmbeddingService protocol + in-memory fake implementation."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingService(Protocol):
    """Protocol satisfied by any embedding backend (Gemini, model2vec, fake)."""

    async def embed(self, text: str) -> list[float]:
        """Return a single embedding vector for *text*."""
        ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per element of *texts*."""
        ...


class FakeEmbeddingService:
    """Deterministic fake embeddings for unit tests (no network calls).

    Returns a 768-dimensional float vector where index 0 is derived from
    ``hash(text) % 1000 / 1000.0`` and all other indices are 0.0.
    This gives stable, distinct vectors without any ML dependency.
    """

    DIM = 768

    async def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.DIM
        vec[0] = float(hash(text) % 1000) / 1000.0
        return vec

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]
