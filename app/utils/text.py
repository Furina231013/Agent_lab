"""Small text helpers live in one place so services normalize consistently.

Even tiny helpers are worth extracting when multiple layers need the same rule.
That keeps ingest and search behavior aligned as the project grows.
"""

from __future__ import annotations

import re

WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()
