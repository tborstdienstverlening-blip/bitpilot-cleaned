# risk_utils.py — Risk & Contract Size (Deribit BTC-PERP; 1 contract = $1)
from __future__ import annotations
import math

def _to_float(x):
    try:
        s = str(x).strip().replace(",", ".")
        return float(s) if s != "" else None
    except Exception:
        return None

def compute_risk_contracts(account_btc: float, risk_pct: float, entry: float, sl: float, rounding: str = "floor"):
    """
    Inputs:
      account_btc (BTC), risk_pct (0..1), entry (prijs), sl (prijs)
    Formules:
      risk_btc        = account_btc * risk_pct
      sl_distance_pct = abs(entry - sl) / entry
      contracts       = (risk_btc * entry) / sl_distance_pct     # 1c = $1
    Rounding: "floor" | "round" | "ceil"
    Returns: (risk_btc, contracts) of (None, None) bij ongeldige invoer/SL==Entry
    """
    if account_btc is None or risk_pct is None: return (None, None)
    if entry is None or sl is None: return (None, None)
    try:
        entry = float(entry); sl = float(sl)
        account_btc = float(account_btc); risk_pct = float(risk_pct)
    except Exception:
        return (None, None)
    if entry == 0 or entry == sl:
        return (None, None)
    sl_distance_pct = abs(entry - sl) / entry
    if sl_distance_pct <= 0: return (None, None)
    risk_btc = account_btc * risk_pct
    contracts = (risk_btc * entry) / sl_distance_pct
    if rounding == "ceil":
        contracts = math.ceil(contracts)
    elif rounding == "round":
        contracts = round(contracts)
    else:
        contracts = math.floor(contracts)
    return (risk_btc, float(contracts))
