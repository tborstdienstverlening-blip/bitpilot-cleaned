# tests_kpi.py — simpele unit tests voor KPI-berekeningen
import pandas as pd
from schema import COL
from kpi_utils import with_pnl_total, compute_kpis

def _df():
    rows = [
        {COL["PNL_TP1"]: "0.1", COL["PNL_TP2"]:"0.0", COL["PNL_TP3"]:"", COL["PNL_EXIT"]:"-0.02", COL["FEES"]:"0.005", COL["WIN"]:"Win",  COL["DATUM"]:"2025-01-02"},
        {COL["PNL_TP1"]: "0.0", COL["PNL_TP2"]:"0.0", COL["PNL_TP3"]:"", COL["PNL_EXIT"]:"-0.01", COL["FEES"]:"0.003", COL["WIN"]:"Loss", COL["DATUM"]:"2025-01-03"},
    ]
    return pd.DataFrame(rows)

def test_pnl_total_and_kpis():
    df = with_pnl_total(_df())
    k = compute_kpis(df, start_btc=1.0, rolling_n=2)
    assert round(k["pnl"], 6) == round(0.1 - 0.02 - 0.01, 6)
    assert round(k["fees"], 6) == round(0.005 + 0.003, 6)
    assert k["wins"] == 1 and k["losses"] == 1
    assert k["winrate_pct"] == 50.0
    assert k["rolling_winrate_pct"] == 50.0
