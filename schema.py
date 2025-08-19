# schema.py — ENIGE bron voor kolomnamen + volgorde (NL)
COL = {
    "DATUM": "Datum",
    "TRADE_ID": "Trade_ID",
    "SETUP": "Setup_type",
    "TFS": "Gebruikte_TFs",

    "CONTRACT_SIZE": "Contract_size",
    "RR": "RR",

    "ENTRY": "Entry",
    "SL": "StopLoss",
    "TP": "TakeProfit",                 # legacy veld, blijft bestaan

    "TP1": "TP1",
    "TP2": "TP2",
    "TP3": "TP3",
    "PNL_TP1": "PNL_TP1",               # BTC
    "PNL_TP2": "PNL_TP2",               # BTC
    "PNL_TP3": "PNL_TP3",               # BTC
    "PNL_EXIT": "PNL_Exit",             # BTC (uiteindelijke exit)

    "PNL_TOTAL": "PNL_Total",           # NIEUW (verborgen in tabel, wel in export)

    "RISICO_R": "Risico_R",
    "PNL": "PnL",                       # totaal PnL (blijft voor compat)
    "ROI": "ROI",
    "FEES": "Fees",                     # BTC
    "ACCOUNT": "Accountwaarde",
    "WIN": "Win_Loss",
    "TAGS": "Tags",
    "EMOTIES": "Emoties",
    "PLAN": "Plan",
    "NOTES": "Notities",
    "SHOTS": "Screenshots",
}

# CSV/Export vaste kolomvolgorde (bevat ALLES, incl. PNL_Total en niet-zichtbaren)
ORDER = [
    COL["DATUM"], COL["TRADE_ID"], COL["SETUP"], COL["TFS"],
    COL["CONTRACT_SIZE"], COL["RR"],
    COL["ENTRY"], COL["SL"], COL["TP"],
    COL["TP1"], COL["TP2"], COL["TP3"],
    COL["PNL_TP1"], COL["PNL_TP2"], COL["PNL_TP3"], COL["PNL_EXIT"],
    COL["PNL_TOTAL"],
    COL["RISICO_R"], COL["PNL"], COL["ROI"], COL["FEES"], COL["ACCOUNT"],
    COL["WIN"], COL["TAGS"], COL["EMOTIES"], COL["PLAN"], COL["NOTES"], COL["SHOTS"],
]

DATE_FMT = "%Y-%m-%d"

SETUP_OPTS = [
    "V-bottom", "Trap (liquidity)", "Retest", "Range-breakout",
    "Breakout-pullback", "Trend-continuation", "Mean-revert",
    "News-spike", "Anders/Custom",
]
