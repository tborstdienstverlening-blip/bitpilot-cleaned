# schema.py — bron van waarheid kolommen
COL = {
    "DATUM": "Datum",
    "TRADE_ID": "Trade_ID",
    "SETUP": "Setup_type",
    "TFS": "Gebruikte_TFs",
    "ENTRY": "Entry",
    "SL": "StopLoss",
    "TP": "TakeProfit",
    "RISICO_R": "Risico_R",
    "EMOTIE": "Emotie",
    "TAGS": "Tags",
    "PLAN": "Plan",
    "WIN": "Win_Loss",
    "NOTES": "Notities",
}
REQUIRED_ORDER = [
    COL["DATUM"], COL["TRADE_ID"], COL["SETUP"], COL["TFS"], COL["ENTRY"],
    COL["SL"], COL["TP"], COL["RISICO_R"], COL["EMOTIE"], COL["TAGS"],
    COL["PLAN"], COL["WIN"], COL["NOTES"],
]
DATE_FMT = "%Y-%m-%d"
