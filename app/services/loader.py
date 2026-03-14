"""Load documents from disk into a plain text form.

We still keep the supported formats intentionally small, but v0.2.0 expands the
surface just enough to include `.pdf` so the project can grow without losing
its teaching value. Relative filenames are resolved through the configured
data locations so tests and alternate environments can stay isolated.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import markdown
from bs4 import BeautifulSoup
from pypdf import PdfReader

from app.config import PROJECT_DIR, settings, to_relative_path
from app.utils.text import normalize_document_text

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf"}


@dataclass
class LoadedDocument:
    source: str
    text: str


def _resolve_source_path(path_str: str) -> Path:
    candidate = Path(path_str)
    if candidate.is_absolute():
        return candidate.resolve()

    possible_paths = [
        (settings.data_dir.parent / candidate).resolve(),
        (settings.raw_dir / candidate).resolve(),
        (PROJECT_DIR / candidate).resolve(),
    ]

    unique_paths: list[Path] = []
    for path in possible_paths:
        if path not in unique_paths:
            unique_paths.append(path)

    for path in unique_paths:
        if path.exists():
            return path

    return unique_paths[0]


def _markdown_to_text(content: str) -> str:
    html = markdown.markdown(content)
    soup = BeautifulSoup(html, "html.parser")
    block_tags = ("h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "pre")
    paragraphs = [
        element.get_text(separator=" ", strip=True)
        for element in soup.find_all(block_tags)
        if element.get_text(separator=" ", strip=True)
    ]
    if paragraphs:
        return "\n\n".join(paragraphs)
    return soup.get_text(separator=" ", strip=True)


def _pdf_to_text(source_path: Path) -> str:
    try:
        reader = PdfReader(str(source_path))
    except Exception as exc:
        raise ValueError(f"Failed to parse PDF: {to_relative_path(source_path)}") from exc

    try:
        page_texts = []
        for page in reader.pages:
            extracted_text = page.extract_text() or ""
            if extracted_text.strip():
                page_texts.append(extracted_text)
    except Exception as exc:
        raise ValueError(
            f"Failed to extract text from PDF: {to_relative_path(source_path)}"
        ) from exc

    if not page_texts:
        raise ValueError(
            f"PDF is empty or has no extractable text: {to_relative_path(source_path)}"
        )

    return "\n\n".join(page_texts)


def load_document(path_str: str) -> LoadedDocument:
    source_path = _resolve_source_path(path_str)

    if not source_path.exists():
        raise FileNotFoundError(f"File not found: {path_str}")
    if not source_path.is_file():
        raise ValueError(f"Path is not a file: {path_str}")
    if source_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(f"Unsupported file type: {source_path.suffix}. Supported: {supported}")

    if source_path.suffix.lower() == ".pdf":
        raw_text = _pdf_to_text(source_path)
    else:
        raw_text = source_path.read_text(encoding="utf-8")

    if source_path.suffix.lower() == ".md":
        text = _markdown_to_text(raw_text)
    else:
        text = raw_text

    text = normalize_document_text(text)
    if not text:
        raise ValueError(f"Document is empty after normalization: {path_str}")

    return LoadedDocument(source=to_relative_path(source_path), text=text)
