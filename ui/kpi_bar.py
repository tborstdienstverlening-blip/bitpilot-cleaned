# ui/kpi_bar.py
from __future__ import annotations

from typing import Any, Dict, Optional
import streamlit as st

from utils.formatters import format_btc, format_pct


def _int_or_zero(x: Any) -> int:
    try:
        return int(x or 0)
    except Exception:
        return 0


def _fmt_pct_or_dash(x: Optional[float]) -> str:
    """Toon 2dp percentage of '—' als niet beschikbaar."""
    if x is None:
        return "—"
    return format_pct(x, decimals=2, fixed=True)


def _fmt_winrate_with_arrow(winrate_val: Optional[float], kpi: Dict[str, Any]) -> str:
    """
    Winrate met optioneel trendpijltje (alleen tonen als key aanwezig is).
    Pakt één van de gangbare delta/trend keys als die bestaan.
    """
    base = _fmt_pct_or_dash(winrate_val)

    # Optionele trend/delta pijltjes: ▲/▼ alleen als key aanwezig is.
    delta_keys = ("winrate_delta", "winrate_change", "winrate_trend")
    delta = next((kpi.get(k) for k in delta_keys if k in kpi), None)
    try:
        if delta is None:
            return base
        dv = float(delta)
        if dv > 0:
            return f"▲ {base}"
        if dv < 0:
            return f"▼ {base}"
        return base
    except Exception:
        return base


def render(kpi: Dict[str, Any], start_btc: Optional[float]) -> None:
    """
    KPI-balk met 4 hoofdtiles (BTC) en daaronder de aanvullende metrics
    exact zoals gevraagd:

      Onder Startkapitaal (BTC)  : ROI %
      Onder Actueel (BTC)        : Winnende trades (count)
      Onder Totale PnL (BTC)     : Verloren trades (count)
      Onder Totale Fees (BTC)    : Winrate % (met pijltje indien aanwezig)

    BTC-weergave: exact 8dp, geen e-notatie, geen '-0.00000000'.
    Percentages: 2dp + '%'. Counts: integer. N/A → '—'.
    """
    # --- Hoofdtiles (BTC) — 8dp behouden ---
    acct_now = kpi.get("acct_now", 0) or 0
    pnl_btc_total = kpi.get("pnl_btc_total", 0) or 0
    fees_total = kpi.get("fees_total", 0) or 0

    c1, c2, c3, c4 = st.columns(4)

    # Tile 1 — Startkapitaal + ROI%
    with c1:
        st.metric(
            label="Startkapitaal (BTC)",
            value=format_btc(start_btc, decimals=8, fixed=True, thousands=False),
        )
        # ROI%: gebruik bestaande key-varianten uit service
        roi = kpi.get("roi_pct")
        if roi is None:
            roi = kpi.get("roi")
        st.caption(f"ROI: {_fmt_pct_or_dash(roi)}")

    # Tile 2 — Actueel + Winnende trades (count)
    with c2:
        st.metric(
            label="Actueel (BTC)",
            value=format_btc(acct_now, decimals=8, fixed=True, thousands=False),
        )
        winners = (
            kpi.get("winners_count", None)
            if "winners_count" in kpi
            else kpi.get("winners") or kpi.get("wins")
        )
        st.caption(f"Winnende trades: {_int_or_zero(winners)}")

    # Tile 3 — Totale PnL + Verloren trades (count)
    with c3:
        st.metric(
            label="Totale PnL (BTC)",
            value=format_btc(pnl_btc_total, decimals=8, fixed=True, thousands=False),
        )
        losers = (
            kpi.get("losers_count", None)
            if "losers_count" in kpi
            else kpi.get("losers") or kpi.get("losses")
        )
        st.caption(f"Verloren trades: {_int_or_zero(losers)}")

    # Tile 4 — Totale Fees + Winrate% (+ optioneel pijltje)
    with c4:
        st.metric(
            label="Totale Fees (BTC)",
            value=format_btc(fees_total, decimals=8, fixed=True, thousands=False),
        )
        winrate = kpi.get("winrate_pct")
        if winrate is None:
            winrate = kpi.get("winrate")
        st.caption(f"Winrate: {_fmt_winrate_with_arrow(winrate, kpi)}")


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

