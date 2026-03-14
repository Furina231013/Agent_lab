"""Load documents from disk into a plain text form.

Version one deliberately supports only `.txt` and `.md`. A narrow surface area
keeps the first pipeline easy to understand before adding more parsers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import markdown
from bs4 import BeautifulSoup

from app.config import PROJECT_DIR, to_relative_path
from app.utils.text import normalize_text

SUPPORTED_EXTENSIONS = {".txt", ".md"}


@dataclass
class LoadedDocument:
    source: str
    text: str


def _resolve_source_path(path_str: str) -> Path:
    candidate = Path(path_str)
    return candidate if candidate.is_absolute() else (PROJECT_DIR / candidate).resolve()


def _markdown_to_text(content: str) -> str:
    html = markdown.markdown(content)
    return BeautifulSoup(html, "html.parser").get_text(separator=" ")


def load_document(path_str: str) -> LoadedDocument:
    source_path = _resolve_source_path(path_str)

    if not source_path.exists():
        raise FileNotFoundError(f"File not found: {path_str}")
    if not source_path.is_file():
        raise ValueError(f"Path is not a file: {path_str}")
    if source_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(f"Unsupported file type: {source_path.suffix}. Supported: {supported}")

    raw_text = source_path.read_text(encoding="utf-8")
    text = _markdown_to_text(raw_text) if source_path.suffix.lower() == ".md" else raw_text
    text = normalize_text(text)
    if not text:
        raise ValueError(f"Document is empty after normalization: {path_str}")

    return LoadedDocument(source=to_relative_path(source_path), text=text)
