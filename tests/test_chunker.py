"""Chunking tests for the paragraph-first v0.2.0 strategy."""

import pytest

from app.config import settings
from app.services.chunker import chunk_text


@pytest.fixture
def restore_chunk_settings() -> None:
    original_size = settings.chunk_size
    original_overlap = settings.chunk_overlap
    yield
    settings.chunk_size = original_size
    settings.chunk_overlap = original_overlap


def test_chunk_text_prefers_paragraph_boundaries(restore_chunk_settings: None) -> None:
    settings.chunk_size = 40
    settings.chunk_overlap = 5
    paragraph_a = "A" * 18
    paragraph_b = "B" * 18
    paragraph_c = "C" * 18
    text = f"{paragraph_a}\n\n{paragraph_b}\n\n{paragraph_c}"

    chunks = chunk_text(source="demo.txt", text=text)

    assert chunks[0].text == f"{paragraph_a}\n\n{paragraph_b}"
    assert len(chunks) == 2
    assert chunks[1].text.startswith("B" * 5)


def test_chunk_text_splits_long_paragraph_and_keeps_overlap(
    restore_chunk_settings: None,
) -> None:
    settings.chunk_size = 20
    settings.chunk_overlap = 5
    text = "0123456789012345678901234567890123456789"

    chunks = chunk_text(source="long.txt", text=text)

    assert len(chunks) >= 2
    assert all(len(chunk.text) <= settings.chunk_size for chunk in chunks)
    assert chunks[1].start_index == chunks[0].end_index - settings.chunk_overlap


def test_chunk_text_prefers_sentence_boundary_before_falling_back_to_raw_overlap(
    restore_chunk_settings: None,
) -> None:
    settings.chunk_size = 100
    settings.chunk_overlap = 20
    paragraph_one = "Paragraph one is short."
    paragraph_two = (
        "Sentence one in paragraph two should still fit in the current chunk. "
        "Sentence two should become the clean beginning of the next chunk."
    )
    text = f"{paragraph_one}\n\n{paragraph_two}"

    chunks = chunk_text(source="sentences.txt", text=text)

    assert chunks[0].text.endswith("current chunk.")
    assert chunks[1].text.startswith("Sentence two")
