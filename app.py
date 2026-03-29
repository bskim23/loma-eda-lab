import streamlit as st

from src.loader import load_excel
from src.transform import transform_raw_to_long, get_period_options
from src.metrics import (
    calculate_kpis,
    filter_data,
    get_filter_options,
    get_month_periods_sorted,
    get_yoy_periods_for_range,
    ranking_table,
    ranking_table_range,
    sku_detail_table,
    format_pct,
    top_rows_for_focus,
)
from src.charts import (
    monthly_sales_chart,
    ytd_sales_chart,
    top_dimension_chart,
    type_growth_chart,
    sku_contribution_chart,
    time_series_chart,
)
from src.query_parser import parse_question_locally
from src.gemini_client import (
    is_gemini_available,
    parse_question_with_gemini,
    summarize_with_gemini,
)
from src.narrative import build_summary_context, template_summary

st.set_page_config(page_title="LOMA EDA", layout="wide")


@st.cache_data(show_spinner=False)
def process_uploaded_file(uploaded_file):
    raw_df, raw_meta = load_excel(uploaded_file)
    long_df, transform_meta = transform_raw_to_long(raw_df, raw_meta["file_name"])
    return raw_df, raw_meta, long_df, transform_meta


def init_filter_state(default_period: str):
    defaults = {
        "selected_manufacturer": "전체",
        "selected_brand": "전체",
        "selected_typea": "전체",
        "selected_market": "전체",
        "selected_period": default_period,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def normalize_filter_state(
    all_manufacturers: list[str],
    brand_options: list[str],
    type_options: list[str],
    market_options: list[str],
    period_options: list[str],
    default_period: str,
):
    if st.session_state.get("selected_manufacturer") not in all_manufacturers:
        st.session_state["selected_manufacturer"] = "전체"

    if st.session_state.get("selected_brand") not in brand_options:
        st.session_state["selected_brand"] = "전체"

    if st.session_state.get("selected_typea") not in type_options:
        st.session_state["selected_typea"] = "전체"

    if st.session_state.get("selected_market") not in market_options:
        st.session_state["selected_market"] = "전체"

    if st.session_state.get("selected_period") not in period_options:
        st.session_state["selected_period"] = default_period


def format_amount(value) -> str:
    if value is None:
        return "-"
    try:
        if value != value:
            return "-"
    except Exception:
        return "-"

    abs_value = abs(float(value))

    if abs_value >= 100:
        eok = float(value) / 100
        if abs(eok) >= 10:
            return f"{eok:,.0f}억원"
        return f"{eok:,.1f}억원"

    return f"{float(value):,.0f}백만원"


def build_precise_facts(kpis: dict, selected_period: str) -> list[str]:
    facts = [
        f"현재 매출 ({selected_period}): {format_amount(kpis.get('current_sales'))}",
        f"전년 동기 대비: {format_pct(kpis.get('yoy_growth'))}",
        f"전월 대비: {format_pct(kpis.get('mom_growth'))}",
        f"YTD 성장률: {format_pct(kpis.get('ytd_growth'))}",
        f"시장 점유율 ({selected_period}): {format_pct(kpis.get('share'))}",
        f"전년동기 대비 기여액: {format_amount(kpis.get('contribution'))}",
    ]
    return facts


def extract_top3_summary_lines(summary_text: str) -> list[str]:
    if not summary_text:
        return ["요약 결과가 없습니다."]

    raw_lines = [line.strip() for line in summary_text.splitlines() if line.strip()]
    cleaned = []

    skip_exact = {
        "핵심 요약",
        "AI 핵심 요약",
        "요약",
    }

    for line in raw_lines:
        stripped = line.strip().lstrip("-•1234567890. ").strip()
        if not stripped:
            continue
        if stripped in skip_exact:
            continue
        cleaned.append(stripped)

    if not cleaned:
        return ["요약 결과가 없습니다."]

    return cleaned[:3]


def assess_question_feasibility(question: str) -> dict:
    q = (question or "").strip()

    unsupported_keywords = [
        "소비자", "심리", "인지", "광고효과", "캠페인 효과", "브랜드 이미지",
        "전망", "예측", "의도", "정성", "설문", "리뷰"
    ]
    partial_keywords = [
        "이유", "원인", "왜", "배경", "문제점", "의미", "해석"
    ]

    if any(k in q for k in unsupported_keywords):
        return {
            "status": "unsupported",
            "message": "이 질문은 현재 업로드된 판매 데이터만으로 직접 답하기 어렵습니다.",
            "possible_scope": [
                "매출 규모 및 증감",
                "제조사/브랜드/타입/경로별 비교",
                "성장·감소 기여 항목",
                "시계열 흐름 확인",
            ],
            "suggestions": [
                "어떤 브랜드가 감소를 주도했는가",
                "어느 경로에서 약세가 컸는가",
                "전년 대비 하락폭이 큰 SKU는 무엇인가",
            ],
        }

    if any(k in q for k in partial_keywords):
        return {
            "status": "partial",
            "message": "이 질문은 데이터상 징후까지는 볼 수 있지만, 원인을 확정적으로 판단하기는 어렵습니다.",
            "possible_scope": [
                "감소/성장 기여 항목",
                "경로별 약세/강세 구간",
                "시계열 변화 확인",
            ],
            "suggestions": [
                "감소를 주도한 브랜드는 무엇인가",
                "어느 경로에서 하락폭이 컸는가",
                "전년 대비 약세 SKU는 무엇인가",
            ],
        }

    return {"status": "supported"}


st.title("Exploratory Data Analysis for LOMA Experiments (1 Hr. Version)")
st.caption(
    "시장 전체를 기본값으로 두고 제조사 · 브랜드 · 타입 · 경로 필터로 내려가며 보는 1단계 MVP입니다. "
    "(탐색적 데이터 분석 도구 개발 예시)"
)

uploaded_file = st.file_uploader("엑셀 파일 업로드", type=["xlsx"])

if uploaded_file is None:
    st.info("먼저 월간 엑셀 파일을 업로드해 주세요.")
    st.stop()

try:
    raw_df, raw_meta, long_df, transform_meta = process_uploaded_file(uploaded_file)
except Exception as e:
    st.error(f"파일 처리 중 오류가 발생했습니다: {e}")
    st.stop()

status_cols = st.columns(7)
status_cols[0].metric("파일명", raw_meta["file_name"])
status_cols[1].metric("카테고리", transform_meta.get("category", "-"))
status_cols[2].metric("시트명", raw_meta["sheet_name"])
status_cols[3].metric("파일크기", f"{raw_meta['file_size_mb']} MB")
status_cols[4].metric("원본 행수", f"{raw_meta['raw_rows']:,}")
status_cols[5].metric("정규화 행수", f"{transform_meta['normalized_rows']:,}")
status_cols[6].metric("최신 월", transform_meta["latest_month_period"] or "-")

period_options = get_period_options(long_df)
if not period_options:
    st.error("인식 가능한 기간 정보가 없습니다.")
    st.stop()

default_period = (
    transform_meta["latest_month_period"]
    if transform_meta["latest_month_period"] in period_options
    else period_options[0]
)

init_filter_state(default_period)

all_manufacturers, all_brands, all_types, all_markets = get_filter_options(long_df)

try:
    secrets_obj = st.secrets
except Exception:
    secrets_obj = None

gemini_ready = is_gemini_available(secrets_obj)

brand_seed_options = get_filter_options(
    long_df,
    manufacturer=st.session_state.get("selected_manufacturer", "전체"),
    brand="전체",
)
brand_options = brand_seed_options[1]

detail_seed_options = get_filter_options(
    long_df,
    manufacturer=st.session_state.get("selected_manufacturer", "전체"),
    brand=st.session_state.get("selected_brand", "전체"),
)
type_options = detail_seed_options[2]
market_options = detail_seed_options[3]

normalize_filter_state(
    all_manufacturers=all_manufacturers,
    brand_options=brand_options,
    type_options=type_options,
    market_options=market_options,
    period_options=period_options,
    default_period=default_period,
)

filter_col1, filter_col2, filter_col3, filter_col4, filter_col5 = st.columns(5)

selected_manufacturer = filter_col1.selectbox(
    "제조사",
    options=all_manufacturers,
    key="selected_manufacturer",
)

manufacturer_options, brand_options, type_options, market_options = get_filter_options(
    long_df,
    manufacturer=selected_manufacturer,
    brand="전체",
)

if st.session_state.get("selected_brand") not in brand_options:
    st.session_state["selected_brand"] = "전체"

selected_brand = filter_col2.selectbox(
    "브랜드",
    options=brand_options,
    key="selected_brand",
)

manufacturer_options, brand_options, type_options, market_options = get_filter_options(
    long_df,
    manufacturer=selected_manufacturer,
    brand=selected_brand,
)

if st.session_state.get("selected_typea") not in type_options:
    st.session_state["selected_typea"] = "전체"

if st.session_state.get("selected_market") not in market_options:
    st.session_state["selected_market"] = "전체"

selected_typea = filter_col3.selectbox(
    "타입",
    options=type_options,
    key="selected_typea",
)

selected_market = filter_col4.selectbox(
    "채널",
    options=market_options,
    key="selected_market",
)

if st.session_state.get("selected_period") not in period_options:
    st.session_state["selected_period"] = default_period

selected_period = filter_col5.selectbox(
    "기준 기간",
    options=period_options,
    key="selected_period",
)

filtered_df = filter_data(
    long_df,
    manufacturer=selected_manufacturer,
    brand=selected_brand,
    typea=selected_typea,
    market=selected_market,
)

st.caption("YoY = 현재월 대비 전년동월 비교 / YTD = 올해 누적 대비 전년 누적 비교")

if filtered_df.empty:
    st.warning("현재 필터 조건에 해당하는 데이터가 없습니다.")
    st.stop()

kpis = calculate_kpis(filtered_df, long_df, selected_period)

current_label = f"현재 매출 ({selected_period})"
yoy_label = f"YoY 성장률 (vs {kpis['yoy_period'] or '-'})"
mom_label = f"MoM 성장률 (vs {kpis['mom_period'] or '-'})"
ytd_label = "YTD 성장률 (올해 누적 vs 전년 누적)"
share_label = f"시장 점유율 ({selected_period})"
contribution_label = f"전년동월 대비 기여액 ({selected_period})"

kpi_cols = st.columns(6)
with kpi_cols[0]:
    st.metric(current_label, format_amount(kpis["current_sales"]))
with kpi_cols[1]:
    st.metric(yoy_label, format_pct(kpis["yoy_growth"]), help="현재 선택 기간과 전년동기 비교")
with kpi_cols[2]:
    st.metric(mom_label, format_pct(kpis["mom_growth"]), help="현재 선택 월과 직전 월 비교")
with kpi_cols[3]:
    st.metric(ytd_label, format_pct(kpis["ytd_growth"]), help="YTD vs YTD YA 비교")
with kpi_cols[4]:
    st.metric(share_label, format_pct(kpis["share"]), help="동일 기준 기간 전체 시장 대비 점유율")
with kpi_cols[5]:
    st.metric(contribution_label, format_amount(kpis["contribution"]), help="현재 기간 매출 - 전년동기 매출")

row0_col1, row0_col2 = st.columns(2)
row0_col1.plotly_chart(time_series_chart(filtered_df), use_container_width=True)
row0_col2.plotly_chart(monthly_sales_chart(filtered_df), use_container_width=True)

row1_col1, row1_col2 = st.columns(2)
row1_col1.plotly_chart(ytd_sales_chart(filtered_df), use_container_width=True)
row1_col2.plotly_chart(
    top_dimension_chart(filtered_df, "brand", selected_period, top_n=10),
    use_container_width=True,
)

row2_col1, row2_col2 = st.columns(2)
row2_col1.plotly_chart(
    top_dimension_chart(filtered_df, "manufacturer", selected_period, top_n=10),
    use_container_width=True,
)
row2_col2.plotly_chart(
    top_dimension_chart(filtered_df, "market", selected_period, top_n=10),
    use_container_width=True,
)

row3_col1, row3_col2 = st.columns(2)
row3_col1.plotly_chart(
    top_dimension_chart(filtered_df, "typea", selected_period, top_n=10),
    use_container_width=True,
)
row3_col2.plotly_chart(type_growth_chart(filtered_df, selected_period), use_container_width=True)

row4_col1, row4_col2 = st.columns(2)
row4_col1.plotly_chart(
    sku_contribution_chart(filtered_df, selected_period, top_n=20),
    use_container_width=True,
)
row4_col2.empty()

tab1, tab2, tab3, tab4 = st.tabs(["랭킹", "SKU 상세", "정규화 데이터", "원본 미리보기"])

with tab1:
    month_periods = get_month_periods_sorted(filtered_df)

    rank_opt_cols = st.columns([1, 1, 1, 1, 1])

    dimension_labels = {"manufacturer": "제조사", "brand": "브랜드", "typea": "타입", "market": "채널"}
    rank_dimension = rank_opt_cols[0].selectbox(
        "랭킹 기준",
        options=list(dimension_labels.keys()),
        format_func=lambda x: dimension_labels[x],
        index=1,
    )

    analysis_basis_options = ["최근 1개월", "올해 누적", "최근 12개월", "기간 직접 선택"]
    rank_basis = rank_opt_cols[1].selectbox(
        "분석 기준",
        options=analysis_basis_options,
        index=0,
        key="rank_analysis_basis",
    )

    if month_periods:
        if rank_basis == "최근 1개월":
            selected_range = [month_periods[-1]]
            yoy_range = get_yoy_periods_for_range(filtered_df, selected_range)
            rank_opt_cols[4].caption(f"기간: {month_periods[-1]}")

        elif rank_basis == "올해 누적":
            selected_range = ["YTD"]
            yoy_range = ["YTD YA"] if "YTD YA" in filtered_df["period_display"].values else []
            rank_opt_cols[4].caption("기간: YTD")

        elif rank_basis == "최근 12개월":
            selected_range = month_periods[-12:] if len(month_periods) >= 12 else month_periods
            yoy_range = get_yoy_periods_for_range(filtered_df, selected_range)
            rank_opt_cols[4].caption(f"기간: {selected_range[0]} ~ {selected_range[-1]} ({len(selected_range)}개월)")

        else:
            rank_start = rank_opt_cols[2].selectbox(
                "시작 기간",
                options=month_periods,
                index=0,
                key="rank_period_start",
            )
            start_idx = month_periods.index(rank_start)
            end_options = month_periods[start_idx:]
            rank_end = rank_opt_cols[3].selectbox(
                "종료 기간",
                options=end_options,
                index=len(end_options) - 1,
                key="rank_period_end",
            )
            end_idx = month_periods.index(rank_end)
            selected_range = month_periods[start_idx : end_idx + 1]
            yoy_range = get_yoy_periods_for_range(filtered_df, selected_range)
            rank_opt_cols[4].caption(f"선택: {len(selected_range)}개월")

        # 기간 매칭 검증
        period_mismatch = False
        if yoy_range:
            rank_opt_cols[4].caption(f"비교: {yoy_range[0]} ~ {yoy_range[-1]}")
            if rank_basis != "올해 누적" and len(yoy_range) < len(selected_range):
                period_mismatch = True
        elif rank_basis == "올해 누적":
            if "YTD YA" not in filtered_df["period_display"].values:
                period_mismatch = True
                rank_opt_cols[4].caption("비교: 전년 데이터 없음")
            else:
                rank_opt_cols[4].caption("비교: YTD YA")
        else:
            period_mismatch = True
            rank_opt_cols[4].caption("비교: 전년 데이터 없음")

        rank_df = ranking_table_range(filtered_df, rank_dimension, selected_range, yoy_range)
    else:
        rank_df = ranking_table(filtered_df, rank_dimension, selected_period)
        period_mismatch = True

    # 기간 불일치 경고
    if period_mismatch:
        st.warning(
            f"⚠️ 전년 비교 데이터가 부족합니다 "
            f"(현재 {len(selected_range)}개 기간 vs 비교 {len(yoy_range)}개 기간). "
            f"성장률 · 기여액 · 구성비 변동은 정확하지 않을 수 있습니다."
            if 'selected_range' in dir() and yoy_range
            else "⚠️ 전년 비교 데이터가 없어 성장률 · 기여액 · 구성비 변동을 산출할 수 없습니다."
        )

    display_rank_df = rank_df.copy()

    # 구성비 레이블: 필터 범위에 따라 동적 표기
    active_filters = []
    if selected_manufacturer != "전체":
        active_filters.append(selected_manufacturer)
    if selected_brand != "전체":
        active_filters.append(selected_brand)
    if selected_typea != "전체":
        active_filters.append(selected_typea)
    if selected_market != "전체":
        active_filters.append(selected_market)

    if active_filters:
        share_label_text = f"구성비 (%, {' > '.join(active_filters)} 내)"
        share_chg_label_text = f"구성비 변동 (%p, {' > '.join(active_filters)} 내)"
    else:
        share_label_text = "시장 점유율 (%)"
        share_chg_label_text = "점유율 변동 (%p)"

    display_dim_label = dimension_labels.get(rank_dimension, "기준")
    share_col_name = "시장 점유율" if not active_filters else "구성비"
    share_chg_col_name = "점유율 변동" if not active_filters else "구성비 변동"

    rename_map = {
        rank_dimension: display_dim_label,
        "current_sales": "현재 매출",
        "base_sales": "비교 기준 매출",
        "YoY": "성장률",
        "Contribution": "기여액",
        "Share": share_col_name,
        "Share_chg": share_chg_col_name,
    }
    display_rank_df = display_rank_df.drop(columns=["base_Share"], errors="ignore")
    display_rank_df = display_rank_df.rename(columns=rename_map)

    for col in ["성장률", share_col_name, share_chg_col_name]:
        if col in display_rank_df.columns:
            display_rank_df[col] = display_rank_df[col] * 100

    st.dataframe(
        display_rank_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "현재 매출": st.column_config.NumberColumn("현재 매출", format="%.0f 백만원"),
            "비교 기준 매출": st.column_config.NumberColumn("비교 기준 매출", format="%.0f 백만원"),
            "성장률": st.column_config.NumberColumn("성장률 (%)", format="%.1f%%"),
            "기여액": st.column_config.NumberColumn("기여액", format="%.0f 백만원"),
            share_col_name: st.column_config.NumberColumn(share_label_text, format="%.1f%%"),
            share_chg_col_name: st.column_config.NumberColumn(share_chg_label_text, format="%+.1f"),
        },
    )

with tab2:
    sku_df = sku_detail_table(filtered_df, selected_period, top_n=200)
    display_sku_df = sku_df.copy()

    rename_map = {
        "item_code": "ITEM CODE",
        "item": "ITEM",
        "manufacturer": "제조사",
        "brand": "브랜드",
        "typea": "타입",
        "market": "채널",
        "current_sales": "현재 매출",
        "yoy_sales": "전년동기 매출",
        "mom_sales": "전월 매출",
        "YoY": "YoY",
        "MoM": "MoM",
    }
    display_sku_df = display_sku_df.rename(columns=rename_map)

    for col in ["YoY", "MoM"]:
        if col in display_sku_df.columns:
            display_sku_df[col] = display_sku_df[col] * 100

    st.dataframe(
        display_sku_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "현재 매출": st.column_config.NumberColumn("현재 매출", format="%.0f 백만원"),
            "전년동기 매출": st.column_config.NumberColumn("전년동기 매출", format="%.0f 백만원"),
            "전월 매출": st.column_config.NumberColumn("전월 매출", format="%.0f 백만원"),
            "YoY": st.column_config.NumberColumn("YoY (%)", format="%.1f%%"),
            "MoM": st.column_config.NumberColumn("MoM (%)", format="%.1f%%"),
        },
    )

with tab3:
    tab3_df = filtered_df.copy()

    filter_columns = {
        "period_display": "기간",
        "manufacturer": "제조사",
        "brand": "브랜드",
        "typea": "타입",
        "market": "채널",
    }

    with st.expander("컬럼 필터", expanded=False):
        tab3_filter_cols = st.columns(len(filter_columns))
        for i, (col_key, col_label) in enumerate(filter_columns.items()):
            if col_key in tab3_df.columns:
                unique_vals = sorted(tab3_df[col_key].dropna().astype(str).unique().tolist())
                selected = tab3_filter_cols[i].multiselect(
                    col_label,
                    options=unique_vals,
                    default=[],
                    key=f"tab3_filter_{col_key}",
                )
                if selected:
                    tab3_df = tab3_df[tab3_df[col_key].astype(str).isin(selected)]

    st.caption(f"{len(tab3_df):,}행 표시 (최대 500행)")
    st.dataframe(tab3_df.head(500), use_container_width=True, hide_index=True)

with tab4:
    st.dataframe(raw_df.head(50), use_container_width=True, hide_index=True)

st.markdown("---")

with st.container(border=True):
    st.subheader("한 걸음 더, 자연어 분석 v3")

    if gemini_ready:
        st.caption("Gemini API가 연결되어 있습니다. 질문 해석과 요약에 Gemini를 사용합니다.")
    else:
        st.caption(
            "Gemini API 키가 없어 로컬 규칙 기반 해석으로 동작합니다. "
            "나중에 Streamlit Secrets 또는 환경변수에 GEMINI_API_KEY를 넣으면 Gemini를 사용할 수 있습니다."
        )

    question = st.text_area(
        "질문 입력",
        value=st.session_state.get("question_text", ""),
        placeholder="예: 롯데웰푸드 관점에서 빼빼로가 어느 경로에서 강한지 분석해줘",
        height=100,
        key="question_text",
    )

    feasibility = assess_question_feasibility(question)

    if question.strip():
        if feasibility["status"] == "unsupported":
            st.warning(feasibility["message"])
            st.markdown("**현재 가능한 분석 범위**")
            for item in feasibility["possible_scope"]:
                st.markdown(f"- {item}")

            st.markdown("**이렇게 바꾸면 분석 가능합니다**")
            for item in feasibility["suggestions"]:
                st.markdown(f"- {item}")

        elif feasibility["status"] == "partial":
            st.info(feasibility["message"])
            st.markdown("**현재 데이터 기준으로는 아래 범위까지 가능합니다**")
            for item in feasibility["possible_scope"]:
                st.markdown(f"- {item}")

    action_cols = st.columns([1, 1, 1, 5])
    analyze_clicked = action_cols[0].button("질문 분석", use_container_width=True)
    apply_clicked = action_cols[1].button("필터에 반영", use_container_width=True)
    reset_clicked = action_cols[2].button("초기화", use_container_width=True)

    if reset_clicked:
        st.session_state.pop("parsed_query", None)
        st.session_state.pop("ai_summary_text", None)
        st.session_state["selected_manufacturer"] = "전체"
        st.session_state["selected_brand"] = "전체"
        st.session_state["selected_typea"] = "전체"
        st.session_state["selected_market"] = "전체"
        st.session_state["selected_period"] = default_period
        st.rerun()

    if analyze_clicked and question.strip() and feasibility["status"] != "unsupported":
        try:
            if gemini_ready:
                parsed_query = parse_question_with_gemini(
                    question=question,
                    category=transform_meta.get("category", "-"),
                    manufacturers=all_manufacturers,
                    brands=all_brands,
                    types=all_types,
                    markets=all_markets,
                    periods=period_options,
                    default_period=default_period,
                    streamlit_secrets=secrets_obj,
                )
            else:
                parsed_query = parse_question_locally(
                    question=question,
                    manufacturer_options=all_manufacturers,
                    brand_options=all_brands,
                    type_options=all_types,
                    market_options=all_markets,
                    period_options=period_options,
                    default_period=default_period,
                    category=transform_meta.get("category", "-"),
                )

            st.session_state["parsed_query"] = parsed_query

        except Exception as e:
            st.error(f"질문 해석 중 오류가 발생했습니다: {e}")

    parsed_query = st.session_state.get("parsed_query")

    if apply_clicked and parsed_query:
        st.session_state["selected_manufacturer"] = parsed_query.get("manufacturer", "전체")
        st.session_state["selected_brand"] = parsed_query.get("brand", "전체")
        st.session_state["selected_typea"] = parsed_query.get("typea", "전체")
        st.session_state["selected_market"] = parsed_query.get("market", "전체")
        st.session_state["selected_period"] = parsed_query.get("period", default_period)
        st.rerun()

    if parsed_query:
        st.markdown("**질문 해석 결과**")
        st.json(parsed_query)

        focus_rows = top_rows_for_focus(
            filtered_df,
            parsed_query.get("focus_dimension", "brand"),
            selected_period,
            top_n=5,
        )
        summary_context = build_summary_context(
            kpis=kpis,
            top_rows=focus_rows,
            focus_dimension=parsed_query.get("focus_dimension", "brand"),
            selected_period=selected_period,
            category=transform_meta.get("category", "-"),
        )

        gemini_error_message = None
        gemini_error_detail = None

        if gemini_ready:
            try:
                summary_text = summarize_with_gemini(
                    question=parsed_query.get("question", question),
                    structured_query=parsed_query,
                    computed_context=summary_context,
                    streamlit_secrets=secrets_obj,
                )
            except Exception as e:
                gemini_error_detail = str(e)

                if "429" in gemini_error_detail or "RESOURCE_EXHAUSTED" in gemini_error_detail:
                    gemini_error_message = "Gemini 사용량 한도에 도달해 템플릿 요약으로 전환했습니다. 잠시 후 다시 시도해 주세요."
                else:
                    gemini_error_message = "Gemini 요약 생성에 실패해 템플릿 요약으로 전환했습니다."

                summary_text = template_summary(parsed_query, kpis, focus_rows, transform_meta.get("category", "-"))
        else:
            summary_text = template_summary(parsed_query, kpis, focus_rows, transform_meta.get("category", "-"))

        if gemini_error_message:
            st.info(gemini_error_message)
            with st.expander("상세 오류 보기"):
                st.code(gemini_error_detail)

        st.markdown("### AI 핵심 요약")
        summary_lines = extract_top3_summary_lines(summary_text)
        for line in summary_lines:
            st.markdown(f"- {line}")

        st.markdown("### 정밀 팩트")
        precise_facts = build_precise_facts(kpis, selected_period)
        for fact in precise_facts:
            st.markdown(f"- {fact}")

st.markdown("---")
st.markdown(
    "<p style='text-align:center; color:#d62828; font-weight:600;'>"
    "powered by WK Marketing Group 2026 for LOMA"
    "</p>",
    unsafe_allow_html=True,
)
