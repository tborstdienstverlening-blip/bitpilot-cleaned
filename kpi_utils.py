# kpi_utils.py — KPI-berekeningen + filters (R0.2-04b)
from __future__ import annotations
import pandas as pd
import numpy as np
from schema import COL, DATE_FMT

# ---------- number helpers ----------
def _maybe_num(v):
    if v is None:
        return None
    s = str(v).strip()
    if s == "":
        return None
    try:
        return float(s.replace(",", "."))
    except Exception:
        return None

def _num0(v) -> float:
    n = _maybe_num(v)
    return 0.0 if n is None else float(n)

# ---------- per-rij PnL ----------
def row_pnl_total(row: dict) -> float:
    """
    R0.2-04-regel:
    - Als PNL_Exit gevuld is -> gebruik ALLEEN die waarde
    - Anders -> som van PNL_TP1..3
    """
    ex = _maybe_num(row.get(COL["PNL_EXIT"]))
    if ex is not None:
        return float(ex)
    return float(np.nansum([_num0(row.get(COL["PNL_TP1"])),
                            _num0(row.get(COL["PNL_TP2"])),
                            _num0(row.get(COL["PNL_TP3"]))]))

def with_pnl_total(df: pd.DataFrame) -> pd.DataFrame:
    df2 = df.copy()
    df2[COL["PNL_TOTAL"]] = df2.apply(lambda r: row_pnl_total(r), axis=1)
    return df2

def _ensure_dt(df: pd.DataFrame) -> pd.DataFrame:
    df2 = df.copy()
    try:
        df2["_dt"] = pd.to_datetime(df2[COL["DATUM"]], format=DATE_FMT, errors="coerce")
    except Exception:
        df2["_dt"] = pd.to_datetime(df2[COL["DATUM"]], errors="coerce")
    return df2

# ---------- filters ----------
def _period_bounds(kind: str):
    today = pd.Timestamp.today().normalize()
    if kind == "YTD":
        return pd.Timestamp(year=today.year, month=1, day=1), None
    if kind == "MTD":
        return pd.Timestamp(year=today.year, month=today.month, day=1), None
    if kind == "WTD":
        return today - pd.Timedelta(days=today.weekday()), None  # maandag
    return None, None

def apply_filters(
    df: pd.DataFrame,
    search: str = "",
    tags_csv: str = "",
    emoties: list[str] | None = None,
    periode: str = "Alle",
) -> pd.DataFrame:
    df2 = _ensure_dt(df)
    # Periode
    if periode in {"YTD", "MTD", "WTD"}:
        start, _ = _period_bounds(periode)
        if start is not None:
            df2 = df2[df2["_dt"] >= start]
    # Search
    q = (search or "").strip().lower()
    if q:
        m = df2[COL["TRADE_ID"]].astype(str).str.lower().str.contains(q) | \
            df2[COL["TAGS"]].astype(str).str.lower().str.contains(q)
        df2 = df2[m]
    # Tags (comma)
    tags = [t.strip().lower() for t in (tags_csv or "").split(",") if t.strip()]
    if tags:
        col = df2[COL["TAGS"]].astype(str).str.lower()
        m = False
        for t in tags:
            m = m | col.str.contains(t)
        df2 = df2[m]
    # Emoties
    if emoties:
        col = df2[COL["EMOTIES"]].astype(str).str.lower()
        m = False
        for e in [x.lower() for x in emoties]:
            m = m | col.str.contains(e)
        df2 = df2[m]
    # Sort aflopend op Datum + fallback op Trade_ID
    df2 = df2.sort_values([COL["DATUM"], COL["TRADE_ID"]], ascending=[False, False], kind="mergesort")
    return df2

# ---------- KPI's ----------
def compute_kpis(df: pd.DataFrame, start_btc: float) -> dict:
    """
    Totals:
      Totale PnL = Σ row_pnl_total (Exit of TP-som)
      Totale Fees = Σ Fees
      Actueel = Start + Totale PnL − Totale Fees
      ROI% = (Actueel − Start) / Start * 100

    Win/Loss:
      Win  = (PNL_Exit > 0)  (als Exit leeg → gebruik row_pnl_total)
      Loss = (PNL_Exit ≤ 0)

    Deltas (laatste trade = sort op Datum DESC, ID DESC):
      delta_actueel_btc = PNL_Exit(last)
      delta_pnl_btc     = PNL_Exit(last)
      delta_fees_btc    = Fees(last)
      delta_roi_pp      = ROI_na − ROI_voor  (pp)

    Winrate-delta:
      Alleen pijltje ↑ als PNL_Exit(last) > 0, anders ↓ (bij 0/None → ↓).
    """
    df2 = with_pnl_total(df.copy())
    df2 = _ensure_dt(df2)
    # Robuuste sort: datum desc, daarna ID desc (stabiele mergesort)
    df2 = df2.sort_values([COL["DATUM"], COL["TRADE_ID"]], ascending=[False, False], kind="mergesort")

    # totals
    pnl_total = float(pd.to_numeric(df2[COL["PNL_TOTAL"]], errors="coerce").fillna(0).sum())
    fees_total = float(pd.to_numeric(df2[COL["FEES"]], errors="coerce").fillna(0).sum())
    actueel = float(start_btc) + pnl_total - fees_total
    roi_pct = None if float(start_btc) == 0 else ((actueel - float(start_btc)) / float(start_btc) * 100.0)

    # wins/losses
    def _row_is_win(r) -> bool:
        ex = _maybe_num(r.get(COL["PNL_EXIT"]))
        val = ex if ex is not None else _maybe_num(r.get(COL["PNL_TOTAL"]))
        val = 0.0 if val is None else float(val)
        return val > 0.0

    wins = int(df2.apply(_row_is_win, axis=1).sum())
    losses = int(len(df2) - wins)  # ≤ 0 telt als loss
    decided = wins + losses
    winrate_pct = None if decided == 0 else (wins / decided * 100.0)

    # laatste trade (voor deltas)
    if len(df2) >= 1:
        last = df2.iloc[0].to_dict()
        last_exit = _num0(last.get(COL["PNL_EXIT"]))  # SPEC: deltas refereren aan Exit (geen fallback)
        last_fees = _num0(last.get(COL["FEES"]))
        # ROI delta: voor en na laatste trade
        last_row_total = row_pnl_total(last)  # voor totals (kan TP-som zijn)
        pnl_before = pnl_total - last_row_total
        fees_before = fees_total - last_fees
        act_before = float(start_btc) + pnl_before - fees_before
        roi_before = None if float(start_btc) == 0 else ((act_before - float(start_btc)) / float(start_btc) * 100.0)
        roi_after = roi_pct
        delta_roi_pp = None if (roi_before is None or roi_after is None) else (roi_after - roi_before)

        winrate_arrow = "↑" if last_exit > 0 else "↓"
    else:
        last_exit = 0.0
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
        # deltas voor KPI-balk
        "delta_actueel_btc": float(last_exit),
        "delta_pnl_btc": float(last_exit),
        "delta_fees_btc": float(last_fees),
        "delta_roi_pp": None if delta_roi_pp is None else float(delta_roi_pp),
        "winrate_arrow": winrate_arrow,
    }
