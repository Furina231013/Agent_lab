"""Search router for keyword baseline plus embedding retrieval."""

from fastapi import APIRouter, HTTPException, status

from app.schemas import SearchRequest, SearchResponse
from app.services.searcher import search_chunks

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
def search_documents(request: SearchRequest) -> SearchResponse:
    try:
        results, total_hits = search_chunks(
            query=request.query,
            top_k=request.top_k,
            mode=request.mode,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return SearchResponse(
        query=request.query,
        mode=request.mode,
        total_hits=total_hits,
        returned_count=len(results),
        results=results,
    )
