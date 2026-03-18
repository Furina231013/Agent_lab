"""Run a small, reviewable evaluation loop without external tooling.

The first evaluator keeps everything as local files so you can inspect one run,
label failures by hand, and decide whether the next investment belongs in
retrieval, generation, data cleanup, or storage infrastructure.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from app.config import PROJECT_DIR, settings, to_relative_path
from app.schemas import AskChunk
from app.services.asker import answer_with_chunks, ask_question
from app.services.chunker import chunk_text
from app.services.embedder import attach_embeddings
from app.services.loader import load_document
from app.services.storage import save_ask_record, save_chunks
from app.utils.text import normalize_text

DEFAULT_EVAL_MODES = ("vector", "direct_read")
SUPPORTED_EVAL_MODES = ("keyword", "vector", "direct_read")
EVAL_RUNS_DIRNAME = "eval_runs"
EVAL_REPORTS_DIRNAME = "eval_reports"
REVIEW_LABELS = ("correct", "incorrect", "insufficient")
ERROR_TYPES = ("检索错", "生成错", "引用错", "数据问题")
ANSWER_PREVIEW_LIMIT = 220
EVIDENCE_PREVIEW_LIMIT = 160
MAX_EVIDENCE_ITEMS = 2


@dataclass
class EvalCase:
    case_id: str
    question: str
    source_paths: list[str]
    expected_sources: list[str]
    expected_answer_points: list[str]
    difficulty: str
    notes: str


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _safe_name(value: str, fallback: str = "eval") -> str:
    safe_value = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_")
    return safe_value or fallback


def _resolve_dataset_path(dataset_path: Path) -> Path:
    return dataset_path if dataset_path.is_absolute() else (PROJECT_DIR / dataset_path).resolve()


def _relative(path: Path) -> str:
    return to_relative_path(path)


def _manual_review_slot() -> dict[str, str]:
    return {"label": "", "error_type": "", "notes": ""}


def _compact_preview(text: str, max_chars: int) -> str:
    preview = normalize_text(text)
    if not preview:
        return ""
    if len(preview) <= max_chars:
        return preview
    return f"{preview[:max_chars].rstrip()}..."


def _serialize_evidence(chunks: list[AskChunk]) -> list[dict[str, Any]]:
    return [
        {
            "rank": chunk.rank,
            "source": chunk.source,
            "chunk_id": chunk.chunk_id,
            "score": chunk.score,
            "text_preview": _compact_preview(chunk.text, EVIDENCE_PREVIEW_LIMIT),
        }
        for chunk in chunks[:MAX_EVIDENCE_ITEMS]
    ]


def load_eval_dataset(dataset_path: Path) -> tuple[str, list[EvalCase]]:
    resolved_path = _resolve_dataset_path(dataset_path)
    payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    dataset_name = str(payload.get("name", resolved_path.stem)).strip() or resolved_path.stem
    raw_cases = payload.get("cases", [])
    if not raw_cases:
        raise ValueError("Evaluation dataset has no cases.")

    cases: list[EvalCase] = []
    for index, raw_case in enumerate(raw_cases, start=1):
        case_id = str(raw_case.get("id", f"case-{index:03d}")).strip()
        question = str(raw_case.get("question", "")).strip()
        source_paths = [str(path).strip() for path in raw_case.get("source_paths", []) if str(path).strip()]
        if not case_id:
            raise ValueError(f"Case #{index} is missing an id.")
        if not question:
            raise ValueError(f"Case '{case_id}' is missing a question.")
        if not source_paths:
            raise ValueError(f"Case '{case_id}' must list at least one source path.")

        cases.append(
            EvalCase(
                case_id=case_id,
                question=question,
                source_paths=source_paths,
                expected_sources=[
                    str(path).strip()
                    for path in raw_case.get("expected_sources", source_paths)
                    if str(path).strip()
                ],
                expected_answer_points=[
                    str(point).strip()
                    for point in raw_case.get("expected_answer_points", [])
                    if str(point).strip()
                ],
                difficulty=str(raw_case.get("difficulty", "medium")).strip() or "medium",
                notes=str(raw_case.get("notes", "")).strip(),
            )
        )

    return dataset_name, cases


def _iter_saved_chunk_dicts() -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for json_path in sorted(settings.processed_dir.glob("*.json")):
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        chunks.extend(payload.get("chunks", []))
    return chunks


def _selected_chunks(source_paths: list[str] | None = None) -> list[AskChunk]:
    selected_sources = source_paths or []
    source_order = {source: index for index, source in enumerate(selected_sources)}
    chunk_rows: list[tuple[int, int, str, AskChunk]] = []

    for chunk_data in _iter_saved_chunk_dicts():
        source = str(chunk_data.get("source", ""))
        if selected_sources and source not in source_order:
            continue
        start_index = int(chunk_data.get("start_index", 0))
        rank_group = source_order.get(source, len(source_order))
        chunk_rows.append(
            (
                rank_group,
                start_index,
                str(chunk_data.get("chunk_id", "")),
                AskChunk(
                    rank=0,
                    source=source,
                    chunk_id=str(chunk_data.get("chunk_id", "")),
                    score=1.0,
                    text=str(chunk_data.get("text", "")),
                ),
            )
        )

    chunk_rows.sort(key=lambda item: (item[0], item[1], item[2]))
    return [
        chunk.model_copy(update={"rank": index + 1})
        for index, (_, _, _, chunk) in enumerate(chunk_rows)
    ]


@contextmanager
def _evaluation_workspace(run_root: Path) -> Iterator[None]:
    processed_dir = run_root / "processed"
    ask_log_dir = run_root / "ask_logs"
    processed_dir.mkdir(parents=True, exist_ok=True)
    ask_log_dir.mkdir(parents=True, exist_ok=True)

    original_processed_dir = settings.processed_dir
    original_ask_log_dir = settings.ask_log_dir

    settings.processed_dir = processed_dir
    settings.ask_log_dir = ask_log_dir
    try:
        yield
    finally:
        settings.processed_dir = original_processed_dir
        settings.ask_log_dir = original_ask_log_dir


def prepare_eval_corpus(source_paths: list[str]) -> list[str]:
    prepared_sources: list[str] = []
    for source_path in dict.fromkeys(source_paths):
        loaded_document = load_document(source_path)
        chunks = chunk_text(source=loaded_document.source, text=loaded_document.text)
        chunks = attach_embeddings(chunks)
        save_chunks(loaded_document.source, chunks)
        prepared_sources.append(loaded_document.source)
    return prepared_sources


def answer_question_direct_read(
    question: str,
    source_paths: list[str] | None = None,
) -> tuple[list[AskChunk], list[str], int, dict[str, Optional[str]], str]:
    ask_chunks = _selected_chunks(source_paths)
    sources, answer_payload = answer_with_chunks(question, ask_chunks)
    output_path = save_ask_record(
        question=question,
        top_k=len(ask_chunks),
        mode="direct_read",
        answer_payload=answer_payload,
        total_hits=len(ask_chunks),
        chunks=ask_chunks,
        sources=sources,
    )
    return ask_chunks, sources, len(ask_chunks), answer_payload, _relative(output_path)


def _serialize_mode_result(
    *,
    chunks: list[AskChunk],
    sources: list[str],
    total_hits: int,
    answer_payload: dict[str, Optional[str]],
    log_path: str,
) -> dict[str, Any]:
    return {
        "answer_preview": _compact_preview(
            str(answer_payload.get("answer", "")),
            ANSWER_PREVIEW_LIMIT,
        ),
        "answer_status": answer_payload.get("answer_status", "disabled"),
        "answer_note": answer_payload.get("answer_note"),
        "total_hits": total_hits,
        "returned_count": len(chunks),
        "source_count": len(sources),
        "sources": sources,
        "evidence": _serialize_evidence(chunks),
        "log_path": log_path,
        "manual_review": _manual_review_slot(),
    }


def run_evaluation(
    *,
    dataset_path: Path,
    top_k: int = 3,
    modes: list[str] | None = None,
) -> Path:
    selected_modes = modes or list(DEFAULT_EVAL_MODES)
    invalid_modes = [mode for mode in selected_modes if mode not in SUPPORTED_EVAL_MODES]
    if invalid_modes:
        raise ValueError(
            "Unsupported evaluation mode(s): " + ", ".join(sorted(set(invalid_modes)))
        )

    dataset_name, cases = load_eval_dataset(dataset_path)
    run_id = f"{_utc_timestamp()}_{_safe_name(dataset_name)}"
    run_root = settings.index_dir / EVAL_RUNS_DIRNAME / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    unique_sources = list(
        dict.fromkeys(
            source
            for case in cases
            for source in case.source_paths
        )
    )

    with _evaluation_workspace(run_root):
        prepared_sources = prepare_eval_corpus(unique_sources)
        case_payloads: list[dict[str, Any]] = []
        for case in cases:
            mode_payloads: dict[str, Any] = {}
            for mode in selected_modes:
                if mode == "direct_read":
                    chunks, sources, total_hits, answer_payload, log_path = (
                        answer_question_direct_read(
                            question=case.question,
                            source_paths=case.source_paths,
                        )
                    )
                else:
                    chunks, sources, total_hits, answer_payload, log_path = ask_question(
                        question=case.question,
                        top_k=top_k,
                        mode=mode,
                    )

                mode_payloads[mode] = _serialize_mode_result(
                    chunks=chunks,
                    sources=sources,
                    total_hits=total_hits,
                    answer_payload=answer_payload,
                    log_path=log_path,
                )

            case_payloads.append(
                {
                    "id": case.case_id,
                    "question": case.question,
                    "source_paths": case.source_paths,
                    "expected_sources": case.expected_sources,
                    "expected_answer_points": case.expected_answer_points,
                    "difficulty": case.difficulty,
                    "notes": case.notes,
                    "modes": mode_payloads,
                }
            )

    run_path = run_root / "run.json"
    payload = {
        "run_id": run_id,
        "dataset_name": dataset_name,
        "dataset_path": _relative(_resolve_dataset_path(dataset_path)),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "top_k": top_k,
        "modes": selected_modes,
        "ask_provider": settings.ask_provider,
        "lm_studio_model": settings.lm_studio_model or None,
        "embedding_model": settings.embedding_model_name,
        "prepared_sources": prepared_sources,
        "review_guide": {
            "labels": list(REVIEW_LABELS),
            "error_types": list(ERROR_TYPES),
            "note": "run.json 只保留 answer_preview 和 evidence 预览；如需完整回答与全文 chunk，请打开每个 mode 的 log_path。",
        },
        "workspace": {
            "processed_dir": _relative(run_root / "processed"),
            "ask_log_dir": _relative(run_root / "ask_logs"),
        },
        "cases": case_payloads,
    }
    run_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return run_path


def _empty_counts() -> dict[str, int]:
    return {}


def summarize_eval_run(run_path: Path) -> dict[str, Any]:
    resolved_path = run_path if run_path.is_absolute() else (PROJECT_DIR / run_path).resolve()
    payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    modes = payload.get("modes") or list(DEFAULT_EVAL_MODES)

    mode_summary: dict[str, Any] = {}
    for mode in modes:
        mode_summary[mode] = {
            "total_cases": 0,
            "reviewed_cases": 0,
            "unreviewed_cases": 0,
            "labels": {label: 0 for label in REVIEW_LABELS},
            "error_types": _empty_counts(),
        }

    for case in payload.get("cases", []):
        for mode, mode_data in case.get("modes", {}).items():
            if mode not in mode_summary:
                mode_summary[mode] = {
                    "total_cases": 0,
                    "reviewed_cases": 0,
                    "unreviewed_cases": 0,
                    "labels": {label: 0 for label in REVIEW_LABELS},
                    "error_types": _empty_counts(),
                }
            summary = mode_summary[mode]
            summary["total_cases"] += 1

            manual_review = mode_data.get("manual_review", {})
            label = str(manual_review.get("label", "")).strip().lower()
            error_type = str(manual_review.get("error_type", "")).strip()

            if label in REVIEW_LABELS:
                summary["reviewed_cases"] += 1
                summary["labels"][label] += 1
            else:
                summary["unreviewed_cases"] += 1

            if error_type:
                summary["error_types"][error_type] = summary["error_types"].get(error_type, 0) + 1

    recommendations: list[str] = []
    for mode, summary in mode_summary.items():
        if not summary["error_types"]:
            continue
        dominant_error_type, dominant_count = max(
            summary["error_types"].items(),
            key=lambda item: item[1],
        )
        if dominant_count <= 0:
            continue
        if dominant_error_type == "检索错":
            recommendations.append(
                f"{mode}: 检索错最多，下一步优先考虑 hybrid 检索或 reranker。"
            )
        elif dominant_error_type == "生成错":
            recommendations.append(
                f"{mode}: 生成错最多，说明召回可能够了，下一步更适合看提示词和小模型调优准备。"
            )
        elif dominant_error_type == "引用错":
            recommendations.append(
                f"{mode}: 引用错最多，下一步先收紧答案模板和引用拼装逻辑。"
            )
        elif dominant_error_type == "数据问题":
            recommendations.append(
                f"{mode}: 数据问题最多，下一步先回到 loader、chunker 和原始文档质量。"
            )

    return {
        "run_id": payload.get("run_id", resolved_path.parent.name),
        "dataset_name": payload.get("dataset_name", resolved_path.stem),
        "dataset_path": payload.get("dataset_path", ""),
        "top_k": payload.get("top_k", 0),
        "modes": mode_summary,
        "recommendations": recommendations,
        "run_path": _relative(resolved_path),
    }


def write_eval_report(run_path: Path) -> Path:
    summary = summarize_eval_run(run_path)
    report_dir = settings.index_dir / EVAL_REPORTS_DIRNAME
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{summary['run_id']}.md"

    lines = [
        f"# Eval Report: {summary['run_id']}",
        "",
        f"- dataset: {summary['dataset_name']}",
        f"- dataset_path: {summary['dataset_path']}",
        f"- top_k: {summary['top_k']}",
        f"- run_path: {summary['run_path']}",
        "",
    ]

    for mode, mode_summary in summary["modes"].items():
        lines.extend(
            [
                f"## {mode}",
                "",
                f"- total_cases: {mode_summary['total_cases']}",
                f"- reviewed_cases: {mode_summary['reviewed_cases']}",
                f"- unreviewed_cases: {mode_summary['unreviewed_cases']}",
                f"- correct: {mode_summary['labels']['correct']}",
                f"- incorrect: {mode_summary['labels']['incorrect']}",
                f"- insufficient: {mode_summary['labels']['insufficient']}",
                "- error_types:",
            ]
        )
        if mode_summary["error_types"]:
            for error_type, count in sorted(mode_summary["error_types"].items()):
                lines.append(f"  - {error_type}: {count}")
        else:
            lines.append("  - none")
        lines.append("")

    lines.append("## Recommendations")
    lines.append("")
    if summary["recommendations"]:
        for recommendation in summary["recommendations"]:
            lines.append(f"- {recommendation}")
    else:
        lines.append("- 还没有足够的人工标注，先补完 manual_review 再看趋势。")
    lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def latest_eval_run_path() -> Path | None:
    eval_runs_dir = settings.index_dir / EVAL_RUNS_DIRNAME
    if not eval_runs_dir.exists():
        return None

    run_paths = sorted(eval_runs_dir.glob("*/run.json"))
    return run_paths[-1] if run_paths else None
