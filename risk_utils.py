# risk_utils.py — R0.2-04p (schaal & afronden: HALF_UP; alleen rij-velden)
from __future__ import annotations
import math
from decimal import Decimal, ROUND_HALF_UP

def _f(x):
    try:
        s = str(x).strip().replace(",", ".")
        return None if s == "" else float(s)
    except Exception:
        return None

def round_contracts_nearest(x: float) -> int:
    """Rond naar dichtstbijzijnde hele contract (HALF_UP)."""
    if x is None:
        return 0
    return int(Decimal(x).quantize(0, rounding=ROUND_HALF_UP))

def contracts_from_row(cap_btc, risk_pct_value, entry, sl):
    """
    Deribit BTC-PERP (1 contract = $1). Alleen rij-velden.
    cap_btc: 'Kapitaal (trade)' (BTC)
    risk_pct_value: bijv. 1.0 (==1%), 0.8 (==0.8%), enz.
    entry/sl: prijzen
    Returns: (risk_btc, contracts_int) of (None, None) bij ongeldige invoer
    """
    entry = _f(entry); sl = _f(sl); cap = _f(cap_btc)
    if entry is None or sl is None or cap is None: 
        return (None, None)
    if entry == 0 or entry == sl or cap <= 0:
        return (None, None)

    rp = _f(risk_pct_value)
    if rp is None or rp <= 0:
        return (None, None)

    # ✅ schaalfix: 1.0 => 1% => 0.01
    risk_frac = rp / 100.0

    sl_distance_pct = abs(entry - sl) / entry
    if sl_distance_pct <= 0:
        return (None, None)

    risk_btc = float(cap) * risk_frac
    raw_contracts = (risk_btc * entry) / sl_distance_pct
    contracts = round_contracts_nearest(raw_contracts)
    return (float(risk_btc), float(contracts))
