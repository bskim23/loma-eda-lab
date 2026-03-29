import numpy as np
import pandas as pd

from .metrics import get_benchmark_periods, safe_growth, format_money, format_pct, sales_for_period


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def can_generate_insights(manufacturer: str, brand: str) -> bool:
    return manufacturer != "전체" or brand != "전체"


def _determine_free_dimensions(manufacturer: str, brand: str, typea: str, market: str) -> list[str]:
    dims = []
    if manufacturer != "전체" and brand == "전체":
        dims.append("brand")
    if typea == "전체":
        dims.append("typea")
    if market == "전체":
        dims.append("market")
    dims.append("item")
    return dims


def _dim_label(dim: str) -> str:
    return {"manufacturer": "제조사", "brand": "브랜드", "typea": "타입", "market": "채널", "item": "SKU"}.get(dim, dim)


def _fmt_growth(val: float) -> str:
    if pd.isna(val):
        return "-"
    prefix = "+" if val > 0 else ""
    return f"{prefix}{val * 100:.1f}%"


def _fmt_money_signed(val: float) -> str:
    if pd.isna(val):
        return "-"
    prefix = "+" if val > 0 else ""
    abs_v = abs(val)
    if abs_v >= 100:
        eok = val / 100
        if abs(eok) >= 10:
            return f"{prefix}{eok:,.0f}억원"
        return f"{prefix}{eok:,.1f}억원"
    return f"{prefix}{val:,.0f}백만원"


def _growth_table(df: pd.DataFrame, dimension: str, current_period: str, yoy_period: str | None) -> pd.DataFrame:
    current = (
        df[df["period_display"] == current_period]
        .groupby(dimension, dropna=False)["sales_value"]
        .sum()
        .reset_index()
        .rename(columns={"sales_value": "current_sales"})
    )
    if not yoy_period:
        current["base_sales"] = np.nan
        current["growth"] = np.nan
        current["contribution"] = np.nan
        return current

    base = (
        df[df["period_display"] == yoy_period]
        .groupby(dimension, dropna=False)["sales_value"]
        .sum()
        .reset_index()
        .rename(columns={"sales_value": "base_sales"})
    )
    merged = current.merge(base, on=dimension, how="outer").fillna(0)
    merged["growth"] = merged.apply(
        lambda r: np.nan if r["base_sales"] == 0 else (r["current_sales"] - r["base_sales"]) / r["base_sales"],
        axis=1,
    )
    merged["contribution"] = merged["current_sales"] - merged["base_sales"]
    return merged.sort_values("contribution", ascending=False)


# ---------------------------------------------------------------------------
# External insights (시장 내 우리 위치)
# ---------------------------------------------------------------------------

def _insight_my_vs_market(me_df, market_df, period, yoy_period) -> list[str]:
    my_cur = sales_for_period(me_df, period)
    my_base = sales_for_period(me_df, yoy_period) if yoy_period else np.nan
    mkt_cur = sales_for_period(market_df, period)
    mkt_base = sales_for_period(market_df, yoy_period) if yoy_period else np.nan

    my_growth = safe_growth(my_cur, my_base)
    mkt_growth = safe_growth(mkt_cur, mkt_base)

    results = []
    results.append(f"현재 매출: {format_money(my_cur)} (시장 전체: {format_money(mkt_cur)})")

    if pd.isna(my_growth) or pd.isna(mkt_growth):
        results.append("전년 동기 데이터가 없어 시장 대비 성장률을 비교할 수 없습니다.")
        return results

    diff = my_growth - mkt_growth
    if diff > 0.001:
        results.append(
            f"우리 성장률({_fmt_growth(my_growth)})이 시장 평균({_fmt_growth(mkt_growth)})을 "
            f"{_fmt_growth(diff)}p 상회 → 시장 대비 초과 성장"
        )
    elif diff < -0.001:
        results.append(
            f"우리 성장률({_fmt_growth(my_growth)})이 시장 평균({_fmt_growth(mkt_growth)})을 "
            f"{_fmt_growth(abs(diff))}p 하회 → 시장 대비 부진"
        )
    else:
        results.append(f"우리 성장률({_fmt_growth(my_growth)})이 시장 평균({_fmt_growth(mkt_growth)})과 유사합니다.")
    return results


def _insight_share_change(me_df, market_df, period, yoy_period) -> list[str]:
    my_cur = sales_for_period(me_df, period)
    mkt_cur = sales_for_period(market_df, period)
    cur_share = my_cur / mkt_cur if mkt_cur else np.nan

    if pd.isna(cur_share):
        return []

    if not yoy_period:
        return [f"시장 점유율: {format_pct(cur_share)}"]

    my_base = sales_for_period(me_df, yoy_period)
    mkt_base = sales_for_period(market_df, yoy_period)
    base_share = my_base / mkt_base if mkt_base else np.nan

    if pd.isna(base_share):
        return [f"시장 점유율: {format_pct(cur_share)} (전년 비교 불가)"]

    delta = cur_share - base_share
    direction = "상승" if delta > 0 else "하락" if delta < 0 else "유지"
    return [
        f"시장 점유율: {format_pct(base_share)} → {format_pct(cur_share)} "
        f"({'+' if delta > 0 else ''}{delta * 100:.1f}%p {direction})"
    ]


def _insight_competitors(me_df, market_df, period, yoy_period, manufacturer, brand) -> list[str]:
    if not yoy_period:
        return ["전년 데이터 없음으로 경쟁사 분석 불가"]

    comp_dim = "brand" if manufacturer != "전체" else "manufacturer"

    me_values = set()
    if manufacturer != "전체":
        if brand != "전체":
            me_values.add(brand)
        else:
            me_values = set(me_df[comp_dim].dropna().unique())
    else:
        me_values.add(brand)

    comp_df = market_df[~market_df[comp_dim].isin(me_values)]
    if comp_df.empty:
        return ["경쟁사 데이터가 없습니다."]

    table = _growth_table(comp_df, comp_dim, period, yoy_period)
    table = table[table["current_sales"] > 0].head(5)

    if table.empty:
        return []

    growers = table[table["contribution"] > 0].head(3)
    decliners = table.sort_values("contribution").head(3)
    decliners = decliners[decliners["contribution"] < 0]

    results = []
    if not growers.empty:
        parts = [f"{r[comp_dim]}({_fmt_growth(r['growth'])}, {_fmt_money_signed(r['contribution'])})" for _, r in growers.iterrows()]
        results.append(f"성장 경쟁사: {', '.join(parts)}")
    if not decliners.empty:
        parts = [f"{r[comp_dim]}({_fmt_growth(r['growth'])}, {_fmt_money_signed(r['contribution'])})" for _, r in decliners.iterrows()]
        results.append(f"하락 경쟁사: {', '.join(parts)}")
    return results


def _insight_channel_position(me_df, market_df, period, yoy_period) -> list[str]:
    if not yoy_period:
        return []

    channels = market_df["market"].dropna().unique()
    if len(channels) <= 1:
        return []

    rows = []
    for ch in channels:
        ch_market = market_df[market_df["market"] == ch]
        ch_me = me_df[me_df["market"] == ch]
        mkt_cur = sales_for_period(ch_market, period)
        my_cur = sales_for_period(ch_me, period)
        mkt_base = sales_for_period(ch_market, yoy_period)
        my_base = sales_for_period(ch_me, yoy_period)

        share_cur = my_cur / mkt_cur if mkt_cur else np.nan
        share_base = my_base / mkt_base if mkt_base else np.nan
        share_chg = share_cur - share_base if not pd.isna(share_cur) and not pd.isna(share_base) else np.nan

        if not pd.isna(share_cur) and my_cur > 0:
            rows.append({"channel": ch, "share": share_cur, "share_chg": share_chg, "sales": my_cur})

    if not rows:
        return []

    ch_df = pd.DataFrame(rows).sort_values("share_chg", ascending=False)
    strong = ch_df[ch_df["share_chg"] > 0.005].head(3)
    weak = ch_df[ch_df["share_chg"] < -0.005].tail(3).sort_values("share_chg")

    results = []
    if not strong.empty:
        parts = [f"{r['channel']}(점유율 {r['share']*100:.1f}%, {'+' if r['share_chg']>0 else ''}{r['share_chg']*100:.1f}%p)" for _, r in strong.iterrows()]
        results.append(f"강세 채널: {', '.join(parts)}")
    if not weak.empty:
        parts = [f"{r['channel']}(점유율 {r['share']*100:.1f}%, {r['share_chg']*100:.1f}%p)" for _, r in weak.iterrows()]
        results.append(f"약세 채널: {', '.join(parts)}")

    if not results:
        results.append("채널별 점유율 변동이 미미합니다.")

    return results


def external_insights(
    me_df: pd.DataFrame,
    market_df: pd.DataFrame,
    long_df: pd.DataFrame,
    selected_period: str,
    manufacturer: str,
    brand: str,
) -> list[str]:
    benchmarks = get_benchmark_periods(long_df, selected_period)
    yoy_period = benchmarks["yoy"]

    results = []
    results += _insight_my_vs_market(me_df, market_df, selected_period, yoy_period)
    results += _insight_share_change(me_df, market_df, selected_period, yoy_period)
    results += _insight_competitors(me_df, market_df, selected_period, yoy_period, manufacturer, brand)
    results += _insight_channel_position(me_df, market_df, selected_period, yoy_period)

    return results if results else ["현재 조건에서 외부 인사이트를 생성할 수 없습니다."]


# ---------------------------------------------------------------------------
# Internal insights (우리 안에서 무슨 일이)
# ---------------------------------------------------------------------------

def _insight_top_movers(me_df, dimension, period, yoy_period) -> list[str]:
    if not yoy_period:
        return []

    table = _growth_table(me_df, dimension, period, yoy_period)
    label = _dim_label(dimension)

    growers = table[table["contribution"] > 0].head(3)
    decliners = table.sort_values("contribution").head(3)
    decliners = decliners[decliners["contribution"] < 0]

    results = []
    if not growers.empty:
        parts = [f"{r[dimension]}({_fmt_money_signed(r['contribution'])}, {_fmt_growth(r['growth'])})" for _, r in growers.iterrows()]
        results.append(f"성장 주도 {label}: {', '.join(parts)}")
    if not decliners.empty:
        parts = [f"{r[dimension]}({_fmt_money_signed(r['contribution'])}, {_fmt_growth(r['growth'])})" for _, r in decliners.iterrows()]
        results.append(f"하락 주도 {label}: {', '.join(parts)}")
    return results


def _insight_mix_change(me_df, dimension, period, yoy_period, threshold=0.01) -> list[str]:
    if not yoy_period or dimension == "item":
        return []

    cur = (
        me_df[me_df["period_display"] == period]
        .groupby(dimension)["sales_value"].sum()
    )
    base = (
        me_df[me_df["period_display"] == yoy_period]
        .groupby(dimension)["sales_value"].sum()
    )

    cur_share = cur / cur.sum() if cur.sum() else cur
    base_share = base / base.sum() if base.sum() else base

    delta = (cur_share - base_share).dropna()
    significant = delta[delta.abs() >= threshold].sort_values(ascending=False)

    if significant.empty:
        return []

    label = _dim_label(dimension)
    parts = []
    for name, chg in significant.items():
        cur_pct = cur_share.get(name, 0) * 100
        parts.append(f"{name}({cur_pct:.0f}%, {'+' if chg > 0 else ''}{chg * 100:.1f}%p)")
    return [f"{label} 구성 변화: {', '.join(parts[:5])}"]


def _insight_new_exit(me_df, period, yoy_period) -> list[str]:
    if not yoy_period:
        return []

    cur_items = set(
        me_df[me_df["period_display"] == period]["item"].dropna().unique()
    )
    base_items = set(
        me_df[me_df["period_display"] == yoy_period]["item"].dropna().unique()
    )

    new_items = cur_items - base_items
    exit_items = base_items - cur_items

    results = []
    if new_items:
        new_sales = me_df[
            (me_df["period_display"] == period) & (me_df["item"].isin(new_items))
        ]["sales_value"].sum()
        results.append(f"신규 SKU {len(new_items)}개 (매출 합계 {format_money(new_sales)})")
    if exit_items:
        exit_sales = me_df[
            (me_df["period_display"] == yoy_period) & (me_df["item"].isin(exit_items))
        ]["sales_value"].sum()
        results.append(f"퇴출 SKU {len(exit_items)}개 (전년 매출 {format_money(exit_sales)})")
    return results


def _insight_momentum(me_df, period, yoy_period, mom_period) -> list[str]:
    my_cur = sales_for_period(me_df, period)
    my_yoy = sales_for_period(me_df, yoy_period) if yoy_period else np.nan
    my_mom = sales_for_period(me_df, mom_period) if mom_period else np.nan

    yoy_g = safe_growth(my_cur, my_yoy)
    mom_g = safe_growth(my_cur, my_mom)

    if pd.isna(mom_g):
        return []

    mom_text = f"전월 대비 {_fmt_growth(mom_g)}"

    if pd.isna(yoy_g):
        return [f"MoM 추세: {mom_text}"]

    if mom_g > 0.001 and yoy_g > 0.001:
        signal = "성장 가속"
    elif mom_g > 0.001 and yoy_g < -0.001:
        signal = "회복 조짐"
    elif mom_g < -0.001 and yoy_g > 0.001:
        signal = "모멘텀 둔화 주의"
    elif mom_g < -0.001 and yoy_g < -0.001:
        signal = "하락 지속"
    else:
        signal = "보합"

    return [f"MoM 추세: {mom_text} → {signal} (YoY {_fmt_growth(yoy_g)})"]


def internal_insights(
    me_df: pd.DataFrame,
    long_df: pd.DataFrame,
    selected_period: str,
    manufacturer: str,
    brand: str,
    typea: str,
    market: str,
) -> list[str]:
    benchmarks = get_benchmark_periods(long_df, selected_period)
    yoy_period = benchmarks["yoy"]
    mom_period = benchmarks["mom"]

    free_dims = _determine_free_dimensions(manufacturer, brand, typea, market)

    results = []

    # Top movers: 가장 의미 있는 차원 1~2개만
    for dim in free_dims[:2]:
        results += _insight_top_movers(me_df, dim, selected_period, yoy_period)

    # Mix change: item 제외
    for dim in free_dims:
        if dim != "item":
            results += _insight_mix_change(me_df, dim, selected_period, yoy_period)

    # New/Exit SKUs
    results += _insight_new_exit(me_df, selected_period, yoy_period)

    # Momentum
    results += _insight_momentum(me_df, selected_period, yoy_period, mom_period)

    return results if results else ["현재 조건에서 내부 인사이트를 생성할 수 없습니다."]
