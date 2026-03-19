from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest


def test_build_eval_dataset_from_markdown_handles_missing_separator_between_questions(
    tmp_path: Path,
) -> None:
    markdown_path = tmp_path / "evaluatetest.md"
    dataset_path = tmp_path / "test_eval_set.json"
    markdown_path.write_text(
        """## 1

**question**
第一个问题是什么？

**expected_source_section**
1. 第一节

**expected_key_points**

* 第一条
* 第二条

**reference_answer**
第一个问题的参考答案。

**error_type_hint**
A1

## 2

**question**
第二个问题是什么？

**expected_source_section**
2. 第二节

**expected_key_points**

* 第三条

**reference_answer**
第二个问题的参考答案。

**error_type_hint**
A2 / R1
""",
        encoding="utf-8",
    )

    from app.services.eval_dataset_builder import build_eval_dataset_from_markdown

    output_path = build_eval_dataset_from_markdown(
        markdown_path=markdown_path,
        dataset_path=dataset_path,
        source_document="data/raw/test.md",
        dataset_name="tiny-eval",
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert output_path == dataset_path
    assert payload["name"] == "tiny-eval"
    assert len(payload["cases"]) == 2
    assert payload["cases"][0]["id"] == "test-md-001"
    assert payload["cases"][1]["id"] == "test-md-002"
    assert payload["cases"][0]["source_paths"] == ["data/raw/test.md"]
    assert payload["cases"][1]["expected_answer_points"] == ["第三条"]
    assert payload["cases"][0]["question_types"] == ["事实查找"]
    assert payload["cases"][1]["question_types"] == ["事实查找"]


def test_build_eval_dataset_script_defaults_to_project_eval_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["build_eval_dataset.py"])

    from scripts.build_eval_dataset import _parse_args

    args = _parse_args()

    assert args.markdown == "data/raw/evaluatetest.md"
    assert args.output == "data/evals/test_eval_set.json"
    assert args.source_document == "data/raw/test.md"
