"""Split text into overlapping character chunks.

Overlap exists so information near chunk boundaries is less likely to be lost.
We start with simple character windows because they are easy to inspect before
introducing tokenizers or model-specific chunking strategies.
"""

from __future__ import annotations

import re

from app.config import settings
from app.schemas import ChunkItem
from app.utils.text import normalize_text


def _build_chunk_id(source: str, index: int, start: int) -> str:
    safe_source = re.sub(r"[^a-zA-Z0-9]+", "_", source).strip("_") or "document"
    return f"{safe_source}-{index:04d}-{start:06d}"


def chunk_text(source: str, text: str) -> list[ChunkItem]:
    normalized_text = normalize_text(text)
    if not normalized_text:
        raise ValueError("Cannot chunk an empty document.")

    step = settings.chunk_size - settings.chunk_overlap
    if step <= 0:
        raise ValueError("Chunk overlap must be smaller than chunk size.")

    chunks: list[ChunkItem] = []
    start = 0
    index = 0
    text_length = len(normalized_text)

    while start < text_length:
        end = min(start + settings.chunk_size, text_length)
        chunk_value = normalized_text[start:end].strip()
        if chunk_value:
            chunks.append(
                ChunkItem(
                    chunk_id=_build_chunk_id(source, index, start),
                    source=source,
                    text=chunk_value,
                    start_index=start,
                    end_index=end,
                )
            )
        if end >= text_length:
            break
        start += step
        index += 1

    return chunks
