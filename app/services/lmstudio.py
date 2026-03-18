"""Isolate LM Studio wiring so `/api/ask` can evolve without touching routing.

Keeping the local model client in its own module makes it easy to swap or
extend later, while the ask service stays focused on retrieval orchestration.
"""

from __future__ import annotations

import json
import re
import socket
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import settings


class LMStudioError(RuntimeError):
    """Raised when the local LM Studio server cannot return a usable answer."""


MAX_COMPLETION_TOKENS = 220
MAX_CORRECTION_RETRIES = 1


def _chat_completions_url() -> str:
    return f"{settings.lm_studio_base_url.rstrip('/')}/chat/completions"


def _question_profiles(question: str) -> set[str]:
    profiles: set[str] = set()

    if "Lookup" in question and "Explain" in question and any(
        token in question for token in ("分别", "各自", "对应")
    ):
        profiles.add("mode_pair_mapping")
    elif "Lookup" in question and "Explain" in question:
        profiles.add("mode_classification")

    if any(token in question for token in ("会不会", "是否", "是不是", "能不能", "可不可以", "会否", "能否", "可否")):
        profiles.add("yes_no")

    asks_quantity = bool(re.search(r"(多少|几[个项次条]|数量|上限|下限)", question))
    asks_condition = any(
        token in question
        for token in ("什么条件", "什么情况下", "在什么条件下", "何种条件", "何时", "什么时候", "触发条件")
    )
    if asks_quantity and asks_condition:
        profiles.add("quantity_and_condition")

    if any(token in question for token in ("表达方式", "如何表达", "怎么表达", "偏向哪种表达", "输出风格")):
        profiles.add("style")

    if "420" in question and any(token in question for token in ("硬切", "字符", "切分", "截断")):
        profiles.add("hard_cut_rule")

    if any(token in question for token in ("外再次", "之外", "范围外", "24 小时外", "超出")) and any(
        token in question for token in ("适用", "仍适用", "还适用")
    ):
        profiles.add("range_outside")

    if "冲突" in question and any(token in question for token in ("怎么做", "如何处理", "应该怎么做", "怎么办")):
        profiles.add("conflict_handling")

    return profiles


def _question_specific_rules(question: str) -> list[str]:
    profiles = _question_profiles(question)
    rules: list[str] = []

    if "mode_pair_mapping" in profiles:
        rules.append("必须同时覆盖 Lookup 和 Explain 两边，优先写成“Lookup …；Explain …”。")

    if "mode_classification" in profiles:
        rules.append("结论第一句必须直接写“属于 Lookup”或“属于 Explain”，不要只回答具体事实值。")

    if "yes_no" in profiles:
        rules.append("结论第一句必须直接写“会”或“不会”；如果材料未明示，只能写“文档未明示”。")

    if "quantity_and_condition" in profiles:
        rules.append("必须同时回答数量和条件两个子问题，不要只回答前半句。")

    if "style" in profiles:
        rules.append("不要把表达方式题答成具体事实值，要直接说明应该怎么表达。")

    if "hard_cut_rule" in profiles:
        rules.append("必须同时说明“优先按段落边界处理”和“只有单段超过 420 字符才允许强制截断”。")

    if "range_outside" in profiles:
        rules.append("如果题目问范围外是否仍适用，先判断文档是否明确覆盖范围外；未明示时不要外推。")

    if "conflict_handling" in profiles:
        rules.append("冲突处理题的结论至少覆盖：保留冲突、提示不一致、禁止强行合并。")

    return rules


def _build_user_prompt(question: str, chunks: list[dict[str, Any]]) -> str:
    sections: list[str] = []
    for chunk in chunks:
        sections.append(
            "\n".join(
                [
                    f"Chunk rank: {chunk['rank']}",
                    f"Source: {chunk['source']}",
                    f"Chunk ID: {chunk['chunk_id']}",
                    "Content:",
                    str(chunk["text"]),
                ]
            )
        )

    context_block = "\n\n---\n\n".join(sections) if sections else "No retrieved context."
    question_specific_rules = _question_specific_rules(question)
    question_specific_block = ""
    if question_specific_rules:
        question_specific_block = "题型补充规则（优先遵守）：\n" + "\n".join(
            f"- {rule}" for rule in question_specific_rules
        ) + "\n\n"

    return (
        f"问题：\n{question}\n\n"
        f"检索上下文：\n{context_block}\n\n"
        "回答规则（必须遵守）：\n"
        "1. 只使用简体中文。\n"
        "2. 只能依据检索上下文回答，不要补常识，不要改写成上下文里没有的新规则。\n"
        "3. 如果材料只明确某个时间范围或条件范围，只能回答已明确的部分，并明确写出未明示的范围。\n"
        "4. 不要把计划版本或拟增加规则写成当前已生效规则；如果问题问当前状态，必须先说当前生效值。\n"
        "5. 数值、阈值、百分比、行数必须逐字复制，不要四舍五入，不要把 0.42 写成 0.4。\n"
        "6. 如果材料出现冲突，不要强行合并成单一结论，也不要凭常识替代来源内容。\n"
        "7. 只有在上下文确实没有答案时，才允许写“根据当前检索结果，信息不足”。\n"
        "8. 不要输出思维链、分析过程、Thinking Process、<think> 标签或额外前言。\n\n"
        f"{question_specific_block}"
        "输出格式（必须严格遵守，只输出下面三行）：\n"
        "结论：<先直接回答问题>\n"
        "依据：<引用上下文中的关键规则、条件或数值>\n"
        "边界：<如果材料已明确，写“当前材料已明确。”；如果材料未覆盖全部范围，写“文档只明确……，未明示……”。>"
    )


def _strip_reasoning_blocks(answer: str) -> str:
    cleaned = answer.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"(?is)<think>.*?</think>", "", cleaned)
    cleaned = re.sub(r"(?im)^thinking process:\s*$", "", cleaned)
    cleaned = re.sub(r"(?im)^analysis:\s*$", "", cleaned)
    return cleaned.strip()


def _insert_section_breaks(answer: str) -> str:
    normalized = answer
    for label in ("结论", "依据", "边界"):
        normalized = re.sub(
            rf"(?<!\n)\s*({label}[:：])",
            r"\n\1",
            normalized,
        )
    return normalized.strip()


def _structured_answer_only(answer: str) -> str:
    structured_answer = _insert_section_breaks(answer)
    lines = [line.strip() for line in structured_answer.splitlines() if line.strip()]
    structured_lines: list[str] = []
    for label in ("结论", "依据", "边界"):
        matched_line = next(
            (
                line
                for line in lines
                if line.startswith(f"{label}：") or line.startswith(f"{label}:")
            ),
            None,
        )
        if matched_line is not None:
            structured_lines.append(matched_line.replace(":", "：", 1))

    if structured_lines:
        return "\n".join(structured_lines)
    return answer.strip()


def _sanitize_answer(answer: str) -> str:
    cleaned = _strip_reasoning_blocks(answer)
    cleaned = _structured_answer_only(cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def _structured_sections(answer: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    for line in answer.splitlines():
        stripped = line.strip()
        for label in ("结论", "依据", "边界"):
            prefix = f"{label}："
            if stripped.startswith(prefix):
                sections[label] = stripped[len(prefix) :].strip()
                break
    return sections


def _collect_numeric_tokens(text: str) -> set[str]:
    raw_tokens = set(re.findall(r"\d+(?:\.\d+)?%?", text))
    section_reference_tokens = {
        match.group(1)
        for match in re.finditer(
            r"(?<!\d)(\d+\.\d+)(?!\d)(?=\s*(?:[\u4e00-\u9fffA-Za-z]{0,8})?(?:规则|策略|模式|约束|流程|定义|标题|要求|结构|目标|错误|示例))",
            text,
        )
    }
    return raw_tokens - section_reference_tokens


def _chunks_text(chunks: list[dict[str, Any]]) -> str:
    return "\n".join(str(chunk.get("text", "")) for chunk in chunks)


def _answer_validation_issues(
    question: str,
    chunks: list[dict[str, Any]],
    answer: str,
) -> list[str]:
    profiles = _question_profiles(question)
    sections = _structured_sections(answer)
    conclusion = sections.get("结论", "").strip()
    combined_text = "\n".join(value for value in sections.values() if value).strip() or answer
    context_text = _chunks_text(chunks)
    issues: list[str] = []

    if "mode_pair_mapping" in profiles:
        if not all(term in combined_text for term in ("Lookup", "Explain")):
            issues.append("题目同时问 Lookup 和 Explain 两边，但答案没有同时覆盖两边。")
        if "检索器" in question and not all(term in combined_text for term in ("K-Search", "V-Search")):
            issues.append("题目问两种模式各自使用哪种检索器，但答案没有完整给出 K-Search 和 V-Search。")

    if "mode_classification" in profiles and not re.search(r"\b(?:Lookup|Explain)\b", conclusion):
        issues.append("题目要求判断 Lookup/Explain，但结论没有直接给出模式。")

    if "yes_no" in profiles:
        allowed_prefixes = (
            "会",
            "不会",
            "能",
            "不能",
            "是",
            "不是",
            "文档未明示",
            "根据当前检索结果，信息不足",
        )
        if not any(conclusion.startswith(prefix) for prefix in allowed_prefixes):
            issues.append("题目是会不会/是否判断题，但结论没有直接给出会/不会或未明示。")
        if conclusion.startswith("会") and "不会" in combined_text:
            issues.append("结论与依据出现“会/不会”冲突。")

    if "quantity_and_condition" in profiles:
        if not re.search(r"\d", combined_text):
            issues.append("题目同时问数量和条件，但答案没有给出明确数量。")
        if not re.search(r"(条件|情况下|当|如果|时|前提|模式|触发|满足)", combined_text):
            issues.append("题目同时问数量和条件，但答案没有说明触发条件。")

    if "style" in profiles and not re.search(r"(表达|直接|先|背景|方式|写法|风格)", combined_text):
        issues.append("题目问表达方式，但答案没有直接说明该怎么表达。")

    if "hard_cut_rule" in profiles:
        if not re.search(r"(段落边界|按段落)", combined_text):
            issues.append("题目问 420 字符硬切规则，但答案没有明确说明优先按段落边界处理。")
        mentions_single_paragraph_limit = bool(re.search(r"(单段|超过\s*420|超出\s*420)", combined_text))
        mentions_forced_cut = bool(re.search(r"(强制截断|强制切分|硬切|截断)", combined_text))
        if not (mentions_single_paragraph_limit and mentions_forced_cut):
            issues.append("题目问 420 字符硬切规则，但答案没有明确说明只有单段超过 420 字符时才允许强制截断。")

    if "range_outside" in profiles and not re.search(r"(未明示|只明确|范围外|范围内|24 小时内)", combined_text):
        issues.append("题目问范围外是否适用，但答案没有明确交代文档是否覆盖范围外。")
    if "range_outside" in profiles and conclusion.startswith(("适用", "会", "仍适用")):
        issues.append("题目问范围外是否适用，但答案把范围内规则直接外推成了范围外结论。")
    if "range_outside" in profiles and conclusion.startswith(("不适用", "不会", "不能")) and re.search(
        r"(未明示|只明确)",
        combined_text,
    ):
        issues.append("题目问范围外是否适用，但答案把未明示场景写成了确定不适用。")
    if "range_outside" in profiles and "未明示" in combined_text and conclusion.startswith(("适用", "会", "仍适用")):
        issues.append("题目问范围外是否适用，但答案一边写适用一边又写未明示，前后矛盾。")

    if "conflict_handling" in profiles:
        if not re.search(r"(冲突|不一致)", combined_text):
            issues.append("题目问冲突处理，但答案没有明确说明冲突或不一致。")
        if "保留" not in combined_text:
            issues.append("题目问冲突处理，但答案没有明确要求保留冲突。")
        if not re.search(r"(结合来源进行确认|请结合来源进行确认)", combined_text):
            issues.append("题目问冲突处理，但答案没有提醒结合来源进行确认。")
        if not re.search(r"(不允许|不能|不得|禁止).{0,8}(合并|替代)", combined_text):
            issues.append("题目问冲突处理，但答案没有明确禁止强行合并或替代来源。")
        if "当前材料存在不一致描述，请结合来源进行确认。" in context_text and "当前材料存在不一致描述，请结合来源进行确认。" not in combined_text:
            issues.append("题目问冲突处理，但答案没有包含文档要求的固定提示语。")

    if any(marker in context_text for marker in ("除非", "例外", "以下内容之一")) and any(
        token in question for token in ("错误码标题", "参数表标题", "特殊告警标题")
    ):
        if conclusion.startswith("会"):
            issues.append("当前题目命中了例外项，但结论仍沿用了默认规则。")
        if not re.search(r"(例外|不会被强制|可以单独|不适用默认)", combined_text):
            issues.append("当前题目命中了例外项，但答案没有明确说明这是例外规则。")

    question_numbers = _collect_numeric_tokens(question)
    missing_question_numbers = sorted(token for token in question_numbers if token not in answer)
    if missing_question_numbers and not re.search(r"(未明示|信息不足)", combined_text):
        issues.append(
            "答案必须保留题目中的关键数字，不要改写成别的数字："
            + "、".join(missing_question_numbers[:3])
        )

    allowed_numbers = _collect_numeric_tokens(question)
    for chunk in chunks:
        allowed_numbers.update(_collect_numeric_tokens(str(chunk.get("text", ""))))
    unexpected_numbers = sorted(
        token for token in _collect_numeric_tokens(answer) if token not in allowed_numbers
    )
    if unexpected_numbers:
        issues.append(
            "答案出现了上下文里没有的数字，请删除或改回证据中的原数字："
            + "、".join(unexpected_numbers[:3])
        )

    return issues


def _extract_answer(payload: dict[str, Any]) -> str:
    choices = payload.get("choices", [])
    if not choices:
        raise LMStudioError("LM Studio returned no choices.")

    first_choice = choices[0]
    message = first_choice.get("message", {})
    answer = _sanitize_answer(str(message.get("content", "")))
    if not answer:
        raise LMStudioError("LM Studio returned an empty answer.")
    return answer


def _request_lm_studio(messages: list[dict[str, str]]) -> str:
    payload = {
        "model": settings.lm_studio_model,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": MAX_COMPLETION_TOKENS,
    }
    request = Request(
        _chat_completions_url(),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=settings.lm_studio_timeout_seconds) as response:
            raw_payload = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise LMStudioError(
            f"LM Studio request failed with status {exc.code}: {detail or exc.reason}"
        ) from exc
    except URLError as exc:
        raise LMStudioError(
            f"LM Studio server is not reachable at {settings.lm_studio_base_url}"
        ) from exc
    except (socket.timeout, TimeoutError) as exc:
        raise LMStudioError(
            f"LM Studio request timed out after {settings.lm_studio_timeout_seconds} seconds."
        ) from exc

    try:
        response_payload = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise LMStudioError("LM Studio returned invalid JSON.") from exc

    return _extract_answer(response_payload)


def _build_retry_prompt(
    question: str,
    chunks: list[dict[str, Any]],
    previous_answer: str,
    issues: list[str],
) -> str:
    issue_block = "\n".join(f"- {issue}" for issue in issues)
    return (
        f"{_build_user_prompt(question, chunks)}\n\n"
        "你上一版答案没有完全满足题型要求。请只重写答案，不要解释修改过程。\n"
        f"上一版答案：\n{previous_answer}\n\n"
        "需要修正的问题：\n"
        f"{issue_block}\n\n"
        "请重新输出且仍然只能输出三行：\n"
        "结论：...\n"
        "依据：...\n"
        "边界：..."
    )


def generate_lm_studio_answer(
    question: str,
    chunks: list[dict[str, Any]],
) -> dict[str, Optional[str]]:
    if not settings.lm_studio_model:
        raise LMStudioError("LM_STUDIO_MODEL is empty.")

    base_messages = [
        {"role": "system", "content": settings.ask_system_prompt},
        {"role": "user", "content": _build_user_prompt(question, chunks)},
    ]
    answer = _request_lm_studio(base_messages)
    issues = _answer_validation_issues(question, chunks, answer)
    answer_note = "Answered by local LM Studio model."

    if issues:
        best_answer = answer
        best_issues = issues
        for _ in range(MAX_CORRECTION_RETRIES):
            retry_answer = _request_lm_studio(
                [
                    {"role": "system", "content": settings.ask_system_prompt},
                    {
                        "role": "user",
                        "content": _build_retry_prompt(question, chunks, best_answer, best_issues),
                    },
                ]
            )
            retry_issues = _answer_validation_issues(question, chunks, retry_answer)
            if len(retry_issues) <= len(best_issues):
                best_answer = retry_answer
                best_issues = retry_issues
            if not best_issues:
                answer_note = "Answered by local LM Studio model after one validation retry."
                break
        answer = best_answer

    return {
        "answer": answer,
        "answer_mode": "lm_studio",
        "answer_status": "generated",
        "answer_note": answer_note,
        "provider": "lm_studio",
        "model": settings.lm_studio_model,
    }
