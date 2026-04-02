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
)
from src.charts import (
    monthly_sales_chart,
    ytd_sales_chart,
    top_dimension_chart,
    type_growth_chart,
    sku_contribution_chart,
    time_series_chart,
)
from src.insights import external_insights, internal_insights, can_generate_insights

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


def sign_color(val):
    """부호에 따라 색상 반환: 양수 파랑, 음수 빨강, 그 외 검정."""
    try:
        if val is None or (isinstance(val, float) and val != val):
            return "color: black"
        if isinstance(val, str):
            return "color: black"
        if val < 0:
            return "color: red"
        if val > 0:
            return "color: blue"
    except (TypeError, ValueError):
        pass
    return "color: black"


def fmt_signed_amount(value) -> str:
    """부호 포함 금액 포맷."""
    if value is None:
        return "-"
    try:
        if value != value:
            return "-"
    except Exception:
        return "-"
    prefix = "+" if float(value) > 0 else ""
    abs_value = abs(float(value))
    if abs_value >= 100:
        eok = float(value) / 100
        if abs(eok) >= 10:
            return f"{prefix}{eok:,.0f}억원"
        return f"{prefix}{eok:,.1f}억원"
    return f"{prefix}{float(value):,.0f}백만원"


def fmt_signed_pct(value) -> str:
    """부호 포함 퍼센트 포맷."""
    if value is None:
        return "-"
    try:
        if value != value:
            return "-"
    except Exception:
        return "-"
    prefix = "+" if float(value) > 0 else ""
    return f"{prefix}{float(value):,.1f}%"


def fmt_signed_pp(value) -> str:
    """부호 포함 %p 포맷."""
    if value is None:
        return "-"
    try:
        if value != value:
            return "-"
    except Exception:
        return "-"
    prefix = "+" if float(value) > 0 else ""
    return f"{prefix}{float(value):,.1f}%p"


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
    month_periods = get_month_periods_sorted(long_df)

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
            yoy_range = get_yoy_periods_for_range(long_df, selected_range)
            rank_opt_cols[4].caption(f"기간: {month_periods[-1]}")

        elif rank_basis == "올해 누적":
            selected_range = ["YTD"]
            yoy_range = ["YTD YA"] if "YTD YA" in long_df["period_display"].values else []
            rank_opt_cols[4].caption("기간: YTD")

        elif rank_basis == "최근 12개월":
            selected_range = month_periods[-12:] if len(month_periods) >= 12 else month_periods
            yoy_range = get_yoy_periods_for_range(long_df, selected_range)
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
            yoy_range = get_yoy_periods_for_range(long_df, selected_range)
            rank_opt_cols[4].caption(f"선택: {len(selected_range)}개월")

        # 기간 매칭 검증
        period_mismatch = False
        if yoy_range:
            rank_opt_cols[4].caption(f"비교: {yoy_range[0]} ~ {yoy_range[-1]}")
            if rank_basis != "올해 누적" and len(yoy_range) < len(selected_range):
                period_mismatch = True
        elif rank_basis == "올해 누적":
            if "YTD YA" not in long_df["period_display"].values:
                period_mismatch = True
                rank_opt_cols[4].caption("비교: 전년 데이터 없음")
            else:
                rank_opt_cols[4].caption("비교: YTD YA")
        else:
            period_mismatch = True
            rank_opt_cols[4].caption("비교: 전년 데이터 없음")

        rank_df = ranking_table_range(long_df, rank_dimension, selected_range, yoy_range)
    else:
        rank_df = ranking_table(long_df, rank_dimension, selected_period)
        period_mismatch = True

    # 기간 불일치 경고
    if period_mismatch:
        st.warning(
            f"⚠️ 전년 비교 데이터가 부족합니다 "
            f"(현재 {len(selected_range)}개 기간 vs 비교 {len(yoy_range)}개 기간). "
            f"성장률 · 증감액 · 구성비 변동은 정확하지 않을 수 있습니다."
            if 'selected_range' in dir() and yoy_range
            else "⚠️ 전년 비교 데이터가 없어 성장률 · 증감액 · 구성비 변동을 산출할 수 없습니다."
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
        "Contribution": "증감액",
        "Share": share_col_name,
        "Share_chg": share_chg_col_name,
    }
    display_rank_df = display_rank_df.drop(columns=["base_Share"], errors="ignore")
    display_rank_df = display_rank_df.rename(columns=rename_map)

    # 퍼센트 컬럼 × 100
    for col in ["성장률", share_col_name, share_chg_col_name]:
        if col in display_rank_df.columns:
            display_rank_df[col] = display_rank_df[col] * 100

    # 부호 있는 컬럼 포맷
    display_rank_df["현재 매출"] = display_rank_df["현재 매출"].map(format_amount)
    display_rank_df["비교 기준 매출"] = display_rank_df["비교 기준 매출"].map(format_amount)
    if share_col_name in display_rank_df.columns:
        display_rank_df[share_col_name] = display_rank_df[share_col_name].map(
            lambda v: f"{v:,.1f}%" if v == v and v is not None else "-"
        )
    display_rank_df["성장률"] = display_rank_df["성장률"].map(fmt_signed_pct)
    if "증감액" in display_rank_df.columns:
        display_rank_df["증감액"] = display_rank_df["증감액"].map(fmt_signed_amount)
    if share_chg_col_name in display_rank_df.columns:
        display_rank_df[share_chg_col_name] = display_rank_df[share_chg_col_name].map(fmt_signed_pp)

    # 부호 색상 적용 (실제 존재하는 컬럼만 subset으로 제한)
    signed_cols = [col for col in ["성장률", "증감액", share_chg_col_name] if col in display_rank_df.columns]

    def apply_sign_color(val):
        if not isinstance(val, str) or val == "-":
            return "color: black"
        if val.startswith("+"):
            return "color: blue"
        if val.startswith("-") or val.startswith("−"):
            return "color: red"
        return "color: black"

    styled_rank_df = display_rank_df.style.map(
        apply_sign_color, subset=signed_cols
    )

    st.dataframe(
        styled_rank_df,
        use_container_width=True,
        hide_index=True,
    )

with tab2:
    sku_df = sku_detail_table(filtered_df, selected_period, top_n=200)
    display_sku_df = sku_df.copy()

    sku_filter_columns = {"manufacturer": "제조사", "brand": "브랜드", "typea": "타입", "market": "채널"}
    sku_filter_cols = st.columns(len(sku_filter_columns))
    for i, (col_key, col_label) in enumerate(sku_filter_columns.items()):
        if col_key in display_sku_df.columns:
            unique_vals = sorted(display_sku_df[col_key].dropna().astype(str).unique().tolist())
            selected = sku_filter_cols[i].multiselect(col_label, options=unique_vals, key=f"sku_filter_{col_key}")
            if selected:
                display_sku_df = display_sku_df[display_sku_df[col_key].astype(str).isin(selected)]

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
    st.subheader("자동 인사이트")

    if not can_generate_insights(selected_manufacturer, selected_brand):
        st.info(
            "📌 상단의 제조사 · 브랜드 필터를 선택하면 아래 인사이트가 자동으로 생성됩니다 ↑\n\n"
            "- **External**: 시장 대비 성장률, 점유율 변동, 채널별 강약점\n"
            "- **Internal**: 성장/하락 주도 항목, 포트폴리오 구성 변화, MoM 모멘텀\n\n"
            "타입 · 채널 필터를 함께 설정하면 더 세밀한 분석이 가능합니다."
        )
    else:
        me_label_parts = []
        if selected_manufacturer != "전체":
            me_label_parts.append(selected_manufacturer)
        if selected_brand != "전체":
            me_label_parts.append(selected_brand)
        if selected_typea != "전체":
            me_label_parts.append(selected_typea)
        if selected_market != "전체":
            me_label_parts.append(selected_market)
        me_label = " > ".join(me_label_parts)

        market_df = filter_data(long_df, typea=selected_typea, market=selected_market)

        ext_col, int_col = st.columns(2)

        with ext_col:
            st.markdown(f"#### External — 시장 내 위치")
            st.caption(f"{me_label} vs 시장 전체 ({selected_period})")
            ext_items = external_insights(
                me_df=filtered_df,
                market_df=market_df,
                long_df=long_df,
                selected_period=selected_period,
                manufacturer=selected_manufacturer,
                brand=selected_brand,
            )
            for item in ext_items:
                st.markdown(f"- {item}")

        with int_col:
            st.markdown(f"#### Internal — 내부 구조 분석")
            st.caption(f"{me_label} 내부 ({selected_period})")
            int_items = internal_insights(
                me_df=filtered_df,
                long_df=long_df,
                selected_period=selected_period,
                manufacturer=selected_manufacturer,
                brand=selected_brand,
                typea=selected_typea,
                market=selected_market,
            )
            for item in int_items:
                st.markdown(f"- {item}")

st.markdown("---")
st.markdown(
    "<p style='text-align:center; color:#d62828; font-weight:600;'>"
    "powered by WK Marketing Group 2026 for LOMA"
    "</p>",
    unsafe_allow_html=True,
)
