"""Search router for the first keyword-based retrieval pass."""

from fastapi import APIRouter

from app.schemas import SearchRequest, SearchResponse
from app.services.searcher import search_chunks

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
def search_documents(request: SearchRequest) -> SearchResponse:
    results = search_chunks(query=request.query, top_k=request.top_k)
    return SearchResponse(
        query=request.query,
        total_hits=len(results),
        results=results,
    )
