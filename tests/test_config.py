"""Configuration tests keep default local settings intentional."""

from __future__ import annotations

from app.config import Settings


def test_default_embedding_model_targets_chinese_learning_use_case(monkeypatch) -> None:
    monkeypatch.delenv("EMBEDDING_MODEL_NAME", raising=False)

    settings = Settings.from_env()

    assert settings.embedding_model_name == "BAAI/bge-small-zh-v1.5"
