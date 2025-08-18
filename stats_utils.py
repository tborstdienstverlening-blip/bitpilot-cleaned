# stats_utils.py — KPI's veilig bij lege data
import pandas as pd
from schema import COL

def kpi_count(df: pd.DataFrame) -> int:
    return int(len(df)) if df is not None else 0

def kpi_winrate(df: pd.DataFrame) -> str:
    if df is None or df.empty or COL["WIN"] not in df.columns:
        return "—"
    valid = df[df[COL["WIN"]].isin(["Win","Loss"])]
    if len(valid) == 0:
        return "—"
    wins = (valid[COL["WIN"]] == "Win").sum()
    return f"{(wins/len(valid))*100:.0f}%"

def kpi_avg_r(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "—"
    col = COL["RISICO_R"] if COL["RISICO_R"] in df.columns else "Risico_R"
    if col not in df.columns:
        return "—"
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    return f"{s.mean():.2f}" if len(s) else "—"
