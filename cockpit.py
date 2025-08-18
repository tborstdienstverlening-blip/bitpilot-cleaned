from __future__ import annotations
import streamlit as st
import pandas as pd

from schema import COL, ORDER, DATE_FMT, SETUP_OPTS
from import_export import read_entries, write_entries, export_visible
from utils_config import load_config

st.set_page_config(page_title="Bitpilot — Journal", layout="wide")
CFG = load_config()

# ---------- Filters + reset ----------
DEFAULTS = dict(f_port="Alle", f_per="Alle", f_cat=[], f_tags="", f_emo=[])
def reset_filters():
    for k,v in DEFAULTS.items():
        st.session_state[k] = v

with st.sidebar:
    st.title("⚙️ Filters")
    st.selectbox("Portefeuille", ["Alle","LT","Swing"], key="f_port")
    st.selectbox("Periode", ["Alle","YTD","MTD","WTD"], key="f_per")
    st.multiselect("Categorie", ["BTC","Equities","FX","Commodities"], key="f_cat")
    st.text_input("🔖 Tags (comma)", key="f_tags")
    st.multiselect("Emoties", ["Kalm","Twijfel","Stress"], key="f_emo")
    st.button("Reset filters", key="f_reset", on_click=reset_filters)

st.title("📓 Journal — Fundament R0.2-A")
# Header + Healthcheck
if hasattr(healthcheck, "report"):
    rep = healthcheck.report()
    c0, c1, c2, c3 = st.columns(4)
    c0.metric("Python", rep.get("python", "?"))
    c1.metric("Start_kapitaal", rep.get("start_kapitaal", 1000))
    c2.metric("AI", "Online" if rep.get("ai", {}).get("online") else rep.get("ai", {}).get("reason", "Offline"))
    c3.metric("Dirs OK", "✅" if rep.get("dirs_ok") else "⚠️")

# ---------- Data ----------
df = read_entries()

# ---------- Tabelweergave (TFS verbergen) ----------
VISIBLE_COLS = [c for c in ORDER if c != COL["TFS"]]
df_view = df[VISIBLE_COLS].copy()

# Plan/Notities: ingeklapte preview (±60 tekens)
def _short(txt: str, n=60):
    txt = str(txt or "")
    return txt if len(txt) <= n else txt[:n] + "…"

if df_view.empty:
    st.info("Nog geen entries. Voeg er één toe of importeer data.")
else:
    preview = df_view.copy()
    preview[COL["PLAN"]]  = preview[COL["PLAN"]].apply(_short)
    preview[COL["NOTES"]] = preview[COL["NOTES"]].apply(_short)

    st.dataframe(preview, use_container_width=True)

    st.markdown("### 📄 Details per rij")
    idx = st.number_input("Rij-index", min_value=0, max_value=len(df)-1, step=1, key="row_detail")
    with st.expander("Uitklappen / volledige tekst"):
        st.write(f"**Plan**:\n\n{df.iloc[idx][COL['PLAN']]}")
        st.write(f"**Notities**:\n\n{df.iloc[idx][COL['NOTES']]}")

# ---------- Toevoegen ----------
st.markdown("### ➕ Toevoegen")
with st.form(key="add_form"):
    c1,c2,c3 = st.columns(3)
    with c1:
        d_datum = st.date_input(COL["DATUM"], key="add_datum")
        d_id    = st.text_input(COL["TRADE_ID"], key="add_id")
        d_setup = st.selectbox(COL["SETUP"], SETUP_OPTS, key="add_setup")
        d_custom = ""
        if d_setup == "Anders/Custom":
            d_custom = st.text_input("Eigen setup-naam", key="add_setup_custom")
        d_tfs   = st.text_input(COL["TFS"], key="add_tfs")
    with c2:
        d_entry = st.text_input(COL["ENTRY"], key="add_entry")
        d_sl    = st.text_input(COL["SL"], key="add_sl")
        d_tp    = st.text_input(COL["TP"], key="add_tp")
        d_r     = st.number_input(COL["RISICO_R"], step=0.25, key="add_r")
        d_win   = st.selectbox(COL["WIN"], ["","Win","Loss","BE"], key="add_win")
    with c3:
        d_pnl   = st.text_input(COL["PNL"], key="add_pnl")
        d_roi   = st.text_input(COL["ROI"], key="add_roi")
        d_fees  = st.text_input(COL["FEES"], key="add_fees")
        d_acc   = st.text_input(COL["ACCOUNT"], key="add_acc")
        d_tags  = st.text_input(COL["TAGS"], key="add_tags")
        d_emo   = st.text_input(COL["EMOTIES"], key="add_emo")
        d_plan  = st.text_area(COL["PLAN"], key="add_plan")
        d_notes = st.text_area(COL["NOTES"], key="add_notes")
        d_shots = st.text_input(COL["SHOTS"], key="add_shots")

    add_btn = st.form_submit_button("Opslaan", use_container_width=True)

if add_btn:
    setup_value = d_custom.strip() if ("Anders/Custom" in (d_setup or "")) and d_custom else d_setup
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

# ---------- Export ----------
st.divider()
if st.button("Exporteer zichtbare rijen (.csv)", key="export_btn"):
    out = export_visible(df_view)
    st.success(f"Export voltooid: `{out}`")

