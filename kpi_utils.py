# kpi_utils.py — filters + KPI-berekeningen voor R0.2-04
from __future__ import annotations
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from schema import COL, DATE_FMT

def with_pnl_total(df: pd.DataFrame) -> pd.DataFrame:
    def _row(row):
        vals = []
        for c in (COL["PNL_TP1"], COL["PNL_TP2"], COL["PNL_TP3"], COL["PNL_EXIT"]):
            v = row.get(c, 0)
            try:
                v = float(str(v).replace(",", ".")) if str(v).strip() != "" else 0.0
            except Exception:
                v = 0.0
            vals.append(v)
        return float(np.nansum(vals))
    if COL["PNL_TOTAL"] not in df.columns:
        df = df.copy()
        df[COL["PNL_TOTAL"]] = df.apply(_row, axis=1)
    return df

def _period_bounds(kind: str) -> tuple[pd.Timestamp|None, pd.Timestamp|None]:
    today = pd.Timestamp.today().normalize()
    if kind == "YTD":
        start = pd.Timestamp(year=today.year, month=1, day=1)
        return start, None
    if kind == "MTD":
        start = pd.Timestamp(year=today.year, month=today.month, day=1)
        return start, None
    if kind == "WTD":
        start = today - pd.Timedelta(days=today.weekday())  # maandag
        return start, None
    return None, None

def apply_filters(
    df: pd.DataFrame,
    search: str = "",
    tags_csv: str = "",
    emoties: list[str] | None = None,
    periode: str = "Alle",
) -> pd.DataFrame:
    df2 = df.copy()
    # Datum naar datetime (tolerant)
    try:
        df2["_dt"] = pd.to_datetime(df2[COL["DATUM"]], format=DATE_FMT, errors="coerce")
    except Exception:
        df2["_dt"] = pd.to_datetime(df2[COL["DATUM"]], errors="coerce")

    # Periode
    if periode in {"YTD","MTD","WTD"}:
        start, _ = _period_bounds(periode)
        if start is not None:
            df2 = df2[df2["_dt"] >= start]

    # Search (Trade_ID / Tags)
    q = (search or "").strip().lower()
    if q:
        mask = df2[COL["TRADE_ID"]].astype(str).str.lower().str.contains(q) | \
               df2[COL["TAGS"]].astype(str).str.lower().str.contains(q)
        df2 = df2[mask]

    # Tags (comma)
    tags = [t.strip().lower() for t in (tags_csv or "").split(",") if t.strip()]
    if tags:
        m = False
        col = df2[COL["TAGS"]].astype(str).str.lower()
        for t in tags:
            m = m | col.str.contains(t)
        df2 = df2[m]

    # Emoties (match als substring)
    if emoties:
        m = False
        col = df2[COL["EMOTIES"]].astype(str).str.lower()
        for e in [x.lower() for x in emoties]:
            m = m | col.str.contains(e)
        df2 = df2[m]

    # sort op datum aflopend + cleanup
    df2 = df2.sort_values("_dt", ascending=False).drop(columns=["_dt"])
    return df2

def compute_kpis(df: pd.DataFrame, start_btc: float, rolling_n: int = 20) -> dict:
    df2 = with_pnl_total(df)

    pnl_total = pd.to_numeric(df2[COL["PNL_TOTAL"]], errors="coerce").fillna(0).sum()
    fees_total = pd.to_numeric(df2[COL["FEES"]], errors="coerce").fillna(0).sum()
    actueel = float(start_btc) + float(pnl_total) - float(fees_total)

    # Win/Loss telling
    wins = int((df2[COL["WIN"]].astype(str) == "Win").sum())
    losses = int((df2[COL["WIN"]].astype(str) == "Loss").sum())
    decided = wins + losses
    winrate = (wins / decided * 100.0) if decided > 0 else None

    # Rolling (laatste N besliste trades op datum)
    try:
        dfx = df2.copy()
        dfx["_dt"] = pd.to_datetime(dfx[COL["DATUM"]], format=DATE_FMT, errors="coerce")
        dfx = dfx[dfx[COL["WIN"]].astype(str).isin(["Win","Loss"])].sort_values("_dt", ascending=False)
        last = dfx.head(max(1, int(rolling_n)))
        rw_wins = int((last[COL["WIN"]] == "Win").sum())
        rw_total = len(last)
        rolling_winrate = (rw_wins / rw_total * 100.0) if rw_total > 0 else None
    except Exception:
        rolling_winrate = None

    # ROI
    roi = ((actueel - float(start_btc)) / float(start_btc) * 100.0) if float(start_btc) > 0 else None

    return {
        "start": float(start_btc),
        "actueel": float(actueel),
        "pnl": float(pnl_total),
        "fees": float(fees_total),
        "roi_pct": None if roi is None else float(roi),
        "wins": wins,
        "losses": losses,
        "winrate_pct": None if winrate is None else float(winrate),
        "rolling_winrate_pct": None if rolling_winrate is None else float(rolling_winrate),
    }
