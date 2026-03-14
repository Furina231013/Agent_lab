"""Search saved chunks with simple scoring plus readable previews.

The matching logic stays intentionally naive, but the returned shape is now
closer to what a human expects from a search endpoint: rank, hit counts, and a
short preview instead of the whole chunk body.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.config import settings
from app.schemas import SearchResult
from app.utils.text import normalize_text

PREVIEW_RADIUS = 80
PREVIEW_LOOKAROUND = 40
SENTENCE_BOUNDARIES = ("。", "！", "？", "；", ".", "!", "?", "\n")


@dataclass
class _SearchMatch:
    source: str
    chunk_id: str
    score: int
    match_count: int
    match_term: str
    match_index: int
    preview: str


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


def _evaluate_match(query: str, text: str) -> _SearchMatch | None:
    normalized_text = normalize_text(text)
    exact_count = _count_occurrences(normalized_text, query)
    if exact_count > 0:
        match_index = _find_match_index(normalized_text, query)
        return _SearchMatch(
            source="",
            chunk_id="",
            score=exact_count,
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
        score=total_count,
        match_count=total_count,
        match_term=match_term,
        match_index=match_index,
        preview=_build_preview(normalized_text, match_index, match_term),
    )


def search_chunks(query: str, top_k: int = 5) -> tuple[list[SearchResult], int]:
    normalized_query = normalize_text(query)
    if not normalized_query:
        return [], 0

    matches: list[_SearchMatch] = []
    for json_path in sorted(settings.processed_dir.glob("*.json")):
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        for chunk_data in payload.get("chunks", []):
            match = _evaluate_match(normalized_query, chunk_data.get("text", ""))
            if match is None:
                continue
            matches.append(
                _SearchMatch(
                    source=chunk_data["source"],
                    chunk_id=chunk_data["chunk_id"],
                    score=match.score,
                    match_count=match.match_count,
                    match_term=match.match_term,
                    match_index=match.match_index,
                    preview=match.preview,
                )
            )

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
