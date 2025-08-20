# services/pnl_service.py
from __future__ import annotations
from typing import Any, Optional
import pandas as pd
from decimal import Decimal, ROUND_HALF_UP, getcontext

from schema import COL
from risk_utils import contracts_from_row

# Hoge precisie voor BTC-berekeningen
getcontext().prec = 28


def to_decimal(s: Any) -> Optional[Decimal]:
    """EU-parser: accepteert ',' en '.'; leeg/ongeldig -> None."""
    if s is None:
        return None
    t = str(s).strip()
    if t == "":
        return None
    t = t.replace(",", ".")
    try:
        return Decimal(t)
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
    Exacte logica met extra precisie (07e):
    - Contract Size: integer-weergave
    - PNL_TP1/2/3: Decimal met EU-komma support
    - PNL_Exit: leeg -> 0
    - PNL_BTC: TP1+TP2+TP3+Exit (inclusief Exit-only uitstopper)
    - RR(Actueel) = PNL_BTC / (Kapitaal × Risk%/100) (guard -> '—')
    - RR(Plan) onveranderd (float ok)
    """
    # Contract Size (gebruikt floats in helper; output blijft hetzelfde)
    entry_f = to_decimal(row.get(COL["ENTRY"]))
    sl_f = to_decimal(row.get(COL["SL"]))
    cap_f = to_decimal(row.get(COL["CAP_TRADE"]))
    risk_pct_f = to_decimal(row.get(COL["RISK_PCT"]))
    entry = float(entry_f) if entry_f is not None else None
    sl = float(sl_f) if sl_f is not None else None
    cap = float(cap_f) if cap_f is not None else None
    risk_pct_val = float(risk_pct_f) if risk_pct_f is not None else default_risk_pct

    _, contracts = contracts_from_row(cap, risk_pct_val, entry, sl)
    row[COL["CONTRACT_SIZE"]] = "" if contracts is None else fmt_int_grouped(contracts)

    # RR Plan (ongewijzigd)
    side = (row.get(COL["SIDE"]) or "").strip().lower()
    tp1_price, tp2_price, tp3_price = (
        float(entry) if (entry := entry) is not None else None,
        None,
        None,
    )
    # gebruik originele prijsvelden (TP1/2/3 als targets) voor RR Plan
    tp1_p = to_decimal(row.get(COL["TP1"]))
    tp2_p = to_decimal(row.get(COL["TP2"]))
    tp3_p = to_decimal(row.get(COL["TP3"]))
    rr_plan = None
    den = None
    if entry_f is not None and sl_f is not None:
        den = abs(float(entry_f - sl_f))
    if den not in (None, 0):
        cands = []
        for tp_d in (tp1_p, tp2_p, tp3_p):
            if tp_d is None:
                continue
            tp = float(tp_d)
            if side == "short":
                cands.append((entry - tp) / den)
            else:
                cands.append((tp - entry) / den)
        rr_plan = max(cands) if cands else None
    row[COL["RR_PLAN"]] = "n.v.t." if rr_plan is None else f"{rr_plan:.2f}"

    # PNL invoervelden als Decimal (EU-komma)
    pnl_tp1 = to_decimal(row.get(COL["PNL_TP1"])) or Decimal("0")
    pnl_tp2 = to_decimal(row.get(COL["PNL_TP2"])) or Decimal("0")
    pnl_tp3 = to_decimal(row.get(COL["PNL_TP3"])) or Decimal("0")
    # normaliseer opslag als float (DataFrame), maar zonder vroeg afronden
    row[COL["PNL_TP1"]] = float(pnl_tp1)
    row[COL["PNL_TP2"]] = float(pnl_tp2)
    row[COL["PNL_TP3"]] = float(pnl_tp3)

    # PNL_Exit: leeg -> 0 (Decimal)
    pnl_exit_d = to_decimal(row.get(COL["PNL_EXIT"])) or Decimal("0")
    row[COL["PNL_EXIT"]] = float(pnl_exit_d)

    # ✅ PNL_BTC = TP1 + TP2 + TP3 + Exit (Decimal som, geen vroegtijdige afronding)
    pnl_btc_d = pnl_tp1 + pnl_tp2 + pnl_tp3 + pnl_exit_d
    row["PNL_BTC"] = float(pnl_btc_d)

    # ✅ RR (Actueel) = PNL_BTC / (Kapitaal × Risk%/100) met guard
    row_risk_btc = None
    if cap_f is not None and risk_pct_f is not None:
        try:
            row_risk_btc = (cap_f * (risk_pct_f / Decimal("100")))
        except Exception:
            row_risk_btc = None

    if row_risk_btc is None or row_risk_btc <= 0:
        row[COL["RR_ACTUAL"]] = "—"
    else:
        try:
            rr_actual_val = (pnl_btc_d / row_risk_btc)
            row[COL["RR_ACTUAL"]] = f"{float(rr_actual_val):.2f}"
        except Exception:
            row[COL["RR_ACTUAL"]] = "—"

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
