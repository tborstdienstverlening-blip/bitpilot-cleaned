# kpi_utils.py — KPI-berekeningen + filters (R0.2-04a)
from __future__ import annotations
import pandas as pd
import numpy as np
from schema import COL, DATE_FMT

# ---------- helpers ----------
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

def row_pnl_total(row: dict) -> float:
    """
    R0.2-04a regel:
    - Als PNL_Exit gevuld is -> gebruik ALLEEN die waarde
    - Anders -> som van PNL_TP1..3
    """
    ex = _maybe_num(row.get(COL["PNL_EXIT"]))
    if ex is not None:
        return float(ex)
    # fallback: som van TP's
    return float(np.nansum([_num0(row.get(COL["PNL_TP1"])),
                            _num0(row.get(COL["PNL_TP2"])),
                            _num0(row.get(COL["PNL_TP3"]))]))

def with_pnl_total(df: pd.DataFrame) -> pd.DataFrame:
    if COL["PNL_TOTAL"] in df.columns:
        # herbereken volgens nieuwe regel
        df = df.copy()
        df[COL["PNL_TOTAL"]] = df.apply(lambda r: row_pnl_total(r), axis=1)
        return df
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
    # Sort aflopend op Datum
    df2 = df2.sort_values("_dt", ascending=False).drop(columns=["_dt"])
    return df2

# ---------- KPI's ----------
def compute_kpis(df: pd.DataFrame, start_btc: float, rolling_n: int = 20) -> dict:
    """
    Totals:
      Totale PnL = Σ row_pnl_total (Exit of TP-som)
      Totale Fees = Σ Fees
      Actueel = Start + Totale PnL − Totale Fees
      ROI% = (Actueel − Start) / Start * 100
      Win  = count(PNL_Exit > 0) ; Loss = count(PNL_Exit <= 0)  (als Exit leeg → gebruik row_pnl_total)
      Winrate% = wins / (wins+losses) * 100
      Rolling winrate% = idem over laatste N trades
    Deltas (laatste trade):
      last_actueel_delta_btc = last_row_pnl_total − last_row_fees
      last_pnl_delta_btc     = last_row_pnl_total
      last_fees_delta_btc    = last_row_fees
      last_roi_delta_pct     = (last_actueel_delta_btc / Start) * 100   (None als Start=0)
      winrate_delta_pp / rolling_winrate_delta_pp: verschil in pp t.o.v. toestand zonder laatste trade
    """
    df2 = with_pnl_total(df.copy())
    df2 = _ensure_dt(df2).sort_values("_dt", ascending=False)

    # totals
    pnl_total = float(pd.to_numeric(df2[COL["PNL_TOTAL"]], errors="coerce").fillna(0).sum())
    fees_total = float(pd.to_numeric(df2[COL["FEES"]], errors="coerce").fillna(0).sum())
    actueel = float(start_btc) + pnl_total - fees_total
    roi_pct = None if float(start_btc) == 0 else ((actueel - float(start_btc)) / float(start_btc) * 100.0)

    # win / loss per Exit (fallback total)
    def _row_is_win(r) -> bool:
        ex = _maybe_num(r.get(COL["PNL_EXIT"]))
        val = ex if ex is not None else _maybe_num(r.get(COL["PNL_TOTAL"]))
        val = 0.0 if val is None else float(val)
        return val > 0.0

    wins = int(df2.apply(_row_is_win, axis=1).sum())
    losses = int(len(df2) - wins)  # verlies ook bij ==0 zoals ticket zegt (Exit ≤ 0)
    decided = wins + losses
    winrate_pct = None if decided == 0 else (wins / decided * 100.0)

    # rolling window op datum
    if len(df2) > 0:
        last_n = df2.head(max(1, int(rolling_n)))
        rw_wins = int(last_n.apply(_row_is_win, axis=1).sum())
        rw_total = int(len(last_n))
        rolling_winrate_pct = None if rw_total == 0 else (rw_wins / rw_total * 100.0)
    else:
        rolling_winrate_pct = None

    # laatste trade deltas
    if len(df2) >= 1:
        last = df2.iloc[0].to_dict()
        last_pnl_total = row_pnl_total(last)
        last_fees = _num0(last.get(COL["FEES"]))
        last_act_delta = last_pnl_total - last_fees
        last_roi_delta_pct = None if float(start_btc) == 0 else (last_act_delta / float(start_btc) * 100.0)
        # winrate delta (vol set vs set zonder laatste)
        if len(df2) >= 2:
            rest = df2.iloc[1:].copy()
            w2 = int(rest.apply(_row_is_win, axis=1).sum())
            l2 = int(len(rest) - w2)
            wr2 = None if (w2 + l2) == 0 else (w2 / (w2 + l2) * 100.0)
            wr_full = winrate_pct
            winrate_delta_pp = None if (wr2 is None or wr_full is None) else (wr_full - wr2)
        else:
            winrate_delta_pp = None
        # rolling delta (window N)
        if len(df2) >= 2:
            prev_n = df2.iloc[1:].head(max(1, int(rolling_n)))
            rw2_wins = int(prev_n.apply(_row_is_win, axis=1).sum())
            rw2_total = int(len(prev_n))
            rw2 = None if rw2_total == 0 else (rw2_wins / rw2_total * 100.0)
            rw_full = rolling_winrate_pct
            rolling_winrate_delta_pp = None if (rw2 is None or rw_full is None) else (rw_full - rw2)
        else:
            rolling_winrate_delta_pp = None
    else:
        last_pnl_total = 0.0
        last_fees = 0.0
        last_act_delta = 0.0
        last_roi_delta_pct = None
        winrate_delta_pp = None
        rolling_winrate_delta_pp = None

    return {
        "start": float(start_btc),
        "actueel": float(actueel),
        "pnl": float(pnl_total),
        "fees": float(fees_total),
        "roi_pct": None if roi_pct is None else float(roi_pct),
        "wins": wins,
        "losses": losses,
        "winrate_pct": None if winrate_pct is None else float(winrate_pct),
        "rolling_winrate_pct": None if rolling_winrate_pct is None else float(rolling_winrate_pct),
        # deltas obv laatste trade
        "last_actueel_delta_btc": float(last_act_delta),
        "last_pnl_delta_btc": float(last_pnl_total),
        "last_fees_delta_btc": float(last_fees),
        "last_roi_delta_pct": None if last_roi_delta_pct is None else float(last_roi_delta_pct),
        "winrate_delta_pp": None if winrate_delta_pp is None else float(winrate_delta_pp),
        "rolling_winrate_delta_pp": None if rolling_winrate_delta_pp is None else float(rolling_winrate_delta_pp),
    }
