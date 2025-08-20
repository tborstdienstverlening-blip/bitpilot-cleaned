# utils/formatters.py
from __future__ import annotations
from typing import Optional

def format_btc(x: Optional[float], decimals: int = 3, fixed: bool = False) -> str:
    """
    BTC-waarde met duizendscheiding.
    - Standaard gedrag (compat): 3 dec + trim trailing nullen.
    - Als 'fixed=True': altijd exact 'decimals' decimalen (bijv. 8).
    None -> "—".
    """
    if x is None:
        return "—"
    v = float(x)
    if fixed:
        return f"{v:,.{decimals}f}"
    # legacy: trim nullen
    s = f"{v:,.{decimals}f}".rstrip("0").rstrip(".")
    return s

def format_btc_delta(x: Optional[float], suffix: str = "") -> Optional[str]:
    """
    Delta-tekst met teken en btc-format; None -> None (geen badge).
    """
    if x is None:
        return None
    sign = "+" if x > 0 else ""
    tail = f" {suffix}" if suffix else ""
    return f"{sign}{format_btc(x)}{tail}"

def format_pct_signed(pct: Optional[float], decimals: int = 2) -> str:
    """
    Percentage met teken en vaste decimalen; None -> "—".
    """
    if pct is None:
        return "—"
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:.{decimals}f}%"
