"""Isolate LM Studio wiring so `/api/ask` can evolve without touching routing.

Keeping the local model client in its own module makes it easy to swap or
extend later, while the ask service stays focused on retrieval orchestration.
"""

from __future__ import annotations

import json
import socket
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import settings


class LMStudioError(RuntimeError):
    """Raised when the local LM Studio server cannot return a usable answer."""


def _chat_completions_url() -> str:
    return f"{settings.lm_studio_base_url.rstrip('/')}/chat/completions"


def _build_user_prompt(question: str, chunks: list[dict[str, Any]]) -> str:
    sections: list[str] = []
    for chunk in chunks:
        sections.append(
            "\n".join(
                [
                    f"Chunk rank: {chunk['rank']}",
                    f"Source: {chunk['source']}",
                    f"Chunk ID: {chunk['chunk_id']}",
                    "Content:",
                    str(chunk["text"]),
                ]
            )
        )

    context_block = "\n\n---\n\n".join(sections) if sections else "No retrieved context."
    return (
        f"Question:\n{question}\n\n"
        f"Retrieved context:\n{context_block}\n\n"
        "Write a concise answer grounded in the retrieved context. "
        "If the context is insufficient, say so explicitly."
    )


def _extract_answer(payload: dict[str, Any]) -> str:
    choices = payload.get("choices", [])
    if not choices:
        raise LMStudioError("LM Studio returned no choices.")

    first_choice = choices[0]
    message = first_choice.get("message", {})
    answer = str(message.get("content", "")).strip()
    if not answer:
        raise LMStudioError("LM Studio returned an empty answer.")
    return answer


def generate_lm_studio_answer(
    question: str,
    chunks: list[dict[str, Any]],
) -> dict[str, Optional[str]]:
    if not settings.lm_studio_model:
        raise LMStudioError("LM_STUDIO_MODEL is empty.")

    payload = {
        "model": settings.lm_studio_model,
        "messages": [
            {"role": "system", "content": settings.ask_system_prompt},
            {"role": "user", "content": _build_user_prompt(question, chunks)},
        ],
        "temperature": 0.2,
    }
    request = Request(
        _chat_completions_url(),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=settings.lm_studio_timeout_seconds) as response:
            raw_payload = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise LMStudioError(
            f"LM Studio request failed with status {exc.code}: {detail or exc.reason}"
        ) from exc
    except URLError as exc:
        raise LMStudioError(
            f"LM Studio server is not reachable at {settings.lm_studio_base_url}"
        ) from exc
    except (socket.timeout, TimeoutError) as exc:
        raise LMStudioError(
            f"LM Studio request timed out after {settings.lm_studio_timeout_seconds} seconds."
        ) from exc

    try:
        response_payload = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise LMStudioError("LM Studio returned invalid JSON.") from exc

    return {
        "answer": _extract_answer(response_payload),
        "answer_mode": "lm_studio",
        "answer_status": "generated",
        "answer_note": "Answered by local LM Studio model.",
        "provider": "lm_studio",
        "model": settings.lm_studio_model,
    }
