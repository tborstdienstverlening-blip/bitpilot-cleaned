# schema.py — centrale bron (NL)
COL = {
    "DATUM": "Datum",
    "TRADE_ID": "Trade_ID",
    "SETUP": "Setup_type",
    "TFS": "Gebruikte_TFs",
    "ENTRY": "Entry",
    "SL": "StopLoss",
    "TP": "TakeProfit",
    "RISICO_R": "Risico_R",
    "PNL": "PnL",
    "ROI": "ROI",
    "FEES": "Fees",
    "ACCOUNT": "Accountwaarde",
    "WIN": "Win_Loss",
    "TAGS": "Tags",
    "EMOTIES": "Emoties",
    "PLAN": "Plan",
    "NOTES": "Notities",
    "SHOTS": "Screenshots",
}
ORDER = [
    COL["DATUM"], COL["TRADE_ID"], COL["SETUP"], COL["TFS"], COL["ENTRY"], COL["SL"],
    COL["TP"], COL["RISICO_R"], COL["PNL"], COL["ROI"], COL["FEES"], COL["ACCOUNT"],
    COL["WIN"], COL["TAGS"], COL["EMOTIES"], COL["PLAN"], COL["NOTES"], COL["SHOTS"]
]
DATE_FMT = "%Y-%m-%d"

SETUP_OPTS = [
    "V-bottom", "Trap (liquidity)", "Retest", "Range-breakout",
    "Breakout-pullback", "Trend-continuation", "Mean-revert",
    "News-spike", "Anders/Custom"
]
