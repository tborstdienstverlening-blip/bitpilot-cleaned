# ui/kpi_bar.py
from __future__ import annotations
import streamlit as st
from utils.formatters import format_btc, format_btc_delta, format_pct_signed


def render_kpi_bar(start_btc: float, kpi: dict) -> None:
    """
    Rendert KPI-balk exact zoals 07d (labels en onderbalkjes).
    """
    r1 = st.columns(4)
    r2 = st.columns(4)

    # Rij 1
    r1[0].metric("Startkapitaal (BTC)", format_btc(start_btc))
    r1[1].metric(
        "Actueel kapitaal (BTC)",
        format_btc(kpi["acct_now"]),
        delta=format_btc_delta(kpi.get("last_net"), "laatste trade"),
    )
    r1[2].metric(
        "Totale PnL (BTC)",
        format_btc(kpi["pnl_btc_total"]),
        delta=format_btc_delta(kpi.get("last_pnl_btc"), "laatste trade"),
    )
    r1[3].metric(
        "Totale Fees (BTC)",
        format_btc(kpi["fees_total"]),
        delta=format_btc_delta(kpi.get("last_fee")),
    )

    # Rij 2
    r2[0].metric("ROI %", format_pct_signed(kpi["roi_pct"]), delta=(format_pct_signed(kpi.get("last_roi_pp")) if kpi.get("last_roi_pp") is not None else None))
    last_win_add = kpi.get("last_win_add")
    last_loss_add = kpi.get("last_loss_add")
    r2[1].metric("Winnende trades", f"{kpi['wins']}", delta=(f"+{last_win_add}" if last_win_add is not None else None))
    r2[2].metric("Verloren trades", f"{kpi['losses']}", delta=(f"+{last_loss_add}" if last_loss_add is not None else None))
    last_result_text = "—" if kpi.get("last_result") is None else f"Laatst: {kpi['last_result']}"
    winrate_pct = kpi.get("winrate_pct")
    r2[3].metric("Winrate %", ("—" if winrate_pct is None else f"{winrate_pct:.2f}%"), delta=last_result_text)
