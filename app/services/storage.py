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
from app.schemas import AskChunk, ChunkItem


def _build_output_name(source: str, fallback: str = "document") -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    source_stem = Path(source).stem or fallback
    safe_stem = re.sub(r"[^a-zA-Z0-9]+", "_", source_stem).strip("_") or fallback
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


def save_ask_record(
    *,
    question: str,
    top_k: int,
    answer_payload: dict[str, object],
    total_hits: int,
    chunks: list[AskChunk],
    sources: list[str],
) -> Path:
    output_path = settings.ask_log_dir / _build_output_name(question, fallback="ask")
    payload = {
        "question": question,
        "top_k": top_k,
        "answer": answer_payload.get("answer", ""),
        "answer_mode": answer_payload.get("answer_mode", "placeholder"),
        "answer_status": answer_payload.get("answer_status", "disabled"),
        "answer_note": answer_payload.get("answer_note"),
        "provider": answer_payload.get("provider", "placeholder"),
        "model": answer_payload.get("model"),
        "total_hits": total_hits,
        "returned_count": len(chunks),
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "chunks": jsonable_encoder(chunks),
        "sources": sources,
    }
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path
