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
MAX_CORRECTION_RETRIES = 2
YES_NO_TOKENS = ("会不会", "是否", "是不是", "能不能", "可不可以", "会否", "能否", "可否")
LIMITED_SCOPE_PATTERN = re.compile(r"(未明示|只明确|仅明确|只覆盖|仅覆盖|仅在|只在|只适用|仅适用)")
EXCEPTION_PATTERN = re.compile(r"(除非|例外|以下内容之一|仅当|只有)")
EXPLANATION_PATTERN = re.compile(r"(为什么|为何|原因|为什么说|为什么更接近|为什么不能|为什么不应该)")
REFUSAL_PATTERN = re.compile(r"(有没有(?:明确)?(?:说明|解释|规定|写明|给出)|是否(?:明确)?(?:说明|规定|写明|给出))")
UNSPECIFIED_PATTERN = re.compile(r"(未明示|未明确|未说明|没有说明|未规定|未涉及|没有解释|未给出)")
SPECULATION_PATTERN = re.compile(r"(可能|也许|可推断|推断|暗示|猜测|估计|大概|或需|或许|应与上一段|应与前一段)")
UNIQUE_CLAIM_PATTERN = re.compile(r"(唯一|仅此一个|只有这一个)")
DETERMINISTIC_CONCLUSION_PREFIXES = (
    "适用",
    "不适用",
    "会",
    "不会",
    "能",
    "不能",
    "是",
    "不是",
    "应",
    "不应",
    "需要",
    "不需要",
)
DEFAULT_RULE_PREFIXES = ("适用", "会", "应", "需要", "默认会", "默认应")


def _chat_completions_url() -> str:
    return f"{settings.lm_studio_base_url.rstrip('/')}/chat/completions"


def _normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _unique_terms(items: list[str]) -> list[str]:
    unique: list[str] = []
    for item in items:
        normalized = item.strip()
        if normalized and normalized not in unique:
            unique.append(normalized)
    return unique


def _extract_choice_terms(question: str) -> list[str]:
    choice_terms: list[str] = []
    if "Lookup" in question and "Explain" in question:
        choice_terms.extend(["Lookup", "Explain"])

    pair_pattern = re.compile(
        r"([A-Za-z][A-Za-z0-9_-]{1,30}|[\u4e00-\u9fff]{2,12})\s*(?:还是|或|或者)\s*([A-Za-z][A-Za-z0-9_-]{1,30}|[\u4e00-\u9fff]{2,12})"
    )
    for match in pair_pattern.finditer(question):
        choice_terms.extend([match.group(1), match.group(2)])

    return _unique_terms(choice_terms)


def _extract_contrast_terms(question: str) -> list[str]:
    contrast_terms: list[str] = []
    for match in re.finditer(r"(跨[\u4e00-\u9fffA-Za-z0-9]{1,8}|\d+\s*[\u4e00-\u9fff]{0,4}(?:外|之外|以外)|范围外)", question):
        contrast_terms.append(match.group(1))
    return _unique_terms(contrast_terms)


def _extract_domain_focus_terms(question: str) -> list[str]:
    focus_terms: list[str] = []
    pattern = re.compile(
        r"([\u4e00-\u9fffA-Za-z0-9 _-]{2,24}(?:标题|模式|规则|条件|日志|流程|默认值|候选事实|Source Unit|Evidence Block|Segment))"
    )
    for match in pattern.finditer(question):
        term = match.group(1).strip()
        if term:
            focus_terms.append(term)
    return _unique_terms(focus_terms)


def _extract_ordered_clauses(text: str) -> list[str]:
    normalized_text = text.replace("\n", "")
    clauses: list[str] = []
    for marker in ("先", "再", "然后", "最后"):
        for match in re.finditer(rf"{marker}([^。；！？\n]{{2,40}})", normalized_text):
            clause = match.group(1).strip("：:，, ")
            clause = re.sub(r"^(如果|若仍超限|仍超限|超限时|需要|会|则)", "", clause).strip("：:，, ")
            if clause:
                clauses.append(_normalize_for_match(clause))
    return _unique_terms(clauses)


def _extract_prohibition_clauses(text: str) -> list[str]:
    normalized_text = text.replace("\n", "")
    clauses: list[str] = []
    for match in re.finditer(r"(?:不允许|不能|不得)([^。；！？\n]{2,30})", normalized_text):
        clause = match.group(1).strip("：:，, ")
        if clause:
            clauses.append(_normalize_for_match(clause))
    return _unique_terms(clauses)


def _extract_fixed_notice_phrases(text: str) -> list[str]:
    notices: list[str] = []
    for match in re.finditer(r"[“\"]([^”\"]{6,40})[”\"]", text):
        phrase = match.group(1).strip()
        if any(token in phrase for token in ("来源", "确认", "材料")):
            notices.append(phrase)
    return _unique_terms(notices)


def _context_has_limited_scope(text: str) -> bool:
    return bool(
        re.search(r"(只明确|仅明确|仅在|只在|仅适用|只适用|\d+\s*[\u4e00-\u9fff]{0,4}内|同一分钟)", text)
    )


def _has_unspecified_language(text: str) -> bool:
    return bool(UNSPECIFIED_PATTERN.search(text))


def _has_speculation_language(text: str) -> bool:
    return bool(SPECULATION_PATTERN.search(text))


def _has_limited_scope_language(text: str) -> bool:
    return bool(LIMITED_SCOPE_PATTERN.search(text))


def _has_exception_language(text: str) -> bool:
    return bool(EXCEPTION_PATTERN.search(text))


def _mentions_scope_guardrail(text: str) -> bool:
    return bool(re.search(r"(未明示|只明确|仅明确|只覆盖|仅覆盖|仅在|只在)", text))


def _mentions_exception_guardrail(text: str) -> bool:
    return bool(
        re.search(r"(除非|例外|仅当|只有|不适用默认|不按默认|不强制|可以单独|单独保留)", text)
    )


def _conclusion_is_deterministic(conclusion: str) -> bool:
    return conclusion.startswith(DETERMINISTIC_CONCLUSION_PREFIXES)


def _conclusion_uses_default_direction(conclusion: str) -> bool:
    return conclusion.startswith(DEFAULT_RULE_PREFIXES)


def _extract_scope_pairs(question: str) -> list[tuple[str, list[str]]]:
    pairs: list[tuple[str, list[str]]] = []
    for match in re.finditer(r"(\d+\s*[\u4e00-\u9fff]{0,4})\s*(?:外|之外|以外)", question):
        base_term = re.sub(r"\s+", "", match.group(1))
        outside_term = re.sub(r"\s+", "", match.group(0))
        pairs.append((outside_term, [f"{base_term}内"]))

    for match in re.finditer(r"跨([\u4e00-\u9fffA-Za-z0-9]{1,10})", question):
        term = match.group(1)
        outside_term = f"跨{term}"
        pairs.append((outside_term, [f"同{term}", f"同一{term}"]))

    for match in re.finditer(r"不同\s*([A-Za-z][A-Za-z0-9 _-]{1,20}|[\u4e00-\u9fffA-Za-z0-9]{2,20})", question):
        term = match.group(1).strip()
        outside_term = _normalize_for_match(match.group(0))
        pairs.append((outside_term, [f"同一{term}", f"同{term}"]))

    return pairs


def _extract_exception_items(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("*"):
            item = stripped.lstrip("*").strip()
            if item:
                items.append(item)

    if items:
        return _unique_terms(items)

    for match in re.finditer(r"(?:以下内容之一|包括|如下)[:：]([^。！？\n]+)", text):
        raw_items = re.split(r"[、，,；;]|和|或", match.group(1))
        for raw_item in raw_items:
            item = raw_item.strip("“”\"' \t")
            if len(item) >= 2:
                items.append(item)
    return _unique_terms(items)


def _extract_decimal_values(text: str) -> list[float]:
    values: list[float] = []
    for token in re.findall(r"\d+\.\d+", text):
        try:
            values.append(float(token))
        except ValueError:
            continue
    return values


def _extract_threshold_rules(text: str) -> list[tuple[str, float]]:
    rules: list[tuple[str, float]] = []
    for pattern, operator in (
        (r"(?:低于|小于|不足)\s*(\d+\.\d+)", "lt"),
        (r"(?:高于|大于|超过)\s*(\d+\.\d+)", "gt"),
    ):
        for match in re.finditer(pattern, text):
            try:
                rules.append((operator, float(match.group(1))))
            except ValueError:
                continue
    return rules


def _question_profiles(question: str) -> set[str]:
    profiles: set[str] = set()
    choice_terms = _extract_choice_terms(question)

    if len(choice_terms) >= 2 and any(token in question for token in ("分别", "各自", "对应")):
        profiles.add("paired_mapping")
    elif len(choice_terms) >= 2 and any(
        token in question for token in ("属于", "哪种", "哪个", "更接近", "归为", "模式", "分类", "Query Mode")
    ):
        profiles.add("classification")
    elif any(token in question for token in ("Query Mode", "模式", "类型", "类别")) and any(
        token in question for token in ("属于", "哪种", "哪个", "更接近", "归为")
    ):
        profiles.add("classification")

    if any(token in question for token in YES_NO_TOKENS):
        profiles.add("binary_decision")

    asks_quantity = bool(re.search(r"(多少|几[个项次条]|数量|上限|下限)", question))
    asks_condition = any(
        token in question
        for token in ("什么条件", "什么情况下", "在什么条件下", "何种条件", "何时", "什么时候", "触发条件")
    )
    if asks_quantity and asks_condition:
        profiles.add("value_with_condition")

    asks_sequence = any(token in question for token in ("顺序", "步骤", "流程", "怎么处理", "如何处理", "超限"))
    if asks_quantity and asks_sequence:
        profiles.add("value_with_sequence")

    if any(token in question for token in ("表达方式", "如何表达", "怎么表达", "偏向哪种表达", "输出风格")):
        profiles.add("style")

    if _extract_contrast_terms(question) and any(token in question for token in ("适用", "优先", "合并", "仍", "还")):
        profiles.add("scope_boundary")

    if "冲突" in question and any(token in question for token in ("怎么做", "如何处理", "应该怎么做", "怎么办")):
        profiles.add("conflict_resolution")

    if any(token in question for token in YES_NO_TOKENS) and any(
        token in question for token in ("切分", "截断", "合并", "适用", "保留")
    ):
        profiles.add("rule_judgement")

    if EXPLANATION_PATTERN.search(question):
        profiles.add("explanation_reason")

    if "降级" in question:
        profiles.add("degradation")

    if REFUSAL_PATTERN.search(question):
        profiles.add("refusal_check")

    return profiles


def _question_specific_rules(question: str) -> list[str]:
    profiles = _question_profiles(question)
    rules: list[str] = []

    if "paired_mapping" in profiles:
        rules.append("如果问题同时给了多个选项，必须把各选项分别写清楚，不要只答一边。")

    if "classification" in profiles:
        rules.append("如果问题在问分类或模式，结论第一句先直接给出所属类别，再补一句理由。")

    if "binary_decision" in profiles:
        rules.append("结论第一句必须直接写“会”或“不会”；如果材料未明示，只能写“文档未明示”。")

    if "value_with_condition" in profiles:
        rules.append("必须同时回答数量和条件两个子问题，不要只回答前半句。")

    if "value_with_sequence" in profiles:
        rules.append("必须同时回答数值和处理顺序，不要漏掉关键步骤或限制条件。")

    if "style" in profiles:
        rules.append("不要把表达方式题答成具体事实值，要直接说明应该怎么表达。")

    if "scope_boundary" in profiles:
        rules.append("如果问题在问范围外或对比条件，先说文档明确覆盖了什么；未明示时不要外推。")

    if "conflict_resolution" in profiles:
        rules.append("如果证据存在冲突，答案至少要覆盖：保留冲突、提示来源不一致、不要强行合并。")

    if "rule_judgement" in profiles:
        rules.append("对规则判断题，要同时说明结论、触发条件和例外/边界，不要只给一句是或不是。")

    if "explanation_reason" in profiles:
        rules.append("如果题目在问为什么或一般原则，不要只给一个具体事实值或单个例子，要直接说明原因。")

    if "degradation" in profiles:
        rules.append("如果题目涉及降级，先判断阈值或触发条件是否成立，再回答降级后的行为或标记方式。")

    if "refusal_check" in profiles:
        rules.append("如果文档未明确说明某件事，就停在“文档未明示”，不要再补猜测或外推。")

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
    choice_terms = _extract_choice_terms(question)
    contrast_terms = [_normalize_for_match(term) for term in _extract_contrast_terms(question)]
    sections = _structured_sections(answer)
    conclusion = sections.get("结论", "").strip()
    basis = sections.get("依据", "").strip()
    boundary = sections.get("边界", "").strip()
    reasoning_text = "\n".join(part for part in (basis, boundary) if part)
    combined_text = "\n".join(value for value in sections.values() if value).strip() or answer
    normalized_combined_text = _normalize_for_match(combined_text)
    context_text = _chunks_text(chunks)
    normalized_context_text = _normalize_for_match(context_text)
    scope_pairs = _extract_scope_pairs(question)
    issues: list[str] = []

    if "paired_mapping" in profiles and choice_terms:
        missing_choices = [term for term in choice_terms if term not in combined_text]
        if missing_choices:
            issues.append("题目同时问多个选项，但答案没有完整覆盖这些选项：" + "、".join(missing_choices[:3]))

    if "classification" in profiles:
        if choice_terms and not any(term in conclusion for term in choice_terms):
            issues.append("题目要求判断所属类别，但结论没有直接给出分类选项。")
        elif not choice_terms and not re.search(r"(属于|归为|模式|类型|类别|Lookup|Explain)", conclusion):
            issues.append("题目要求判断所属类别，但结论没有直接给出分类结论。")

    if "binary_decision" in profiles:
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

    if "value_with_condition" in profiles:
        if not re.search(r"\d", combined_text):
            issues.append("题目同时问数量和条件，但答案没有给出明确数量。")
        if not re.search(r"(条件|情况下|当|如果|时|前提|模式|触发|满足)", combined_text):
            issues.append("题目同时问数量和条件，但答案没有说明触发条件。")

    if "value_with_sequence" in profiles:
        if not re.search(r"\d", combined_text):
            issues.append("题目同时问数值和处理顺序，但答案没有给出明确数值。")
        ordered_clauses = _extract_ordered_clauses(context_text)
        for clause in ordered_clauses[:3]:
            if clause and clause not in normalized_combined_text:
                issues.append(f"题目问处理顺序，但答案漏掉了关键步骤：{clause}")
        prohibition_clauses = _extract_prohibition_clauses(context_text)
        for clause in prohibition_clauses[:2]:
            if clause and clause not in normalized_combined_text:
                issues.append(f"题目问处理边界，但答案漏掉了关键限制：{clause}")

    if "style" in profiles and not re.search(r"(表达|直接|先|背景|方式|写法|风格)", combined_text):
        issues.append("题目问表达方式，但答案没有直接说明该怎么表达。")

    if "explanation_reason" in profiles:
        explanation_signals = re.search(
            r"(因为|原因|因此|所以|更接近|更适合|属于|适合|用于|需要|子问题|条件|变化)",
            combined_text,
        )
        if not explanation_signals:
            issues.append("题目在问为什么或一般原则，但答案没有直接给出解释原因。")
        if re.search(r"\d", conclusion) and not explanation_signals:
            issues.append("题目在问为什么或一般原则，答案不能只给具体事实值或单个例子。")
        if "为什么不能只" in question and not re.search(r"(条件|变化|子问题|不只|还要|同时)", combined_text):
            issues.append("题目在解释为什么不能只给一个值，但答案没有说明还需要覆盖哪些附加条件。")

    if "scope_boundary" in profiles and contrast_terms:
        if not any(term in normalized_combined_text for term in contrast_terms):
            issues.append("题目在问对比条件或范围边界，但答案没有明确点出题目里的对比范围。")
        if _context_has_limited_scope(context_text) and not _mentions_scope_guardrail(combined_text):
            issues.append("题目在问范围外或对比条件，但答案没有明确说明文档只覆盖了已知范围。")
        if _context_has_limited_scope(context_text) and not any(term in normalized_context_text for term in contrast_terms):
            if _conclusion_is_deterministic(conclusion) and "未明示" not in combined_text:
                issues.append("上下文只覆盖了原始范围，答案却把范围外场景写成确定结论；这里应明确写未明示。")
        if "未明示" in combined_text and _conclusion_is_deterministic(conclusion):
            issues.append("答案一边写未明示，一边又给出确定结论，边界和结论冲突。")

    if scope_pairs and any(token in question for token in YES_NO_TOKENS):
        for _, inner_terms in scope_pairs:
            if any(_normalize_for_match(term) in normalized_context_text for term in inner_terms):
                if (
                    "未明示" in combined_text
                    and re.search(r"(优先|去重|合并|只保留|视为)", context_text)
                ):
                    issues.append("上下文已经把规则限定在已知优先条件内，答案不应只停在“未明示”；应明确说明题目里的范围不属于当前优先条件。")
                    break

    if _has_limited_scope_language(reasoning_text):
        if _conclusion_is_deterministic(conclusion) and not _mentions_scope_guardrail(conclusion):
            issues.append("依据或边界已经说明规则只覆盖部分范围，结论不能继续给出范围外的确定判断。")

    if "conflict_resolution" in profiles:
        if not re.search(r"(冲突|不一致)", combined_text):
            issues.append("题目问冲突处理，但答案没有明确说明冲突或不一致。")
        if not re.search(r"(保留.{0,6}冲突|冲突.{0,6}保留)", combined_text):
            issues.append("题目问冲突处理，但答案没有明确要求保留冲突。")
        if not re.search(r"(结合来源进行确认|请结合来源进行确认)", combined_text):
            issues.append("题目问冲突处理，但答案没有提醒结合来源进行确认。")
        if not re.search(r"(不允许|不能|不得|禁止|不要).{0,12}(合并|替代)", combined_text):
            issues.append("题目问冲突处理，但答案没有明确禁止强行合并或替代来源。")
        fixed_notices = _extract_fixed_notice_phrases(context_text)
        if fixed_notices and not any(notice in combined_text for notice in fixed_notices):
            issues.append("题目问冲突处理，但答案没有带出上下文中的固定提示语。")

    if "rule_judgement" in profiles:
        if _has_exception_language(context_text):
            if not _mentions_exception_guardrail(combined_text):
                issues.append("上下文包含例外或限定条件，但答案没有把例外或限定条件说清楚。")
            elif _conclusion_uses_default_direction(conclusion) and not _mentions_exception_guardrail(conclusion):
                issues.append("依据已经承认存在例外或限定条件，结论不能继续沿用默认规则的方向。")
        if re.search(r"(只有|除非|优先|不强制|例外)", context_text) and not re.search(
            r"(只有|除非|优先|不强制|例外|限定|边界|段落边界)",
            combined_text,
        ):
            issues.append("题目在问规则判断，但答案没有把触发条件或例外边界一起说清楚。")

    if "degradation" in profiles:
        question_values = _extract_decimal_values(question)
        for operator, threshold in _extract_threshold_rules(context_text):
            for value in question_values:
                if operator == "lt" and value < threshold and conclusion.startswith(("不会", "不能", "不应")):
                    issues.append(f"上下文说明低于 {threshold:.2f} 会触发降级，题目里的 {value:.2f} 已满足该阈值，结论方向错误。")
                    break
                if operator == "gt" and value > threshold and conclusion.startswith(("不会", "不能", "不应")):
                    issues.append(f"上下文说明高于 {threshold:.2f} 会触发降级，题目里的 {value:.2f} 已满足该阈值，结论方向错误。")
                    break
        if re.search(r"(候选事实|标记)", question):
            if "候选事实" in context_text and "候选事实" not in combined_text:
                issues.append("题目在问降级后是否还能给候选事实，但答案没有明确回答候选事实这一点。")
            if "未确认" in context_text and "未确认" not in combined_text:
                issues.append("题目在问降级后的标记方式，但答案没有保留“未确认”标记。")
            if re.search(r"(仍然必须给出|仍可给出|仍然可以给出)", context_text) and conclusion.startswith(("不会", "不能", "不可以")):
                issues.append("上下文明确允许降级后仍给候选事实，结论不能直接答成不会。")

    if len(_extract_exception_items(context_text)) >= 2 and UNIQUE_CLAIM_PATTERN.search(combined_text):
        issues.append("上下文列出了多个并列项，答案不能把其中一项说成唯一例外。")

    if ("refusal_check" in profiles or _has_unspecified_language(combined_text)) and _has_speculation_language(combined_text):
        issues.append("答案已经说明文档未明示，但后面又加入猜测或推断；未明示场景必须停在未说明。")

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
        "你上一版答案没有完全满足题型要求。请只补齐缺失点并重写最终答案，不要解释修改过程，不要复述规则。\n"
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
