# ui/kpi_bar.py
from __future__ import annotations

from typing import Any, Dict, Optional
import streamlit as st

from utils.formatters import format_btc, format_usd, format_pct


def render(kpi: Dict[str, Any], start_btc: Optional[float]) -> None:
    """
    KPI-balk:
      Rij 1 (BTC, 8dp): Startkapitaal, Actueel, Totale PnL, Totale Fees
      Rij 2 (overige): ROI%, Winrate (All)%, Winrate (Recent)%, Actueel (USD) of Totale PnL (USD)

    Keys (services/kpi_service.compute_kpis):
      - acct_now, pnl_btc_total, fees_total
      - roi_pct (of roi), winrate_overall|winrate_total, winrate_recent|winrate_30d
      - acct_now_usd of pnl_usd_total (fallback)
    """
    # --- BTC rij (vast 8dp, geen wetenschappelijke notatie, anti -0) ---
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

    # --- Rij 2: overige 4 tiles teruggezet (alleen renderen als data aanwezig is) ---
    roi = kpi.get("roi_pct")
    if roi is None:
        roi = kpi.get("roi")

    wr_all = (
        kpi.get("winrate_overall")
        if "winrate_overall" in kpi
        else kpi.get("winrate_total") or kpi.get("wr_all")
    )

    wr_recent = (
        kpi.get("winrate_recent")
        if "winrate_recent" in kpi
        else kpi.get("winrate_30d") or kpi.get("wr_recent")
    )

    acct_now_usd = kpi.get("acct_now_usd") or kpi.get("account_usd")
    pnl_usd_total = kpi.get("pnl_usd_total") or kpi.get("pnl_total_usd")

    d1, d2, d3, d4 = st.columns(4)

    with d1:
        if roi is not None:
            st.metric(label="ROI", value=format_pct(roi, decimals=2, fixed=True))
    with d2:
        if wr_all is not None:
            st.metric(label="Winrate (All)", value=format_pct(wr_all, decimals=1, fixed=True))
    with d3:
        if wr_recent is not None:
            st.metric(label="Winrate (Recent)", value=format_pct(wr_recent, decimals=1, fixed=True))
    with d4:
        # Toon bij voorkeur Actueel (USD), anders Totale PnL (USD) als fallback.
        if acct_now_usd is not None:
            st.metric(label="Actueel (USD)", value=format_usd(acct_now_usd, decimals=2, fixed=True))
        elif pnl_usd_total is not None:
            st.metric(label="Totale PnL (USD)", value=format_usd(pnl_usd_total, decimals=2, fixed=True))


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

