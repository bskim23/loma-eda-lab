from io import BytesIO
import pandas as pd

def load_excel(uploaded_file):
    file_bytes = uploaded_file.getvalue()
    excel_buffer = BytesIO(file_bytes)
    xls = pd.ExcelFile(excel_buffer)
    sheet_name = xls.sheet_names[0]
    raw_df = pd.read_excel(BytesIO(file_bytes), sheet_name=sheet_name, header=None)
    meta = {
        "file_name": uploaded_file.name,
        "sheet_name": sheet_name,
        "raw_rows": int(raw_df.shape[0]),
        "raw_cols": int(raw_df.shape[1]),
        "file_size_mb": round(len(file_bytes) / 1024 / 1024, 2),
    }
    return raw_df, meta
