# utils/formatters.py
from __future__ import annotations
from typing import Optional


def format_btc(x: Optional[float]) -> str:
    """
    BTC-waarde met duizendscheiding en max 3 decimalen.
    Leeg -> "—".
    """
    if x is None:
        return "—"
    s = f"{float(x):,.3f}".rstrip("0").rstrip(".")
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

