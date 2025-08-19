# schema.py — centrale schema/labels/volgorde (R0.2-04f)
from __future__ import annotations

DATE_FMT = "%Y-%m-%d"

# NL labels (één bron)
COL = {
    "DATUM": "Datum",
    "TRADE_ID": "Trade_ID",
    "SIDE": "Side",  # "Long" of "Short"
    "SETUP": "Setup_type",
    "RISK_BTC": "Risk",                 # auto, BTC
    "CONTRACT_SIZE": "Contract size",   # auto, contracts (Deribit 1c=$1)
    "RR_PLAN": "RR (Plan)",             # auto, 2 dec
    "RR_ACTUAL": "RR (Actueel)",        # auto, 2 dec (ΣTP-PNL−Fees)/risk_btc
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
    "EMOTIES": "Emoties",
    "TAGS": "Tags",
    "SHOTS": "Screenshots",

    # Bestaande/compat velden die we in dataset willen behouden
    "TFS": "Gebruikte_TFs",
    "RISICO_R": "Risico_R",
    "PNL": "PnL",
    "ROI": "ROI",
    "ACCOUNT": "Accountwaarde",
    "WIN": "Win_Loss",
    "PLAN": "Plan",
    "NOTES": "Notities",
    "PNL_TOTAL": "PNL_Total",  # intern/ export
}

# Setup dropdown opties (incl. Custom)
SETUP_OPTS = [
    "V-bottom","Trap (liquidity)","Retest","Range-breakout","Breakout-pullback",
    "Trend-continuation","Mean-revert","News-spike","Anders/Custom"
]

# Volgorde voor CSV/export (bevat ook hidden velden; zichtbaar regelen we in cockpit)
ORDER = [
    COL["DATUM"], COL["TRADE_ID"], COL["SIDE"], COL["SETUP"],
    COL["RISK_BTC"], COL["CONTRACT_SIZE"], COL["RR_PLAN"], COL["RR_ACTUAL"],
    COL["ENTRY"], COL["SL"], COL["TP1"], COL["TP2"], COL["TP3"],
    COL["FEES"], COL["PNL_TP1"], COL["PNL_TP2"], COL["PNL_TP3"], COL["PNL_EXIT"],
    COL["EMOTIES"], COL["TAGS"], COL["SHOTS"],
    # compat/overig achteraan:
    COL["TFS"], COL["RISICO_R"], COL["PNL"], COL["ROI"], COL["ACCOUNT"], COL["WIN"], COL["PLAN"], COL["NOTES"], COL["PNL_TOTAL"],
]
