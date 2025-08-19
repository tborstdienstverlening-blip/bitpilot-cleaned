from __future__ import annotations
import time
import numpy as np
import streamlit as st
import pandas as pd
from math import ceil

from schema import COL, ORDER, DATE_FMT, SETUP_OPTS
from utils_config import load_config, format_btc
from journal_store import load_journal, append_entry, update_entry, delete_entry
from import_export import export_visible
from app_state import load_state, save_state

# JS-fix: page_config zo vroeg mogelijk
st.set_page_config(page_title="Bitpilot — Journal", layout="wide")

# veilige import healthcheck
try:
    import healthcheck
except Exception:
    healthcheck = None

CFG = load_config()             # fallback config
APP = load_state()              # user settings (persist)
START_UI = APP.get("start_kapitaal", CFG.get("START_KAPITAAL", 0))

# ---------- helpers ----------
def _to_num(s) -> float:
    try:
        return float(str(s).strip().replace(",", ".")) if str(s).strip() != "" else 0.0
    except Exception:
        return 0.0

def _short(txt: str, n=60):
    txt = str(txt or "")
    return txt if len(txt) <= n else txt[:n] + "…"

def calc_row_pnl(row) -> float:
    cols = [COL["PNL_TP1"], COL["PNL_TP2"], COL["PNL_TP3"], COL["PNL_EXIT"]]
    vals = []
    for c in cols:
        v = row.get(c, 0)
        try:
            v = float(str(v).replace(",", ".")) if str(v).strip() != "" else 0.0
        except Exception:
            v = 0.0
        vals.append(v)
    return float(np.nansum(vals))

def _kpis_btc(df: pd.DataFrame, start_btc: float) -> dict:
    pnl_total = pd.to_numeric(df.get(COL["PNL_TOTAL"], pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
    fees = pd.to_numeric(df.get(COL["FEES"], pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
    actuel = float(start_btc) + float(pnl_total) - float(fees)
    return {"start": float(start_btc), "pnl": float(pnl_total), "fees": float(fees), "actueel": float(actuel)}

# ---------- Sidebar filters ----------
DEFAULTS = dict(
    f_portefeuille="Alle",
    f_periode="Alle",
    f_categorie=[],
    f_search="",
    f_tags="",
    f_emoties=[],
)
def reset_filters():
    for k, v in DEFAULTS.items():
        st.session_state[k] = v

with st.sidebar:
    st.title("⚙️ Filters")
    st.selectbox("Portefeuille", ["Alle","LT","Swing"])
    st.selectbox("Periode", ["Alle","YTD","MTD","WTD"])
    st.multiselect("Categorie", ["BTC","Equities","FX","Commodities"])
    st.text_input("🔍 Zoek (Trade_ID of Tags)", key="f_search")
    st.text_input("🔖 Tags (comma)", key="f_tags")
    st.multiselect("Emoties", ["Kalm","Twijfel","Stress"])
    st.button("Reset filters", on_click=reset_filters)

# ---------- Tabs ----------
tab_journal, tab_settings = st.tabs(["📓 Journal", "⚙️ Settings"])

# =======================
# Tab: Settings
# =======================
with tab_settings:
    st.subheader("Instellingen")
    start_val = st.number_input("Startkapitaal (BTC)", min_value=0.0, step=0.000001, value=float(START_UI))
    cols = st.columns([1,1])
    if cols[0].button("💾 Opslaan (Settings)"):
        save_state({"start_kapitaal": float(start_val)})
        st.success("Settings opgeslagen. Herberekenen…")
        st.experimental_set_query_params(cb=str(int(time.time())))
        st.rerun()
    # Hard reload / cache-bust tegen 1Ldio.js
    if cols[1].button("🔄 Hard reload (cache-bust)"):
        st.experimental_set_query_pa_

