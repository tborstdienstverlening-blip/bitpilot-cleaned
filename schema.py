from __future__ import annotations
from typing import List
COL={"DATUM":"Datum","TRADE_ID":"Trade_ID","SETUP":"Setup_type","STRATEGIE":"Strategie","TFS":"Gebruikte_TFs","PLAN_SHORT":"Plan","ENTRY":"Entry","STOPLOSS":"Stoploss","RISK_PCT":"Risk_%","R_INZET":"R_inzet","TP1":"TP1","TP2":"TP2","TP3":"TP3","UITKOMST":"Uitkomst","RR_REAL":"RR_realized","PLAN_TROUW":"Plantrouw","EMOTIES":"Emoties","TAGS":"Tags","NOTITIES":"Notities","STATUS":"Status","SCREEN1":"Screenshot_1","SCREEN2":"Screenshot_2","SCREEN3":"Screenshot_3","SCREEN4":"Screenshot_4","SCREEN5":"Screenshot_5","SCREEN6":"Screenshot_6","RESULT_PNL":"Resultaat_PnL","ROI_SIMPLE":"ROI_%","FEES":"Fees","TA_SUMMARY":"TA_Summary","AI_PREFLIGHT_STATUS":"AI_Preflight_Status","AI_PREFLIGHT_NOTES":"AI_Preflight_Notes","AI_LAST_ADVICE":"AI_Eindadvies_Last","AI_SETUP":"AI_Setup_Type"}
ALIAS={"date":COL["DATUM"],"tradeid":COL["TRADE_ID"],"setup":COL["SETUP"],"strategy":COL["STRATEGIE"],"tfs":COL["TFS"],"plan":COL["PLAN_SHORT"],"entry":COL["ENTRY"],"stop":COL["STOPLOSS"],"risk":COL["RISK_PCT"],"r":COL["R_INZET"],"tp1":COL["TP1"],"tp2":COL["TP2"],"tp3":COL["TP3"],"result":COL["UITKOMST"],"rr":COL["RR_REAL"],"pnl":COL["RESULT_PNL"],"roi":COL["ROI_SIMPLE"],"fees":COL["FEES"]}
def canonical_columns()->List[str]:
    order=[COL["DATUM"],COL["TRADE_ID"],COL["STATUS"],COL["STRATEGIE"],COL["SETUP"],COL["TFS"],COL["PLAN_SHORT"],COL["ENTRY"],COL["STOPLOSS"],COL["RISK_PCT"],COL["R_INZET"],COL["TP1"],COL["TP2"],COL["TP3"],COL["RESULT_PNL"],COL["RR_REAL"],COL["ROI_SIMPLE"],COL["FEES"],COL["UITKOMST"],COL["PLAN_TROUW"],COL["EMOTIES"],COL["TAGS"],COL["NOTITIES"],COL["TA_SUMMARY"],COL["AI_PREFLIGHT_STATUS"],COL["AI_PREFLIGHT_NOTES"],COL["AI_LAST_ADVICE"],COL["AI_SETUP"],COL["SCREEN1"],COL["SCREEN2"],COL["SCREEN3"],COL["SCREEN4"],COL["SCREEN5"],COL["SCREEN6"]]
    seen=set(); uniq=[c for c in order if not (c in seen or seen.add(c))]; return uniq
def ensure_columns(df):
    for c in canonical_columns():
        if c not in df.columns: df[c]=None
    return df
