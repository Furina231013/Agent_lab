"""Evaluation tests lock the small review loop before script wiring grows."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from app.config import settings
from app.schemas import AskChunk


@pytest.fixture
def isolated_eval_settings(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    processed_dir = data_dir / "processed"
    index_dir = data_dir / "index"
    ask_log_dir = index_dir / "ask_logs"
    for directory in (data_dir, processed_dir, index_dir, ask_log_dir):
        directory.mkdir(parents=True, exist_ok=True)

    original_values = {
        "data_dir": settings.data_dir,
        "processed_dir": settings.processed_dir,
        "index_dir": settings.index_dir,
        "ask_log_dir": settings.ask_log_dir,
        "ask_provider": settings.ask_provider,
        "lm_studio_model": settings.lm_studio_model,
    }

    settings.data_dir = data_dir
    settings.processed_dir = processed_dir
    settings.index_dir = index_dir
    settings.ask_log_dir = ask_log_dir

    yield

    for field_name, original_value in original_values.items():
        setattr(settings, field_name, original_value)


def test_answer_question_direct_read_limits_context_to_selected_sources(
    isolated_eval_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "source": "data/raw/direct-read.md",
        "chunk_count": 2,
        "chunks": [
            {
                "chunk_id": "alpha-0001",
                "source": "data/raw/alpha.md",
                "text": "Loader reads local files from disk.",
                "start_index": 0,
                "end_index": 35,
            },
            {
                "chunk_id": "beta-0001",
                "source": "data/raw/beta.md",
                "text": "Chunker splits long text into chunks.",
                "start_index": 36,
                "end_index": 73,
            },
        ],
    }
    (settings.processed_dir / "direct-read.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    settings.ask_provider = "lm_studio"
    settings.lm_studio_model = "local-model"

    def fake_generate(question: str, chunks: list[dict[str, object]]) -> dict[str, str]:
        assert question == "loader 是什么"
        assert len(chunks) == 1
        assert chunks[0]["source"] == "data/raw/alpha.md"
        return {
            "answer": "Loader 负责读取本地文件。",
            "answer_mode": "lm_studio",
            "answer_status": "generated",
            "answer_note": "Answered by local LM Studio model.",
            "provider": "lm_studio",
            "model": "local-model",
        }

    monkeypatch.setattr(
        "app.services.asker.generate_lm_studio_answer",
        fake_generate,
        raising=False,
    )

    from app.services.evaluator import answer_question_direct_read

    chunks, sources, total_hits, answer_payload, output_path = answer_question_direct_read(
        question="loader 是什么",
        source_paths=["data/raw/alpha.md"],
    )

    assert total_hits == 1
    assert sources == ["data/raw/alpha.md"]
    assert len(chunks) == 1
    assert chunks[0].chunk_id == "alpha-0001"
    assert answer_payload["answer_status"] == "generated"
    assert output_path.endswith(".json")


def test_answer_question_direct_read_caps_and_restores_document_order(
    isolated_eval_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "source": "data/raw/test.md",
        "chunk_count": 8,
        "chunks": [
            {
                "chunk_id": "chunk-01",
                "source": "data/raw/test.md",
                "text": "alpha",
                "start_index": 0,
                "end_index": 5,
                "embedding": [0.95, 0.0],
            },
            {
                "chunk_id": "chunk-02",
                "source": "data/raw/test.md",
                "text": "beta",
                "start_index": 10,
                "end_index": 14,
                "embedding": [0.40, 0.0],
            },
            {
                "chunk_id": "chunk-03",
                "source": "data/raw/test.md",
                "text": "gamma",
                "start_index": 20,
                "end_index": 25,
                "embedding": [0.92, 0.0],
            },
            {
                "chunk_id": "chunk-04",
                "source": "data/raw/test.md",
                "text": "delta",
                "start_index": 30,
                "end_index": 35,
                "embedding": [0.15, 0.9],
            },
            {
                "chunk_id": "chunk-05",
                "source": "data/raw/test.md",
                "text": "epsilon",
                "start_index": 40,
                "end_index": 47,
                "embedding": [0.88, 0.0],
            },
            {
                "chunk_id": "chunk-06",
                "source": "data/raw/test.md",
                "text": "zeta",
                "start_index": 50,
                "end_index": 54,
                "embedding": [0.20, 0.8],
            },
            {
                "chunk_id": "chunk-07",
                "source": "data/raw/test.md",
                "text": "eta",
                "start_index": 60,
                "end_index": 63,
                "embedding": [0.84, 0.0],
            },
            {
                "chunk_id": "chunk-08",
                "source": "data/raw/test.md",
                "text": "theta",
                "start_index": 70,
                "end_index": 75,
                "embedding": [0.82, 0.0],
            },
        ],
    }
    (settings.processed_dir / "direct-read-ranked.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "app.services.evaluator.embed_text",
        lambda text: [1.0, 0.0],
        raising=False,
    )

    captured_chunk_ids: list[str] = []

    def fake_answer_with_chunks(question: str, ask_chunks: list[AskChunk]):
        assert question == "哪个 chunk 最相关？"
        captured_chunk_ids.extend(chunk.chunk_id for chunk in ask_chunks)
        return (
            ["data/raw/test.md"],
            {
                "answer": "mock",
                "answer_mode": "placeholder",
                "answer_status": "disabled",
                "answer_note": "demo",
                "provider": "placeholder",
                "model": None,
            },
        )

    monkeypatch.setattr(
        "app.services.evaluator.answer_with_chunks",
        fake_answer_with_chunks,
        raising=False,
    )

    from app.services.evaluator import answer_question_direct_read

    chunks, _, total_hits, _, _ = answer_question_direct_read(
        question="哪个 chunk 最相关？",
        source_paths=["data/raw/test.md"],
    )

    assert total_hits == 6
    assert captured_chunk_ids == [
        "chunk-01",
        "chunk-02",
        "chunk-03",
        "chunk-05",
        "chunk-07",
        "chunk-08",
    ]
    assert [chunk.chunk_id for chunk in chunks] == captured_chunk_ids


def test_select_direct_read_chunks_boosts_query_mode_chunk_for_mode_questions(
    isolated_eval_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "source": "data/raw/test.md",
        "chunk_count": 2,
        "chunks": [
            {
                "chunk_id": "chunk-reason",
                "source": "data/raw/test.md",
                "text": "标题是轻量语义锚点，因此系统会保留标题。",
                "start_index": 0,
                "end_index": 24,
                "embedding": [0.8, 0.6],
            },
            {
                "chunk_id": "chunk-mode",
                "source": "data/raw/test.md",
                "text": "带有“为什么”的问题默认归为 Explain 模式，属于 Query Mode 分类规则。",
                "start_index": 30,
                "end_index": 72,
                "embedding": [0.55, 0.8351646544],
            },
        ],
    }
    (settings.processed_dir / "direct-read-query-mode.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "app.services.evaluator.embed_text",
        lambda text: [1.0, 0.0],
        raising=False,
    )

    from app.services.evaluator import _select_direct_read_chunks

    chunks = _select_direct_read_chunks(
        "如果用户问“为什么系统保留标题”，这类问题默认属于哪种 Query Mode？",
        ["data/raw/test.md"],
        max_chunks=1,
    )

    assert [chunk.chunk_id for chunk in chunks] == ["chunk-mode"]


def test_select_direct_read_chunks_prefers_exception_explanation_chunk_for_why_question(
    isolated_eval_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "source": "data/raw/test.md",
        "chunk_count": 2,
        "chunks": [
            {
                "chunk_id": "chunk-title-anchor",
                "source": "data/raw/test.md",
                "text": "标题之所以保留，是因为标题被视为轻量语义锚点。",
                "start_index": 0,
                "end_index": 28,
                "embedding": [0.95, 0.0],
            },
            {
                "chunk_id": "chunk-short-exception",
                "source": "data/raw/test.md",
                "text": "错误码标题即使很短，也属于短段例外，因此可以单独作为 Segment。",
                "start_index": 30,
                "end_index": 70,
                "embedding": [0.80, 0.0],
            },
        ],
    }
    (settings.processed_dir / "direct-read-exception.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "app.services.evaluator.embed_text",
        lambda text: [1.0, 0.0],
        raising=False,
    )

    from app.services.evaluator import _select_direct_read_chunks

    chunks = _select_direct_read_chunks(
        "为什么错误码标题即使很短，也可能被单独保留下来？",
        ["data/raw/test.md"],
        max_chunks=1,
    )

    assert [chunk.chunk_id for chunk in chunks] == ["chunk-short-exception"]


def test_run_evaluation_writes_default_vector_and_direct_read_results_with_manual_review_slots(
    isolated_eval_settings: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataset_path = tmp_path / "small_eval_set.json"
    dataset_path.write_text(
        json.dumps(
            {
                "name": "tiny-eval",
                "cases": [
                    {
                        "id": "case-001",
                        "question": "Loader 做什么？",
                        "question_types": ["事实查找"],
                        "source_paths": ["data/raw/vector_demo.md"],
                        "expected_sources": ["data/raw/vector_demo.md"],
                        "expected_answer_points": ["读取本地文件", "转成纯文本"],
                        "difficulty": "easy",
                        "notes": "最小评测用例",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    def fake_prepare(case_sources: list[str]) -> list[str]:
        assert case_sources == ["data/raw/vector_demo.md"]
        payload = {
            "source": "data/raw/vector_demo.md",
            "chunk_count": 1,
            "chunks": [
                {
                    "chunk_id": "embed-0001",
                    "source": "data/raw/vector_demo.md",
                    "text": "Loader reads local files from disk and turns them into plain text.",
                    "start_index": 0,
                    "end_index": 67,
                }
            ],
        }
        (settings.processed_dir / "embedding-demo.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return case_sources

    def fake_ask_question(question: str, top_k: int, mode: str):
        long_answer = f"{mode} answer " + ("x" * 280)
        long_chunk = f"{mode} chunk " + ("y" * 220)
        return (
            [
                AskChunk(
                    rank=1,
                    source="data/raw/vector_demo.md",
                    chunk_id=f"{mode}-0001",
                    score=1.0,
                    text=long_chunk,
                )
            ],
            ["data/raw/vector_demo.md"],
            1,
            {
                "answer": long_answer,
                "answer_mode": "placeholder",
                "answer_status": "disabled",
                "answer_note": "demo",
                "provider": "placeholder",
                "model": None,
            },
            f"data/index/ask_logs/{mode}.json",
        )

    def fake_direct_read(question: str, source_paths: list[str] | None = None):
        return (
            [
                AskChunk(
                    rank=1,
                    source="data/raw/vector_demo.md",
                    chunk_id="direct-0001",
                    score=1.0,
                    text="direct chunk " + ("z" * 220),
                )
            ],
            ["data/raw/vector_demo.md"],
            1,
            {
                "answer": "direct answer " + ("q" * 280),
                "answer_mode": "placeholder",
                "answer_status": "disabled",
                "answer_note": "demo",
                "provider": "placeholder",
                "model": None,
            },
            "data/index/ask_logs/direct_read.json",
        )

    monkeypatch.setattr(
        "app.services.evaluator.prepare_eval_corpus",
        fake_prepare,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.evaluator.ask_question",
        fake_ask_question,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.evaluator.answer_question_direct_read",
        fake_direct_read,
        raising=False,
    )

    from app.services.evaluator import run_evaluation

    run_path = run_evaluation(dataset_path=dataset_path, top_k=2)
    saved_payload = json.loads(run_path.read_text(encoding="utf-8"))

    assert run_path.exists()
    assert saved_payload["dataset_name"] == "tiny-eval"
    assert saved_payload["top_k"] == 2
    assert saved_payload["prepared_sources"] == ["data/raw/vector_demo.md"]
    assert len(saved_payload["cases"]) == 1
    case_payload = saved_payload["cases"][0]
    assert case_payload["id"] == "case-001"
    assert case_payload["question_types"] == ["事实查找"]
    assert set(case_payload["modes"]) == {"vector", "direct_read"}
    assert case_payload["modes"]["vector"]["manual_review"] == {
        "label": "",
        "error_type": "",
        "notes": "",
    }
    assert "answer" not in case_payload["modes"]["vector"]
    assert "chunks" not in case_payload["modes"]["vector"]
    assert case_payload["modes"]["vector"]["answer_preview"].startswith("vector answer")
    assert case_payload["modes"]["vector"]["answer_preview"].endswith("...")
    assert case_payload["modes"]["vector"]["source_count"] == 1
    assert case_payload["modes"]["vector"]["evidence"][0]["text_preview"].startswith(
        "vector chunk"
    )
    assert case_payload["modes"]["vector"]["evidence"][0]["text_preview"].endswith("...")
    assert case_payload["modes"]["direct_read"]["answer_preview"].startswith("direct answer")
    assert case_payload["modes"]["direct_read"]["log_path"].endswith(".json")


def test_prepare_eval_corpus_keeps_chunk_source_and_text_in_correct_fields(
    isolated_eval_settings: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_path = tmp_path / "lesson.md"
    raw_path.write_text(
        "Loader reads local files from disk.\n\nChunker splits long text.",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.services.evaluator.attach_embeddings",
        lambda chunks: chunks,
        raising=False,
    )

    from app.services.evaluator import prepare_eval_corpus

    prepare_eval_corpus([str(raw_path)])

    saved_path = next(settings.processed_dir.glob("*.json"))
    saved_payload = json.loads(saved_path.read_text(encoding="utf-8"))
    first_chunk = saved_payload["chunks"][0]

    assert first_chunk["source"].endswith("lesson.md")
    assert first_chunk["text"].startswith("Loader reads local files")


def test_write_eval_report_summarizes_manual_labels(
    isolated_eval_settings: None,
) -> None:
    run_root = settings.index_dir / "eval_runs" / "eval-demo"
    run_root.mkdir(parents=True, exist_ok=True)
    run_path = run_root / "run.json"
    run_path.write_text(
        json.dumps(
            {
                "run_id": "eval-demo",
                "dataset_name": "tiny-eval",
                "top_k": 3,
                "cases": [
                    {
                        "id": "case-001",
                        "question_types": ["事实查找", "多跳推理"],
                        "modes": {
                            "keyword": {
                                "manual_review": {
                                    "label": "correct",
                                    "error_type": "",
                                    "notes": "",
                                }
                            },
                            "vector": {
                                "manual_review": {
                                    "label": "incorrect",
                                    "error_type": "检索错",
                                    "notes": "",
                                }
                            },
                            "direct_read": {
                                "manual_review": {
                                    "label": "insufficient",
                                    "error_type": "数据问题",
                                    "notes": "",
                                }
                            },
                        },
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    from app.services.evaluator import summarize_eval_run, write_eval_report

    summary = summarize_eval_run(run_path)
    report_path = write_eval_report(run_path)
    report_text = report_path.read_text(encoding="utf-8")

    assert summary["modes"]["keyword"]["labels"]["correct"] == 1
    assert summary["modes"]["vector"]["error_types"]["检索错"] == 1
    assert summary["modes"]["direct_read"]["labels"]["insufficient"] == 1
    assert summary["modes"]["keyword"]["question_types"]["事实查找"]["labels"]["correct"] == 1
    assert summary["modes"]["vector"]["question_types"]["多跳推理"]["labels"]["incorrect"] == 1
    assert report_path.exists()
    assert "keyword" in report_text
    assert "检索错" in report_text
    assert "question_types" in report_text
    assert "事实查找" in report_text


def test_summarize_eval_run_uses_dataset_question_types_when_run_case_omits_them(
    isolated_eval_settings: None,
    tmp_path: Path,
) -> None:
    dataset_path = tmp_path / "typed_eval.json"
    dataset_path.write_text(
        json.dumps(
            {
                "name": "typed-eval",
                "cases": [
                    {
                        "id": "case-typed",
                        "question": "为什么要这样做？",
                        "question_types": ["容易混淆概念", "多跳推理"],
                        "source_paths": ["data/raw/test.md"],
                        "expected_sources": ["data/raw/test.md"],
                        "expected_answer_points": ["原因", "约束"],
                        "difficulty": "medium",
                        "notes": "",
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    run_root = settings.index_dir / "eval_runs" / "eval-typed"
    run_root.mkdir(parents=True, exist_ok=True)
    run_path = run_root / "run.json"
    run_path.write_text(
        json.dumps(
            {
                "run_id": "eval-typed",
                "dataset_name": "typed-eval",
                "dataset_path": str(dataset_path),
                "top_k": 3,
                "cases": [
                    {
                        "id": "case-typed",
                        "modes": {
                            "vector": {
                                "manual_review": {
                                    "label": "correct",
                                    "error_type": "",
                                    "notes": "",
                                }
                            }
                        },
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    from app.services.evaluator import summarize_eval_run

    summary = summarize_eval_run(run_path)

    assert summary["modes"]["vector"]["question_types"]["容易混淆概念"]["labels"]["correct"] == 1
    assert summary["modes"]["vector"]["question_types"]["多跳推理"]["labels"]["correct"] == 1


def test_small_eval_dataset_references_existing_source_files() -> None:
    dataset_path = Path("/Users/huyh/learning/agent_lab/agent-lab/data/evals/small_eval_set.json")
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))

    missing_sources = []
    referenced_sources = []
    for case in payload["cases"]:
        for source_path in case["source_paths"]:
            referenced_sources.append(source_path)
            resolved_path = Path("/Users/huyh/learning/agent_lab/agent-lab") / source_path
            if not resolved_path.exists():
                missing_sources.append(source_path)

    assert missing_sources == []
    assert "data/raw/embedding_demo.md" not in referenced_sources


def test_vector_demo_is_named_clearly_and_uses_chinese_content() -> None:
    demo_path = Path("/Users/huyh/learning/agent_lab/agent-lab/data/raw/vector_demo.md")

    assert demo_path.exists()
    content = demo_path.read_text(encoding="utf-8")
    assert "# 向量检索演示文档" in content
    assert "向量检索" in content


def test_evaluate_script_defaults_to_test_eval_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", ["evaluate.py", "run"])

    from scripts.evaluate import _parse_args

    args = _parse_args()

    assert args.dataset == "data/evals/test_eval_set.json"
    assert args.modes == ["vector", "direct_read"]


def test_test_eval_dataset_targets_test_md_with_hundred_cases() -> None:
    dataset_path = Path("/Users/huyh/learning/agent_lab/agent-lab/data/evals/test_eval_set.json")
    source_markdown_path = Path("/Users/huyh/learning/agent_lab/agent-lab/data/raw/evaluatetest.md")

    assert dataset_path.exists()
    assert source_markdown_path.exists()

    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    question_count = sum(
        1
        for line in source_markdown_path.read_text(encoding="utf-8").splitlines()
        if line.startswith("## ")
    )
    assert question_count == 100
    assert len(payload["cases"]) == 100
    assert len(payload["cases"]) == question_count

    seen_question_types = set()
    for case in payload["cases"]:
        assert case["source_paths"] == ["data/raw/test.md"]
        assert case["expected_sources"] == ["data/raw/test.md"]
        assert case["question_types"]
        seen_question_types.update(case["question_types"])

    assert {
        "事实查找",
        "多跳推理",
        "跨段聚合",
        "带时间限制",
        "容易混淆概念",
        "需要拒答的问题",
    }.issubset(seen_question_types)


def test_ingest_demo_uses_test_md() -> None:
    script_path = Path("/Users/huyh/learning/agent_lab/agent-lab/scripts/ingest_demo.py")
    script_text = script_path.read_text(encoding="utf-8")

    assert 'load_document("data/raw/test.md")' in script_text
