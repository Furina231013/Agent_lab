"""Ingest router.

The router translates HTTP requests into service calls. Keeping the concrete
loading, chunking, and saving logic in services makes those parts reusable
from scripts and tests without going through FastAPI.
"""

from fastapi import APIRouter, HTTPException, status

from app.config import to_relative_path
from app.schemas import IngestRequest, IngestResponse
from app.services.chunker import chunk_text
from app.services.loader import load_document
from app.services.storage import save_chunks

router = APIRouter(tags=["ingest"])


@router.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
def ingest_document(request: IngestRequest) -> IngestResponse:
    try:
        document = load_document(request.path)
        chunks = chunk_text(source=document.source, text=document.text)
        output_path = save_chunks(source=document.source, chunks=chunks)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return IngestResponse(
        source=document.source,
        chunk_count=len(chunks),
        output_path=to_relative_path(output_path),
    )
