# stats_utils.py — light/stub version for Streamlit deploy
from __future__ import annotations
import math
from typing import Dict, Any
try:
    import pandas as pd
except Exception:  # Streamlit Cloud zal pandas installeren via requirements
    pd = None

# Best-effort helpers (werken met NL kolomnamen of fallback)
COL_NAMES = {
    "PNL": ["Resultaat_PnL", "PNL", "PnL", "pnl"],
    "RR": ["RR_realized", "RR", "rr"],
    "ROI": ["ROI_%", "ROI", "roi"],
    "OUTCOME": ["Uitkomst", "Outcome", "result", "WinLoss"],
    "FEES": ["Fees", "fees", "Kosten"],
}

def _pick_col(df, keys):
    for k in keys:
        if k in df.columns:
            return k
    return None

def _to_float(x):
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return 0.0
        if isinstance(x, str):
            x = x.replace("%","").replace(",", ".").strip()
        return float(x)
    except Exception:
        return 0.0

def compute_kpis(df, start_capital: float = 10_000.0) -> Dict[str, Any]:
    if df is None or len(df) == 0:
        return {
            "trades": 0, "wins": 0, "losses": 0, "winrate": 0.0,
            "pnl_total": 0.0, "fees_total": 0.0, "avg_rr": 0.0, "avg_roi": 0.0,
            "account_value": start_capital,
        }

    pnl_col = _pick_col(df, COL_NAMES["PNL"])
    rr_col  = _pick_col(df, COL_NAMES["RR"])
    roi_col = _pick_col(df, COL_NAMES["ROI"])
    out_col = _pick_col(df, COL_NAMES["OUTCOME"])
    fee_col = _pick_col(df, COL_NAMES["FEES"])

    pnl = df[pnl_col].map(_to_float) if pnl_col else [0.0]*len(df)
    rr  = df[rr_col].map(_to_float)  if rr_col  else [0.0]*len(df)
    roi = df[roi_col].map(_to_float) if roi_col else [0.0]*len(df)
    fees= df[fee_col].map(_to_float) if fee_col else [0.0]*len(df)

    trades = len(df)
    pnl_total = float(sum(pnl))
    fees_total = float(sum(fees))
    wins = 0; losses = 0
    if out_col and out_col in df.columns:
        for v in df[out_col]:
            s = str(v).strip().lower()
            if s in ("win","w","1","true","ja"): wins += 1
            elif s in ("loss","l","0","false","nee"): losses += 1
            else:
                # fallback: beslis op basis van pnl>0
                pass
    if wins + losses < trades and pnl_col:
        # vul aan op basis van pnl teken
        for x in pnl:
            if x > 0: wins += 1
            elif x < 0: losses += 1

    winrate = (wins / trades * 100.0) if trades else 0.0
    avg_rr = (sum(rr) / trades) if trades else 0.0
    avg_roi = (sum(roi) / trades) if trades else 0.0
    account_value = start_capital + pnl_total - fees_total

    return {
        "trades": trades, "wins": wins, "losses": losses, "winrate": winrate,
        "pnl_total": pnl_total, "fees_total": fees_total,
        "avg_rr": avg_rr, "avg_roi": avg_roi, "account_value": account_value,
    }

def render_kpi_bar(st, df, cfg: dict | None = None) -> None:
    """Eenvoudige KPI-balk; werkt zelfs als sommige kolommen ontbreken."""
    start_capital = 10_000.0
    if cfg:
        sc = (cfg.get("START_CAPITAL") or cfg.get("start_capital")
              or cfg.get("budget", {}).get("start_capital"))
        try:
            if sc is not None:
                start_capital = float(sc)
        except Exception:
            pass

    k = compute_kpis(df, start_capital=start_capital)
    cols = st.columns(6)
    cols[0].metric("Trades", k["trades"])
    cols[1].metric("Winrate", f"{k['winrate']:.1f}%")
    cols[2].metric("Totaal PnL", f"{k['pnl_total']:.2f}")
    cols[3].metric("Fees", f"{k['fees_total']:.2f}")
    cols[4].metric("Avg RR", f"{k['avg_rr']:.2f}")
    cols[5].metric("Account waarde", f"{k['account_value']:.2f}")
