# ui/kpi_bar.py
from __future__ import annotations

from typing import Any, Dict, Optional

import streamlit as st

from utils.formatters import format_btc


def render(kpi: Dict[str, Any], start_btc: Optional[float]) -> None:
    """
    Rendert de KPI-balk met 4 tiles in BTC, exact 8 decimalen (trailing zeros),
    geen wetenschappelijke notatie en geen -0.00000000.
    Keys komen uit services/kpi_service.compute_kpis:
      - acct_now
      - pnl_btc_total
      - fees_total
    """
    acct_now = kpi.get("acct_now", 0) or 0
    pnl_btc_total = kpi.get("pnl_btc_total", 0) or 0
    fees_total = kpi.get("fees_total", 0) or 0

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric(
            label="Startkapitaal (BTC)",
            value=format_btc(start_btc, decimals=8, fixed=True, thousands=False),
        )

    with c2:
        st.metric(
            label="Actueel (BTC)",
            value=format_btc(acct_now, decimals=8, fixed=True, thousands=False),
        )

    with c3:
        st.metric(
            label="Totale PnL (BTC)",
            value=format_btc(pnl_btc_total, decimals=8, fixed=True, thousands=False),
        )

    with c4:
        st.metric(
            label="Totale Fees (BTC)",
            value=format_btc(fees_total, decimals=8, fixed=True, thousands=False),
        )


# Alias voor bestaande call-sites die mogelijk een andere naam gebruiken
def render_kpi_bar(kpi: Dict[str, Any], start_btc: Optional[float]) -> None:
    render(kpi, start_btc)
