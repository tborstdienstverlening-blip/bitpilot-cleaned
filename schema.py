# schema.py — R0.2-04o
from __future__ import annotations

DATE_FMT = "%Y-%m-%d"

COL = {
    "DATUM": "Datum",
    "TRADE_ID": "Trade_ID",
    "SIDE": "Richting",                 # Long/Short
    "SETUP": "Setup_type",

    "RISK_PCT": "Risk %",               # editbaar per rij (0.1–5.0)
    "CAP_TRADE": "Kapitaal (trade)",    # editbaar (BTC)
    "CONTRACT_SIZE": "Contract size",   # auto (contracts, Deribit $1/contract)

    "RR_PLAN": "RR (Plan)",             # auto, 2 dec
    "RR_ACTUAL": "RR (Actueel)",        # auto, 2 dec (netto / rij-risk)

    "ENTRY": "Entry",
    "SL": "StopLoss",
    "TP1": "TP1",
    "TP2": "TP2",
    "TP3": "TP3",

    "FEES": "Fees",
    "PNL_TP1": "PNL_TP1",
    "PNL_TP2": "PNL_TP2",
    "PNL_TP3": "PNL_TP3",
    "PNL_EXIT": "PNL_Exit",

    "PLAN": "Plan",
    "NOTES": "Notities",
    "EMOTIES": "Emoties",
    "SHOTS": "Screenshots",

    # compat (blijven in CSV/export maar niet in tabel)
    "TFS": "Gebruikte_TFs",
    "RISICO_R": "Risico_R",
    "PNL": "PnL",
    "ROI": "ROI",
    "ACCOUNT": "Accountwaarde",
    "WIN": "Win_Loss",
    "PNL_TOTAL": "PNL_Total",  # ΣTP of fallback Exit (zonder Fees); KPI trekt Fees af
}

SETUP_OPTS = [
    "V-bottom","Trap (liquidity)","Retest","Range-breakout","Breakout-pullback",
    "Trend-continuation","Mean-revert","News-spike","Anders/Custom"
]

# Definitieve export-volgorde (zonder Tags en zonder Risk (BTC))
ORDER = [
    COL["DATUM"], COL["TRADE_ID"], COL["SIDE"], COL["SETUP"],
    COL["RISK_PCT"], COL["CAP_TRADE"], COL["CONTRACT_SIZE"],
    COL["RR_PLAN"], COL["RR_ACTUAL"],
    COL["ENTRY"], COL["SL"], COL["TP1"], COL["TP2"], COL["TP3"],
    COL["FEES"], COL["PNL_TP1"], COL["PNL_TP2"], COL["PNL_TP3"], COL["PNL_EXIT"],
    COL["PLAN"], COL["NOTES"], COL["EMOTIES"], COL["SHOTS"],
    # compat achteraan:
    COL["TFS"], COL["RISICO_R"], COL["PNL"], COL["ROI"], COL["ACCOUNT"], COL["WIN"], COL["PNL_TOTAL"],
]
