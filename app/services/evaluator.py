"""Run a small, reviewable evaluation loop without external tooling.

The first evaluator keeps everything as local files so you can inspect one run,
label failures by hand, and decide whether the next investment belongs in
retrieval, generation, data cleanup, or storage infrastructure.
"""

from __future__ import annotations

import json
import math
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
from app.services.embedder import attach_embeddings, embed_text
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
DIRECT_READ_MAX_CONTEXT_CHUNKS = 6


@dataclass
class EvalCase:
    case_id: str
    question: str
    question_types: list[str]
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
                question_types=[
                    str(question_type).strip()
                    for question_type in raw_case.get("question_types", [])
                    if str(question_type).strip()
                ]
                or ["未分类"],
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


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0

    dot_product = sum(left_value * right_value for left_value, right_value in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot_product / (left_norm * right_norm)


def _quoted_focus_terms(question: str) -> list[str]:
    return [
        match.group(1).strip()
        for match in re.finditer(r"[“\"]([^”\"]{2,30})[”\"]", question)
        if match.group(1).strip()
    ]


def _ascii_focus_terms(question: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"\b[A-Za-z][A-Za-z0-9_-]{2,}\b", question)))


def _numeric_focus_terms(question: str) -> list[str]:
    return list(dict.fromkeys(re.findall(r"\d+(?:\.\d+)?%?", question)))


def _domain_focus_terms(question: str) -> list[str]:
    terms: list[str] = []
    for match in re.finditer(
        r"([\u4e00-\u9fffA-Za-z0-9 _-]{2,24}(?:标题|模式|规则|条件|日志|流程|默认值|候选事实|Source Unit|Evidence Block|Segment))",
        question,
    ):
        term = re.sub(
            r"^(?:如果问题是|如果用户问|如果问题问|如果一个|如果|为什么|为何|是否|是不是|能不能|可不可以|文档有没有(?:明确)?(?:说明|解释|规定|写明|给出)|文档|这类问题|问题是)+",
            "",
            match.group(1).strip(),
        ).strip("“”\"' ")
        if term:
            terms.append(term)
    return list(dict.fromkeys(terms))


def _choice_focus_terms(question: str) -> list[str]:
    choice_terms: list[str] = []
    pair_pattern = re.compile(
        r"([A-Za-z][A-Za-z0-9_-]{1,30}|[\u4e00-\u9fff]{2,12})\s*(?:还是|或|或者)\s*([A-Za-z][A-Za-z0-9_-]{1,30}|[\u4e00-\u9fff]{2,12})"
    )
    for match in pair_pattern.finditer(question):
        choice_terms.extend([match.group(1), match.group(2)])
    return list(dict.fromkeys(choice_terms))


def _looks_like_classification_question(question: str) -> bool:
    return any(token in question for token in ("属于", "哪种", "哪个", "更接近", "归为", "模式", "分类", "类型"))


def _looks_like_procedure_question(question: str) -> bool:
    return any(token in question for token in ("步骤", "顺序", "流程", "怎么处理", "如何处理", "超限"))


def _looks_like_conflict_question(question: str) -> bool:
    return "冲突" in question and any(token in question for token in ("怎么做", "如何处理", "应该怎么做", "怎么办"))


def _looks_like_boundary_question(question: str) -> bool:
    return bool(
        re.search(r"(范围外|以外|之外|跨[\u4e00-\u9fffA-Za-z0-9]{1,8})", question)
    ) or any(token in question for token in ("适用", "边界", "仍", "还"))


def _looks_like_explanation_question(question: str) -> bool:
    return any(token in question for token in ("为什么", "为何", "原因", "为什么说", "为什么不能", "为什么不应该"))


def _looks_like_degradation_question(question: str) -> bool:
    return "降级" in question


def _direct_read_focus_boost(question: str, chunk_text: str) -> float:
    normalized_chunk = normalize_text(chunk_text)
    boost = 0.0
    matched_domain_terms = 0

    for phrase in _quoted_focus_terms(question)[:2]:
        normalized_phrase = normalize_text(phrase)
        if normalized_phrase and normalized_phrase in normalized_chunk:
            boost += 0.22

    for term in _ascii_focus_terms(question)[:4]:
        if term in chunk_text:
            boost += 0.12

    for token in _numeric_focus_terms(question)[:4]:
        if token in chunk_text:
            boost += 0.08

    for term in _domain_focus_terms(question)[:4]:
        if term in chunk_text:
            boost += 0.14
            matched_domain_terms += 1

    matched_choices = sum(term in chunk_text for term in _choice_focus_terms(question)[:4])
    boost += 0.12 * matched_choices

    if _looks_like_classification_question(question) and re.search(
        r"(属于|归为|模式|分类|类型|Lookup|Explain)",
        chunk_text,
    ):
        boost += 0.18

    if _looks_like_procedure_question(question) and re.search(
        r"(先|再|然后|最后|步骤|顺序|流程|超限|裁剪)",
        chunk_text,
    ):
        boost += 0.18

    if _looks_like_conflict_question(question) and re.search(
        r"(冲突|不一致|来源|确认|合并)",
        chunk_text,
    ):
        boost += 0.18

    if _looks_like_boundary_question(question) and re.search(
        r"(未明示|只明确|仅明确|范围|边界|除非|例外|仅在|只在)",
        chunk_text,
    ):
        boost += 0.18

    if _looks_like_explanation_question(question) and re.search(
        r"(因为|原因|更接近|更适合|归为|属于|例外|除非|为何|模式|原则)",
        chunk_text,
    ):
        boost += 0.18
        if matched_domain_terms and re.search(r"(例外|除非|以下内容之一|短段)", chunk_text):
            boost += 0.14

    if _looks_like_degradation_question(question) and re.search(
        r"(降级|未确认|候选事实|低于|高于|阈值|0\.\d+)",
        chunk_text,
    ):
        boost += 0.18

    return boost


def _select_direct_read_chunks(
    question: str,
    source_paths: list[str] | None = None,
    *,
    max_chunks: int = DIRECT_READ_MAX_CONTEXT_CHUNKS,
) -> list[AskChunk]:
    selected_sources = source_paths or []
    source_order = {source: index for index, source in enumerate(selected_sources)}
    chunk_rows: list[tuple[int, int, str, AskChunk, list[float]]] = []

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
                list(map(float, chunk_data.get("embedding", []) or [])),
            )
        )

    chunk_rows.sort(key=lambda item: (item[0], item[1], item[2]))
    if len(chunk_rows) <= max_chunks:
        return [
            chunk.model_copy(update={"rank": index + 1})
            for index, (_, _, _, chunk, _) in enumerate(chunk_rows)
        ]

    normalized_question = normalize_text(question)
    query_embedding = list(map(float, embed_text(normalized_question))) if normalized_question else []

    scored_rows: list[tuple[float, int, int, int, str]] = []
    for index, (rank_group, start_index, chunk_id, chunk, embedding) in enumerate(chunk_rows):
        similarity = _cosine_similarity(query_embedding, embedding) if query_embedding and embedding else 0.0
        similarity += _direct_read_focus_boost(question, chunk.text)
        scored_rows.append((similarity, index, rank_group, start_index, chunk_id))

    if not any(score > 0.0 for score, *_ in scored_rows):
        chosen_indexes = {index for _, index, *_ in scored_rows[:max_chunks]}
    else:
        chosen_indexes = {
            index
            for _, index, *_ in sorted(
                scored_rows,
                key=lambda item: (-item[0], item[2], item[3], item[4]),
            )[:max_chunks]
        }

    selected_rows = [row for index, row in enumerate(chunk_rows) if index in chosen_indexes]
    return [
        chunk.model_copy(update={"rank": index + 1})
        for index, (_, _, _, chunk, _) in enumerate(selected_rows)
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
    ask_chunks = _select_direct_read_chunks(question, source_paths)
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
                    "question_types": case.question_types,
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


def _empty_type_summary() -> dict[str, Any]:
    return {
        "total_cases": 0,
        "reviewed_cases": 0,
        "unreviewed_cases": 0,
        "labels": {label: 0 for label in REVIEW_LABELS},
        "error_types": _empty_counts(),
    }


def summarize_eval_run(run_path: Path) -> dict[str, Any]:
    resolved_path = run_path if run_path.is_absolute() else (PROJECT_DIR / run_path).resolve()
    payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    modes = payload.get("modes") or list(DEFAULT_EVAL_MODES)
    dataset_case_types: dict[str, list[str]] = {}
    dataset_path_value = str(payload.get("dataset_path", "")).strip()
    if dataset_path_value:
        try:
            _, dataset_cases = load_eval_dataset(Path(dataset_path_value))
            dataset_case_types = {
                dataset_case.case_id: dataset_case.question_types
                for dataset_case in dataset_cases
            }
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            dataset_case_types = {}

    mode_summary: dict[str, Any] = {}
    for mode in modes:
        mode_summary[mode] = {
            "total_cases": 0,
            "reviewed_cases": 0,
            "unreviewed_cases": 0,
            "labels": {label: 0 for label in REVIEW_LABELS},
            "error_types": _empty_counts(),
            "question_types": {},
        }

    for case in payload.get("cases", []):
        question_types = case.get("question_types") or dataset_case_types.get(case.get("id", "")) or ["未分类"]
        for mode, mode_data in case.get("modes", {}).items():
            if mode not in mode_summary:
                mode_summary[mode] = {
                    "total_cases": 0,
                    "reviewed_cases": 0,
                    "unreviewed_cases": 0,
                    "labels": {label: 0 for label in REVIEW_LABELS},
                    "error_types": _empty_counts(),
                    "question_types": {},
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

            for question_type in question_types:
                type_name = str(question_type).strip() or "未分类"
                type_summary = summary["question_types"].setdefault(type_name, _empty_type_summary())
                type_summary["total_cases"] += 1
                if label in REVIEW_LABELS:
                    type_summary["reviewed_cases"] += 1
                    type_summary["labels"][label] += 1
                else:
                    type_summary["unreviewed_cases"] += 1
                if error_type:
                    type_summary["error_types"][error_type] = (
                        type_summary["error_types"].get(error_type, 0) + 1
                    )

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
        lines.append("- question_types:")
        if mode_summary["question_types"]:
            for question_type, type_summary in sorted(mode_summary["question_types"].items()):
                lines.append(
                    "  - "
                    f"{question_type}: total={type_summary['total_cases']}, "
                    f"correct={type_summary['labels']['correct']}, "
                    f"incorrect={type_summary['labels']['incorrect']}, "
                    f"insufficient={type_summary['labels']['insufficient']}"
                )
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
