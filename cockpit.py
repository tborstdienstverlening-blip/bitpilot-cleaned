from __future__ import annotations
import time
import numpy as np
import streamlit as st
import pandas as pd

from schema import COL, ORDER, DATE_FMT, SETUP_OPTS
from utils_config import load_config, format_btc
from journal_store import load_journal, append_entry, update_entry, delete_entry, get_last_save_ts
from import_export import export_visible
from app_state import load_state, save_state
from backup_utils import make_backup_zip, list_local_backups, restore_from_backup
import github_sync
from kpi_utils import with_pnl_total, apply_filters, compute_kpis

st.set_page_config(page_title="Bitpilot — Journal", layout="wide")

# Healthcheck (staat in Settings, niet bovenin)
try:
    import healthcheck
except Exception:
    healthcheck = None

CFG = load_config()
APP = load_state()
START_UI = APP.get("start_kapitaal", CFG.get("START_KAPITAAL", 0))
ROLLING_N = int(APP.get("rolling_n", 20) or 20)

def _to_num(s) -> float:
    try:
        return float(str(s).strip().replace(",", ".")) if str(s).strip() != "" else 0.0
    except Exception:
        return 0.0

def _short(txt: str, n=60):
    txt = str(txt or "")
    return txt if len(txt) <= n else txt[:n] + "…"

# -------- Filters --------
DEFAULTS = dict(
    f_portefeuille="Alle",
    f_periode="Alle",
    f_categorie=[],
    f_search="",
    f_tags="",
    f_emotie_sel=[],
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
    st.multiselect("Emoties", ["Kalm","Twijfel","Stress"], key="f_emotie_sel")
    st.button("Reset filters", on_click=reset_filters)

# -------- Status rechtsboven --------
last_save = get_last_save_ts()
last_sync_ts = APP.get("last_sync_ts", "")
last_sync_msg = APP.get("last_sync_msg", "Sync uit")
scol1, scol2, scol3 = st.columns([6,2,2])
with scol2: st.caption(f"💾 Laatste save: {last_save or '—'}")
with scol3: st.caption(f"☁️ Laatste sync: {last_sync_ts or '—'} ({last_sync_msg})")

# -------- Tabs --------
tab_journal, tab_settings = st.tabs(["📓 Journal", "⚙️ Settings"])

# =======================
# Settings (incl. tech-info + Rolling N)
# =======================
with tab_settings:
    st.subheader("Instellingen")
    c1, c2 = st.columns(2)
    with c1:
        start_val = st.number_input("Startkapitaal (BTC)", min_value=0.0, step=0.000001, value=float(START_UI))
    with c2:
        rolling_val = st.number_input("Rolling winrate — N trades", min_value=5, max_value=200, step=1, value=int(ROLLING_N))
    if st.button("💾 Opslaan (Settings)"):
        APP["start_kapitaal"] = float(start_val)
        APP["rolling_n"] = int(rolling_val)
        save_state(APP)
        st.success("Settings opgeslagen. Herberekenen…")
        st.experimental_set_query_params(cb=str(int(time.time()))); st.rerun()

    st.divider()
    st.subheader("Back-ups naar GitHub (optioneel)")
    APP["gh_sync_enabled"] = st.toggle("Back-ups naar GitHub inschakelen", value=bool(APP.get("gh_sync_enabled", False)))
    APP["gh_repo"]   = st.text_input("Repo (owner/repo)", value=str(APP.get("gh_repo","")))
    APP["gh_branch"] = st.text_input("Branch", value=str(APP.get("gh_branch","main") or "main"))
    APP["gh_dir"]    = st.text_input("Pad in repo", value=str(APP.get("gh_dir","data") or "data"))
    cols = st.columns(4)
    if cols[0].button("🔌 Test verbinding"):
        ok, msg = github_sync.test_connection(
            github_sync.GhSettings(APP["gh_sync_enabled"], APP["gh_repo"], APP["gh_branch"], APP["gh_dir"])
        )
        st.success(msg) if ok else st.error(msg)
    if cols[1].button("☁️ Back-up nu (GitHub)"):
        save_state(APP)
        ok, msg = github_sync.sync_now(force=True)
        st.success(msg) if ok else st.error(msg)
        st.experimental_set_query_params(cb=str(int(time.time()))); st.rerun()
    if cols[2].button("📦 Download back-up (.zip)"):
        blob = make_backup_zip()
        st.download_button("Download ZIP", data=blob, file_name="bitpilot-backup.zip", mime="application/zip")
    if cols[3].button("🔄 Hard reload (cache-bust)"):
        st.experimental_set_query_params(cb=str(int(time.time()))); st.rerun()

    st.divider()
    st.subheader("Herstel uit back-up (lokaal)")
    bak_type = st.selectbox("Type", ["Journal (.csv)","App state (.json)"])
    ext = ".csv" if bak_type.startswith("Journal") else ".json"
    choices = list_local_backups(ext=ext)
    if choices:
        names = [p.name for p in choices]
        idx = st.selectbox("Kies back-up", list(range(len(choices))), format_func=lambda i: names[i])
        sel = choices[int(idx)]
        st.caption(f"Geselecteerd: {sel.name}")
        if ext == ".csv":
            try:
                df_prev = pd.read_csv(sel)
                st.write("Voorbeeld (head):", df_prev.head(5)); st.write("Rijen:", len(df_prev))
            except Exception as e:
                st.warning(f"Kan preview niet laden: {e}")
        if st.button("♻️ Herstel deze back-up"):
            ok, msg = restore_from_backup(sel)
            st.success(msg) if ok else st.error(msg)
            st.experimental_set_query_params(cb=str(int(time.time()))); st.rerun()
    else:
        st.info("Geen lokale back-ups gevonden in data/.bak/")

    st.divider()
    st.subheader("Systeeminfo")
    try:
        if healthcheck and hasattr(healthcheck, "report"):
            rep = healthcheck.report()
            s0, s1, s2 = st.columns(3)
            s0.metric("Python", rep.get("python","?"))
            s1.metric("AI", "Online" if rep.get("ai",{}).get("online") else rep.get("ai",{}).get("reason","Offline"))
            s2.metric("Dirs OK", "✅" if rep.get("dirs_ok") else "⚠️")
        else:
            st.caption("Healthcheck niet beschikbaar.")
    except Exception:
        st.caption("Healthcheck niet beschikbaar.")

# =======================
# Journal (KPI-balk bovenaan)
# =======================
with tab_journal:
    st.title("Journal")

    # Data + filters
    df_all = with_pnl_total(load_journal())
    df_filtered = apply_filters(
        df_all,
        search=st.session_state.get("f_search"),
        tags_csv=st.session_state.get("f_tags"),
        emoties=st.session_state.get("f_emotie_sel", []),
        periode=st.session_state.get("f_periode", "Alle"),
    )

    # KPI's
    k = compute_kpis(df_filtered, start_btc=START_UI, rolling_n=ROLLING_N)
    def _pct(x):
        return "—" if x is None else f"{x:.2f}%"

    # Rij 1 — deltas = effect laatste trade
    r1 = st.columns(4)
    r1[0].metric("Startkapitaal (BTC)", format_btc(k["start"]))
    r1[1].metric("Actueel kapitaal (BTC)", format_btc(k["actueel"]),
                 delta=(format_btc(k["last_actueel_delta_btc"]) if k["last_actueel_delta_btc"] != 0 else None))
    r1[2].metric("Totale PnL (BTC)", format_btc(k["pnl"]),
                 delta=(format_btc(k["last_pnl_delta_btc"]) if k["last_pnl_delta_btc"] != 0 else None))
    # Fees als negatieve delta tonen
    last_fee = k["last_fees_delta_btc"]
    fee_delta_str = f"-{format_btc(abs(last_fee))}" if last_fee else None
    r1[3].metric("Totale Fees (BTC)", format_btc(k["fees"]), delta=fee_delta_str)

    # Rij 2 — ROI & winrates (met delta obv laatste trade)
    r2 = st.columns(4)
    roi_delta = (f'{k["last_roi_delta_pct"]:.2f} pp' if k["last_roi_delta_pct"] is not None and k["last_roi_delta_pct"] != 0 else None)
    r2[0].metric("ROI %", _pct(k["roi_pct"]), delta=roi_delta)

    r2[1].metric("Winnende trades", f'{k["wins"]}')
    r2[2].metric("Verloren trades", f'{k["losses"]}')

    # Winrate delta pijltje ↑/↓
    wr = _pct(k["winrate_pct"])
    wrd = k.get("winrate_delta_pp", None)
    wr_delta_str = None
    if wrd is not None and wrd != 0:
        arrow = "↑" if wrd > 0 else "↓"
        wr_delta_str = f"{arrow} {abs(wrd):.2f} pp"
    r2[3].metric(f"Rolling Winrate % (N={ROLLING_N})", _pct(k["rolling_winrate_pct"]),
                 delta=(f"{'↑' if (k.get('rolling_winrate_delta_pp',0) or 0) > 0 else '↓'} {abs(k.get('rolling_winrate_delta_pp',0.0)):.2f} pp"
                        if k.get("rolling_winrate_delta_pp") not in (None, 0) else None))

    if df_filtered.empty:
        st.info("Nog geen trades in selectie.")
    st.divider()

    # Tabel zoals eerder
    vis_cols = [
        COL["DATUM"], "ID", COL["SETUP"], COL["CONTRACT_SIZE"], COL["RR"],
        COL["ENTRY"], COL["SL"], COL["TP1"], COL["PNL_TP1"],
        COL["TP2"], COL["PNL_TP2"], COL["TP3"], COL["PNL_TP3"],
        COL["PNL_EXIT"], COL["FEES"], COL["EMOTIES"],
        "Plan_preview", "Notities_preview", "🖼️",
    ]
    df_view = df_filtered.copy()
    df_view["ID"] = df_view[COL["TRADE_ID"]].astype(str)
    df_view["Plan_preview"]     = df_view[COL["PLAN"]].apply(lambda x: _short(x, 60))
    df_view["Notities_preview"] = df_view[COL["NOTES"]].apply(lambda x: _short(x, 60))
    df_view["🖼️"] = df_view[COL["SHOTS"]].apply(lambda x: "🖼️" if str(x).strip() else "")
    for col in vis_cols:
        if col not in df_view.columns: df_view[col] = ""
    table_df = df_view[vis_cols].reset_index(drop=True)

    pnl_cols = [COL["PNL_TP1"], COL["PNL_TP2"], COL["PNL_TP3"], COL["PNL_EXIT"]]
    fmt_map = {c: (lambda v: format_btc(v) if pd.notna(v) and str(v) != "" else "—") for c in pnl_cols + [COL["FEES"]]}

    try:
        styled = table_df.style.map(
            lambda x: "color: green;" if _to_num(x) > 0 else ("color: red;" if _to_num(x) < 0 else ""),
            subset=pnl_cols
        ).format(fmt_map, na_rep="—")
        st.dataframe(styled, use_container_width=True, hide_index=True)
    except Exception:
        st.dataframe(table_df, use_container_width=True, hide_index=True)

    # ---- Invoeren
    with st.expander("🆕 Trades invoeren", expanded=False):
        with st.form(key="form_add"):
            c1, c2 = st.columns(2)
            with c1:
                d_datum = st.date_input(COL["DATUM"])
                d_id    = st.text_input("ID (Trade_ID)")
                d_setup = st.selectbox(COL["SETUP"], SETUP_OPTS)
                d_custom= st.text_input("Custom setup") if d_setup == "Anders/Custom" else ""
                d_contract = st.text_input(COL["CONTRACT_SIZE"])
                d_rr   = st.text_input(COL["RR"])
                d_entry= st.text_input(COL["ENTRY"])
                d_sl   = st.text_input(COL["SL"])
                d_tp1  = st.text_input(COL["TP1"])
                d_p1   = st.text_input(COL["PNL_TP1"])
            with c2:
                d_tp2  = st.text_input(COL["TP2"])
                d_p2   = st.text_input(COL["PNL_TP2"])
                d_tp3  = st.text_input(COL["TP3"])
                d_p3   = st.text_input(COL["PNL_TP3"])
                d_px   = st.text_input(COL["PNL_EXIT"])
                d_fees = st.text_input(COL["FEES"])
                d_em   = st.text_input(COL["EMOTIES"])
                d_plan = st.text_area(COL["PLAN"])
                d_note = st.text_area(COL["NOTES"])
                d_shot = st.text_input(COL["SHOTS"])
            add_btn = st.form_submit_button("Opslaan (nieuw)", type="primary")
        if add_btn:
            setup_value = d_custom.strip() if d_setup == "Anders/Custom" and d_custom else d_setup
            new = {
                COL["DATUM"]: pd.to_datetime(d_datum).strftime(DATE_FMT),
                COL["TRADE_ID"]: d_id.strip(),
                COL["SETUP"]: setup_value, COL["TFS"]: "",
                COL["CONTRACT_SIZE"]: d_contract, COL["RR"]: d_rr,
                COL["ENTRY"]: d_entry, COL["SL"]: d_sl, COL["TP"]: "",
                COL["TP1"]: d_tp1, COL["TP2"]: d_tp2, COL["TP3"]: d_tp3,
                COL["PNL_TP1"]: d_p1, COL["PNL_TP2"]: d_p2, COL["PNL_TP3"]: d_p3, COL["PNL_EXIT"]: d_px,
                COL["PNL_TOTAL"]: "",  # berekenen bij load
                COL["RISICO_R"]: "", COL["PNL"]: "", COL["ROI"]: "", COL["FEES"]: d_fees, COL["ACCOUNT"]: "",
                COL["WIN"]: "", COL["TAGS"]: "", COL["EMOTIES"]: d_em, COL["PLAN"]: d_plan, COL["NOTES"]: d_note, COL["SHOTS"]: d_shot
            }
            try:
                tid = append_entry(new)
                if APP.get("gh_sync_enabled", False):
                    ok, msg = github_sync.sync_now(); st.info(msg)
                st.success(f"Toegevoegd ✅ (Trade_ID: {tid})")
                st.experimental_set_query_params(cb=str(int(time.time()))); st.rerun()
            except Exception as e:
                st.error(str(e))

    # ---- Bewerken/verwijderen
    with st.expander("✏️ Trades bewerken/verwijderen", expanded=False):
        trade_ids = df_filtered[COL["TRADE_ID"]].astype(str).tolist()
        sel_tid = st.selectbox("Selecteer Trade_ID", ["(geen)"] + trade_ids, index=0)
        initial = df_filtered[df_filtered[COL["TRADE_ID"]].astype(str) == sel_tid].iloc[0].to_dict() if sel_tid != "(geen)" else {c:"" for c in ORDER}

        with st.form(key="form_edit"):
            c1, c2 = st.columns(2)
            with c1:
                e_datum = st.date_input(COL["DATUM"], value=pd.to_datetime(initial.get(COL["DATUM"]) or pd.Timestamp.now()).date())
                e_id    = st.text_input("ID (Trade_ID)", value=str(initial.get(COL["TRADE_ID"], "")))
                e_setup = st.selectbox(COL["SETUP"], SETUP_OPTS, index=(SETUP_OPTS.index(initial.get(COL["SETUP"])) if initial.get(COL["SETUP"]) in SETUP_OPTS else 0))
                e_custom= st.text_input("Custom setup", value="" if e_setup!="Anders/Custom" else ("" if initial.get(COL["SETUP"]) in SETUP_OPTS else str(initial.get(COL["SETUP"])) ))
                e_contract = st.text_input(COL["CONTRACT_SIZE"], value=str(initial.get(COL["CONTRACT_SIZE"], "")))
                e_rr   = st.text_input(COL["RR"], value=str(initial.get(COL["RR"], "")))
                e_entry= st.text_input(COL["ENTRY"], value=str(initial.get(COL["ENTRY"], "")))
                e_sl   = st.text_input(COL["SL"], value=str(initial.get(COL["SL"], "")))
                e_tp1  = st.text_input(COL["TP1"], value=str(initial.get(COL["TP1"], "")))
                e_p1   = st.text_input(COL["PNL_TP1"], value=str(initial.get(COL["PNL_TP1"], "")))
            with c2:
                e_tp2  = st.text_input(COL["TP2"], value=str(initial.get(COL["TP2"], "")))
                e_p2   = st.text_input(COL["PNL_TP2"], value=str(initial.get(COL["PNL_TP2"], "")))
                e_tp3  = st.text_input(COL["TP3"], value=str(initial.get(COL["TP3"], "")))
                e_p3   = st.text_input(COL["PNL_TP3"], value=str(initial.get(COL["PNL_TP3"], "")))
                e_px   = st.text_input(COL["PNL_EXIT"], value=str(initial.get(COL["PNL_EXIT"], "")))
                e_fees = st.text_input(COL["FEES"], value=str(initial.get(COL["FEES"], "")))
                e_em   = st.text_input(COL["EMOTIES"], value=str(initial.get(COL["EMOTIES"], "")))
                e_plan = st.text_area(COL["PLAN"], value=str(initial.get(COL["PLAN"], "")))
                e_note = st.text_area(COL["NOTES"], value=str(initial.get(COL["NOTES"], "")))
                e_shot = st.text_input(COL["SHOTS"], value=str(initial.get(COL["SHOTS"], "")))

            colA, colB, colC = st.columns(3)
            do_update = colA.form_submit_button("Wijzigen", type="primary", disabled=(sel_tid=="(geen)"))
            do_delete = colB.form_submit_button("Verwijderen", disabled=(sel_tid=="(geen)"))
            confirm   = colC.checkbox("Bevestig verwijderen")

        if do_update and sel_tid != "(geen)":
            setup_value = e_custom.strip() if e_setup == "Anders/Custom" and e_custom else e_setup
            upd = {
                COL["DATUM"]: pd.to_datetime(e_datum).strftime(DATE_FMT),
                COL["TRADE_ID"]: e_id.strip(),
                COL["SETUP"]: setup_value, COL["TFS"]: "",
                COL["CONTRACT_SIZE"]: e_contract, COL["RR"]: e_rr,
                COL["ENTRY"]: e_entry, COL["SL"]: e_sl, COL["TP"]: "",
                COL["TP1"]: e_tp1, COL["TP2"]: e_tp2, COL["TP3"]: e_tp3,
                COL["PNL_TP1"]: e_p1, COL["PNL_TP2"]: e_p2, COL["PNL_TP3"]: e_p3, COL["PNL_EXIT"]: e_px,
                COL["PNL_TOTAL"]: "",  # wordt telkens herberekend bij load
                COL["RISICO_R"]: "", COL["PNL"]: "", COL["ROI"]: "", COL["FEES"]: e_fees, COL["ACCOUNT"]: "",
                COL["WIN"]: "", COL["TAGS"]: "", COL["EMOTIES"]: e_em, COL["PLAN"]: e_plan, COL["NOTES"]: e_note, COL["SHOTS"]: e_shot
            }
            try:
                if e_id.strip() != sel_tid:
                    if (load_journal()[COL["TRADE_ID"]].astype(str) == e_id.strip()).any():
                        st.error(f"Trade_ID bestaat al: {e_id.strip()}")
                    else:
                        from journal_store import append_entry as _append, delete_entry as _del
                        _append(upd); _del(sel_tid)
                        st.success(f"Gewijzigd ✅ (Trade_ID → {e_id.strip()})")
                else:
                    update_entry(sel_tid, upd)
                    st.success("Gewijzigd ✅")
                if APP.get("gh_sync_enabled", False):
                    ok, msg = github_sync.sync_now(); st.info(msg)
                st.experimental_set_query_params(cb=str(int(time.time()))); st.rerun()
            except Exception as e:
                st.error(str(e))

        if do_delete and sel_tid != "(geen)" and confirm:
            try:
                delete_entry(sel_tid)
                st.success("Verwijderd ✅")
                if APP.get("gh_sync_enabled", False):
                    ok, msg = github_sync.sync_now(); st.info(msg)
                st.experimental_set_query_params(cb=str(int(time.time()))); st.rerun()
            except Exception as e:
                st.error(str(e))

    if st.button("Exporteer zichtbare rijen (.csv)"):
        out = export_visible(df_filtered)
        st.success(f"Export voltooid: `{out}`")
