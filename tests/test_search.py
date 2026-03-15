"""Search endpoint tests for ranking and empty-result behavior."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.schemas import ChunkItem
from app.services.storage import save_chunks


@pytest.fixture
def isolated_processed_dir(tmp_path: Path) -> None:
    original_processed_dir = settings.processed_dir
    settings.processed_dir = tmp_path
    yield
    settings.processed_dir = original_processed_dir


def _save_demo_chunks() -> None:
    save_chunks(
        source="data/raw/alpha.md",
        chunks=[
            ChunkItem(
                chunk_id="alpha-0001",
                source="data/raw/alpha.md",
                text="FastAPI helps build API services. FastAPI also powers docs.",
                start_index=0,
                end_index=59,
            )
        ],
    )
    save_chunks(
        source="data/raw/beta.md",
        chunks=[
            ChunkItem(
                chunk_id="beta-0001",
                source="data/raw/beta.md",
                text="Keyword search is simple. FastAPI appears once here.",
                start_index=0,
                end_index=53,
            )
        ],
    )


def _save_vector_demo_chunks(processed_dir: Path) -> None:
    payloads = [
        {
            "source": "data/raw/alpha.md",
            "chunk_count": 1,
            "chunks": [
                {
                    "chunk_id": "alpha-0001",
                    "source": "data/raw/alpha.md",
                    "text": "Loader reads local documents from disk.",
                    "start_index": 0,
                    "end_index": 38,
                    "embedding": [1.0, 0.0],
                }
            ],
        },
        {
            "source": "data/raw/beta.md",
            "chunk_count": 1,
            "chunks": [
                {
                    "chunk_id": "beta-0001",
                    "source": "data/raw/beta.md",
                    "text": "Chunker splits paragraphs into smaller pieces.",
                    "start_index": 0,
                    "end_index": 46,
                    "embedding": [0.0, 1.0],
                }
            ],
        },
    ]
    for index, payload in enumerate(payloads):
        output_path = processed_dir / f"vector-{index}.json"
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def test_search_endpoint_returns_ranked_results_and_respects_top_k(
    isolated_processed_dir: None,
) -> None:
    _save_demo_chunks()
    client = TestClient(app)

    response = client.post("/api/search", json={"query": "FastAPI", "top_k": 1})

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "FastAPI"
    assert payload["mode"] == "keyword"
    assert payload["total_hits"] == 2
    assert payload["returned_count"] == 1
    assert len(payload["results"]) == 1
    result = payload["results"][0]
    assert result["rank"] == 1
    assert result["source"] == "data/raw/alpha.md"
    assert result["score"] == 2
    assert result["match_count"] == 2
    assert result["match_term"] == "FastAPI"
    assert "FastAPI" in result["preview"]
    assert "text" not in result


def test_search_endpoint_returns_empty_results_when_nothing_matches(
    isolated_processed_dir: None,
) -> None:
    client = TestClient(app)

    response = client.post("/api/search", json={"query": "missing-keyword", "top_k": 5})

    assert response.status_code == 200
    assert response.json() == {
        "query": "missing-keyword",
        "mode": "keyword",
        "total_hits": 0,
        "returned_count": 0,
        "results": [],
    }


def test_search_endpoint_supports_vector_mode(
    isolated_processed_dir: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _save_vector_demo_chunks(settings.processed_dir)

    monkeypatch.setattr(
        "app.services.searcher.embed_text",
        lambda text: [0.8, 0.6],
        raising=False,
    )
    client = TestClient(app)

    response = client.post(
        "/api/search",
        json={"query": "Which service loads files?", "top_k": 1, "mode": "vector"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "Which service loads files?"
    assert payload["mode"] == "vector"
    assert payload["total_hits"] == 2
    assert payload["returned_count"] == 1
    assert payload["results"][0]["source"] == "data/raw/alpha.md"
