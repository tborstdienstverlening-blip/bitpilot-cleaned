from __future__ import annotations
import streamlit as st
import pandas as pd
from math import ceil

from schema import COL, ORDER, DATE_FMT, SETUP_OPTS
from utils_config import load_config, format_btc
from journal_store import load_journal, append_entry, update_entry, delete_entry
from import_export import export_visible

# veilige import van healthcheck
try:
    import healthcheck
except Exception:
    healthcheck = None

st.set_page_config(page_title="Bitpilot — Journal", layout="wide")
CFG = load_config()

# ---------- helpers ----------
def _to_num(s):
    try:
        return float(str(s).strip().replace(",",".")) if str(s).strip() != "" else 0.0
    except Exception:
        return 0.0

def _short(txt: str, n=60):
    txt = str(txt or "")
    return txt if len(txt) <= n else txt[:n] + "…"

def _kpis_btc(df: pd.DataFrame) -> dict:
    start = CFG.get("START_KAPITAAL", 0)
    pnl  = pd.to_numeric(df.get(COL["PNL"], pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
    fees = pd.to_numeric(df.get(COL["FEES"], pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
    actuel = start + pnl - fees
    return {
        "start": start,
        "pnl": float(pnl),
        "fees": float(fees),
        "actueel": float(actuel),
    }

# ---------- Sidebar filters ----------
DEFAULTS = dict(
    f_portefeuille="Alle",
    f_periode="Alle",
    f_categorie=[],
    f_tags="",
    f_emoties=[],
    f_search="",
)

def reset_filters():
    for k, v in DEFAULTS.items():
        st.session_state[k] = v

with st.sidebar:
    st.title("⚙️ Filters")
    st.selectbox("Portefeuille", ["Alle","LT","Swing"], key="f_portefeuille")
    st.selectbox("Periode", ["Alle","YTD","MTD","WTD"], key="f_periode")
    st.multiselect("Categorie", ["BTC","Equities","FX","Commodities"], key="f_categorie")
    st.text_input("🔍 Zoek (Trade_ID of Tags)", key="f_search")
    st.text_input("🔖 Tags (comma)", key="f_tags")
    st.multiselect("Emoties", ["Kalm","Twijfel","Stress"], key="f_emoties")
    st.button("Reset filters", key="f_reset", on_click=reset_filters)

# ---------- Header + Health ----------
st.title("📓 Journal — Overzicht + CRUD (R0.2-03)")
if healthcheck and hasattr(healthcheck, "report"):
    rep = healthcheck.report()
    c0, c1, c2, c3, c4 = st.columns(5)
    c0.metric("Python", rep.get("python","?"))
    c1.metric("Denominatie", rep.get("denom","BTC"))
    c2.metric("Start (BTC)", rep.get("start_kapitaal_fmt","—"))
    c3.metric("AI", "Online" if rep.get("ai",{}).get("online") else rep.get("ai",{}).get("reason","Offline"))
    c4.metric("Dirs OK", "✅" if rep.get("dirs_ok") else "⚠️")

# ---------- 60/40 layout ----------
left, right = st.columns([3,2])

# ---------- Data laden + filter/sort ----------
df_all = load_journal()

# sort op Datum aflopend (tolerant)
try:
    df_all["_dt"] = pd.to_datetime(df_all[COL["DATUM"]], format=DATE_FMT, errors="coerce")
except Exception:
    df_all["_dt"] = pd.to_datetime(df_all[COL["DATUM"]], errors="coerce")
df_all = df_all.sort_values("_dt", ascending=False).drop(columns=["_dt"])

# zoekfilter
q = (st.session_state.get("f_search") or "").strip().lower()
if q:
    mask = df_all[COL["TRADE_ID"]].astype(str).str.lower().str.contains(q) | \
           df_all[COL["TAGS"]].astype(str).str.lower().str.contains(q)
    df_all = df_all[mask]

# zichtbare kolommen (zonder TFs) + ingeklapte Plan/Notities + icoon voor Screenshots
VISIBLE_COLS = [c for c in ORDER if c != COL["TFS"]]
df_view = df_all[VISIBLE_COLS].copy()
df_view[COL["PLAN"]]  = df_view[COL["PLAN"]].apply(_short)
df_view[COL["NOTES"]] = df_view[COL["NOTES"]].apply(_short)
df_view["🖼️"] = df_all[COL["SHOTS"]].apply(lambda x: "🖼️" if str(x).strip() else "")

# ---------- KPI-minibalk (BTC) ----------
kpis = _kpis_btc(df_all)
kc0, kc1, kc2, kc3 = st.columns(4)
kc0.metric("Startkapitaal",  format_btc(kpis["start"]))
kc1.metric("Actueel kapitaal", format_btc(kpis["actueel"]))
kc2.metric("Totale PnL",     format_btc(kpis["pnl"]))
kc3.metric("Totale Fees",    format_btc(kpis["fees"]))

# ---------- Tabel links met paginatie + selectie ----------
with left:
    PAGE = 25
    total = len(df_view)
    pages = max(1, ceil(total / PAGE))
    pg = st.number_input("Pagina", min_value=1, max_value=pages, value=1, step=1, key="tbl_page")
    start, end = (pg-1)*PAGE, min(pg*PAGE, total)

    page_df = df_view.iloc[start:end].copy()
    # enkele rij kiezen: op Trade_ID
    trade_ids_page = df_all.iloc[start:end][COL["TRADE_ID"]].astype(str).tolist()
    sel_tid = st.selectbox("Selecteer Trade_ID voor bewerken", ["(geen)"] + trade_ids_page, index=0, key="tbl_select")
    st.dataframe(page_df, use_container_width=True)

    # export van zichtbare rijen (alle schema-kolommen)
    if st.button("Exporteer zichtbare rijen (.csv)"):
        out = export_visible(df_all.iloc[start:end][VISIBLE_COLS])
        st.success(f"Export voltooid: `{out}`")

# ---------- Detail rechts: Toevoegen / Bewerken ----------
with right:
    mode_edit = (sel_tid != "(geen)")
    st.subheader("Details")
    if mode_edit:
        # bestaande rij ophalen
        cur = df_all[df_all[COL["TRADE_ID"]].astype(str) == sel_tid]
        initial = cur.iloc[0].to_dict() if not cur.empty else {c:"" for c in ORDER}
    else:
        initial = {c:"" for c in ORDER}

    with st.form(key="detail_form"):
        c1,c2 = st.columns(2)
        with c1:
            d_datum = st.date_input(COL["DATUM"], value=pd.to_datetime(initial.get(COL["DATUM"]) or pd.Timestamp.now()).date())
            d_id    = st.text_input(COL["TRADE_ID"], value=str(initial.get(COL["TRADE_ID"], "")))
            d_setup = st.selectbox(COL["SETUP"], SETUP_OPTS, index=(SETUP_OPTS.index(initial.get(COL["SETUP"])) if initial.get(COL["SETUP"]) in SETUP_OPTS else 0))
            d_custom = st.text_input("Custom setup", value="" if d_setup!="Anders/Custom" else ("" if initial.get(COL["SETUP"]) in SETUP_OPTS else str(initial.get(COL["SETUP"])) ))
            d_tfs   = st.text_input(COL["TFS"], value=str(initial.get(COL["TFS"], "")))
            d_entry = st.text_input(COL["ENTRY"], value=str(initial.get(COL["ENTRY"], "")))
            d_sl    = st.text_input(COL["SL"], value=str(initial.get(COL["SL"], "")))
            d_tp    = st.text_input(COL["TP"], value=str(initial.get(COL["TP"], "")))
            d_r     = st.text_input(COL["RISICO_R"], value=str(initial.get(COL["RISICO_R"], "")))
        with c2:
            d_pnl   = st.text_input(COL["PNL"], value=str(initial.get(COL["PNL"], "")))
            d_roi   = st.text_input(COL["ROI"], value=str(initial.get(COL["ROI"], "")))
            d_fees  = st.text_input(COL["FEES"], value=str(initial.get(COL["FEES"], "")))
            d_acc   = st.text_input(COL["ACCOUNT"], value=str(initial.get(COL["ACCOUNT"], "")))
            d_win   = st.selectbox(COL["WIN"], ["","Win","Loss","BE"], index=(["","Win","Loss","BE"].index(str(initial.get(COL["WIN"], ""))) if str(initial.get(COL["WIN"], "")) in ["","Win","Loss","BE"] else 0))
            d_tags  = st.text_input(COL["TAGS"], value=str(initial.get(COL["TAGS"], "")))
            d_emo   = st.text_input(COL["EMOTIES"], value=str(initial.get(COL["EMOTIES"], "")))
            d_plan  = st.text_area(COL["PLAN"], value=str(initial.get(COL["PLAN"], "")))
            d_notes = st.text_area(COL["NOTES"], value=str(initial.get(COL["NOTES"], "")))
            d_shots = st.text_input(COL["SHOTS"], value=str(initial.get(COL["SHOTS"], "")))

        colA, colB, colC = st.columns(3)
        if not mode_edit:
            save_new = colA.form_submit_button("Opslaan (nieuw)", type="primary")
            if save_new:
                setup_value = d_custom.strip() if d_setup == "Anders/Custom" and d_custom else d_setup
                new = {
                    COL["DATUM"]: pd.to_datetime(d_datum).strftime(DATE_FMT),
                    COL["TRADE_ID"]: d_id.strip(),
                    COL["SETUP"]: setup_value, COL["TFS"]: d_tfs,
                    COL["ENTRY"]: d_entry, COL["SL"]: d_sl, COL["TP"]: d_tp, COL["RISICO_R"]: d_r,
                    COL["PNL"]: d_pnl, COL["ROI"]: d_roi, COL["FEES"]: d_fees, COL["ACCOUNT"]: d_acc,
                    COL["WIN"]: d_win, COL["TAGS"]: d_tags, COL["EMOTIES"]: d_emo,
                    COL["PLAN"]: d_plan, COL["NOTES"]: d_notes, COL["SHOTS"]: d_shots
                }
                # basic numerieke validatie
                for fld in (COL["ENTRY"], COL["SL"], COL["TP"], COL["RISICO_R"], COL["PNL"], COL["ROI"], COL["FEES"], COL["ACCOUNT"]):
                    _ = _to_num(new[fld])
                try:
                    tid = append_entry(new)
                    st.success(f"Toegevoegd ✅ (Trade_ID: {tid})")
                except Exception as e:
                    st.error(str(e))
        else:
            do_update = colA.form_submit_button("Wijzigen", type="primary")
            do_delete = colB.form_submit_button("Verwijderen")
            confirm   = colC.checkbox("Bevestig verwijderen")

            if do_update:
                setup_value = d_custom.strip() if d_setup == "Anders/Custom" and d_custom else d_setup
                upd = {
                    COL["DATUM"]: pd.to_datetime(d_datum).strftime(DATE_FMT),
                    COL["TRADE_ID"]: d_id.strip(),  # mag wijzigen zolang uniek blijft; store checkt
                    COL["SETUP"]: setup_value, COL["TFS"]: d_tfs,
                    COL["ENTRY"]: d_entry, COL["SL"]: d_sl, COL["TP"]: d_tp, COL["RISICO_R"]: d_r,
                    COL["PNL"]: d_pnl, COL["ROI"]: d_roi, COL["FEES"]: d_fees, COL["ACCOUNT"]: d_acc,
                    COL["WIN"]: d_win, COL["TAGS"]: d_tags, COL["EMOTIES"]: d_emo,
                    COL["PLAN"]: d_plan, COL["NOTES"]: d_notes, COL["SHOTS"]: d_shots
                }
                for fld in (COL["ENTRY"], COL["SL"], COL["TP"], COL["RISICO_R"], COL["PNL"], COL["ROI"], COL["FEES"], COL["ACCOUNT"]):
                    _ = _to_num(upd[fld])
                try:
                    # als Trade_ID gewijzigd is, doen we het als "update op oud id" + ensure geen dup
                    if d_id.strip() != sel_tid:
                        # check duplicaat
                        if (load_journal()[COL["TRADE_ID"]].astype(str) == d_id.strip()).any():
                            st.error(f"Trade_ID bestaat al: {d_id.strip()}")
                        else:
                            # simuleer hernoemen: voeg nieuwe toe en verwijder oude
                            append_entry(upd)
                            delete_entry(sel_tid)
                            st.success(f"Gewijzigd ✅ (Trade_ID gewijzigd naar {d_id.strip()})")
                    else:
                        update_entry(sel_tid, upd)
                        st.success("Gewijzigd ✅")
                except Exception as e:
                    st.error(str(e))

            if do_delete and confirm:
                try:
                    delete_entry(sel_tid)
                    st.success("Verwijderd ✅")
                except Exception as e:
                    st.error(str(e))

