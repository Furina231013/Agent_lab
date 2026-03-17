"""Build a stable JSON eval dataset from editable markdown question notes.

The evaluation runner intentionally reads JSON only, so the runtime format stays
simple and predictable. This builder keeps the more human-friendly markdown
editing workflow separate from the machine-friendly dataset file.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


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

        cases.append(
            {
                "id": f"test-md-{index:03d}",
                "question": match.group("question").strip(),
                "source_paths": [source_document],
                "expected_sources": [source_document],
                "expected_answer_points": _parse_expected_points(match.group("points")),
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
