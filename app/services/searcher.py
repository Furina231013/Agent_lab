"""Search over saved chunks with a very simple keyword score.

Starting with naive matching makes the retrieval path easy to debug. Later,
the scoring function can be replaced by embeddings or vector search while the
API contract and storage flow stay familiar.
"""

from __future__ import annotations

import json

from app.config import settings
from app.schemas import SearchResult
from app.utils.text import normalize_text


def _score_text(query: str, text: str) -> int:
    normalized_text = normalize_text(text)
    exact_score = normalized_text.count(query)
    if exact_score > 0:
        return exact_score

    tokens = [token for token in query.split(" ") if token]
    return sum(normalized_text.count(token) for token in tokens)


def search_chunks(query: str, top_k: int = 5) -> list[SearchResult]:
    normalized_query = normalize_text(query)
    if not normalized_query:
        return []

    matches: list[SearchResult] = []
    for json_path in sorted(settings.processed_dir.glob("*.json")):
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        for chunk_data in payload.get("chunks", []):
            score = _score_text(normalized_query, chunk_data.get("text", ""))
            if score <= 0:
                continue
            matches.append(
                SearchResult(
                    chunk_id=chunk_data["chunk_id"],
                    source=chunk_data["source"],
                    text=chunk_data["text"],
                    score=score,
                )
            )

    matches.sort(key=lambda item: (-item.score, item.source, item.chunk_id))
    return matches[:top_k]
