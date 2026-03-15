"""End-to-end API tests for ingest and search.

These tests intentionally drive the app through HTTP only. They also use a
temporary configured data directory so we can verify the API respects
configuration rather than relying on the repository's real `data/` folder.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.config import settings
from app.main import app


@pytest.fixture(autouse=True)
def stub_chunk_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.api.ingest.attach_embeddings",
        lambda chunks: chunks,
    )


@pytest.fixture
def isolated_data_dirs(tmp_path: Path) -> tuple[Path, Path, Path]:
    data_dir = tmp_path / "data"
    raw_dir = data_dir / "raw"
    processed_dir = data_dir / "processed"
    index_dir = data_dir / "index"
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    index_dir.mkdir(parents=True, exist_ok=True)

    original_data_dir = settings.data_dir
    original_raw_dir = settings.raw_dir
    original_processed_dir = settings.processed_dir
    original_index_dir = settings.index_dir

    settings.data_dir = data_dir
    settings.raw_dir = raw_dir
    settings.processed_dir = processed_dir
    settings.index_dir = index_dir

    yield raw_dir, processed_dir, index_dir

    settings.data_dir = original_data_dir
    settings.raw_dir = original_raw_dir
    settings.processed_dir = original_processed_dir
    settings.index_dir = original_index_dir


def _write_pdf_with_text(path: Path, text: str) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        }
    )
    font_ref = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})}
    )
    content = DecodedStreamObject()
    content.set_data(f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode("latin-1"))
    content_ref = writer._add_object(content)
    page[NameObject("/Contents")] = content_ref

    with path.open("wb") as output_file:
        writer.write(output_file)


def test_ingest_endpoint_reads_markdown_from_configured_raw_dir(
    isolated_data_dirs: tuple[Path, Path, Path],
) -> None:
    raw_dir, processed_dir, _ = isolated_data_dirs
    (raw_dir / "lesson.md").write_text(
        "FastAPI keeps the API layer thin.\n\nChunk overlap protects boundary context.",
        encoding="utf-8",
    )
    client = TestClient(app)

    response = client.post("/api/ingest", json={"path": "lesson.md"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["source"].endswith("lesson.md")
    assert payload["chunk_count"] >= 1
    assert payload["output_path"].endswith(".json")
    assert len(list(processed_dir.glob("*.json"))) == 1


def test_ingest_endpoint_reads_pdf_from_configured_raw_dir(
    isolated_data_dirs: tuple[Path, Path, Path],
) -> None:
    raw_dir, processed_dir, _ = isolated_data_dirs
    _write_pdf_with_text(raw_dir / "lesson.pdf", "FastAPI inside PDF")
    client = TestClient(app)

    response = client.post("/api/ingest", json={"path": "lesson.pdf"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["source"].endswith("lesson.pdf")
    assert payload["chunk_count"] >= 1
    assert len(list(processed_dir.glob("*.json"))) == 1


def test_search_endpoint_works_after_ingesting_multiple_documents_via_api(
    isolated_data_dirs: tuple[Path, Path, Path],
) -> None:
    raw_dir, _, _ = isolated_data_dirs
    (raw_dir / "alpha.md").write_text(
        "FastAPI appears once here.\n\nThis is the smaller hit.",
        encoding="utf-8",
    )
    (raw_dir / "beta.md").write_text(
        "FastAPI appears twice here. FastAPI keeps search readable.\n\nPreview should be short.",
        encoding="utf-8",
    )
    client = TestClient(app)

    ingest_alpha = client.post("/api/ingest", json={"path": "alpha.md"})
    ingest_beta = client.post("/api/ingest", json={"path": "beta.md"})
    response = client.post("/api/search", json={"query": "FastAPI", "top_k": 1})

    assert ingest_alpha.status_code == 201
    assert ingest_beta.status_code == 201
    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "FastAPI"
    assert payload["mode"] == "keyword"
    assert payload["total_hits"] == 2
    assert payload["returned_count"] == 1
    assert len(payload["results"]) == 1
    result = payload["results"][0]
    assert result["rank"] == 1
    assert result["source"].endswith("beta.md")
    assert result["score"] == 2
    assert result["match_count"] == 2
    assert result["match_term"] == "FastAPI"
    assert "FastAPI" in result["preview"]
