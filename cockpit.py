from __future__ import annotations
import time
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
def _to_num(s):
    try:
        return float(str(s).strip().replace(",",".")) if str(s).strip() != "" else 0.0
    except Exception:
        return 0.0

def _short(txt: str, n=60):
    txt = str(txt or "")
    return txt if len(txt) <= n else txt[:n] + "…"

def _btc_series(df, col):
    return pd.to_numeric(df.get(col, pd.Series(dtype=float)), errors="coerce").fillna(0.0)

def _kpis_btc(df: pd.DataFrame, start_btc: float) -> dict:
    pnl  = _btc_series(df, COL["PNL"]).sum()
    fees = _btc_series(df, COL["FEES"]).sum()
    actuel = float(start_btc) + float(pnl) - float(fees)
    return {"start": float(start_btc), "pnl": float(pnl), "fees": float(fees), "actueel": float(actuel)}

def _pnl_color(val):
    # styler helper: positief -> groen; negatief -> rood; 0/NaN -> neutraal
    try:
        v = float(val)
    except Exception:
        return ""
    if pd.isna(v) or v == 0:
        return ""
    return "color: green;" if v > 0 else "color: red;"

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
    st.selectbox("Portefeuille", ["Alle","LT","Swing"], key="f_portefeuille")
    st.selectbox("Periode", ["Alle","YTD","MTD","WTD"], key="f_periode")
    st.multiselect("Categorie", ["BTC","Equities","FX","Commodities"], key="f_categorie")
    st.text_input("🔍 Zoek (Trade_ID of Tags)", key="f_search")
    st.text_input("🔖 Tags (comma)", key="f_tags")
    st.multiselect("Emoties", ["Kalm","Twijfel","Stress"], key="f_emoties")
    st.button("Reset filters", on_click=reset_filters)
    # Hard reload / cache-bust tegen 1Ldio.js
    if st.button("🔄 Hard reload (cache-bust)"):
        st.experimental_set_query_params(cb=str(int(time.time())))
        st.rerun()

# ---------- Tabs ----------
tab_journal, tab_settings = st.tabs(["📓 Journal", "⚙️ Settings"])

# =======================
# Tab: Settings
# =======================
with tab_settings:
    st.subheader("Instellingen")
    start_val = st.number_input("Startkapitaal (BTC)", min_value=0.0, step=0.000001, value=float(START_UI))
    if st.button("💾 Opslaan (Settings)"):
        save_state({"start_kapitaal": float(start_val)})
        st.success("Settings opgeslagen. Herberekenen…")
        st.experimental_set_query_params(cb=str(int(time.time())))
        st.rerun()

# =======================
# Tab: Journal
# =======================
with tab_journal:
    st.title("Journal — Overzicht + CRUD")

    # Header/Health
    if healthcheck and hasattr(healthcheck, "report"):
        rep = healthcheck.report()
        c0, c1, c2, c3, c4 = st.columns(5)
        c0.metric("Python", rep.get("python","?"))
        c1.metric("Denominatie", rep.get("denom","BTC"))
        c2.metric("Start (BTC)", format_btc(START_UI))
        c3.metric("AI", "Online" if rep.get("ai",{}).get("online") else rep.get("ai",{}).get("reason","Offline"))
        c4.metric("Dirs OK", "✅" if rep.get("dirs_ok") else "⚠️")

    # Data laden + sort + zoek
    df_all = load_journal()

    try:
        df_all["_dt"] = pd.to_datetime(df_all[COL["DATUM"]], format=DATE_FMT, errors="coerce")
    except Exception:
        df_all["_dt"] = pd.to_datetime(df_all[COL["DATUM"]], errors="coerce")
    df_all = df_all.sort_values("_dt", ascending=False).drop(columns=["_dt"])

    q = (st.session_state.get("f_search") or "").strip().lower()
    if q:
        mask = df_all[COL["TRADE_ID"]].astype(str).str.lower().str.contains(q) | \
               df_all[COL["TAGS"]].astype(str).str.lower().str.contains(q)
        df_all = df_all[mask]

    # 60/40 layout
    left, right = st.columns([3,2])

    # --- TABEL LINKS: zichtbare kolommen & volgorde (zonder TFs etc.)
    # Doelvolgorde (labels):
    vis_order_labels = [
        COL["DATUM"], "ID", COL["SETUP"], COL["CONTRACT_SIZE"], COL["RR"],
        COL["ENTRY"], COL["SL"], COL["TP1"], COL["PNL_TP1"],
        COL["TP2"], COL["PNL_TP2"], COL["TP3"], COL["PNL_TP3"],
        COL["PNL_EXIT"], COL["FEES"], COL["EMOTIES"],
        "Plan_preview", "Notities_preview", "🖼️",
    ]

    # Bouw viewframe
    df_view = df_all.copy()
    # Alias ID en previews
    df_view["ID"] = df_view[COL["TRADE_ID"]].astype(str)
    df_view["Plan_preview"]    = df_view[COL["PLAN"]].apply(lambda x: _short(x, 60))
    df_view["Notities_preview"]= df_view[COL["NOTES"]].apply(lambda x: _short(x, 60))
    df_view["🖼️"] = df_view[COL["SHOTS"]].apply(lambda x: "🖼️" if str(x).strip() else "")
    # Zet ontbrekende kolommen leeg
    for col in vis_order_labels:
        if col not in df_view.columns:
            df_view[col] = ""
    table_df = df_view[vis_order_labels].reset_index(drop=True)

    # Style: PNL-kolommen groen/rood + BTC-format
    pnl_cols = [COL["PNL_TP1"], COL["PNL_TP2"], COL["PNL_TP3"], COL["PNL_EXIT"]]
    # maak numerieke hulp-kopie voor format
    num_map = {}
    for c in pnl_cols + [COL["FEES"]]:
        try:
            num_map[c] = pd.to_numeric(df_view[c], errors="coerce")
        except Exception:
            num_map[c] = pd.Series([None]*len(table_df))
    fmt_map = {c: (lambda v, cm=c: format_btc(v) if pd.notna(v) else "—") for c in pnl_cols + [COL["FEES"]]}

    try:
        styled = table_df.style.applymap(_pnl_color, subset=pnl_cols).format(fmt_map, na_rep="—")
        with left:
            st.dataframe(styled, use_container_width=True, hide_index=True)
    except Exception:
        # fallback zonder styling
        with left:
            st.dataframe(table_df, use_container_width=True, hide_index=True)

    # Paginatie + selectie (op basis van huidige tabel)
    with left:
        PAGE = 25
        total = len(table_df)
        pages = max(1, ceil(total / PAGE))
        pg = st.number_input("Pagina", min_value=1, max_value=pages, value=1, step=1)
        start, end = (pg-1)*PAGE, min(pg*PAGE, total)
        # selectie op Trade_ID
        trade_ids_page = df_view.iloc[start:end]["ID"].astype(str).tolist()
        sel_tid = st.selectbox("Selecteer Trade_ID voor bewerken", ["(geen)"] + trade_ids_page, index=0)

        # Invoer/bewerken INGeklapt
        with st.expander("✍️ Trades invoeren/bewerken", expanded=False):
            is_edit = sel_tid != "(geen)"
            initial = df_all[df_all[COL["TRADE_ID"]].astype(str) == sel_tid].iloc[0].to_dict() if is_edit else {c:"" for c in ORDER}

            with st.form(key="entry_form"):
                c1,c2 = st.columns(2)
                with c1:
                    d_datum = st.date_input(COL["DATUM"], value=pd.to_datetime(initial.get(COL["DATUM"]) or pd.Timestamp.now()).date())
                    d_id    = st.text_input("ID (Trade_ID)", value=str(initial.get(COL["TRADE_ID"], "")))
                    d_setup = st.selectbox(COL["SETUP"], SETUP_OPTS, index=(SETUP_OPTS.index(initial.get(COL["SETUP"])) if initial.get(COL["SETUP"]) in SETUP_OPTS else 0))
                    d_custom = st.text_input("Custom setup", value="" if d_setup!="Anders/Custom" else ("" if initial.get(COL["SETUP"]) in SETUP_OPTS else str(initial.get(COL["SETUP"])) ))
                    d_contract = st.text_input(COL["CONTRACT_SIZE"], value=str(initial.get(COL["CONTRACT_SIZE"], "")))
                    d_rr   = st.text_input(COL["RR"], value=str(initial.get(COL["RR"], "")))
                    d_entry= st.text_input(COL["ENTRY"], value=str(initial.get(COL["ENTRY"], "")))
                    d_sl   = st.text_input(COL["SL"], value=str(initial.get(COL["SL"], "")))
                with c2:
                    d_tp1  = st.text_input(COL["TP1"], value=str(initial.get(COL["TP1"], "")))
                    d_p1   = st.text_input(COL["PNL_TP1"], value=str(initial.get(COL["PNL_TP1"], "")))
                    d_tp2  = st.text_input(COL["TP2"], value=str(initial.get(COL["TP2"], "")))
                    d_p2   = st.text_input(COL["PNL_TP2"], value=str(initial.get(COL["PNL_TP2"], "")))
                    d_tp3  = st.text_input(COL["TP3"], value=str(initial.get(COL["TP3"], "")))
                    d_p3   = st.text_input(COL["PNL_TP3"], value=str(initial.get(COL["PNL_TP3"], "")))
                    d_px   = st.text_input(COL["PNL_EXIT"], value=str(initial.get(COL["PNL_EXIT"], "")))
                    d_fees = st.text_input(COL["FEES"], value=str(initial.get(COL["FEES"], "")))
                d_em   = st.text_input(COL["EMOTIES"], value=str(initial.get(COL["EMOTIES"], "")))
                d_plan = st.text_area(COL["PLAN"], value=str(initial.get(COL["PLAN"], "")))
                d_note = st.text_area(COL["NOTES"], value=str(initial.get(COL["NOTES"], "")))
                d_shot = st.text_input(COL["SHOTS"], value=str(initial.get(COL["SHOTS"], "")))
                colA, colB, colC = st.columns(3)

                if not is_edit:
                    save_new = colA.form_submit_button("Opslaan (nieuw)", type="primary")
                    if save_new:
                        setup_value = d_custom.strip() if d_setup == "Anders/Custom" and d_custom else d_setup
                        new = {
                            COL["DATUM"]: pd.to_datetime(d_datum).strftime(DATE_FMT),
                            COL["TRADE_ID"]: d_id.strip(),
                            COL["SETUP"]: setup_value, COL["TFS"]: "",
                            COL["CONTRACT_SIZE"]: d_contract, COL["RR"]: d_rr,
                            COL["ENTRY"]: d_entry, COL["SL"]: d_sl, COL["TP"]: "",
                            COL["TP1"]: d_tp1, COL["TP2"]: d_tp2, COL["TP3"]: d_tp3,
                            COL["PNL_TP1"]: d_p1, COL["PNL_TP2"]: d_p2, COL["PNL_TP3"]: d_p3, COL["PNL_EXIT"]: d_px,
                            COL["RISICO_R"]: "", COL["PNL"]: "", COL["ROI"]: "", COL["FEES"]: d_fees, COL["ACCOUNT"]: "",
                            COL["WIN"]: "", COL["TAGS"]: "", COL["EMOTIES"]: d_em, COL["PLAN"]: d_plan, COL["NOTES"]: d_note, COL["SHOTS"]: d_shot
                        }
                        # numerieke validatie (throws niet; forceer parse)
                        _ = [_to_num(new[x]) for x in [COL["ENTRY"], COL["SL"], COL["TP1"], COL["TP2"], COL["TP3"],
                                                       COL["PNL_TP1"], COL["PNL_TP2"], COL["PNL_TP3"], COL["PNL_EXIT"], COL["FEES"]]]
                        try:
                            tid = append_entry(new)
                            st.success(f"Toegevoegd ✅ (Trade_ID: {tid})")
                            st.experimental_set_query_params(cb=str(int(time.time())))
                            st.rerun()
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
                            COL["TRADE_ID"]: d_id.strip(),
                            COL["SETUP"]: setup_value, COL["TFS"]: "",
                            COL["CONTRACT_SIZE"]: d_contract, COL["RR"]: d_rr,
                            COL["ENTRY"]: d_entry, COL["SL"]: d_sl, COL["TP"]: "",
                            COL["TP1"]: d_tp1, COL["TP2"]: d_tp2, COL["TP3"]: d_tp3,
                            COL["PNL_TP1"]: d_p1, COL["PNL_TP2"]: d_p2, COL["PNL_TP3"]: d_p3, COL["PNL_EXIT"]: d_px,
                            COL["RISICO_R"]: "", COL["PNL"]: "", COL["ROI"]: "", COL["FEES"]: d_fees, COL["ACCOUNT"]: "",
                            COL["WIN"]: "", COL["TAGS"]: "", COL["EMOTIES"]: d_em, COL["PLAN"]: d_plan, COL["NOTES"]: d_note, COL["SHOTS"]: d_shot
                        }
                        _ = [_to_num(upd[x]) for x in [COL["ENTRY"], COL["SL"], COL["TP1"], COL["TP2"], COL["TP3"],
                                                       COL["PNL_TP1"], COL["PNL_TP2"], COL["PNL_TP3"], COL["PNL_EXIT"], COL["FEES"]]]
                        try:
                            if d_id.strip() != sel_tid:
                                # hernoemen met duplicate-check
                                if (load_journal()[COL["TRADE_ID"]].astype(str) == d_id.strip()).any():
                                    st.error(f"Trade_ID bestaat al: {d_id.strip()}")
                                else:
                                    from journal_store import append_entry as _append, delete_entry as _del
                                    _append(upd); _del(sel_tid)
                                    st.success(f"Gewijzigd ✅ (Trade_ID → {d_id.strip()})")
                            else:
                                update_entry(sel_tid, upd)
                                st.success("Gewijzigd ✅")
                            st.experimental_set_query_params(cb=str(int(time.time())))
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
                    if do_delete and confirm:
                        try:
                            delete_entry(sel_tid)
                            st.success("Verwijderd ✅")
                            st.experimental_set_query_params(cb=str(int(time.time())))
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))

    # --- DETAIL RECHTS: volledige Plan/Notities (uitklap)
    with right:
        st.subheader("Details")
        if 'sel_tid' in locals() and sel_tid != "(geen)":
            cur = df_all[df_all[COL["TRADE_ID"]].astype(str) == sel_tid]
            if not cur.empty:
                r = cur.iloc[0]
                st.markdown(f"**Trade_ID:** {sel_tid}  |  **Setup:** {r.get(COL['SETUP'],'')}")
                with st.expander("Plan — volledig", expanded=False):
                    st.write(str(r.get(COL["PLAN"], "")))
                with st.expander("Notities — volledig", expanded=False):
                    st.write(str(r.get(COL["NOTES"], "")))
        else:
            st.info("Selecteer een rij links om details te zien.")

    # --- KPI-balk ONDERAAN (BTC)
    kpis = _kpis_btc(df_all, start_btc=START_UI)
    st.divider()
    kc0, kc1, kc2, kc3 = st.columns(4)
    kc0.metric("Startkapitaal",  format_btc(kpis["start"]))
    kc1.metric("Actueel kapitaal", format_btc(kpis["actueel"]))
    kc2.metric("Totale PnL",     format_btc(kpis["pnl"]))
    kc3.metric("Totale Fees",    format_btc(kpis["fees"]))

    # Export zichtbare rijen (neemt ALLE schema-kolommen mee via export_visible)
    if st.button("Exporteer zichtbare rijen (.csv)"):
        out = export_visible(df_all)  # export_visible vult ontbrekende kolommen aan en ordent volgens ORDER
        st.success(f"Export voltooid: `{out}`")

