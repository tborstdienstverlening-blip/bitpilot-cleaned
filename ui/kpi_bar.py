# ui/kpi_bar.py
from __future__ import annotations

from typing import Any, Dict, Optional
import streamlit as st

from utils.formatters import format_btc


# --- Helpers (inline, geen nieuwe deps) --------------------------------------

def _int_or_zero(x: Any) -> int:
    try:
        return int(x or 0)
    except Exception:
        return 0


def _fmt_pct(value: Optional[float], decimals: int = 2) -> str:
    """
    Percentage als vaste string met 'decimals' decimalen + '%'.
    Bij None → '—'. Anti '-0.00%'.
    Accepteert zowel fractie (0.12) als procent (12).
    Heuristiek: |x| <= 1 → interpreteer als fractie (×100).
    """
    if value is None:
        return "—"
    try:
        v = float(value)
    except Exception:
        return "—"
    v = v * 100.0 if abs(v) <= 1.0 else v
    # afronden en anti negative-zero
    s = f"{v:.{decimals}f}"
    # normaliseer -0.00 → 0.00
    if float(s) == 0.0:
        s = f"{0:.{decimals}f}"
    return f"{s}%"


def _extract_counts(kpi: Dict[str, Any]) -> tuple[int, int]:
    """Zet winners/losers naar integers met ruime key-fallbacks."""
    wins = (
        kpi.get("winners_count", None)
        if "winners_count" in kpi
        else kpi.get("winners") or kpi.get("wins")
    )
    losses = (
        kpi.get("losers_count", None)
        if "losers_count" in kpi
        else kpi.get("losers") or kpi.get("losses")
    )
    return _int_or_zero(wins), _int_or_zero(losses)


# --- Render ------------------------------------------------------------------

def render(kpi: Dict[str, Any], start_btc: Optional[float]) -> None:
    """
    KPI-balk met 4 hoofdtiles (BTC op 8dp) en exact deze onderregels:

      Onder Startkapitaal (BTC)  →  ROI %          (2dp; '—' bij N/A)
      Onder Actueel (BTC)        →  Winnende trades (integer)
      Onder Totale PnL (BTC)     →  Verloren trades (integer)
      Onder Totale Fees (BTC)    →  Winrate %      (2dp; '—' bij N/A)

    BTC-weergave: exact 8dp, geen e-notatie, geen '-0.00000000'.
    """
    # Hoofdtiles (BTC) — 8dp behouden
    acct_now = kpi.get("acct_now", 0) or 0
    pnl_btc_total = kpi.get("pnl_btc_total", 0) or 0
    fees_total = kpi.get("fees_total", 0) or 0

    wins, losses = _extract_counts(kpi)
    total_trades = wins + losses

    # Percent-keys (reuse bestaande keys; bij 0 trades tonen we '—')
    roi_val = kpi.get("roi_pct")
    if roi_val is None:
        roi_val = kpi.get("roi")

    winrate_val = kpi.get("winrate_pct")
    if winrate_val is None:
        winrate_val = kpi.get("winrate")

    c1, c2, c3, c4 = st.columns(4)

    # 1) Startkapitaal + ROI %
    with c1:
        st.metric(
            label="Startkapitaal (BTC)",
            value=format_btc(start_btc, decimals=8, fixed=True, thousands=False),
        )
        roi_str = "—" if total_trades == 0 else _fmt_pct(roi_val, decimals=2)
        st.caption(f"ROI % {roi_str}")

    # 2) Actueel + Winnende trades
    with c2:
        st.metric(
            label="Actueel (BTC)",
            value=format_btc(acct_now, decimals=8, fixed=True, thousands=False),
        )
        st.caption(f"Winnende trades {wins}")

    # 3) Totale PnL + Verloren trades
    with c3:
        st.metric(
            label="Totale PnL (BTC)",
            value=format_btc(pnl_btc_total, decimals=8, fixed=True, thousands=False),
        )
        st.caption(f"Verloren trades {losses}")

    # 4) Totale Fees + Winrate %
    with c4:
        st.metric(
            label="Totale Fees (BTC)",
            value=format_btc(fees_total, decimals=8, fixed=True, thousands=False),
        )
        winrate_str = "—" if total_trades == 0 else _fmt_pct(winrate_val, decimals=2)
        st.caption(f"Winrate % {winrate_str}")


def render_kpi_bar(a: Any, b: Any) -> None:
    """
    Backwards-compatible wrapper:
    ondersteunt zowel (kpi, start_btc) als (start_btc, kpi).
    """
    if isinstance(a, dict) and not isinstance(b, dict):
        kpi, start_btc = a, b
    elif isinstance(b, dict) and not isinstance(a, dict):
        kpi, start_btc = b, a
    else:
        # Legacy volgorde (start_btc, kpi) fallback
        start_btc, kpi = a, b
    render(kpi, start_btc)
