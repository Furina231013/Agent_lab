"""Wrap embedding model loading behind one small service.

Keeping embedding code here avoids scattering heavy model setup across ingest,
search, and ask. That makes the first JSON-based vector search easier to read
today and easier to swap for another backend later.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import settings
from app.schemas import ChunkItem


@lru_cache(maxsize=1)
def _get_model():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers is not installed. Run `pip install -r requirements.txt`."
        ) from exc

    try:
        return SentenceTransformer(
            settings.embedding_model_name,
            device=settings.embedding_device,
        )
    except Exception as exc:  # pragma: no cover - depends on local model download/runtime
        raise RuntimeError(
            f"Failed to load embedding model '{settings.embedding_model_name}'."
        ) from exc


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    model = _get_model()
    embeddings = model.encode(texts, normalize_embeddings=True)
    return [list(map(float, embedding)) for embedding in embeddings]


def embed_text(text: str) -> list[float]:
    embeddings = embed_texts([text])
    return embeddings[0] if embeddings else []


def attach_embeddings(chunks: list[ChunkItem]) -> list[ChunkItem]:
    if not chunks:
        return []

    embeddings = embed_texts([chunk.text for chunk in chunks])
    return [
        chunk.model_copy(update={"embedding": embedding})
        for chunk, embedding in zip(chunks, embeddings)
    ]
