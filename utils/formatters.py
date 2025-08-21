# utils/formatters.py
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation, getcontext
from typing import Optional, Union

# Hoge precisie voor interne berekeningen; we ronden pas bij weergave.
getcontext().prec = 50

NumberLike = Union[int, float, str, Decimal]

def _to_decimal(x: Optional[NumberLike]) -> Optional[Decimal]:
    if x is None:
        return None
    if isinstance(x, Decimal):
        return x
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _apply_thousands(s: str) -> str:
    neg = s.startswith("-")
    if neg:
        s = s[1:]
    if "." in s:
        whole, frac = s.split(".", 1)
        whole_fmt = "{:,}".format(int(whole)).replace(",", " ")
        out = f"{whole_fmt}.{frac}"
    else:
        out = "{:,}".format(int(s)).replace(",", " ")
    return f"-{out}" if neg else out


def format_btc(
    x: Optional[NumberLike],
    decimals: int = 3,
    fixed: bool = False,
    thousands: bool = True,
) -> str:
    """
    BTC formatter.

    fixed=False: korte weergave tot 'decimals' dp (default 3), trim zeros.
    fixed=True: exact 'decimals' dp (trailing zeros), geen e-notatie, anti -0.000…:
                als afgerond == 0 → "0." + "0"*decimals.
    """
    d = _to_decimal(x)
    if d is None:
        return "-"

    q = Decimal(1).scaleb(-decimals)

    if fixed:
        d_q = d.quantize(q, rounding=ROUND_HALF_UP)
        if d_q == 0:
            s = "0" if decimals == 0 else "0." + ("0" * decimals)
        else:
            s = f"{d_q:.{decimals}f}"
        if thousands:
            s = _apply_thousands(s)
        return s

    d_q = d.quantize(q, rounding=ROUND_HALF_UP)
    if d_q == 0:
        s = "0"
    else:
        s = format(d_q, "f")
        if "." in s:
            s = s.rstrip("0").rstrip(".")
    if thousands and s not in ("-", "0"):
        s = _apply_thousands(s)
    return s


# --- Teruggeplaatste helpers (voor bestaande call-sites / KPI-tiles) ---------

def format_usd(
    x: Optional[NumberLike],
    decimals: int = 2,
    fixed: bool = False,
    thousands: bool = True,
    symbol: str = "$",
) -> str:
    d = _to_decimal(x)
    if d is None:
        return "-"
    q = Decimal(1).scaleb(-decimals)
    d_q = d.quantize(q, rounding=ROUND_HALF_UP)
    # Anti-negative-zero
    if d_q == 0:
        num = "0" if decimals == 0 else ("0." + ("0" * decimals) if fixed else "0")
    else:
        num = f"{d_q:.{decimals}f}" if fixed else format(d_q, "f")
        if not fixed and "." in num:
            num = num.rstrip("0").rstrip(".")
    if thousands:
        num = _apply_thousands(num)
    return f"{symbol}{num}"


def format_pct(
    x: Optional[NumberLike],
    decimals: int = 2,
    fixed: bool = True,
) -> str:
    """
    Percentage formatter. Accepteert zowel fractie (0.12) als procent (12).
    Heuristiek: |x| <= 1 → interpreteer als fractie, anders als procent.
    """
    d = _to_decimal(x)
    if d is None:
        return "-"
    val = d * 100 if abs(d) <= 1 else d
    q = Decimal(1).scaleb(-decimals)
    vq = val.quantize(q, rounding=ROUND_HALF_UP)
    # Anti -0.00%
    if vq == 0:
        num = "0" if decimals == 0 else "0." + ("0" * decimals)
    else:
        num = f"{vq:.{decimals}f}" if fixed else format(vq, "f").rstrip("0").rstrip(".")
    return f"{num}%"


def format_btc_delta(
    x: Optional[NumberLike],
    decimals: int = 3,
) -> str:
    """Korte deltaweergave met expliciet '+' voor positief."""
    d = _to_decimal(x)
    if d is None:
        return "-"
    s = format_btc(d, decimals=decimals, fixed=False, thousands=False)
    if d > 0:
        return f"+{s}"
    if d == 0:
        return "0"
    return s

