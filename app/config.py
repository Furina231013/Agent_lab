"""Centralize configuration so code changes less when environments change.

Moving from macOS to Ubuntu should mostly be a matter of updating `.env`
or shell settings instead of rewriting file paths across the codebase.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

PROJECT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_DIR / ".env")


def _resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (PROJECT_DIR / path).resolve()


def to_relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_DIR).as_posix()
    except ValueError:
        return path.resolve().as_posix()


class Settings(BaseModel):
    app_name: str
    app_env: str
    data_dir: Path
    raw_dir: Path
    processed_dir: Path
    index_dir: Path
    chunk_size: int
    chunk_overlap: int

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls(
            app_name=os.getenv("APP_NAME", "agent-lab"),
            app_env=os.getenv("APP_ENV", "dev"),
            data_dir=_resolve_path(os.getenv("DATA_DIR", "./data")),
            raw_dir=_resolve_path(os.getenv("RAW_DIR", "./data/raw")),
            processed_dir=_resolve_path(
                os.getenv("PROCESSED_DIR", "./data/processed")
            ),
            index_dir=_resolve_path(os.getenv("INDEX_DIR", "./data/index")),
            chunk_size=int(os.getenv("CHUNK_SIZE", "500")),
            chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "50")),
        )
        if settings.chunk_size <= 0:
            raise ValueError("CHUNK_SIZE must be greater than 0.")
        if settings.chunk_overlap < 0:
            raise ValueError("CHUNK_OVERLAP cannot be negative.")
        if settings.chunk_overlap >= settings.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE.")
        return settings

    def ensure_directories(self) -> "Settings":
        for path in (self.data_dir, self.raw_dir, self.processed_dir, self.index_dir):
            path.mkdir(parents=True, exist_ok=True)
        return self


settings = Settings.from_env().ensure_directories()
