"""Persist processed chunks as JSON files on disk.

JSON keeps the first version transparent: you can inspect outputs with any
editor before introducing a database or vector store.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi.encoders import jsonable_encoder

from app.config import settings
from app.schemas import ChunkItem


def _build_output_name(source: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    source_stem = Path(source).stem or "document"
    safe_stem = re.sub(r"[^a-zA-Z0-9]+", "_", source_stem).strip("_") or "document"
    return f"{timestamp}_{safe_stem}.json"


def save_chunks(source: str, chunks: list[ChunkItem]) -> Path:
    if not chunks:
        raise ValueError("No chunks to save.")

    output_path = settings.processed_dir / _build_output_name(source)
    payload = {
        "source": source,
        "chunk_count": len(chunks),
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "chunks": jsonable_encoder(chunks),
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path
