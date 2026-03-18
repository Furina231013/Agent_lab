"""LM Studio client tests for local model integration edge cases."""

from __future__ import annotations

import json
import socket

import pytest

from app.config import settings
from app.services.lmstudio import (
    LMStudioError,
    _answer_validation_issues,
    _build_user_prompt,
    _sanitize_answer,
    generate_lm_studio_answer,
)


def test_build_user_prompt_adds_scope_and_exactness_guardrails() -> None:
    prompt = _build_user_prompt(
        "v1.0 是否已经把日志类 Source Unit 的单块上限改成了 24 行？",
        [
            {
                "rank": 1,
                "source": "data/raw/test.md",
                "chunk_id": "chunk-1",
                "score": 0.91,
                "text": "下一个计划版本是 v1.0 ，拟将单块上限从 30 行改为 24 行，但当前尚未生效。",
            }
        ],
    )

    assert "不要把计划版本或拟增加规则写成当前已生效规则" in prompt
    assert "数值、阈值、百分比、行数必须逐字复制" in prompt
    assert "如果材料只明确某个时间范围或条件范围" in prompt
    assert "结论：" in prompt
    assert "依据：" in prompt
    assert "边界：" in prompt


def test_build_user_prompt_adds_question_type_specific_hints() -> None:
    mode_prompt = _build_user_prompt(
        "如果用户问“哪个参数是默认值”，这类问题更接近 Lookup 还是 Explain？",
        [
            {
                "rank": 1,
                "source": "data/raw/test.md",
                "chunk_id": "chunk-1",
                "score": 0.91,
                "text": "如果用户问题里出现“默认值”“哪个参数”之类表达，默认归为 Lookup。",
            }
        ],
    )
    yes_no_prompt = _build_user_prompt(
        "如果一个很短的段落是错误码标题，它会不会被强制和下一段合并？",
        [
            {
                "rank": 1,
                "source": "data/raw/test.md",
                "chunk_id": "chunk-2",
                "score": 0.87,
                "text": "错误码标题属于短段合并例外，可以单独作为 Segment。",
            }
        ],
    )
    multi_part_prompt = _build_user_prompt(
        "默认会选取多少个 Evidence Block 进入回答阶段？在什么条件下可以扩展到 4 个？",
        [
            {
                "rank": 1,
                "source": "data/raw/test.md",
                "chunk_id": "chunk-3",
                "score": 0.88,
                "text": "默认数量是 3 个；Explain 模式且前 3 个块分属至少 2 个不同 Source Unit 时，可扩展到 4 个。",
            }
        ],
    )
    style_prompt = _build_user_prompt(
        "Lookup 模式回答“默认切分长度是多少”时，系统应该更偏向哪种表达方式？",
        [
            {
                "rank": 1,
                "source": "data/raw/test.md",
                "chunk_id": "chunk-4",
                "score": 0.89,
                "text": "Lookup 模式下若答案是数值，必须直接写出数值，不要先讲背景。",
            }
        ],
    )
    paired_prompt = _build_user_prompt(
        "Lookup 模式和 Explain 模式分别优先使用哪种一级检索器？",
        [
            {
                "rank": 1,
                "source": "data/raw/test.md",
                "chunk_id": "chunk-5",
                "score": 0.9,
                "text": "Lookup 模式优先执行 K-Search，Explain 模式优先执行 V-Search。",
            }
        ],
    )
    range_prompt = _build_user_prompt(
        "24 小时外再次导入同一文件，还适用那套 5% 差异规则吗？",
        [
            {
                "rank": 1,
                "source": "data/raw/test.md",
                "chunk_id": "chunk-6",
                "score": 0.9,
                "text": "文档只明确 24 小时内重复导入时适用 5% 差异规则。",
            }
        ],
    )
    conflict_prompt = _build_user_prompt(
        "如果多个 Evidence Block 之间出现冲突，系统应该怎么做？",
        [
            {
                "rank": 1,
                "source": "data/raw/test.md",
                "chunk_id": "chunk-7",
                "score": 0.9,
                "text": "系统必须保留冲突，并明确提示材料不一致，不允许强行合并。",
            }
        ],
    )

    assert "结论第一句必须直接写“属于 Lookup”或“属于 Explain”" in mode_prompt
    assert "结论第一句必须直接写“会”或“不会”" in yes_no_prompt
    assert "必须同时回答数量和条件两个子问题" in multi_part_prompt
    assert "不要把表达方式题答成具体事实值" in style_prompt
    assert "必须同时覆盖 Lookup 和 Explain 两边" in paired_prompt
    assert "先判断文档是否明确覆盖范围外" in range_prompt
    assert "至少覆盖：保留冲突、提示不一致、禁止强行合并" in conflict_prompt


def test_sanitize_answer_splits_inline_structured_sections() -> None:
    raw_answer = (
        "结论：F1 类错误依据：错误分类中 F1 定义为“应降级却未降级”"
        "边界：当前材料已明确。"
    )

    assert _sanitize_answer(raw_answer) == (
        "结论：F1 类错误\n"
        "依据：错误分类中 F1 定义为“应降级却未降级”\n"
        "边界：当前材料已明确。"
    )


def test_answer_validation_issues_flags_range_extrapolation_without_section_number_noise() -> None:
    issues = _answer_validation_issues(
        "24 小时外再次导入同一文件，还适用那套 5% 差异规则吗？",
        [
            {
                "rank": 1,
                "source": "data/raw/test.md",
                "chunk_id": "chunk-range",
                "score": 0.9,
                "text": (
                    "如果同一个文件在 24 小时内被重复导入，系统不立即覆盖旧索引，"
                    "而是做一次内容摘要比对：若差异低于 5%，则记录为重复导入。"
                ),
            }
        ],
        (
            "结论：适用。\n"
            "依据：3.3 重复导入规则中明确，如果同一个文件在 24 小时内被重复导入，会按 5% 差异规则判断。\n"
            "边界：当前材料已明确。"
        ),
    )

    assert any("范围外" in issue or "未明示" in issue for issue in issues)
    assert not any("3.3" in issue for issue in issues)


def test_answer_validation_issues_require_fixed_conflict_prompt() -> None:
    issues = _answer_validation_issues(
        "如果多个 Evidence Block 之间出现冲突，系统应该怎么做？",
        [
            {
                "rank": 1,
                "source": "data/raw/test.md",
                "chunk_id": "chunk-conflict",
                "score": 0.9,
                "text": (
                    "系统必须保留冲突，显式说明存在冲突，并加入固定提示语"
                    "“当前材料存在不一致描述，请结合来源进行确认。”，不得强行合并。"
                ),
            }
        ],
        (
            "结论：系统必须保留冲突，并明确告诉用户材料不一致，禁止强行合并或凭常识替代来源内容。\n"
            "依据：如果材料出现冲突，不要强行合并成单一结论，也不要凭常识替代来源内容。\n"
            "边界：当前材料已明确。"
        ),
    )

    assert any("固定提示语" in issue for issue in issues)
    assert not any("禁止强行合并" in issue for issue in issues)


def test_answer_validation_issues_ignore_section_number_for_exception_case() -> None:
    issues = _answer_validation_issues(
        "如果一个很短的段落是错误码标题，它会不会被强制和下一段合并？",
        [
            {
                "rank": 1,
                "source": "data/raw/test.md",
                "chunk_id": "chunk-exception",
                "score": 0.9,
                "text": (
                    "若某一段长度小于 120 字符，系统不应将其单独作为 Segment，"
                    "除非它是以下内容之一：错误码标题。"
                ),
            }
        ],
        (
            "结论：会。\n"
            "依据：4.3 短段合并规则：若某一段长度小于 120 字符，系统不应将其单独作为 Segment，"
            "除非它是以下内容之一：错误码标题。\n"
            "边界：当前材料已明确。"
        ),
    )

    assert any("例外项" in issue for issue in issues)
    assert not any("4.3" in issue for issue in issues)


def test_answer_validation_issues_flags_range_outside_as_not_applicable() -> None:
    issues = _answer_validation_issues(
        "24 小时外再次导入同一文件，还适用那套 5% 差异规则吗？",
        [
            {
                "rank": 1,
                "source": "data/raw/test.md",
                "chunk_id": "chunk-range-negative",
                "score": 0.9,
                "text": "文档只明确 24 小时内重复导入时适用 5% 差异规则，未提及 24 小时外。",
            }
        ],
        (
            "结论：不适用。\n"
            "依据：文档只明确 24 小时内重复导入时适用 5% 差异规则。\n"
            "边界：文档只明确 24 小时内适用，未明示 24 小时外是否适用。"
        ),
    )

    assert any("确定不适用" in issue or "范围外" in issue for issue in issues)


def test_answer_validation_issues_require_hard_cut_rule_completeness() -> None:
    issues = _answer_validation_issues(
        "文档切分时，是不是一律每 420 个字符硬切一次？",
        [
            {
                "rank": 1,
                "source": "data/raw/test.md",
                "chunk_id": "chunk-hard-cut",
                "score": 0.9,
                "text": (
                    "Segment 默认长度为 420 字符，但系统优先按段落边界切分。"
                    "只有单段超过 420 字符时，才允许强制截断。"
                ),
            }
        ],
        (
            "结论：不会。\n"
            "依据：默认切分长度为 420 字符。\n"
            "边界：当前材料已明确。"
        ),
    )

    assert any("段落边界" in issue for issue in issues)
    assert any("超过 420" in issue or "强制截断" in issue for issue in issues)


def test_answer_validation_issues_require_source_confirmation_for_conflicts() -> None:
    issues = _answer_validation_issues(
        "如果多个 Evidence Block 之间出现冲突，系统应该怎么做？",
        [
            {
                "rank": 1,
                "source": "data/raw/test.md",
                "chunk_id": "chunk-conflict-confirm",
                "score": 0.9,
                "text": "冲突时需要保留冲突，并提示用户结合来源进行确认，不得强行合并。",
            }
        ],
        (
            "结论：系统必须保留冲突，并禁止强行合并成单一结论。\n"
            "依据：多个 Evidence Block 冲突时，不要强行合并。\n"
            "边界：当前材料已明确。"
        ),
    )

    assert any("结合来源进行确认" in issue for issue in issues)


def test_generate_lm_studio_answer_strips_thinking_and_uses_strict_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "lm_studio_model", "local-qwen")
    monkeypatch.setattr(settings, "lm_studio_base_url", "http://127.0.0.1:1234/v1")

    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    "<think>先分析版本状态。</think>\n"
                                    "结论：当前生效值仍是 30 行。\n"
                                    "依据：文档只说 v1.0 拟改为 24 行，且该规则尚未生效。\n"
                                    "边界：回答当前状态时，不要把计划版本当成已生效规则。"
                                )
                            }
                        }
                    ]
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout: int):  # type: ignore[no-untyped-def]
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr("app.services.lmstudio.urlopen", fake_urlopen)

    result = generate_lm_studio_answer(
        "v1.0 是否已经把日志类 Source Unit 的单块上限改成了 24 行？",
        [
            {
                "rank": 1,
                "source": "data/raw/test.md",
                "chunk_id": "chunk-1",
                "score": 0.91,
                "text": "下一个计划版本是 v1.0 ，拟将单块上限从 30 行改为 24 行，但当前尚未生效。",
            }
        ],
    )

    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["temperature"] == 0.0
    assert payload["max_tokens"] == 220
    assert result["answer"] == (
        "结论：当前生效值仍是 30 行。\n"
        "依据：文档只说 v1.0 拟改为 24 行，且该规则尚未生效。\n"
        "边界：回答当前状态时，不要把计划版本当成已生效规则。"
    )


def test_generate_lm_studio_answer_retries_when_question_type_is_missed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "lm_studio_model", "local-qwen")
    monkeypatch.setattr(settings, "lm_studio_base_url", "http://127.0.0.1:1234/v1")

    responses = [
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            "结论：默认值是直接写出的数值，不需背景说明。\n"
                            "依据：Lookup 模式下若答案是数值或默认值，必须直接写出数值。\n"
                            "边界：当前材料已明确。"
                        )
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            "结论：属于 Lookup。\n"
                            "依据：如果用户问题里出现“默认值”“哪个参数”之类表达，默认归为 Lookup。\n"
                            "边界：当前材料已明确。"
                        )
                    }
                }
            ]
        },
    ]
    captured_payloads: list[dict[str, object]] = []

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout: int):  # type: ignore[no-untyped-def]
        captured_payloads.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse(responses[len(captured_payloads) - 1])

    monkeypatch.setattr("app.services.lmstudio.urlopen", fake_urlopen)

    result = generate_lm_studio_answer(
        "如果用户问“哪个参数是默认值”，这类问题更接近 Lookup 还是 Explain？",
        [
            {
                "rank": 1,
                "source": "data/raw/test.md",
                "chunk_id": "chunk-1",
                "score": 0.9,
                "text": "如果用户问题里出现“默认值”“哪个参数”之类表达，默认归为 Lookup。",
            }
        ],
    )

    assert len(captured_payloads) == 2
    assert result["answer"] == (
        "结论：属于 Lookup。\n"
        "依据：如果用户问题里出现“默认值”“哪个参数”之类表达，默认归为 Lookup。\n"
        "边界：当前材料已明确。"
    )


def test_generate_lm_studio_answer_retries_when_pair_mapping_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "lm_studio_model", "local-qwen")
    monkeypatch.setattr(settings, "lm_studio_base_url", "http://127.0.0.1:1234/v1")

    responses = [
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            "结论：属于 Lookup，优先使用 K-Search。\n"
                            "依据：Lookup 模式优先执行 K-Search。\n"
                            "边界：当前材料已明确。"
                        )
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            "结论：Lookup 模式优先使用 K-Search；Explain 模式优先使用 V-Search。\n"
                            "依据：一级检索策略明确规定，Lookup 优先 K-Search，Explain 优先 V-Search。\n"
                            "边界：当前材料已明确。"
                        )
                    }
                }
            ]
        },
    ]
    captured_payloads: list[dict[str, object]] = []

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout: int):  # type: ignore[no-untyped-def]
        captured_payloads.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse(responses[len(captured_payloads) - 1])

    monkeypatch.setattr("app.services.lmstudio.urlopen", fake_urlopen)

    result = generate_lm_studio_answer(
        "Lookup 模式和 Explain 模式分别优先使用哪种一级检索器？",
        [
            {
                "rank": 1,
                "source": "data/raw/test.md",
                "chunk_id": "chunk-9",
                "score": 0.9,
                "text": "Lookup 模式优先执行 K-Search，Explain 模式优先执行 V-Search。",
            }
        ],
    )

    assert len(captured_payloads) == 2
    assert result["answer"] == (
        "结论：Lookup 模式优先使用 K-Search；Explain 模式优先使用 V-Search。\n"
        "依据：一级检索策略明确规定，Lookup 优先 K-Search，Explain 优先 V-Search。\n"
        "边界：当前材料已明确。"
    )


def test_generate_lm_studio_answer_retries_when_range_outside_is_overstated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "lm_studio_model", "local-qwen")
    monkeypatch.setattr(settings, "lm_studio_base_url", "http://127.0.0.1:1234/v1")

    responses = [
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            "结论：适用。\n"
                            "依据：3.3 重复导入规则中明确，如果同一个文件在 24 小时内被重复导入，会按 5% 差异规则判断。\n"
                            "边界：当前材料已明确。"
                        )
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            "结论：文档只明确了 24 小时内重复导入时适用 5% 差异规则，24 小时外是否仍适用未明示。\n"
                            "依据：材料明确写的是 24 小时内重复导入才触发该规则，没有把范围延伸到 24 小时外。\n"
                            "边界：文档只明确 24 小时内场景，未明示范围外是否继续适用。"
                        )
                    }
                }
            ]
        },
    ]
    captured_payloads: list[dict[str, object]] = []

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout: int):  # type: ignore[no-untyped-def]
        captured_payloads.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse(responses[len(captured_payloads) - 1])

    monkeypatch.setattr("app.services.lmstudio.urlopen", fake_urlopen)

    result = generate_lm_studio_answer(
        "24 小时外再次导入同一文件，还适用那套 5% 差异规则吗？",
        [
            {
                "rank": 1,
                "source": "data/raw/test.md",
                "chunk_id": "chunk-10",
                "score": 0.9,
                "text": "文档明确写的是 24 小时内重复导入才触发 5% 差异规则。",
            }
        ],
    )

    assert len(captured_payloads) == 2
    assert "24 小时外是否仍适用未明示" in result["answer"]


def test_generate_lm_studio_answer_retries_when_range_outside_is_marked_not_applicable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "lm_studio_model", "local-qwen")
    monkeypatch.setattr(settings, "lm_studio_base_url", "http://127.0.0.1:1234/v1")

    responses = [
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            "结论：不适用。\n"
                            "依据：文档只明确 24 小时内重复导入时适用 5% 差异规则。\n"
                            "边界：文档只明确 24 小时内适用，未明示 24 小时外是否适用。"
                        )
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            "结论：文档未明示 24 小时外是否适用该规则。\n"
                            "依据：材料只明确了 24 小时内重复导入时适用 5% 差异规则，没有写出范围外处理方式。\n"
                            "边界：文档只明确 24 小时内场景，未明示 24 小时外是否适用。"
                        )
                    }
                }
            ]
        },
    ]
    captured_payloads: list[dict[str, object]] = []

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout: int):  # type: ignore[no-untyped-def]
        captured_payloads.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse(responses[len(captured_payloads) - 1])

    monkeypatch.setattr("app.services.lmstudio.urlopen", fake_urlopen)

    result = generate_lm_studio_answer(
        "24 小时外再次导入同一文件，还适用那套 5% 差异规则吗？",
        [
            {
                "rank": 1,
                "source": "data/raw/test.md",
                "chunk_id": "chunk-10b",
                "score": 0.9,
                "text": "文档只明确写了 24 小时内重复导入的处理方式，未写 24 小时外。",
            }
        ],
    )

    assert len(captured_payloads) == 2
    assert result["answer"].startswith("结论：文档未明示 24 小时外是否适用该规则")


def test_generate_lm_studio_answer_retries_when_conflict_fixed_prompt_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "lm_studio_model", "local-qwen")
    monkeypatch.setattr(settings, "lm_studio_base_url", "http://127.0.0.1:1234/v1")

    responses = [
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            "结论：系统必须保留冲突，并明确告诉用户材料不一致，禁止强行合并或凭常识替代来源内容。\n"
                            "依据：如果材料出现冲突，不要强行合并成单一结论，也不要凭常识替代来源内容。\n"
                            "边界：当前材料已明确。"
                        )
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            "结论：系统必须保留冲突，并明确告诉用户材料不一致，禁止强行合并或凭常识替代来源内容。\n"
                            "依据：最终回答还必须加入固定提示语“当前材料存在不一致描述，请结合来源进行确认。”\n"
                            "边界：当前材料已明确。"
                        )
                    }
                }
            ]
        },
    ]
    captured_payloads: list[dict[str, object]] = []

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout: int):  # type: ignore[no-untyped-def]
        captured_payloads.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse(responses[len(captured_payloads) - 1])

    monkeypatch.setattr("app.services.lmstudio.urlopen", fake_urlopen)

    result = generate_lm_studio_answer(
        "如果多个 Evidence Block 之间出现冲突，系统应该怎么做？",
        [
            {
                "rank": 1,
                "source": "data/raw/test.md",
                "chunk_id": "chunk-14",
                "score": 0.9,
                "text": "系统必须保留冲突，显式说明存在冲突，并加入固定提示语“当前材料存在不一致描述，请结合来源进行确认。”，不得强行合并。",
            }
        ],
    )

    assert len(captured_payloads) == 2
    assert "当前材料存在不一致描述，请结合来源进行确认。" in result["answer"]


def test_generate_lm_studio_answer_retries_when_hard_cut_rule_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "lm_studio_model", "local-qwen")
    monkeypatch.setattr(settings, "lm_studio_base_url", "http://127.0.0.1:1234/v1")

    responses = [
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            "结论：不会。\n"
                            "依据：默认切分长度为 420 字符。\n"
                            "边界：当前材料已明确。"
                        )
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            "结论：不会一律每 420 个字符硬切；系统优先按段落边界切分，只有单段超过 420 字符时才允许强制截断。\n"
                            "依据：文档明确写了默认切分长度 420 字符，但优先按段落边界处理，超长单段才允许强制截断。\n"
                            "边界：当前材料已明确。"
                        )
                    }
                }
            ]
        },
    ]
    captured_payloads: list[dict[str, object]] = []

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout: int):  # type: ignore[no-untyped-def]
        captured_payloads.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse(responses[len(captured_payloads) - 1])

    monkeypatch.setattr("app.services.lmstudio.urlopen", fake_urlopen)

    result = generate_lm_studio_answer(
        "文档切分时，是不是一律每 420 个字符硬切一次？",
        [
            {
                "rank": 1,
                "source": "data/raw/test.md",
                "chunk_id": "chunk-hard-cut-retry",
                "score": 0.9,
                "text": "系统优先按段落边界切分，只有单段超过 420 字符时才允许强制截断。",
            }
        ],
    )

    assert len(captured_payloads) == 2
    assert "优先按段落边界切分" in result["answer"]
    assert "只有单段超过 420 字符时才允许强制截断" in result["answer"]


def test_generate_lm_studio_answer_retries_when_exception_rule_is_missed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "lm_studio_model", "local-qwen")
    monkeypatch.setattr(settings, "lm_studio_base_url", "http://127.0.0.1:1234/v1")

    responses = [
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            "结论：会。\n"
                            "依据：长度小于 120 字符的段落通常不单独作为 Segment。\n"
                            "边界：当前材料已明确。"
                        )
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            "结论：不会被强制和下一段合并；错误码标题属于短段合并例外，可以单独作为 Segment。\n"
                            "依据：短段默认会并入下一段，但错误码标题被列为例外项，因此不适用默认合并规则。\n"
                            "边界：当前材料已明确。"
                        )
                    }
                }
            ]
        },
    ]
    captured_payloads: list[dict[str, object]] = []

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout: int):  # type: ignore[no-untyped-def]
        captured_payloads.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse(responses[len(captured_payloads) - 1])

    monkeypatch.setattr("app.services.lmstudio.urlopen", fake_urlopen)

    result = generate_lm_studio_answer(
        "如果一个很短的段落是错误码标题，它会不会被强制和下一段合并？",
        [
            {
                "rank": 1,
                "source": "data/raw/test.md",
                "chunk_id": "chunk-11",
                "score": 0.9,
                "text": "若某一段长度小于 120 字符，通常与下一段合并；但错误码标题属于例外，可以单独作为 Segment。",
            }
        ],
    )

    assert len(captured_payloads) == 2
    assert result["answer"].startswith("结论：不会被强制和下一段合并")


def test_generate_lm_studio_answer_retries_when_question_number_is_replaced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "lm_studio_model", "local-qwen")
    monkeypatch.setattr(settings, "lm_studio_base_url", "http://127.0.0.1:1234/v1")

    responses = [
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            "结论：不会被强制拒绝。\n"
                            "依据：单次导入建议不超过 5 个 Source Unit，超过 5 个会提示建议分批导入，但不强制拒绝。\n"
                            "边界：当前材料已明确。"
                        )
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            "结论：不会被强制拒绝；15 个只是建议上限。\n"
                            "依据：单次导入建议不超过 15 个 Source Unit，若超过 15 个，系统会提示“建议分批导入”，但不强制拒绝。\n"
                            "边界：当前材料已明确。"
                        )
                    }
                }
            ]
        },
    ]
    captured_payloads: list[dict[str, object]] = []

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout: int):  # type: ignore[no-untyped-def]
        captured_payloads.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse(responses[len(captured_payloads) - 1])

    monkeypatch.setattr("app.services.lmstudio.urlopen", fake_urlopen)

    result = generate_lm_studio_answer(
        "单机模式下一次导入超过 15 个 Source Unit，会不会被系统强制拒绝？",
        [
            {
                "rank": 1,
                "source": "data/raw/test.md",
                "chunk_id": "chunk-12",
                "score": 0.9,
                "text": "单次导入建议不超过 15 个 Source Unit。若超过 15 个，系统应提示“建议分批导入”，但不强制拒绝。",
            }
        ],
    )

    assert len(captured_payloads) == 2
    assert "15 个只是建议上限" in result["answer"]


def test_generate_lm_studio_answer_retries_when_conflict_handling_is_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "lm_studio_model", "local-qwen")
    monkeypatch.setattr(settings, "lm_studio_base_url", "http://127.0.0.1:1234/v1")

    responses = [
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            "结论：应提示存在冲突。\n"
                            "依据：多个 Evidence Block 之间可能出现不一致。\n"
                            "边界：当前材料已明确。"
                        )
                    }
                }
            ]
        },
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            "结论：应保留冲突并明确提示材料不一致，不能强行合并为单一结论。\n"
                            "依据：多个 Evidence Block 冲突时，系统必须显式说明存在冲突，并加入固定提示语“当前材料存在不一致描述，请结合来源进行确认。”\n"
                            "边界：当前材料已明确。"
                        )
                    }
                }
            ]
        },
    ]
    captured_payloads: list[dict[str, object]] = []

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(self.payload).encode("utf-8")

    def fake_urlopen(request, timeout: int):  # type: ignore[no-untyped-def]
        captured_payloads.append(json.loads(request.data.decode("utf-8")))
        return FakeResponse(responses[len(captured_payloads) - 1])

    monkeypatch.setattr("app.services.lmstudio.urlopen", fake_urlopen)

    result = generate_lm_studio_answer(
        "如果多个 Evidence Block 之间出现冲突，系统应该怎么做？",
        [
            {
                "rank": 1,
                "source": "data/raw/test.md",
                "chunk_id": "chunk-13",
                "score": 0.9,
                "text": "系统必须保留冲突，显式说明存在冲突，并加入固定提示语“当前材料存在不一致描述，请结合来源进行确认。”，不得强行合并。",
            }
        ],
    )

    assert len(captured_payloads) == 2
    assert "不能强行合并为单一结论" in result["answer"]


def test_generate_lm_studio_answer_wraps_socket_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(*args: object, **kwargs: object) -> object:
        raise socket.timeout("timed out")

    monkeypatch.setattr("app.services.lmstudio.urlopen", fake_urlopen)

    with pytest.raises(LMStudioError, match="timed out"):
        generate_lm_studio_answer(
            "FastAPI",
            [
                {
                    "rank": 1,
                    "source": "demo.md",
                    "chunk_id": "chunk-1",
                    "score": 1,
                    "text": "FastAPI keeps the route layer thin.",
                }
            ],
        )
