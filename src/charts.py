import pandas as pd
import plotly.express as px
from .metrics import aggregate_for_period, type_growth_table, sku_contribution_table


def _to_eok(value):
    if pd.isna(value):
        return value
    return value / 100.0


def _format_chart_number_eok(value):
    if pd.isna(value):
        return ""
    if abs(value) >= 10:
        return f"{value:,.0f}"
    return f"{value:,.1f}"


def empty_figure(message: str):
    fig = px.bar(title=message)
    fig.update_layout(height=420)
    return fig


def monthly_sales_chart(df: pd.DataFrame):
    monthly = (
        df[df["period_type"] == "month"]
        .groupby(["period_display", "period_end_date"], as_index=False)["sales_value"]
        .sum()
        .sort_values("period_end_date")
    )
    if monthly.empty:
        return empty_figure("No monthly data")

    monthly["sales_value_eok"] = monthly["sales_value"].apply(_to_eok)
    monthly["label_text"] = monthly["sales_value_eok"].apply(_format_chart_number_eok)

    fig = px.bar(
        monthly,
        x="period_display",
        y="sales_value_eok",
        text="label_text",
        title="월별 매출 비교",
        labels={"period_display": "기간", "sales_value_eok": "매출 (억원)"},
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(height=420, yaxis_tickformat=",")
    return fig


def ytd_sales_chart(df: pd.DataFrame):
    ytd = (
        df[df["period_type"].isin(["ytd_2ya", "ytd_ya", "ytd"])]
        .groupby(["period_display", "period_end_date"], as_index=False)["sales_value"]
        .sum()
        .sort_values("period_end_date")
    )
    if ytd.empty:
        return empty_figure("No YTD data")

    ytd["sales_value_eok"] = ytd["sales_value"].apply(_to_eok)
    ytd["label_text"] = ytd["sales_value_eok"].apply(_format_chart_number_eok)

    fig = px.bar(
        ytd,
        x="period_display",
        y="sales_value_eok",
        text="label_text",
        title="YTD 매출 비교",
        labels={"period_display": "기간", "sales_value_eok": "매출 (억원)"},
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(height=420, yaxis_tickformat=",")
    return fig


def top_dimension_chart(df: pd.DataFrame, dimension: str, selected_period: str, top_n: int = 10):
    mapping = {
        "manufacturer": "제조사 Top",
        "brand": "브랜드 Top",
        "typea": "타입 Top",
        "market": "경로 Top",
    }
    chart_df = aggregate_for_period(df, dimension, selected_period, top_n=top_n)
    if chart_df.empty:
        return empty_figure(f"No data for {mapping.get(dimension, dimension)}")

    chart_df["sales_value_eok"] = chart_df["sales_value"].apply(_to_eok)
    chart_df["label_text"] = chart_df["sales_value_eok"].apply(_format_chart_number_eok)

    fig = px.bar(
        chart_df,
        x=dimension,
        y="sales_value_eok",
        text="label_text",
        title=mapping.get(dimension, dimension),
        labels={dimension: dimension.title(), "sales_value_eok": "매출 (억원)"},
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(height=420, xaxis_tickangle=-35, yaxis_tickformat=",")
    return fig


def type_growth_chart(df: pd.DataFrame, selected_period: str):
    growth_df = type_growth_table(df, selected_period).head(15)
    if growth_df.empty:
        return empty_figure("No type growth data")

    fig = px.bar(
        growth_df,
        x="typea",
        y="growth_rate",
        title="타입 성장률",
        labels={"typea": "Type", "growth_rate": "Growth Rate"},
    )
    fig.update_layout(height=420, xaxis_tickangle=-35, yaxis_tickformat=".1%")
    return fig


def sku_contribution_chart(df: pd.DataFrame, selected_period: str, top_n: int = 20):
    contribution_df = sku_contribution_table(df, selected_period, top_n=top_n)
    if contribution_df.empty:
        return empty_figure("No SKU contribution data")

    contribution_df["contribution_eok"] = contribution_df["contribution"].apply(_to_eok)
    contribution_df["label_text"] = contribution_df["contribution_eok"].apply(_format_chart_number_eok)

    fig = px.bar(
        contribution_df,
        x="contribution_eok",
        y="item",
        orientation="h",
        text="label_text",
        title="Top SKU Contribution",
        labels={"item": "SKU", "contribution_eok": "Contribution (억원)"},
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(height=520, yaxis={"categoryorder": "total ascending"}, xaxis_tickformat=",")
    return fig


def time_series_chart(df: pd.DataFrame):
    ts = (
        df[df["period_type"] == "month"]
        .groupby(["period_display", "period_end_date"], as_index=False)["sales_value"]
        .sum()
        .sort_values("period_end_date")
    )
    if ts.empty:
        return empty_figure("시계열 데이터가 없습니다.")

    ts["sales_value_eok"] = ts["sales_value"].apply(_to_eok)
    ts["label_text"] = ts["sales_value_eok"].apply(_format_chart_number_eok)

    fig = px.line(
        ts,
        x="period_end_date",
        y="sales_value_eok",
        markers=True,
        text="label_text",
        title="월별 시계열 추이",
        labels={"period_end_date": "기간", "sales_value_eok": "매출 (억원)"},
    )
    fig.update_traces(textposition="top center")
    fig.update_layout(height=420, yaxis_tickformat=",")
    return fig
