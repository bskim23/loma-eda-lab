import json


def build_parser_prompt(
    question: str,
    category: str,
    manufacturers: list[str],
    brands: list[str],
    types: list[str],
    markets: list[str],
    periods: list[str],
    default_period: str,
) -> str:
    schema = {
        "category": category,
        "manufacturer": "전체 또는 manufacturers 중 하나",
        "brand": "전체 또는 brands 중 하나",
        "typea": "전체 또는 types 중 하나",
        "market": "전체 또는 markets 중 하나",
        "period": f"전체가 아니라 periods 중 하나. 명시 없으면 {default_period}",
        "comparison": "current|yoy|mom|ytd",
        "focus_dimension": "manufacturer|brand|typea|market|item",
        "intent": "summary|ranking|comparison|channel_strength|contribution",
    }

    return f"""
너는 FMCG 판매 데이터 질의를 구조화하는 파서다.
반드시 JSON object 하나만 반환해라.
설명 문장, 마크다운, 코드펜스 금지.

현재 카테고리: {category}
질문: {question}

선택 가능 제조사: {manufacturers[:150]}
선택 가능 브랜드: {brands[:300]}
선택 가능 타입: {types[:150]}
선택 가능 경로: {markets[:150]}
선택 가능 기간: {periods}
기본 기간: {default_period}

규칙:
1) 질문에 없는 항목은 "전체"로 둔다.
2) 비교 기준이 전년/YoY면 comparison="yoy", 전월/MoM이면 "mom", 누적/YTD면 "ytd", 없으면 "current".
3) 어디서/채널/경로는 focus_dimension="market".
4) 타입/유형은 focus_dimension="typea".
5) 브랜드/제품 성과 요약은 보통 focus_dimension="brand" 또는 "item".
6) 기간이 명시되지 않으면 {default_period}.
7) 가능한 값은 반드시 제공된 선택지 중 하나를 사용한다.

반환 스키마 예시:
{json.dumps(schema, ensure_ascii=False, indent=2)}
""".strip()


def build_summary_prompt(question: str, structured_query: dict, computed_context: dict) -> str:
    return f"""
너는 FMCG 시장 데이터 분석 요약 작성자다.
아래 질문과 계산 결과를 바탕으로 한국어로만 답해라.
과장 금지. 데이터가 말하는 범위 안에서만 요약해라.
확정할 수 없는 원인 추정은 "가능성" 수준으로만 표현해라.

질문:
{question}

질의 해석:
{json.dumps(structured_query, ensure_ascii=False, indent=2)}

계산 결과:
{json.dumps(computed_context, ensure_ascii=False, indent=2)}

출력 형식:
- 핵심 요약 3문장
- 시사점 2개
""".strip()
