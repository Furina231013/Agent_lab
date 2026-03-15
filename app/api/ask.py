"""Ask router for retrieval-first question answering in v0.3.3."""

from fastapi import APIRouter, HTTPException, status

from app.schemas import AskRequest, AskResponse
from app.services.asker import ask_question

router = APIRouter(tags=["ask"])


@router.post("/ask", response_model=AskResponse)
def ask_question_endpoint(request: AskRequest) -> AskResponse:
    try:
        chunks, sources, total_hits, answer_payload, output_path = ask_question(
            question=request.question,
            top_k=request.top_k,
            mode=request.mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return AskResponse(
        question=request.question,
        mode=request.mode,
        answer=answer_payload["answer"] or "",
        answer_mode=answer_payload["answer_mode"] or "placeholder",
        answer_status=answer_payload["answer_status"] or "disabled",
        answer_note=answer_payload["answer_note"],
        provider=answer_payload["provider"] or "placeholder",
        model=answer_payload["model"],
        total_hits=total_hits,
        returned_count=len(chunks),
        output_path=output_path,
        chunks=chunks,
        sources=sources,
    )
