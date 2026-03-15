"""Orchestrate retrieval-first question answering.

Version 0.3.3 keeps the retrieval path simple, preserves the local LM Studio
integration point, and now saves each ask result as JSON so the full answer
trace remains easy to inspect outside the API response.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from app.config import settings, to_relative_path
from app.schemas import AskChunk
from app.services.lmstudio import LMStudioError, generate_lm_studio_answer
from app.services.searcher import search_chunks
from app.services.storage import save_ask_record

PLACEHOLDER_ANSWER = (
    "Placeholder answer: no real model is connected yet. Review the retrieved chunks below."
)
DISABLED_NOTE = (
    "Set ASK_PROVIDER=lm_studio and configure LM_STUDIO_MODEL to enable local generation."
)


def _load_chunk_text_lookup(
    selected_keys: set[tuple[str, str]],
) -> dict[tuple[str, str], str]:
    if not selected_keys:
        return {}

    chunk_lookup: dict[tuple[str, str], str] = {}
    for json_path in sorted(settings.processed_dir.glob("*.json")):
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        for chunk_data in payload.get("chunks", []):
            key = (chunk_data["source"], chunk_data["chunk_id"])
            if key in selected_keys and key not in chunk_lookup:
                chunk_lookup[key] = chunk_data["text"]
    return chunk_lookup


def _chunk_dicts(chunks: list[AskChunk]) -> list[dict[str, Any]]:
    return [
        {
            "rank": chunk.rank,
            "source": chunk.source,
            "chunk_id": chunk.chunk_id,
            "score": chunk.score,
            "text": chunk.text,
        }
        for chunk in chunks
    ]


def _placeholder_payload(
    *,
    provider: str,
    answer_status: str,
    answer_note: str,
    model: Optional[str] = None,
) -> dict[str, Optional[str]]:
    return {
        "answer": PLACEHOLDER_ANSWER,
        "answer_mode": "placeholder",
        "answer_status": answer_status,
        "answer_note": answer_note,
        "provider": provider,
        "model": model,
    }


def ask_question(
    question: str,
    top_k: int = 3,
) -> tuple[list[AskChunk], list[str], int, dict[str, Optional[str]], str]:
    search_results, total_hits = search_chunks(query=question, top_k=top_k)
    selected_keys = {(result.source, result.chunk_id) for result in search_results}
    chunk_lookup = _load_chunk_text_lookup(selected_keys)

    ask_chunks = [
        AskChunk(
            rank=result.rank,
            source=result.source,
            chunk_id=result.chunk_id,
            score=result.score,
            text=chunk_lookup.get((result.source, result.chunk_id), ""),
        )
        for result in search_results
    ]
    sources = list(dict.fromkeys(chunk.source for chunk in ask_chunks))

    if settings.ask_provider == "placeholder":
        answer_payload = _placeholder_payload(
            provider="placeholder",
            answer_status="disabled",
            answer_note=DISABLED_NOTE,
        )
    elif not settings.lm_studio_model:
        answer_payload = _placeholder_payload(
            provider="lm_studio",
            answer_status="not_configured",
            answer_note="LM Studio is enabled but LM_STUDIO_MODEL is empty.",
        )
    elif not ask_chunks:
        answer_payload = _placeholder_payload(
            provider="lm_studio",
            answer_status="no_context",
            answer_note="No matching chunks were found, so the local model was not called.",
            model=settings.lm_studio_model,
        )
    else:
        try:
            answer_payload = generate_lm_studio_answer(question, _chunk_dicts(ask_chunks))
        except LMStudioError as exc:
            answer_payload = _placeholder_payload(
                provider="lm_studio",
                answer_status="unreachable",
                answer_note=str(exc),
                model=settings.lm_studio_model,
            )

    output_path = save_ask_record(
        question=question,
        top_k=top_k,
        answer_payload=answer_payload,
        total_hits=total_hits,
        chunks=ask_chunks,
        sources=sources,
    )
    return ask_chunks, sources, total_hits, answer_payload, to_relative_path(output_path)
