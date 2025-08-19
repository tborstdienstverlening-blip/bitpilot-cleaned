# kpi_utils.py — filters + KPI's (R0.2-04f)
from __future__ import annotations
import pandas as pd
import numpy as np
from schema import COL, DATE_FMT

def _maybe_num(v):
    if v is None: return None
    s = str(v).strip()
    if s == "": return None
    try:
        return float(s.replace(",", "."))
    except Exception:
        return None

def _num0(v) -> float:
    n = _maybe_num(v)
    return 0.0 if n is None else float(n)

def ensure_dt(df: pd.DataFrame) -> pd.DataFrame:
    df2 = df.copy()
    try:
        df2["_dt"] = pd.to_datetime(df2[COL["DATUM"]], format=DATE_FMT, errors="coerce")
    except Exception:
        df2["_dt"] = pd.to_datetime(df2[COL["DATUM"]], errors="coerce")
    return df2

# ---- per-rij totals (voor KPI/winrate)
def row_tp_sum_present(row: dict) -> tuple[bool, float]:
    tps = [_maybe_num(row.get(COL["PNL_TP1"])),
           _maybe_num(row.get(COL["PNL_TP2"])),
           _maybe_num(row.get(COL["PNL_TP3"]))]
    present = any(x is not None for x in tps)
    s = float(np.nansum([x if x is not None else 0.0 for x in tps]))
    return present, s

def row_total_trade_pnl(row: dict) -> float:
    present, s = row_tp_sum_present(row)
    if present:
        return s
    ex = _maybe_num(row.get(COL["PNL_EXIT"]))
    return 0.0 if ex is None else float(ex)

def with_pnl_total(df: pd.DataFrame) -> pd.DataFrame:
    df2 = df.copy()
    df2[COL["PNL_TOTAL"]] = df2.apply(lambda r: row_total_trade_pnl(r), axis=1)
    return df2

# ---- filters
def _period_bounds(kind: str):
    today = pd.Timestamp.today().normalize()
    if kind == "YTD": return pd.Timestamp(year=today.year, month=1, day=1), None
    if kind == "MTD": return pd.Timestamp(year=today.year, month=today.month, day=1), None
    if kind == "WTD": return today - pd.Timedelta(days=today.weekday()), None
    return None, None

def apply_filters(df: pd.DataFrame, search="", tags_csv="", emoties=None, periode="Alle") -> pd.DataFrame:
    df2 = ensure_dt(df)
    if periode in {"YTD","MTD","WTD"}:
        start, _ = _period_bounds(periode)
        if start is not None:
            df2 = df2[df2["_dt"] >= start]
    q = (search or "").strip().lower()
    if q:
        m = df2[COL["TRADE_ID"]].astype(str).str.lower().str.contains(q) | \
            df2[COL["TAGS"]].astype(str).str.lower().str.contains(q)
        df2 = df2[m]
    tags = [t.strip().lower() for t in (tags_csv or "").split(",") if t.strip()]
    if tags:
        col = df2[COL["TAGS"]].astype(str).str.lower()
        mask = False
        for t in tags:
            mask = mask | col.str.contains(t)
        df2 = df2[mask]
    if emoties:
        col = df2[COL["EMOTIES"]].astype(str).str.lower()
        mask = False
        for e in [x.lower() for x in emoties]:
            mask = mask | col.str.contains(e)
        df2 = df2[mask]
    # sort: Datum DESC, ID DESC (stabiel)
    df2 = df2.sort_values([COL["DATUM"], COL["TRADE_ID"]], ascending=[False, False], kind="mergesort").drop(columns=["_dt"])
    return df2

# ---- KPI's (deltas = impact laatste trade; sort zoals hierboven)
def compute_kpis(df: pd.DataFrame, start_btc: float) -> dict:
    df2 = with_pnl_total(df.copy())
    df2 = ensure_dt(df2).sort_values([COL["DATUM"], COL["TRADE_ID"]], ascending=[False, False], kind="mergesort")

    pnl_total = float(pd.to_numeric(df2[COL["PNL_TOTAL"]], errors="coerce").fillna(0).sum())
    fees_total = float(pd.to_numeric(df2[COL["FEES"]], errors="coerce").fillna(0).sum())
    actueel = float(start_btc) + pnl_total - fees_total
    roi_pct = None if float(start_btc) == 0 else ((actueel - float(start_btc)) / float(start_btc) * 100.0)

    # wins/losses op basis van total_trade_pnl
    wins = int((pd.to_numeric(df2[COL["PNL_TOTAL"]], errors="coerce").fillna(0) > 0).sum())
    losses = int(len(df2) - wins)
    decided = wins + losses
    winrate_pct = None if decided == 0 else (wins / decided * 100.0)

    # laatste trade (voor deltas)
    if len(df2) >= 1:
        last = df2.iloc[0].to_dict()
        # Delta PnL/Fees = waarden van laatste trade:
        last_total = row_total_trade_pnl(last)  # ΣTP's of fallback Exit
        last_fees  = _num0(last.get(COL["FEES"]))
        # ROI delta = na - voor:
        pnl_before = pnl_total - last_total
        fees_before = fees_total - last_fees
        act_before = float(start_btc) + pnl_before - fees_before
        roi_before = None if float(start_btc) == 0 else ((act_before - float(start_btc)) / float(start_btc) * 100.0)
        delta_roi_pp = None if (roi_before is None or roi_pct is None) else (roi_pct - roi_before)
        # winrate pijltje: ↑ bij win, ↓ bij loss
        winrate_arrow = "↑" if last_total > 0 else "↓"
    else:
        last_total = 0.0
        last_fees = 0.0
        delta_roi_pp = None
        winrate_arrow = None

    return {
        "start": float(start_btc),
        "actueel": float(actueel),
        "pnl": float(pnl_total),
        "fees": float(fees_total),
        "roi_pct": None if roi_pct is None else float(roi_pct),
        "wins": wins,
        "losses": losses,
        "winrate_pct": None if winrate_pct is None else float(winrate_pct),
        # deltas gekoppeld aan laatste trade:
        "delta_actueel_btc": float(last_total - last_fees),
        "delta_pnl_btc": float(last_total),
        "delta_fees_btc": float(last_fees),
        "delta_roi_pp": None if delta_roi_pp is None else float(delta_roi_pp),
        "winrate_arrow": winrate_arrow,
    }

