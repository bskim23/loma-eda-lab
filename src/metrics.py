import numpy as np
import pandas as pd


def filter_data(df: pd.DataFrame, manufacturer="전체", brand="전체", typea="전체", market="전체") -> pd.DataFrame:
    out = df.copy()
    if manufacturer != "전체":
        out = out[out["manufacturer"] == manufacturer]
    if brand != "전체":
        out = out[out["brand"] == brand]
    if typea != "전체":
        out = out[out["typea"] == typea]
    if market != "전체":
        out = out[out["market"] == market]
    return out


def get_filter_options(df: pd.DataFrame, manufacturer="전체", brand="전체"):
    manufacturer_options = ["전체"] + sorted(df["manufacturer"].dropna().astype(str).unique().tolist())

    brand_df = df if manufacturer == "전체" else df[df["manufacturer"] == manufacturer]
    brand_options = ["전체"] + sorted(brand_df["brand"].dropna().astype(str).unique().tolist())

    type_df = brand_df if brand == "전체" else brand_df[brand_df["brand"] == brand]
    type_options = ["전체"] + sorted(type_df["typea"].dropna().astype(str).unique().tolist())

    market_options = ["전체"] + sorted(type_df["market"].dropna().astype(str).unique().tolist())

    return manufacturer_options, brand_options, type_options, market_options


def get_period_end_date(df: pd.DataFrame, period_display: str):
    subset = df[df["period_display"] == period_display]
    if subset.empty:
        return pd.NaT
    return subset["period_end_date"].dropna().iloc[0] if subset["period_end_date"].notna().any() else pd.NaT


def get_benchmark_periods(df: pd.DataFrame, selected_period: str):
    subset = df[df["period_display"] == selected_period]
    if subset.empty:
        return {"yoy": None, "mom": None}

    period_type = subset["period_type"].iloc[0]
    end_date = get_period_end_date(df, selected_period)

    if period_type == "month":
        month_periods = (
            df.loc[df["period_type"] == "month", ["period_display", "period_end_date"]]
            .drop_duplicates()
            .sort_values("period_end_date")
        )

        prev_month = month_periods[month_periods["period_end_date"] < end_date].tail(1)
        yoy_month = month_periods[
            (month_periods["period_end_date"] < end_date)
            & ((month_periods["period_end_date"] - (end_date - pd.Timedelta(days=365))).abs().dt.days <= 60)
        ].tail(1)

        return {
            "yoy": yoy_month["period_display"].iloc[0] if not yoy_month.empty else None,
            "mom": prev_month["period_display"].iloc[0] if not prev_month.empty else None,
        }

    if period_type == "ytd":
        return {"yoy": "YTD YA" if "YTD YA" in df["period_display"].values else None, "mom": None}

    if period_type == "ytd_ya":
        return {"yoy": "YTD 2YA" if "YTD 2YA" in df["period_display"].values else None, "mom": None}

    return {"yoy": None, "mom": None}


def sales_for_period(df: pd.DataFrame, period_display: str | None) -> float:
    if not period_display:
        return np.nan
    return float(df.loc[df["period_display"] == period_display, "sales_value"].sum())


def safe_growth(current: float, base: float) -> float:
    if pd.isna(base) or base == 0:
        return np.nan
    return (current - base) / base


def calculate_kpis(scope_df: pd.DataFrame, full_df: pd.DataFrame, selected_period: str) -> dict:
    benchmarks = get_benchmark_periods(full_df, selected_period)
    current_sales = sales_for_period(scope_df, selected_period)
    yoy_sales = sales_for_period(scope_df, benchmarks["yoy"])
    mom_sales = sales_for_period(scope_df, benchmarks["mom"])

    ytd_sales = sales_for_period(scope_df, "YTD")
    ytd_ya_sales = sales_for_period(scope_df, "YTD YA")

    total_market_sales = sales_for_period(full_df, selected_period)
    share = current_sales / total_market_sales if total_market_sales else np.nan

    return {
        "current_sales": current_sales,
        "yoy_growth": safe_growth(current_sales, yoy_sales),
        "mom_growth": safe_growth(current_sales, mom_sales),
        "ytd_growth": safe_growth(ytd_sales, ytd_ya_sales),
        "share": share,
        "contribution": current_sales - yoy_sales if not pd.isna(yoy_sales) else np.nan,
        "yoy_period": benchmarks["yoy"],
        "mom_period": benchmarks["mom"],
        "yoy_sales": yoy_sales,
        "mom_sales": mom_sales,
        "ytd_sales": ytd_sales,
        "ytd_ya_sales": ytd_ya_sales,
    }


def aggregate_for_period(df: pd.DataFrame, dimension: str, period_display: str, top_n: int = 10) -> pd.DataFrame:
    grouped = (
        df[df["period_display"] == period_display]
        .groupby(dimension, dropna=False)["sales_value"]
        .sum()
        .reset_index()
        .sort_values("sales_value", ascending=False)
        .head(top_n)
    )
    return grouped


def type_growth_table(df: pd.DataFrame, selected_period: str) -> pd.DataFrame:
    benchmarks = get_benchmark_periods(df, selected_period)
    yoy_period = benchmarks["yoy"]
    if yoy_period is None:
        return pd.DataFrame(columns=["typea", "growth_rate"])

    current = (
        df[df["period_display"] == selected_period]
        .groupby("typea")["sales_value"]
        .sum()
        .reset_index()
        .rename(columns={"sales_value": "current_sales"})
    )
    base = (
        df[df["period_display"] == yoy_period]
        .groupby("typea")["sales_value"]
        .sum()
        .reset_index()
        .rename(columns={"sales_value": "base_sales"})
    )

    merged = current.merge(base, on="typea", how="outer").fillna(0)
    merged["growth_rate"] = merged.apply(
        lambda row: np.nan if row["base_sales"] == 0 else (row["current_sales"] - row["base_sales"]) / row["base_sales"],
        axis=1,
    )
    merged = merged.sort_values("growth_rate", ascending=False)
    return merged[["typea", "growth_rate"]]


def sku_contribution_table(df: pd.DataFrame, selected_period: str, top_n: int = 20) -> pd.DataFrame:
    benchmarks = get_benchmark_periods(df, selected_period)
    yoy_period = benchmarks["yoy"]
    if yoy_period is None:
        return pd.DataFrame(columns=["item", "contribution"])

    current = (
        df[df["period_display"] == selected_period]
        .groupby("item")["sales_value"]
        .sum()
        .reset_index()
        .rename(columns={"sales_value": "current_sales"})
    )
    base = (
        df[df["period_display"] == yoy_period]
        .groupby("item")["sales_value"]
        .sum()
        .reset_index()
        .rename(columns={"sales_value": "base_sales"})
    )

    merged = current.merge(base, on="item", how="outer").fillna(0)
    merged["contribution"] = merged["current_sales"] - merged["base_sales"]
    merged = merged.sort_values("contribution", ascending=False).head(top_n)
    return merged[["item", "contribution"]]


def get_month_periods_sorted(df: pd.DataFrame) -> list[str]:
    month_df = (
        df.loc[df["period_type"] == "month", ["period_display", "period_end_date"]]
        .drop_duplicates()
        .sort_values("period_end_date")
    )
    return month_df["period_display"].tolist()


def get_yoy_periods_for_range(df: pd.DataFrame, periods: list[str]) -> list[str]:
    month_df = (
        df.loc[df["period_type"] == "month", ["period_display", "period_end_date"]]
        .drop_duplicates()
        .sort_values("period_end_date")
    )
    if month_df.empty:
        return []

    selected_dates = month_df[month_df["period_display"].isin(periods)]["period_end_date"]
    if selected_dates.empty:
        return []

    yoy_periods = []
    for end_date in selected_dates:
        target = end_date - pd.Timedelta(days=365)
        candidates = month_df[
            (month_df["period_end_date"] - target).abs().dt.days <= 60
        ]
        if not candidates.empty:
            closest = candidates.iloc[(candidates["period_end_date"] - target).abs().argsort()[:1]]
            yoy_periods.append(closest["period_display"].iloc[0])

    return list(dict.fromkeys(yoy_periods))


def ranking_table_range(df: pd.DataFrame, dimension: str, current_periods: list[str], yoy_periods: list[str]) -> pd.DataFrame:
    current = (
        df[df["period_display"].isin(current_periods)]
        .groupby(dimension)["sales_value"]
        .sum()
        .reset_index()
        .rename(columns={"sales_value": "current_sales"})
    )

    if yoy_periods:
        base = (
            df[df["period_display"].isin(yoy_periods)]
            .groupby(dimension)["sales_value"]
            .sum()
            .reset_index()
            .rename(columns={"sales_value": "base_sales"})
        )
        merged = current.merge(base, on=dimension, how="left")
        merged["YoY"] = merged.apply(
            lambda row: np.nan if pd.isna(row["base_sales"]) or row["base_sales"] == 0
            else (row["current_sales"] - row["base_sales"]) / row["base_sales"],
            axis=1,
        )
        merged["Contribution"] = merged["current_sales"] - merged["base_sales"].fillna(0)
    else:
        merged = current.copy()
        merged["base_sales"] = np.nan
        merged["YoY"] = np.nan
        merged["Contribution"] = np.nan

    total_sales = merged["current_sales"].sum()
    merged["Share"] = merged["current_sales"] / total_sales if total_sales else np.nan

    total_base = merged["base_sales"].sum() if yoy_periods else np.nan
    merged["base_Share"] = merged["base_sales"] / total_base if not pd.isna(total_base) and total_base else np.nan
    merged["Share_chg"] = merged["Share"] - merged["base_Share"]

    merged = merged.sort_values("current_sales", ascending=False).reset_index(drop=True)
    merged.index = merged.index + 1
    merged = merged.reset_index().rename(columns={"index": "Rank"})
    return merged


def ranking_table(df: pd.DataFrame, dimension: str, selected_period: str) -> pd.DataFrame:
    benchmarks = get_benchmark_periods(df, selected_period)
    yoy_period = benchmarks["yoy"]

    current = (
        df[df["period_display"] == selected_period]
        .groupby(dimension)["sales_value"]
        .sum()
        .reset_index()
        .rename(columns={"sales_value": "current_sales"})
    )

    if yoy_period:
        base = (
            df[df["period_display"] == yoy_period]
            .groupby(dimension)["sales_value"]
            .sum()
            .reset_index()
            .rename(columns={"sales_value": "base_sales"})
        )
        merged = current.merge(base, on=dimension, how="left").fillna(0)
        merged["YoY"] = merged.apply(
            lambda row: np.nan if row["base_sales"] == 0 else (row["current_sales"] - row["base_sales"]) / row["base_sales"],
            axis=1,
        )
    else:
        merged = current.copy()
        merged["base_sales"] = np.nan
        merged["YoY"] = np.nan

    total_sales = merged["current_sales"].sum()
    merged["Share"] = merged["current_sales"] / total_sales if total_sales else np.nan
    merged = merged.sort_values("current_sales", ascending=False).reset_index(drop=True)
    merged.index = merged.index + 1
    merged = merged.reset_index().rename(columns={"index": "Rank"})
    return merged


def sku_detail_table(df: pd.DataFrame, selected_period: str, top_n: int = 200) -> pd.DataFrame:
    benchmarks = get_benchmark_periods(df, selected_period)
    yoy_period = benchmarks["yoy"]
    mom_period = benchmarks["mom"]

    current = (
        df[df["period_display"] == selected_period]
        .groupby(["item_code", "item", "manufacturer", "brand", "typea", "market"])["sales_value"]
        .sum()
        .reset_index()
        .rename(columns={"sales_value": "current_sales"})
    )

    if yoy_period:
        yoy = (
            df[df["period_display"] == yoy_period]
            .groupby(["item_code", "item", "manufacturer", "brand", "typea", "market"])["sales_value"]
            .sum()
            .reset_index()
            .rename(columns={"sales_value": "yoy_sales"})
        )
        current = current.merge(yoy, on=["item_code", "item", "manufacturer", "brand", "typea", "market"], how="left")
    else:
        current["yoy_sales"] = np.nan

    if mom_period:
        mom = (
            df[df["period_display"] == mom_period]
            .groupby(["item_code", "item", "manufacturer", "brand", "typea", "market"])["sales_value"]
            .sum()
            .reset_index()
            .rename(columns={"sales_value": "mom_sales"})
        )
        current = current.merge(mom, on=["item_code", "item", "manufacturer", "brand", "typea", "market"], how="left")
    else:
        current["mom_sales"] = np.nan

    current["YoY"] = current.apply(
        lambda row: np.nan if pd.isna(row["yoy_sales"]) or row["yoy_sales"] == 0 else (row["current_sales"] - row["yoy_sales"]) / row["yoy_sales"],
        axis=1,
    )
    current["MoM"] = current.apply(
        lambda row: np.nan if pd.isna(row["mom_sales"]) or row["mom_sales"] == 0 else (row["current_sales"] - row["mom_sales"]) / row["mom_sales"],
        axis=1,
    )

    current = current.sort_values("current_sales", ascending=False).head(top_n)
    return current


def format_money(value: float) -> str:
    if pd.isna(value):
        return "-"
    abs_value = abs(value)
    if abs_value >= 100:
        eok = value / 100
        if abs(eok) >= 10:
            return f"{eok:,.0f}억원"
        return f"{eok:,.1f}억원"
    return f"{value:,.0f}백만원"


def value_in_eok(value: float) -> float:
    if pd.isna(value):
        return np.nan
    return value / 100


def format_chart_value_eok(value: float) -> str:
    if pd.isna(value):
        return ""
    if abs(value) >= 10:
        return f"{value:,.0f}"
    return f"{value:,.1f}"


def format_pct(value: float) -> str:
    if pd.isna(value):
        return "-"
    return f"{value * 100:,.1f}%"


def top_rows_for_focus(df: pd.DataFrame, focus_dimension: str, selected_period: str, top_n: int = 5) -> list[dict]:
    dimension = focus_dimension if focus_dimension in {"manufacturer", "brand", "typea", "market"} else "brand"
    top_df = ranking_table(df, dimension, selected_period).head(top_n)
    return top_df.to_dict(orient="records")


def build_precise_facts(kpis: dict, selected_period: str, category: str) -> list[str]:
    facts = [
        f"{selected_period} {category} 시장 현재 매출은 {format_money(kpis.get('current_sales'))}입니다.",
        f"전년 동기 대비 증감률은 {format_pct(kpis.get('yoy_growth'))}입니다.",
        f"전월 대비 증감률은 {format_pct(kpis.get('mom_growth'))}입니다.",
        f"YTD 성장률은 {format_pct(kpis.get('ytd_growth'))}입니다.",
        f"현재 시장점유율은 {format_pct(kpis.get('share'))}입니다.",
        f"전년동월 대비 기여액은 {format_money(kpis.get('contribution'))}입니다.",
    ]
    return facts
