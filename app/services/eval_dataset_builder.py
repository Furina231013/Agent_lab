"""Build a stable JSON eval dataset from editable markdown question notes.

The evaluation runner intentionally reads JSON only, so the runtime format stays
simple and predictable. This builder keeps the more human-friendly markdown
editing workflow separate from the machine-friendly dataset file.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


QUESTION_TYPE_FACT = "事实查找"
QUESTION_TYPE_MULTI_HOP = "多跳推理"
QUESTION_TYPE_CROSS_SECTION = "跨段聚合"
QUESTION_TYPE_TIME_BOUND = "带时间限制"
QUESTION_TYPE_CONCEPTUAL = "容易混淆概念"
QUESTION_TYPE_REFUSAL = "需要拒答的问题"
REQUIRED_QUESTION_TYPES = (
    QUESTION_TYPE_FACT,
    QUESTION_TYPE_MULTI_HOP,
    QUESTION_TYPE_CROSS_SECTION,
    QUESTION_TYPE_TIME_BOUND,
    QUESTION_TYPE_CONCEPTUAL,
    QUESTION_TYPE_REFUSAL,
)

QUESTION_BLOCK_PATTERN = re.compile(
    r"(?ms)^##\s+(?P<num>\d+)\n\n"
    r"\*\*question\*\*\n(?P<question>.+?)\n\n"
    r"\*\*expected_source_section\*\*\n(?P<section>.+?)\n\n"
    r"\*\*expected_key_points\*\*\n\n(?P<points>.+?)\n\n"
    r"\*\*reference_answer\*\*\n(?P<answer>.+?)\n\n"
    r"\*\*error_type_hint\*\*\n(?P<hint>.+?)(?=\n\n---\n|\n\n##\s+\d+|\Z)"
)


def _parse_expected_points(raw_points: str) -> list[str]:
    points: list[str] = []
    for line in raw_points.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        stripped = re.sub(r"^\*\s*", "", stripped).strip()
        if stripped:
            points.append(stripped)
    return points


def _unique_preserve_order(items: list[str]) -> list[str]:
    unique: list[str] = []
    for item in items:
        normalized = item.strip()
        if normalized and normalized not in unique:
            unique.append(normalized)
    return unique


def _infer_question_types(
    *,
    question: str,
    section: str,
    expected_points: list[str],
    reference_answer: str,
) -> list[str]:
    combined_points = " ".join(expected_points)
    combined_text = " ".join([question, section, combined_points, reference_answer])
    question_types: list[str] = []

    if re.search(r"(有没有(?:明确)?(?:说明|解释|规定|写明|给出)|是否(?:明确)?(?:说明|解释|规定|写明|给出))", question) or any(
        re.search(r"^(没有|未明示|未说明|未规定|未涉及)", point) for point in expected_points
    ):
        question_types.append(QUESTION_TYPE_REFUSAL)

    if re.search(r"(\d+\s*小时|\d+\s*分钟|时区|v\d+\.\d+|当前版本|计划版本|重复导入|跨分钟|同一分钟)", combined_text):
        question_types.append(QUESTION_TYPE_TIME_BOUND)

    if re.search(r"(为什么|为何|而不是|更接近|区别|不同于|是不是只|不能只|不应该|混淆)", question):
        question_types.append(QUESTION_TYPE_CONCEPTUAL)

    if len(expected_points) >= 3 and re.search(
        r"(如果|同时|分别|以及|并且|还|什么条件下|什么情况下|怎么做|如何处理|为什么不能只)",
        question,
    ):
        question_types.append(QUESTION_TYPE_MULTI_HOP)

    if len(expected_points) >= 3 and (
        re.search(r"(同时|分别|以及|并且|还|为什么不能只|会不会|能不能|是不是)", question)
        or len({token for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,12}", combined_points)}) >= 6
    ):
        question_types.append(QUESTION_TYPE_CROSS_SECTION)

    if not question_types or re.search(
        r"(多少|是什么|哪些|哪种|默认|上限|下限|阈值|支持|会被如何处理|属于哪种|是不是|会不会|能不能)",
        question,
    ):
        question_types.append(QUESTION_TYPE_FACT)

    return _unique_preserve_order(question_types)


def build_eval_dataset_from_markdown(
    *,
    markdown_path: Path,
    dataset_path: Path,
    source_document: str,
    dataset_name: str,
) -> Path:
    text = markdown_path.read_text(encoding="utf-8").strip()
    cases: list[dict[str, object]] = []

    for match in QUESTION_BLOCK_PATTERN.finditer(text):
        index = int(match.group("num"))
        section = match.group("section").strip()
        reference_answer = match.group("answer").strip()
        error_hint = match.group("hint").strip()
        expected_points = _parse_expected_points(match.group("points"))
        question = match.group("question").strip()

        cases.append(
            {
                "id": f"test-md-{index:03d}",
                "question": question,
                "source_paths": [source_document],
                "expected_sources": [source_document],
                "expected_answer_points": expected_points,
                "question_types": _infer_question_types(
                    question=question,
                    section=section,
                    expected_points=expected_points,
                    reference_answer=reference_answer,
                ),
                "difficulty": "medium",
                "notes": (
                    f"来源章节: {section}；"
                    f"error_hint: {error_hint}；"
                    f"参考答案: {reference_answer}"
                ),
            }
        )

    if not cases:
        raise ValueError(f"No eval questions were parsed from: {markdown_path}")

    payload = {
        "name": dataset_name,
        "description": (
            f"基于 {source_document} 与 {markdown_path.as_posix()} 生成的 "
            f"{len(cases)} 条人工评测集。"
        ),
        "cases": cases,
    }

    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    dataset_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return dataset_path
