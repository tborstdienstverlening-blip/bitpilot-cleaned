# ui/kpi_bar.py
from __future__ import annotations

from typing import Any, Dict, Optional
import streamlit as st

from utils.formatters import format_btc


# -------------------- Helpers (inline; geen nieuwe deps) --------------------

def _int_or_zero(x: Any) -> int:
    try:
        return int(x or 0)
    except Exception:
        return 0


def _fmt_pct(value: Optional[float], decimals: int = 2) -> str:
    """
    Percentage-string met 'decimals' decimalen + '%'.
    - None  -> '—'
    - Heuristiek: |x| <= 1 wordt geïnterpreteerd als fractie (×100)
    - Anti '−0.00%': normaliseer naar '0.00%'
    """
    if value is None:
        return "—"
    try:
        v = float(value)
    except Exception:
        return "—"
    v = v * 100.0 if abs(v) <= 1.0 else v
    s = f"{v:.{decimals}f}"
    # Anti negative zero
    if float(s) == 0.0:
        s = f"{0:.{decimals}f}"
    return f"{s}%"


def _winrate_with_indicator(winrate_val: Optional[float], kpi: Dict[str, Any]) -> str:
    """
    Winrate met bestaand indicator/pijltje behouden:
    - Als 'winrate_indicator' (bv. '▲'/'▼') bestaat, gebruik die.
    - Anders leid pijltje af uit 'winrate_delta' of 'winrate_change' (>0 ▲, <0 ▼).
    - Als geen indicator-keys: toon alleen het percentage.
    """
    pct = _fmt_pct(winrate_val, decimals=2)
    # Als '—', geen pijltje tonen
    if pct == "—":
        return pct

    ind = kpi.get("winrate_indicator")
    if isinstance(ind, str) and ind.strip():
        return f"{ind.strip()} {pct}"

    for dk in ("winrate_delta", "winrate_change"):
        dv = kpi.get(dk)
        if dv is None:
            continue
        try:
            dvf = float(dv)
        except Exception:
            continue
        if dvf > 0:
            return f"▲ {pct}"
        if dvf < 0:
            return f"▼ {pct}"
        break  # dvf == 0 -> geen pijltje

    return pct


# ------------------------------ Render -------------------------------------

def render(kpi: Dict[str, Any], start_btc: Optional[float]) -> None:
    """
    KPI-balk (parity restore + 8dp):
    Hoofdtiles (BTC) exact 8 decimalen; onderregels/labels/indicatoren identiek aan referentie:

      Onder Startkapitaal (BTC)  ->  ROI %
      Onder Actueel (BTC)        ->  Winnende trades
      Onder Totale PnL (BTC)     ->  Verloren trades
      Onder Totale Fees (BTC)    ->  Winrate %    (met pijltje/indicator indien aanwezig)

    BTC-weergave: 8dp (trailing zeros), geen e-notatie, geen '-0.00000000'.
    Percentages: 2dp + '%', bij N/A '—'. Counts: integers.
    """
    # --- Hoofdtiles (BTC) — 8dp behouden ---
    acct_now = kpi.get("acct_now", 0) or 0
    pnl_btc_total = kpi.get("pnl_btc_total", 0) or 0
    fees_total = kpi.get("fees_total", 0) or 0

    # Keys volgens ticket (met minimale fallback voor backward compat)
    winners = kpi.get("winners")
    if winners is None:
        winners = kpi.get("winners_count") or kpi.get("wins")
    losers = kpi.get("losers")
    if losers is None:
        losers = kpi.get("losers_count") or kpi.get("losses")

    wins_i = _int_or_zero(winners)
    losses_i = _int_or_zero(losers)
    total_trades = wins_i + losses_i

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
        # Let op: exact label zonder dubbele punt
        st.caption(f"ROI % {roi_str}")

    # 2) Actueel + Winnende trades
    with c2:
        st.metric(
            label="Actueel (BTC)",
            value=format_btc(acct_now, decimals=8, fixed=True, thousands=False),
        )
        st.caption(f"Winnende trades {wins_i}")

    # 3) Totale PnL + Verloren trades
    with c3:
        st.metric(
            label="Totale PnL (BTC)",
            value=format_btc(pnl_btc_total, decimals=8, fixed=True, thousands=False),
        )
        st.caption(f"Verloren trades {losses_i}")

    # 4) Totale Fees + Winrate % (+ indicator indien aanwezig)
    with c4:
        st.metric(
            label="Totale Fees (BTC)",
            value=format_btc(fees_total, decimals=8, fixed=True, thousands=False),
        )
        winrate_str = "—" if total_trades == 0 else _winrate_with_indicator(winrate_val, kpi)
        st.caption(f"Winrate % {winrate_str}")


def render_kpi_bar(a: Any, b: Any) -> None:
    """
    Backwards-compatible wrapper:
    ondersteunt zowel (kpi, start_btc) als (start_btc, kpi).
    (cockpit.py riep legacy volgorde aan)
    """
    if isinstance(a, dict) and not isinstance(b, dict):
        kpi, start_btc = a, b
    elif isinstance(b, dict) and not isinstance(a, dict):
        kpi, start_btc = b, a
    else:
        # Legacy volgorde (start_btc, kpi) fallback
        start_btc, kpi = a, b
    render(kpi, start_btc)
