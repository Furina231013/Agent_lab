"""Search saved chunks with both keyword and vector retrieval.

The project keeps keyword search as a baseline because it is transparent and
easy to debug. Vector search is added next to it, not instead of it, so you
can compare behavior before introducing a real vector database.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from app.config import settings
from app.schemas import SearchResult
from app.services.embedder import embed_text
from app.utils.text import normalize_text

PREVIEW_RADIUS = 80
PREVIEW_LOOKAROUND = 40
SENTENCE_BOUNDARIES = ("。", "！", "？", "；", ".", "!", "?", "\n")
VECTOR_MIN_SIMILARITY = 0.2


@dataclass
class _SearchMatch:
    source: str
    chunk_id: str
    score: float
    match_count: int
    match_term: str
    match_index: int
    preview: str


def _iter_saved_chunks() -> list[dict[str, object]]:
    chunk_items: list[dict[str, object]] = []
    for json_path in sorted(settings.processed_dir.glob("*.json")):
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        chunk_items.extend(payload.get("chunks", []))
    return chunk_items


def _count_occurrences(text: str, term: str) -> int:
    return text.casefold().count(term.casefold())


def _find_match_index(text: str, term: str) -> int:
    return text.casefold().find(term.casefold())


def _build_preview(text: str, match_index: int, match_term: str) -> str:
    preview_start = max(match_index - PREVIEW_RADIUS, 0)
    preview_end = min(len(text), match_index + len(match_term) + PREVIEW_RADIUS)

    left_window_start = max(preview_start - PREVIEW_LOOKAROUND, 0)
    left_boundary = max(
        text.rfind(boundary, left_window_start, preview_start)
        for boundary in SENTENCE_BOUNDARIES
    )
    left_space = text.rfind(" ", left_window_start, preview_start)
    chosen_left = max(left_boundary, left_space)
    if chosen_left >= 0:
        preview_start = chosen_left + 1

    right_window_end = min(preview_end + PREVIEW_LOOKAROUND, len(text))
    right_positions = [
        text.find(boundary, preview_end, right_window_end)
        for boundary in SENTENCE_BOUNDARIES
    ]
    right_positions = [position for position in right_positions if position >= 0]
    right_space = text.find(" ", preview_end, right_window_end)
    if right_space >= 0:
        right_positions.append(right_space)
    if right_positions:
        preview_end = min(right_positions)

    preview = text[preview_start:preview_end].strip()
    first_token, separator, remainder = preview.partition(" ")
    if (
        separator
        and first_token
        and first_token[0].isascii()
        and not first_token[0].isalnum()
    ):
        preview = remainder.lstrip()
    if preview_start > 0:
        preview = f"...{preview}"
    if preview_end < len(text):
        preview = f"{preview}..."
    return preview


def _build_leading_preview(text: str) -> str:
    if len(text) <= PREVIEW_RADIUS * 2:
        return text
    return _build_preview(text, 0, text[:1])


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0

    dot_product = sum(left_value * right_value for left_value, right_value in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot_product / (left_norm * right_norm)


def _evaluate_keyword_match(query: str, text: str) -> _SearchMatch | None:
    normalized_text = normalize_text(text)
    exact_count = _count_occurrences(normalized_text, query)
    if exact_count > 0:
        match_index = _find_match_index(normalized_text, query)
        return _SearchMatch(
            source="",
            chunk_id="",
            score=float(exact_count),
            match_count=exact_count,
            match_term=query,
            match_index=match_index,
            preview=_build_preview(normalized_text, match_index, query),
        )

    tokens = [token for token in query.split(" ") if token]
    token_hits: list[tuple[str, int, int]] = []
    for token in tokens:
        count = _count_occurrences(normalized_text, token)
        if count <= 0:
            continue
        token_hits.append((token, count, _find_match_index(normalized_text, token)))

    if not token_hits:
        return None

    match_term, _, match_index = min(token_hits, key=lambda item: item[2])
    total_count = sum(item[1] for item in token_hits)
    return _SearchMatch(
        source="",
        chunk_id="",
        score=float(total_count),
        match_count=total_count,
        match_term=match_term,
        match_index=match_index,
        preview=_build_preview(normalized_text, match_index, match_term),
    )


def _to_results(matches: list[_SearchMatch], top_k: int) -> tuple[list[SearchResult], int]:
    matches.sort(key=lambda item: (-item.score, item.source, item.chunk_id))
    total_hits = len(matches)
    top_matches = matches[:top_k]
    results = [
        SearchResult(
            rank=index + 1,
            source=match.source,
            chunk_id=match.chunk_id,
            score=match.score,
            match_count=match.match_count,
            match_term=match.match_term,
            preview=match.preview,
        )
        for index, match in enumerate(top_matches)
    ]
    return results, total_hits


def keyword_search(query: str, top_k: int = 5) -> tuple[list[SearchResult], int]:
    normalized_query = normalize_text(query)
    if not normalized_query:
        return [], 0

    matches: list[_SearchMatch] = []
    for chunk_data in _iter_saved_chunks():
        match = _evaluate_keyword_match(normalized_query, str(chunk_data.get("text", "")))
        if match is None:
            continue
        matches.append(
            _SearchMatch(
                source=str(chunk_data["source"]),
                chunk_id=str(chunk_data["chunk_id"]),
                score=match.score,
                match_count=match.match_count,
                match_term=match.match_term,
                match_index=match.match_index,
                preview=match.preview,
            )
        )
    return _to_results(matches, top_k)


def vector_search(query: str, top_k: int = 5) -> tuple[list[SearchResult], int]:
    normalized_query = normalize_text(query)
    if not normalized_query:
        return [], 0

    query_embedding = embed_text(normalized_query)
    if not query_embedding:
        return [], 0

    matches: list[_SearchMatch] = []
    for chunk_data in _iter_saved_chunks():
        chunk_embedding = chunk_data.get("embedding")
        if not chunk_embedding:
            continue

        similarity = _cosine_similarity(
            list(map(float, query_embedding)),
            list(map(float, chunk_embedding)),
        )
        if similarity < VECTOR_MIN_SIMILARITY:
            continue

        normalized_text = normalize_text(str(chunk_data.get("text", "")))
        matches.append(
            _SearchMatch(
                source=str(chunk_data["source"]),
                chunk_id=str(chunk_data["chunk_id"]),
                score=similarity,
                match_count=0,
                match_term="",
                match_index=0,
                preview=_build_leading_preview(normalized_text),
            )
        )
    return _to_results(matches, top_k)


def search_chunks(
    query: str,
    top_k: int = 5,
    mode: str = "keyword",
) -> tuple[list[SearchResult], int]:
    normalized_mode = mode.strip().lower()
    if normalized_mode == "keyword":
        return keyword_search(query=query, top_k=top_k)
    if normalized_mode == "vector":
        return vector_search(query=query, top_k=top_k)
    raise ValueError("mode must be 'keyword' or 'vector'.")
