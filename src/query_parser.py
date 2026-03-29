import json
import re
from typing import Any


def normalize_value(value: Any) -> str:
    if value is None:
        return "전체"
    text = str(value).strip()
    return text if text else "전체"


def detect_value(question: str, candidates: list[str]) -> str:
    for candidate in candidates:
        if candidate == "전체":
            continue
        if candidate and candidate.lower() in question.lower():
            return candidate
    return "전체"


def infer_intent(question: str) -> str:
    q = question.lower()
    if any(token in q for token in ["기여", "견인", "만든"]):
        return "contribution"
    if any(token in q for token in ["어디서", "경로", "채널", "유통"]):
        return "channel_strength"
    if any(token in q for token in ["비교", "vs", "대비"]):
        return "comparison"
    if any(token in q for token in ["top", "랭킹", "순위"]):
        return "ranking"
    return "summary"


def infer_comparison(question: str) -> str:
    q = question.lower()
    if "전월" in q or "mom" in q:
        return "mom"
    if "누적" in q or "ytd" in q:
        return "ytd"
    if "전년" in q or "yoy" in q:
        return "yoy"
    return "current"


def infer_focus_dimension(question: str) -> str:
    q = question.lower()
    if any(token in q for token in ["경로", "채널", "어디서"]):
        return "market"
    if "타입" in q or "유형" in q:
        return "typea"
    if "sku" in q or "제품" in q or "상품" in q:
        return "item"
    if "제조사" in q or "회사" in q:
        return "manufacturer"
    return "brand"


def parse_question_locally(
    question: str,
    manufacturer_options: list[str],
    brand_options: list[str],
    type_options: list[str],
    market_options: list[str],
    period_options: list[str],
    default_period: str,
    category: str,
) -> dict[str, Any]:
    question = question.strip()
    manufacturer = detect_value(question, manufacturer_options)
    brand = detect_value(question, brand_options)
    typea = detect_value(question, type_options)
    market = detect_value(question, market_options)
    period = detect_value(question, period_options)
    if period == "전체":
        period = default_period

    return {
        "category": category,
        "manufacturer": normalize_value(manufacturer),
        "brand": normalize_value(brand),
        "typea": normalize_value(typea),
        "market": normalize_value(market),
        "period": normalize_value(period),
        "comparison": infer_comparison(question),
        "focus_dimension": infer_focus_dimension(question),
        "intent": infer_intent(question),
        "question": question,
        "parser_mode": "local",
    }


def extract_json_from_text(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    json_text = match.group(0) if match else text
    data = json.loads(json_text)
    if not isinstance(data, dict):
        raise ValueError("Gemini 응답이 JSON object가 아닙니다.")
    return data
