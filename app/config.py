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
    resolved_path = path.resolve()
    candidate_roots: list[Path] = []

    active_settings = globals().get("settings")
    if active_settings is not None:
        candidate_roots.append(active_settings.data_dir.parent.resolve())
    candidate_roots.append(PROJECT_DIR.resolve())

    unique_roots: list[Path] = []
    for root in candidate_roots:
        if root not in unique_roots:
            unique_roots.append(root)

    for root in unique_roots:
        try:
            return resolved_path.relative_to(root).as_posix()
        except ValueError:
            continue

    return resolved_path.as_posix()


class Settings(BaseModel):
    app_name: str
    app_env: str
    data_dir: Path
    raw_dir: Path
    processed_dir: Path
    index_dir: Path
    ask_log_dir: Path
    chunk_size: int
    chunk_overlap: int
    embedding_model_name: str
    embedding_device: str
    ask_provider: str
    ask_system_prompt: str
    lm_studio_base_url: str
    lm_studio_model: str
    lm_studio_timeout_seconds: int

    @classmethod
    def from_env(cls) -> "Settings":
        ask_provider = os.getenv("ASK_PROVIDER", "placeholder").strip().lower()
        lm_studio_base_url = os.getenv(
            "LM_STUDIO_BASE_URL",
            "http://127.0.0.1:1234/v1",
        ).strip()
        if lm_studio_base_url.endswith("/"):
            lm_studio_base_url = lm_studio_base_url.rstrip("/")
        if not lm_studio_base_url.endswith("/v1"):
            lm_studio_base_url = f"{lm_studio_base_url}/v1"

        settings = cls(
            app_name=os.getenv("APP_NAME", "agent-lab"),
            app_env=os.getenv("APP_ENV", "dev"),
            data_dir=_resolve_path(os.getenv("DATA_DIR", "./data")),
            raw_dir=_resolve_path(os.getenv("RAW_DIR", "./data/raw")),
            processed_dir=_resolve_path(
                os.getenv("PROCESSED_DIR", "./data/processed")
            ),
            index_dir=_resolve_path(os.getenv("INDEX_DIR", "./data/index")),
            ask_log_dir=_resolve_path(
                os.getenv("ASK_LOG_DIR", "./data/index/ask_logs")
            ),
            chunk_size=int(os.getenv("CHUNK_SIZE", "500")),
            chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "50")),
            embedding_model_name=os.getenv(
                "EMBEDDING_MODEL_NAME",
                "BAAI/bge-small-zh-v1.5",
            ).strip(),
            embedding_device=os.getenv("EMBEDDING_DEVICE", "cpu").strip(),
            ask_provider=ask_provider,
            ask_system_prompt=os.getenv(
                "ASK_SYSTEM_PROMPT",
                (
                    "你是一个本地 RAG 助手。请始终使用简体中文回答。"
                    "只根据检索到的上下文作答，不要补充常识，不要外推未明示规则。"
                    "如果问题涉及计划版本、当前生效值、阈值或数值，请明确区分计划态与现态，并逐字复制关键数字。"
                    "不要输出思维链、Thinking Process 或 <think> 标签。"
                ),
            ),
            lm_studio_base_url=lm_studio_base_url,
            lm_studio_model=os.getenv("LM_STUDIO_MODEL", "").strip(),
            lm_studio_timeout_seconds=int(
                os.getenv("LM_STUDIO_TIMEOUT_SECONDS", "30")
            ),
        )
        if settings.chunk_size <= 0:
            raise ValueError("CHUNK_SIZE must be greater than 0.")
        if settings.chunk_overlap < 0:
            raise ValueError("CHUNK_OVERLAP cannot be negative.")
        if settings.chunk_overlap >= settings.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE.")
        if settings.ask_provider not in {"placeholder", "lm_studio"}:
            raise ValueError("ASK_PROVIDER must be 'placeholder' or 'lm_studio'.")
        if settings.lm_studio_timeout_seconds <= 0:
            raise ValueError("LM_STUDIO_TIMEOUT_SECONDS must be greater than 0.")
        return settings

    def ensure_directories(self) -> "Settings":
        for path in (
            self.data_dir,
            self.raw_dir,
            self.processed_dir,
            self.index_dir,
            self.ask_log_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
        return self


settings = Settings.from_env().ensure_directories()
