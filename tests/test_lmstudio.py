"""LM Studio client tests for local model integration edge cases."""

from __future__ import annotations

import socket

import pytest

from app.services.lmstudio import LMStudioError, generate_lm_studio_answer


def test_generate_lm_studio_answer_wraps_socket_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(*args: object, **kwargs: object) -> object:
        raise socket.timeout("timed out")

    monkeypatch.setattr("app.services.lmstudio.urlopen", fake_urlopen)

    with pytest.raises(LMStudioError, match="timed out"):
        generate_lm_studio_answer(
            "FastAPI",
            [
                {
                    "rank": 1,
                    "source": "demo.md",
                    "chunk_id": "chunk-1",
                    "score": 1,
                    "text": "FastAPI keeps the route layer thin.",
                }
            ],
        )
