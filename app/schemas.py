"""Explicit schemas keep API contracts readable and testable.

When request and response shapes are modeled up front, it is easier to see
what the HTTP layer promises even before the internals become more complex.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    app_name: str
    environment: str


class IngestRequest(BaseModel):
    path: str = Field(
        ...,
        min_length=1,
        description="Path to a local .txt, .md, or .pdf file",
    )


class IngestResponse(BaseModel):
    source: str
    chunk_count: int
    output_path: str


class ChunkItem(BaseModel):
    chunk_id: str
    source: str
    text: str
    start_index: int
    end_index: int


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Keyword or short phrase to search")
    top_k: int = Field(default=5, gt=0, le=20)


class SearchResult(BaseModel):
    rank: int
    source: str
    chunk_id: str
    score: int
    match_count: int
    match_term: str
    preview: str


class SearchResponse(BaseModel):
    query: str
    total_hits: int
    returned_count: int
    results: list[SearchResult]
