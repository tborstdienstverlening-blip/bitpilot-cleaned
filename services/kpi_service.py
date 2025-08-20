# services/kpi_service.py
from __future__ import annotations
from typing import Dict, Optional
import pandas as pd
from schema import COL


def compute_kpis(df_filtered: pd.DataFrame, start_btc: float) -> Dict[str, Optional[float]]:
    """
    Exacte KPI-wiring zoals 07d:
    - Totale PnL (BTC) = Σ PNL_BTC
    - Actueel kapitaal = Start + Σ PNL_BTC − Σ Fees
    - ROI % = ((Actueel/Start)-1)*100 (guard)
    - Winrate op basis van PNL_Exit (>0 win, <0 loss)
    - Deltas 'laatste' (netto = PNL_BTC - Fees)
    """
    if df_filtered is None or df_filtered.empty:
        return dict(
            fees_total=0.0, pnl_btc_total=0.0, acct_now=start_btc, roi_pct=None,
            wins=0, losses=0, winrate_pct=None,
            last_pnl_exit=None, last_pnl_btc=None, last_fee=None,
            last_net=None, last_roi_pp=None, last_result=None,
            last_win_add=None, last_loss_add=None,
        )

    fees_series = pd.to_numeric(df_filtered[COL["FEES"]], errors="coerce").fillna(0.0)
    pnl_btc_series = pd.to_numeric(df_filtered["PNL_BTC"], errors="coerce").fillna(0.0)

    fees_total = float(fees_series.sum())
    pnl_btc_total = float(pnl_btc_series.sum())
    acct_now = (start_btc + pnl_btc_total - fees_total) if start_btc is not None else None

    if start_btc and start_btc != 0 and acct_now is not None:
        roi_pct = (acct_now / start_btc - 1.0) * 100.0
    else:
        roi_pct = None

    last_row = df_filtered.iloc[-1]
    last_pnl_exit = float(pd.to_numeric(pd.Series([last_row.get(COL["PNL_EXIT"])]), errors="coerce").fillna(0.0).iloc[0])
    last_pnl_btc = float(pd.to_numeric(pd.Series([last_row.get("PNL_BTC")]), errors="coerce").fillna(0.0).iloc[0])
    last_fee = float(pd.to_numeric(pd.Series([last_row.get(COL["FEES"])]), errors="coerce").fillna(0.0).iloc[0])
    last_net = last_pnl_btc - last_fee

    last_result = "Win" if last_pnl_exit > 0 else ("Loss" if last_pnl_exit < 0 else "Break-even")
    last_win_add = 1 if last_pnl_exit > 0 else None if last_pnl_exit == 0 else 0
    last_loss_add = 1 if last_pnl_exit < 0 else None if last_pnl_exit == 0 else 0

    pnl_exit_vals = pd.to_numeric(df_filtered[COL["PNL_EXIT"]], errors="coerce").fillna(0.0)
    wins = int((pnl_exit_vals > 0).sum())
    losses = int((pnl_exit_vals < 0).sum())
    winrate_pct = (wins / max(wins + losses, 1) * 100.0) if (wins + losses) > 0 else None

    if start_btc and start_btc != 0:
        last_roi_pp = (last_net / start_btc) * 100.0
    else:
        last_roi_pp = None

    return dict(
        fees_total=fees_total,
        pnl_btc_total=pnl_btc_total,
        acct_now=acct_now,
        roi_pct=roi_pct,
        wins=wins,
        losses=losses,
        winrate_pct=winrate_pct,
        last_pnl_exit=last_pnl_exit,
        last_pnl_btc=last_pnl_btc,
        last_fee=last_fee,
        last_net=last_net,
        last_roi_pp=last_roi_pp,
        last_result=last_result,
        last_win_add=last_win_add,
        last_loss_add=last_loss_add,
    )
