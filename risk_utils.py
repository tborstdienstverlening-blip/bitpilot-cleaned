# risk_utils.py — R0.2-04o (alleen rij-velden)
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
    if mode == "ceil":  return math.ceil(x)
    if mode == "round": return round(x)
    return math.floor(x)  # default

def contracts_from_row(cap_btc, risk_pct_value, entry, sl, rounding_cfg="floor"):
    """
    Deribit BTC-PERP (1 contract = $1).
    cap_btc: 'Kapitaal (trade)' (BTC)
    risk_pct_value: bijvoorbeeld 1.0 (=1%) of 0.01 (ook toegestaan)
    entry/sl: prijzen
    Returns: (risk_btc, contracts_int) of (None, None) bij ongeldige invoer
    """
    entry = _f(entry); sl = _f(sl)
    cap  = _f(cap_btc)
    if cap is None or entry is None or sl is None: return (None, None)
    if entry == 0 or entry == sl: return (None, None)

    rp = _f(risk_pct_value)
    if rp is None: return (None, None)
    risk_frac = rp/100.0 if rp > 1 else rp

    sl_distance_pct = abs(entry - sl) / entry
    if sl_distance_pct <= 0: return (None, None)

    risk_btc = float(cap) * risk_frac
    contracts = (risk_btc * entry) / sl_distance_pct
    contracts = round_contracts(contracts, str(rounding_cfg or "floor"))
    return (float(risk_btc), float(contracts))
