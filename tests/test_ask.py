"""API tests for `/api/ask` in placeholder and LM Studio modes."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.lmstudio import LMStudioError


@pytest.fixture
def isolated_data_dirs(tmp_path: Path) -> tuple[Path, Path, Path]:
    data_dir = tmp_path / "data"
    raw_dir = data_dir / "raw"
    processed_dir = data_dir / "processed"
    index_dir = data_dir / "index"
    ask_log_dir = index_dir / "ask_logs"
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    index_dir.mkdir(parents=True, exist_ok=True)
    ask_log_dir.mkdir(parents=True, exist_ok=True)

    original_data_dir = settings.data_dir
    original_raw_dir = settings.raw_dir
    original_processed_dir = settings.processed_dir
    original_index_dir = settings.index_dir
    original_ask_log_dir = settings.ask_log_dir

    settings.data_dir = data_dir
    settings.raw_dir = raw_dir
    settings.processed_dir = processed_dir
    settings.index_dir = index_dir
    settings.ask_log_dir = ask_log_dir

    yield raw_dir, processed_dir, index_dir

    settings.data_dir = original_data_dir
    settings.raw_dir = original_raw_dir
    settings.processed_dir = original_processed_dir
    settings.index_dir = original_index_dir
    settings.ask_log_dir = original_ask_log_dir


@pytest.fixture
def restore_ask_settings() -> None:
    original_values = {
        "ask_provider": getattr(settings, "ask_provider", None),
        "ask_system_prompt": getattr(settings, "ask_system_prompt", None),
        "lm_studio_base_url": getattr(settings, "lm_studio_base_url", None),
        "lm_studio_model": getattr(settings, "lm_studio_model", None),
        "lm_studio_timeout_seconds": getattr(
            settings,
            "lm_studio_timeout_seconds",
            None,
        ),
        "ask_log_dir": getattr(settings, "ask_log_dir", None),
    }

    yield

    for field_name, original_value in original_values.items():
        if original_value is not None:
            setattr(settings, field_name, original_value)


@pytest.fixture(autouse=True)
def stub_chunk_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.api.ingest.attach_embeddings",
        lambda chunks: chunks,
    )


def test_ask_endpoint_returns_placeholder_answer_and_retrieved_chunks(
    isolated_data_dirs: tuple[Path, Path, Path],
    restore_ask_settings: None,
) -> None:
    setattr(settings, "ask_provider", "placeholder")
    setattr(settings, "lm_studio_model", "")
    raw_dir, _, _ = isolated_data_dirs
    (raw_dir / "alpha.md").write_text(
        "FastAPI appears once here.\n\nThis document is less relevant.",
        encoding="utf-8",
    )
    (raw_dir / "beta.md").write_text(
        "FastAPI appears twice here. FastAPI keeps the ask endpoint simple.\n\nThis should rank first.",
        encoding="utf-8",
    )
    client = TestClient(app)

    ingest_alpha = client.post("/api/ingest", json={"path": "alpha.md"})
    ingest_beta = client.post("/api/ingest", json={"path": "beta.md"})
    response = client.post("/api/ask", json={"question": "FastAPI", "top_k": 1})

    assert ingest_alpha.status_code == 201
    assert ingest_beta.status_code == 201
    assert response.status_code == 200
    payload = response.json()
    assert payload["question"] == "FastAPI"
    assert payload["mode"] == "keyword"
    assert "placeholder" in payload["answer"].lower()
    assert payload["answer_mode"] == "placeholder"
    assert payload["answer_status"] == "disabled"
    assert payload["provider"] == "placeholder"
    assert payload["model"] is None
    assert payload["total_hits"] == 2
    assert payload["returned_count"] == 1
    assert len(payload["chunks"]) == 1
    assert payload["chunks"][0]["source"].endswith("beta.md")
    assert "FastAPI" in payload["chunks"][0]["text"]
    assert payload["sources"] == [payload["chunks"][0]["source"]]
    assert payload["output_path"].endswith(".json")
    saved_path = settings.data_dir.parent / payload["output_path"]
    assert saved_path.exists()
    saved_payload = json.loads(saved_path.read_text(encoding="utf-8"))
    assert saved_payload["question"] == "FastAPI"
    assert saved_payload["answer_status"] == "disabled"
    assert saved_payload["chunks"][0]["source"].endswith("beta.md")


def test_ask_endpoint_returns_empty_chunks_when_nothing_matches(
    isolated_data_dirs: tuple[Path, Path, Path],
    restore_ask_settings: None,
) -> None:
    setattr(settings, "ask_provider", "placeholder")
    setattr(settings, "lm_studio_model", "")
    raw_dir, _, _ = isolated_data_dirs
    (raw_dir / "notes.md").write_text(
        "This file talks about chunking and storage, but not the requested term.",
        encoding="utf-8",
    )
    client = TestClient(app)

    ingest_response = client.post("/api/ingest", json={"path": "notes.md"})
    response = client.post("/api/ask", json={"question": "nonexistent-term", "top_k": 3})

    assert ingest_response.status_code == 201
    assert response.status_code == 200
    payload = response.json()
    assert payload["question"] == "nonexistent-term"
    assert payload["mode"] == "keyword"
    assert payload["answer_status"] == "disabled"
    assert payload["returned_count"] == 0
    assert payload["chunks"] == []
    assert payload["sources"] == []
    assert payload["output_path"].endswith(".json")
    saved_path = settings.data_dir.parent / payload["output_path"]
    assert saved_path.exists()
    saved_payload = json.loads(saved_path.read_text(encoding="utf-8"))
    assert saved_payload["question"] == "nonexistent-term"
    assert saved_payload["chunks"] == []


def test_ask_endpoint_uses_lm_studio_answer_when_configured(
    isolated_data_dirs: tuple[Path, Path, Path],
    restore_ask_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_dir, _, _ = isolated_data_dirs
    (raw_dir / "lesson.md").write_text(
        "FastAPI makes it easy to keep the API layer thin.\n\nSearch returns the chunks we want to ground on.",
        encoding="utf-8",
    )
    setattr(settings, "ask_provider", "lm_studio")
    setattr(settings, "lm_studio_model", "local-qwen")
    setattr(settings, "lm_studio_base_url", "http://127.0.0.1:1234/v1")

    def fake_generate(question: str, chunks: list[dict[str, object]]) -> dict[str, str]:
        assert question == "FastAPI"
        assert chunks[0]["source"].endswith("lesson.md")
        return {
            "answer": "Generated by LM Studio from local-qwen.",
            "answer_mode": "lm_studio",
            "answer_status": "generated",
            "answer_note": "Answered by local LM Studio model.",
            "provider": "lm_studio",
            "model": "local-qwen",
        }

    monkeypatch.setattr(
        "app.services.asker.generate_lm_studio_answer",
        fake_generate,
        raising=False,
    )
    client = TestClient(app)

    ingest_response = client.post("/api/ingest", json={"path": "lesson.md"})
    response = client.post("/api/ask", json={"question": "FastAPI", "top_k": 2})

    assert ingest_response.status_code == 201
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "keyword"
    assert payload["answer"] == "Generated by LM Studio from local-qwen."
    assert payload["answer_mode"] == "lm_studio"
    assert payload["answer_status"] == "generated"
    assert payload["provider"] == "lm_studio"
    assert payload["model"] == "local-qwen"
    assert payload["returned_count"] >= 1
    assert payload["output_path"].endswith(".json")
    saved_path = settings.data_dir.parent / payload["output_path"]
    assert saved_path.exists()
    saved_payload = json.loads(saved_path.read_text(encoding="utf-8"))
    assert saved_payload["answer"] == "Generated by LM Studio from local-qwen."
    assert saved_payload["provider"] == "lm_studio"


def test_ask_endpoint_falls_back_when_lm_studio_is_unreachable(
    isolated_data_dirs: tuple[Path, Path, Path],
    restore_ask_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_dir, _, _ = isolated_data_dirs
    (raw_dir / "lesson.md").write_text(
        "FastAPI and chunk retrieval are still useful even before the model is running.",
        encoding="utf-8",
    )
    setattr(settings, "ask_provider", "lm_studio")
    setattr(settings, "lm_studio_model", "local-qwen")
    setattr(settings, "lm_studio_base_url", "http://127.0.0.1:1234/v1")

    def fake_generate(question: str, chunks: list[dict[str, object]]) -> dict[str, str]:
        raise LMStudioError(
            "LM Studio server is not reachable at http://127.0.0.1:1234/v1"
        )

    monkeypatch.setattr(
        "app.services.asker.generate_lm_studio_answer",
        fake_generate,
        raising=False,
    )
    client = TestClient(app)

    ingest_response = client.post("/api/ingest", json={"path": "lesson.md"})
    response = client.post("/api/ask", json={"question": "FastAPI", "top_k": 2})

    assert ingest_response.status_code == 201
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "keyword"
    assert "placeholder" in payload["answer"].lower()
    assert payload["answer_mode"] == "placeholder"
    assert payload["answer_status"] == "unreachable"
    assert payload["provider"] == "lm_studio"
    assert payload["model"] == "local-qwen"
    assert "not reachable" in payload["answer_note"]
    assert payload["output_path"].endswith(".json")


def test_ask_endpoint_supports_vector_mode(
    isolated_data_dirs: tuple[Path, Path, Path],
    restore_ask_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, processed_dir, _ = isolated_data_dirs
    payload = {
        "source": "data/raw/vector-demo.md",
        "chunk_count": 2,
        "chunks": [
            {
                "chunk_id": "alpha-0001",
                "source": "data/raw/vector-demo.md",
                "text": "Loader reads local documents from disk.",
                "start_index": 0,
                "end_index": 38,
                "embedding": [1.0, 0.0],
            },
            {
                "chunk_id": "beta-0001",
                "source": "data/raw/vector-demo.md",
                "text": "Chunker splits long text into smaller pieces.",
                "start_index": 39,
                "end_index": 84,
                "embedding": [0.0, 1.0],
            },
        ],
    }
    (processed_dir / "vector-demo.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    setattr(settings, "ask_provider", "lm_studio")
    setattr(settings, "lm_studio_model", "local-qwen")
    setattr(settings, "lm_studio_base_url", "http://127.0.0.1:1234/v1")

    monkeypatch.setattr(
        "app.services.searcher.embed_text",
        lambda text: [0.8, 0.2],
        raising=False,
    )

    def fake_generate(question: str, chunks: list[dict[str, object]]) -> dict[str, str]:
        assert question == "What does loader do?"
        assert chunks[0]["text"] == "Loader reads local documents from disk."
        return {
            "answer": "Loader is responsible for reading local documents.",
            "answer_mode": "lm_studio",
            "answer_status": "generated",
            "answer_note": "Answered by local LM Studio model.",
            "provider": "lm_studio",
            "model": "local-qwen",
        }

    monkeypatch.setattr(
        "app.services.asker.generate_lm_studio_answer",
        fake_generate,
        raising=False,
    )
    client = TestClient(app)

    response = client.post(
        "/api/ask",
        json={"question": "What does loader do?", "top_k": 1, "mode": "vector"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "vector"
    assert payload["answer"] == "Loader is responsible for reading local documents."
    assert payload["returned_count"] == 1
    assert payload["chunks"][0]["chunk_id"] == "alpha-0001"
    assert isinstance(payload["chunks"][0]["score"], float)
