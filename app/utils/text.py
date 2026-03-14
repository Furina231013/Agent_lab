"""Small text helpers live in one place so services normalize consistently.

Even tiny helpers are worth extracting when multiple layers need the same rule.
That keeps ingest and search behavior aligned as the project grows.
"""

from __future__ import annotations

import re

LINE_BREAK_RE = re.compile(r"\r\n?")
PARAGRAPH_BREAK_RE = re.compile(r"\n\s*\n+")
WHITESPACE_RE = re.compile(r"\s+")
CJK_CHAR_RE = r"[\u2E80-\u9FFF\uF900-\uFAFF]"
CJK_GAP_RE = re.compile(rf"({CJK_CHAR_RE})\s+({CJK_CHAR_RE})")
CJK_PUNCT_RIGHT_RE = re.compile(rf"({CJK_CHAR_RE})\s+([，。！？；：、）】》])")
CJK_PUNCT_LEFT_RE = re.compile(rf"([（【《])\s+({CJK_CHAR_RE})")


def normalize_text(text: str) -> str:
    normalized = WHITESPACE_RE.sub(" ", text).strip()
    while True:
        updated = CJK_GAP_RE.sub(r"\1\2", normalized)
        updated = CJK_PUNCT_RIGHT_RE.sub(r"\1\2", updated)
        updated = CJK_PUNCT_LEFT_RE.sub(r"\1\2", updated)
        if updated == normalized:
            return updated
        normalized = updated


def split_paragraphs(text: str) -> list[str]:
    canonical_text = LINE_BREAK_RE.sub("\n", text).strip()
    if not canonical_text:
        return []

    paragraphs: list[str] = []
    for raw_paragraph in PARAGRAPH_BREAK_RE.split(canonical_text):
        normalized_paragraph = normalize_text(raw_paragraph)
        if normalized_paragraph:
            paragraphs.append(normalized_paragraph)
    return paragraphs


def normalize_document_text(text: str) -> str:
    return "\n\n".join(split_paragraphs(text))
