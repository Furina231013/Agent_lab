"""Embedder tests keep model wiring isolated from the rest of the app."""

from __future__ import annotations

from app.services.embedder import embed_text, embed_texts


def test_embed_texts_uses_shared_model(monkeypatch) -> None:
    class FakeModel:
        def encode(self, texts, normalize_embeddings):
            assert normalize_embeddings is True
            mapping = {
                "alpha": [1.0, 0.0],
                "beta": [0.0, 1.0],
            }
            return [mapping[text] for text in texts]

    monkeypatch.setattr(
        "app.services.embedder._get_model",
        lambda: FakeModel(),
    )

    assert embed_texts(["alpha", "beta"]) == [[1.0, 0.0], [0.0, 1.0]]
    assert embed_text("alpha") == [1.0, 0.0]
