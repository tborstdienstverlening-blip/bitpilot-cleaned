# services/pnl_service.py
from __future__ import annotations
from typing import Any, Optional, Tuple
import pandas as pd

from schema import COL
from risk_utils import contracts_from_row


def to_num(s: Any) -> Optional[float]:
    """EU-decimalen parser: accepteert ',' en '.'; leeg/ongeldig -> None."""
    try:
        t = str(s).strip().replace(",", ".")
        return None if t == "" else float(t)
    except Exception:
        return None


def fmt_int_grouped(n: int | float) -> str:
    """Excel-achtige integerweergave met duizendtallen: 202596 -> '202,596'."""
    try:
        return f"{int(round(float(n))):,}"
    except Exception:
        return ""


def row_autos(row: pd.Series, default_risk_pct: float) -> pd.Series:
    """
    Houdt de exacte logica van v0.2.07d aan:
    - Contract Size: integer-weergave
    - PNL_TP1/2/3: floats met EU-komma support
    - PNL_Exit: leeg -> 0.0 (zonder herberekening)
    - PNL_BTC (nieuw in 07c/07d): TP1+TP2+TP3+Exit
    - RR(Actueel) = PNL_BTC / (Kapitaal × Risk%/100), guard -> "—"
    - RR(Plan) onveranderd
    """
    entry = to_num(row.get(COL["ENTRY"]))
    sl = to_num(row.get(COL["SL"]))
    cap = to_num(row.get(COL["CAP_TRADE"]))
    risk_pct_val = to_num(row.get(COL["RISK_PCT"])) if row.get(COL["RISK_PCT"]) is not None else default_risk_pct

    # Contract size (als integer-string met duizendscheiding)
    _, contracts = contracts_from_row(cap, risk_pct_val, entry, sl)
    row[COL["CONTRACT_SIZE"]] = "" if contracts is None else fmt_int_grouped(contracts)

    # RR Plan (ongewijzigd)
    side = (row.get(COL["SIDE"]) or "").strip().lower()
    tp1_price, tp2_price, tp3_price = to_num(row.get(COL["TP1"])), to_num(row.get(COL["TP2"])), to_num(row.get(COL["TP3"]))
    rr_plan = None
    den = None
    if entry is not None and sl is not None:
        den = abs(entry - sl)
    if den not in (None, 0):
        cands = []
        for tp in (tp1_price, tp2_price, tp3_price):
            if tp is None:
                continue
            if side == "short":
                cands.append((entry - tp) / den)
            else:
                cands.append((tp - entry) / den)
        rr_plan = max(cands) if cands else None
    row[COL["RR_PLAN"]] = "n.v.t." if rr_plan is None else f"{rr_plan:.2f}"

    # PNL invoer (EU-komma) -> floats
    pnl_tp1 = to_num(row.get(COL["PNL_TP1"])) or 0.0
    pnl_tp2 = to_num(row.get(COL["PNL_TP2"])) or 0.0
    pnl_tp3 = to_num(row.get(COL["PNL_TP3"])) or 0.0
    row[COL["PNL_TP1"]] = pnl_tp1
    row[COL["PNL_TP2"]] = pnl_tp2
    row[COL["PNL_TP3"]] = pnl_tp3

    # PNL_Exit: leeg -> 0.0, verder ongewijzigd
    pnl_exit_existing = to_num(row.get(COL["PNL_EXIT"]))
    pnl_exit = 0.0 if pnl_exit_existing is None else pnl_exit_existing
    row[COL["PNL_EXIT"]] = pnl_exit

    # PNL_BTC = TP1+TP2+TP3+Exit
    pnl_btc = float(pnl_tp1 + pnl_tp2 + pnl_tp3 + pnl_exit)
    row["PNL_BTC"] = pnl_btc  # lokale kolomnaam zoals in 07c/07d

    # RR(Actueel)
    row_risk_btc = None
    if cap is not None and risk_pct_val is not None:
        try:
            row_risk_btc = float(cap) * (float(risk_pct_val) / 100.0)
        except Exception:
            row_risk_btc = None

    if row_risk_btc is None or row_risk_btc <= 0:
        row[COL["RR_ACTUAL"]] = "—"
    else:
        rr_actual_val = pnl_btc / row_risk_btc
        row[COL["RR_ACTUAL"]] = f"{rr_actual_val:.2f}"

    return row


def compute_autos(df: pd.DataFrame, default_risk_pct: float) -> pd.DataFrame:
    """
    Past row_autos toe op alle rijen en cast numerieke kolommen voor aggregaties.
    """
    if df is None or df.empty:
        return df
    df = df.apply(lambda r: row_autos(r, default_risk_pct), axis=1)

    # Numerieke kolommen normaliseren
    for c in (
        COL["RISK_PCT"], COL["FEES"],
        COL["PNL_TP1"], COL["PNL_TP2"], COL["PNL_TP3"], COL["PNL_EXIT"],
        "PNL_BTC",
    ):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df
