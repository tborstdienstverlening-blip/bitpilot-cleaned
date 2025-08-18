from pathlib import Path
import pandas as pd
from schema import ORDER
from utils_config import load_config

def ensure_csv():
    cfg = load_config()
    csv = Path(cfg["DATA_DIR"]) / "journal_entries.csv"
    csv.parent.mkdir(parents=True, exist_ok=True)
    if not csv.exists():
        pd.DataFrame(columns=ORDER).to_csv(csv, index=False)
    return csv

def read_entries() -> pd.DataFrame:
    csv = ensure_csv()
    try:
        df = pd.read_csv(csv)
    except Exception:
        df = pd.DataFrame(columns=ORDER)
    for col in ORDER:
        if col not in df.columns:
            df[col] = ""
    return df[ORDER]

def write_entries(df: pd.DataFrame):
    csv = ensure_csv()
    if df is None or df.empty:
        pd.DataFrame(columns=ORDER).to_csv(csv, index=False)
    else:
        df[ORDER].to_csv(csv, index=False)

def export_visible(df_visible: pd.DataFrame):
    """Alle schema-kolommen (incl. TFS) naar export/*.csv"""
    cfg = load_config()
    out = Path(cfg["EXPORT_DIR"]) / "journal_export.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df_out = df_visible.copy()
    for col in ORDER:
        if col not in df_out.columns:
            df_out[col] = ""
    df_out[ORDER].to_csv(out, index=False)
    return out
