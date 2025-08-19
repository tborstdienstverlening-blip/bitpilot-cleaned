# risk_utils.py — Backend Risk & Contract Size (Deribit BTC-PERP; 1 contract = $1)
from __future__ import annotations
import math

def _f(x):
    try:
        s = str(x).strip().replace(",", ".")
        return None if s == "" else float(s)
    except Exception:
        return None

def round_contracts(x: float, mode: str = "floor") -> int:
    if x is None: return 0
    if mode == "ceil": return math.ceil(x)
    if mode == "round": return round(x)
    return math.floor(x)  # default

def contracts_from_risk_pct(account_btc: float, risk_pct_value, entry, sl, rounding_cfg="floor"):
    """
    Per rij: Risk % (kan 1.0 of 0.01 betekenen; beide accepteren)
    """
    entry = _f(entry); sl = _f(sl)
    if account_btc is None or entry is None or sl is None: return (None, None)
    if entry == 0 or entry == sl: return (None, None)

    rp = _f(risk_pct_value)
    if rp is None: return (None, None)
    risk_frac = rp/100.0 if rp > 1 else rp

    sl_distance_pct = abs(entry - sl) / entry
    if sl_distance_pct <= 0: return (None, None)

    risk_btc = float(account_btc) * risk_frac
    contracts = (risk_btc * entry) / sl_distance_pct
    contracts = round_contracts(contracts, str(rounding_cfg or "floor"))
    return (float(risk_btc), float(contracts))
