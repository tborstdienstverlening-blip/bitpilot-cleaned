# tests_kpi.py — unit tests R0.2-04a
import pandas as pd
from schema import COL
from kpi_utils import with_pnl_total, compute_kpis

def test_exit_takes_precedence_over_tps():
    rows = [
        # Exit gevuld -> neemt Exit, negeert TP's
        {COL["PNL_TP1"]:"0.2", COL["PNL_TP2"]:"0.1", COL["PNL_TP3"]:"0.0",
         COL["PNL_EXIT"]:"0.05", COL["FEES"]:"0.005", COL["DATUM"]:"2025-08-01"},
        # Exit leeg -> som TP's
        {COL["PNL_TP1"]:"0.01", COL["PNL_TP2"]:"0.02", COL["PNL_TP3"]:"", 
         COL["PNL_EXIT"]:"", COL["FEES"]:"0.001", COL["DATUM"]:"2025-08-02"},
        # verlies
        {COL["PNL_TP1"]:"", COL["PNL_TP2"]:"", COL["PNL_TP3"]:"", 
         COL["PNL_EXIT"]:"-0.02", COL["FEES"]:"0.002", COL["DATUM"]:"2025-08-03"},
    ]
    df = pd.DataFrame(rows)
    df = with_pnl_total(df)
    k = compute_kpis(df, start_btc=1.0, rolling_n=2)

    # Totals
    expected_pnl = 0.05 + (0.01+0.02) + (-0.02)
    expected_fees = 0.005 + 0.001 + 0.002
    assert abs(k["pnl"] - expected_pnl) < 1e-9
    assert abs(k["fees"] - expected_fees) < 1e-9

    # Win/Loss: exit>0 = win, exit<=0 = loss; tweede rij exit leeg -> TP som = 0.03 (win)
    assert k["wins"] == 2
    assert k["losses"] == 1

    # ROI
    actueel = 1.0 + expected_pnl - expected_fees
    roi = (actueel - 1.0)/1.0*100
    assert abs(k["roi_pct"] - roi) < 1e-9

    # Rolling (laatste 2 trades: rij2 en rij3: win (0.03) + loss (-0.02) => 50%)
    assert abs(k["rolling_winrate_pct"] - 50.0) < 1e-9
