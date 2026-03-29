from typing import Any

from .metrics import format_pct, format_money


def build_summary_context(kpis: dict, top_rows: list[dict[str, Any]], focus_dimension: str, selected_period: str, category: str) -> dict:
    return {
        "category": category,
        "selected_period": selected_period,
        "current_sales": format_money(kpis.get("current_sales")),
        "yoy_growth": format_pct(kpis.get("yoy_growth")),
        "mom_growth": format_pct(kpis.get("mom_growth")),
        "ytd_growth": format_pct(kpis.get("ytd_growth")),
        "market_share": format_pct(kpis.get("share")),
        "contribution": format_money(kpis.get("contribution")),
        "focus_dimension": focus_dimension,
        "top_rows": top_rows,
    }


def template_summary(structured_query: dict, kpis: dict, top_rows: list[dict[str, Any]], category: str) -> str:
    focus_dimension = structured_query.get("focus_dimension", "brand")
    dimension_label = {
        "market": "경로",
        "typea": "타입",
        "brand": "브랜드",
        "manufacturer": "제조사",
        "item": "SKU",
    }.get(focus_dimension, "기준")

    lines = []
    lines.append(
        f"- {structured_query.get('period', '-')} {category} 시장의 현재 매출은 {format_money(kpis.get('current_sales'))}이며, 전년 동기 대비 {format_pct(kpis.get('yoy_growth'))}입니다."
    )
    lines.append(
        f"- 전월 대비 증감률은 {format_pct(kpis.get('mom_growth'))}, 누적 기준 YTD 성장률은 {format_pct(kpis.get('ytd_growth'))}입니다."
    )
    if top_rows:
        top = top_rows[0]
        value = top.get(focus_dimension) or top.get("item") or "-"
        sales = format_money(top.get("current_sales") if "current_sales" in top else top.get("sales_value"))
        lines.append(f"- 현재 조건에서 가장 큰 {dimension_label}은 {value}이며, 매출은 {sales}입니다.")
    else:
        lines.append("- 현재 조건에서 추가로 강조할 상위 항목은 확인되지 않았습니다.")
    return "\n".join(lines)
