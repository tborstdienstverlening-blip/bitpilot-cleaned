# utils/formatters.py
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation, getcontext
from typing import Optional, Any

# Voldoende precisie voor BTC (8+ decimalen) zonder vroegtijdig afronden
getcontext().prec = 28


def to_decimal(val: Any) -> Optional[Decimal]:
    """
    Parser die zowel '.' als ',' accepteert. Leeg/ongeldig -> None.
    """
    if val is None:
        return None
    s = str(val).strip()
    if s == "":
        return None
    s = s.replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _trim_neg_zero(s: str) -> str:
    # voorkom '-0' of '-0.00000000'
    if s.startswith("-"):
        try:
            if Decimal(s) == Decimal("0"):
                return "0"
        except Exception:
            pass
    return s


def format_btc(value: Optional[float | Decimal]) -> str:
    """
    Compact render voor KPI/labels:
    - tot 8 decimalen, nooit wetenschappelijke notatie
    - trailing nullen en punt verwijderen
    - nooit NaN of '-0'
    """
    if value is None:
        return "—"
    d = value if isinstance(value, Decimal) else to_decimal(value)
    if d is None:
        return "—"
    q = d.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
    s = f"{q:.8f}".rstrip("0").rstrip(".")
    return _trim_neg_zero(s) if s else "0"


def format_btc_delta(value: Optional[float | Decimal], suffix: str = "") -> Optional[str]:
    """
    Delta-tekst met teken en format_btc; None -> None (geen badge).
    """
    if value is None:
        return None
    d = value if isinstance(value, Decimal) else to_decimal(value)
    if d is None:
        return None
    sign = "+" if d > 0 else ""
    core = format_btc(d)
    return f"{sign}{core}{(' ' + suffix) if suffix else ''}"


def format_btc_fixed8(value: Optional[float | Decimal]) -> str:
    """
    Exact 8 decimalen (voor tabelweergave), geen wetenschappelijke notatie.
    Leeg -> "".
    """
    if value is None:
        return ""
    d = value if isinstance(value, Decimal) else to_decimal(value)
    if d is None:
        return ""
    q = d.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
    s = f"{q:.8f}"
    return _trim_neg_zero(s)


def format_pct_signed(pct: Optional[float], decimals: int = 2) -> str:
    """
    Percentage met teken en vaste decimalen; None -> "—".
    Vermijdt '-0.00%' door 0 altijd positief weer te geven.
    """
    if pct is None:
        return "—"
    try:
        d = float(pct)
    except Exception:
        return "—"
    s = f"{d:.{decimals}f}"
    try:
        # normaliseer -0.00 -> 0.00
        if Decimal(s) == 0:
            s = f"{0:.{decimals}f}"
    except Exception:
        pass
    sign = "+" if d > 0 else ""
    return f"{sign}{s}%"
