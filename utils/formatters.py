# utils/formatters.py
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation, getcontext
from typing import Optional, Union

# Hoge precisie voor interne berekeningen; we ronden pas bij weergave.
getcontext().prec = 50

NumberLike = Union[int, float, str, Decimal]

def _to_decimal(x: Optional[NumberLike]) -> Optional[Decimal]:
    """Best-effort conversie naar Decimal zonder binaire float-artefacten."""
    if x is None:
        return None
    if isinstance(x, Decimal):
        return x
    try:
        # via str om 0.1→Decimal('0.1') te krijgen i.p.v. binaire ruis
        return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _apply_thousands(s: str) -> str:
    """Voeg duizendtallen toe aan het integer-deel van een decimaal getal."""
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
    Format een BTC-bedrag.

    - fixed=False (default): rond af op 'decimals' maar trim trailing zeros en punt.
      (Backwards-compatible: maximaal 3 dp + duizendtallen standaard aan.)
    - fixed=True: toon *exact* 'decimals' decimalen (met trailing zeros behouden),
      *geen* wetenschappelijke notatie, en anti-neg-zero:
        afgerond op 0  => "0." + "0"*decimals.

    Parameters
    ----------
    x : getal of None
    decimals : aantal decimalen voor afronding/weergave
    fixed : exact aantal decimalen tonen (trailing zeros)
    thousands : duizendtallen in integer-deel (default True; call-sites kunnen uitzetten)

    Returns
    -------
    str : weergavestring (bij None of ongeldige input: "-")
    """
    d = _to_decimal(x)
    if d is None:
        return "-"

    # Kwantisatie-unit, bv. 10^-8
    q = Decimal(1).scaleb(-decimals)

    if fixed:
        d_q = d.quantize(q, rounding=ROUND_HALF_UP)

        # Anti-negative-zero
        if d_q == 0:
            s = "0" if decimals == 0 else "0." + ("0" * decimals)
        else:
            # Exact 'decimals' decimalen, geen e-notatie
            s = f"{d_q:.{decimals}f}"

        if thousands:
            s = _apply_thousands(s)
        return s

    # Niet-fixed: "korte" weergave met max 'decimals' dp, trim trailing zeros.
    d_q = d.quantize(q, rounding=ROUND_HALF_UP)
    # Als exact 0 na afronding: toon "0" (zonder -0)
    if d_q == 0:
        s = "0"
    else:
        # 'f' forceert fixed-point representatie (geen e-notatie)
        s = format(d_q, "f")
        if "." in s:
            s = s.rstrip("0").rstrip(".")

    if thousands and s not in ("-", "0"):
        s = _apply_thousands(s)
    return s
