from __future__ import annotations
import streamlit as st
import pandas as pd

from schema import COL, ORDER, DATE_FMT, SETUP_OPTS
from import_export import read_entries, write_entries, export_visible
from utils_config import load_config

# veilige import van healthcheck (voorkomt NameError als module ontbreekt)
try:
    import healthcheck
except Exception:
    healthcheck = None

st.set_page_config(page_title="Bitpilot — Journal", layout="wide")
CFG = load_config()

# ---------- Sidebar filters (vaste unieke keys) ----------
DEFAULTS = dict(
    f_portefeuille="Alle",
    f_periode="Alle",
    f_categorie=[],
    f_tags="",
    f_emoties=[],
)

def reset_filters():
    for k, v in DEFAULTS.items():
        st.session_state[k] = v

with st.sidebar:
    st.title("⚙️ Filters")
    st.selectbox("Portefeuille", ["Alle", "LT", "Swing"], key="f_portefeuille")
    st.selectbox("Periode", ["Alle", "YTD", "MTD", "WTD"], key="f_periode")
    st.multiselect("Categorie", ["BTC", "Equities", "FX", "Commodities"], key="f_categorie")
    st.text_input("🔖 Tags (comma)", key="f_tags")
    st.multiselect("Emoties", ["Kalm", "Twijfel", "Stress"], key="f_emoties")
    st.button("Reset filters", key="f_reset", on_click=reset_filters)

# ---------- Header + Health ----------
st.title("📓 Journal — R0.2 Finishing (01/02)")
if healthcheck and hasattr(healthcheck, "report"):
    rep = healthcheck.report()
    c0, c1, c2, c3 = st.columns(4)
    c0.metric("Python", rep.get("python", "?"))
    c1.metric("Start_kapitaal", rep.get("start_kapitaal", 1000))
    c2.metric("AI", "Online" if rep.get("ai", {}).get("online") else rep.get("ai", {}).get("reason", "Offline"))
    c3.metric("Dirs OK", "✅" if rep.get("dirs_ok") else "⚠️")

# ---------- Tabs (LET OP: st.tabs heeft géén key-argument) ----------
tab_journal, tab_ai, tab_events = st.tabs(["📓 Journal", "🤖 AI", "📅 Events"])

with tab_journal:
    # Data
    df = read_entries()

    # TFS verbergen in view (maar blijft in data/export)
    VISIBLE_COLS = [c for c in ORDER if c != COL["TFS"]]
    df_view = df[VISIBLE_COLS].copy()

    # Lege-staat tolerant
    if df_view.empty:
        st.info("Nog geen entries. Tabel is leeg, maar werkt zonder fouten.")
        st.dataframe(df_view, use_container_width=True, key="tbl_empty")
    else:
        st.dataframe(df_view, use_container_width=True, key="tbl_main")

    # Toevoegen (alle widget keys vast)
    st.markdown("### ➕ Toevoegen")
    with st.form(key="add_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            d_datum = st.date_input(COL["DATUM"], key="add_datum")
            d_id = st.text_input(COL["TRADE_ID"], key="add_id")
            d_setup = st.selectbox(COL["SETUP"], SETUP_OPTS, key="add_setup")
            d_custom = st.text_input("Eigen setup-naam", key="add_setup_custom") if d_setup == "Anders/Custom" else ""
            d_tfs = st.text_input(COL["TFS"], key="add_tfs")
        with c2:
            d_entry = st.text_input(COL["ENTRY"], key="add_entry")
            d_sl = st.text_input(COL["SL"], key="add_sl")
            d_tp = st.text_input(COL["TP"], key="add_tp")
            d_r = st.number_input(COL["RISICO_R"], step=0.25, key="add_r")
            d_win = st.selectbox(COL["WIN"], ["", "Win", "Loss", "BE"], key="add_win")
        with c3:
            d_pnl = st.text_input(COL["PNL"], key="add_pnl")
            d_roi = st.text_input(COL["ROI"], key="add_roi")
            d_fees = st.text_input(COL["FEES"], key="add_fees")
            d_acc = st.text_input(COL["ACCOUNT"], key="add_acc")
            d_tags = st.text_input(COL["TAGS"], key="add_tags")
            d_emo = st.text_input(COL["EMOTIES"], key="add_emo")
            d_plan = st.text_area(COL["PLAN"], key="add_plan")
            d_notes = st.text_area(COL["NOTES"], key="add_notes")
            d_shots = st.text_input(COL["SHOTS"], key="add_shots")

        # BELANGRIJK: form_submit_button heeft GEEN 'key' argument
        save_btn = st.form_submit_button("Opslaan", use_container_width=True, type="primary")

    if save_btn:
        setup_value = d_custom.strip() if (d_setup == "Anders/Custom" and d_custom) else d_setup
        new = {
            COL["DATUM"]: d_datum.strftime(DATE_FMT),
            COL["TRADE_ID"]: d_id, COL["SETUP"]: setup_value, COL["TFS"]: d_tfs,
            COL["ENTRY"]: d_entry, COL["SL"]: d_sl, COL["TP"]: d_tp, COL["RISICO_R"]: d_r,
            COL["PNL"]: d_pnl, COL["ROI"]: d_roi, COL["FEES"]: d_fees, COL["ACCOUNT"]: d_acc,
            COL["WIN"]: d_win, COL["TAGS"]: d_tags, COL["EMOTIES"]: d_emo,
            COL["PLAN"]: d_plan, COL["NOTES"]: d_notes, COL["SHOTS"]: d_shots
        }
        df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
        write_entries(df)
        st.success("Entry toegevoegd ✅")

with tab_ai:
    st.info("R0.2-03 pakt AI/uitklappen; nu alleen 01/02 & Start_kapitaal gedaan.")

with tab_events:
    st.info("Geen wijzigingen in deze ticketronde.")

