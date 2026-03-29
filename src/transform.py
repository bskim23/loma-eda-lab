import re
from pathlib import Path
import pandas as pd

DIMENSION_LABELS = {
    "ITEM CODE": "item_code",
    "ITEM": "item",
    "MANUFACTURER": "manufacturer",
    "BRAND": "brand",
    "TYPEA": "typea",
    "VARIANTB": "variantb",
    "PRODNAME": "prodname",
    "SUBBRAND": "subbrand",
    "FORMA": "forma",
}

def infer_category(file_name: str) -> str:
    stem = Path(file_name).stem
    m = re.search(r"Monthly Report\s+(.+?)\s*\(", stem, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return stem

def find_header_row(raw_df: pd.DataFrame) -> int:
    for idx, row in raw_df.iterrows():
        values = row.fillna("").astype(str).str.strip().tolist()
        if "ITEM CODE" in values and "MANUFACTURER" in values and "BRAND" in values:
            return idx
    raise ValueError("헤더 행을 찾지 못했습니다. 'ITEM CODE' 행 구조를 확인해 주세요.")

def normalize_market_name(value) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if "/" in text:
        return text.split("/")[-1].strip()
    return text

def parse_period_label(label) -> dict:
    if pd.isna(label):
        return {
            "period_raw": None,
            "period_display": None,
            "period_type": None,
            "period_end_date": pd.NaT,
        }

    text = str(label).strip()
    period_display = text.split("-")[0].strip()

    matched = re.search(r"w/e\s+(\d{2}/\d{2}/\d{2})", text)
    period_end_date = pd.to_datetime(matched.group(1), format="%d/%m/%y", errors="coerce") if matched else pd.NaT

    upper = period_display.upper()
    if upper.startswith("YTD 2YA"):
        period_type = "ytd_2ya"
    elif upper.startswith("YTD YA"):
        period_type = "ytd_ya"
    elif upper.startswith("YTD"):
        period_type = "ytd"
    else:
        period_type = "month"

    return {
        "period_raw": text,
        "period_display": period_display,
        "period_type": period_type,
        "period_end_date": period_end_date,
    }

def transform_raw_to_long(raw_df: pd.DataFrame, file_name: str) -> tuple[pd.DataFrame, dict]:
    category = infer_category(file_name)
    header_row = find_header_row(raw_df)
    market_row = header_row - 1
    metric_row = header_row - 2

    header_values = raw_df.iloc[header_row]

    dimension_cols = []
    measure_cols = []

    for col_idx, value in header_values.items():
        if pd.isna(value):
            continue
        text = str(value).strip()
        if text in DIMENSION_LABELS:
            dimension_cols.append(col_idx)
        else:
            measure_cols.append(col_idx)

    if not measure_cols:
        raise ValueError("측정값 열을 찾지 못했습니다. 헤더 구조를 확인해 주세요.")

    working_df = raw_df.iloc[header_row + 1 :].copy()
    working_df = working_df.loc[:, dimension_cols + measure_cols]

    id_columns = [DIMENSION_LABELS[str(header_values[c]).strip()] for c in dimension_cols]
    value_columns = [f"measure_{c}" for c in measure_cols]
    working_df.columns = id_columns + value_columns

    measure_meta = []
    for c in measure_cols:
        period_info = parse_period_label(raw_df.iloc[header_row, c])
        measure_meta.append(
            {
                "measure_key": f"measure_{c}",
                "metric_name": raw_df.iloc[metric_row, c],
                "market_path": raw_df.iloc[market_row, c],
                "market": normalize_market_name(raw_df.iloc[market_row, c]),
                **period_info,
            }
        )

    long_df = working_df.melt(
        id_vars=id_columns,
        value_vars=value_columns,
        var_name="measure_key",
        value_name="sales_value",
    )

    meta_df = pd.DataFrame(measure_meta)
    long_df = long_df.merge(meta_df, on="measure_key", how="left")

    long_df["sales_value"] = pd.to_numeric(long_df["sales_value"], errors="coerce")
    long_df = long_df.dropna(subset=["sales_value"]).copy()

    for col in id_columns:
        long_df[col] = long_df[col].fillna("Unknown").astype(str).str.strip()

    long_df["sales_value"] = long_df["sales_value"].astype(float)
    long_df["period_display"] = long_df["period_display"].fillna("").astype(str)
    long_df["market"] = long_df["market"].fillna("Unknown").astype(str)
    long_df["category"] = category

    long_df["is_month"] = long_df["period_type"].eq("month")
    long_df["is_ytd"] = long_df["period_type"].eq("ytd")
    long_df["is_ytd_ya"] = long_df["period_type"].eq("ytd_ya")
    long_df["is_ytd_2ya"] = long_df["period_type"].eq("ytd_2ya")

    transform_meta = {
        "header_row_excel": int(header_row + 1),
        "normalized_rows": int(long_df.shape[0]),
        "normalized_cols": int(long_df.shape[1]),
        "latest_month_period": get_latest_month_period(long_df),
        "category": category,
    }
    return long_df, transform_meta

def get_latest_month_period(long_df: pd.DataFrame) -> str | None:
    month_df = (
        long_df.loc[long_df["period_type"] == "month", ["period_display", "period_end_date"]]
        .drop_duplicates()
        .sort_values("period_end_date")
    )
    if month_df.empty:
        return None
    return month_df.iloc[-1]["period_display"]

def get_period_options(long_df: pd.DataFrame) -> list[str]:
    type_order = {"month": 0, "ytd_2ya": 1, "ytd_ya": 2, "ytd": 3}
    options = (
        long_df[["period_display", "period_end_date", "period_type"]]
        .drop_duplicates()
        .assign(type_order=lambda x: x["period_type"].map(type_order).fillna(9))
        .sort_values(["type_order", "period_end_date", "period_display"])
    )
    return options["period_display"].dropna().tolist()
