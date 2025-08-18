# import_export.py — tolerant CSV IO
from pathlib import Path
import pandas as pd
from schema import REQUIRED_ORDER

CSV = Path("data") / "journal_entries.csv"

def ensure_csv():
    CSV.parent.mkdir(parents=True, exist_ok=True)
    if not CSV.exists():
        pd.DataFrame(columns=REQUIRED_ORDER).to_csv(CSV, index=False)

def read_entries() -> pd.DataFrame:
    ensure_csv()
    try:
        df = pd.read_csv(CSV)
    except Exception:
        df = pd.DataFrame(columns=REQUIRED_ORDER)
    for c in REQUIRED_ORDER:
        if c not in df.columns:
            df[c] = ""
    return df[REQUIRED_ORDER]

def write_entries(df: pd.DataFrame) -> None:
    if df is None or df.empty:
        pd.DataFrame(columns=REQUIRED_ORDER).to_csv(CSV, index=False)
    else:
        df[REQUIRED_ORDER].to_csv(CSV, index=False)
