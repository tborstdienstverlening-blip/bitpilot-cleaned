from __future__ import annotations
import time
import streamlit as st
import pandas as pd

from schema import COL, ORDER, DATE_FMT, SETUP_OPTS
from utils_config import load_config, format_btc
from journal_store import load_journal, save_journal, append_entry, update_entry, delete_entry, get_last_save_ts
from import_export import export_visible
from app_state import load_state, save_state
from backup_utils import make_backup_zip, list_local_backups, restore_from_backup
import github_sync
from kpi_utils import with_pnl_total, apply_filters, compute_kpis
from risk_utils import compute_risk_contracts

st.set_page_config(page_title="Bitpilot — Journal", layout="wide")

# ------- config/state -------
CFG = load_config()
APP = load_state()
START_UI = float(APP.get("start_kapitaal", CFG.get("START_KAPITAAL", 0)))
# Risk settings (inline, persist in app_state)
APP.setdefault("risk_pct", 0.01)           # 1%
APP.setdefault("risk_rounding", "floor")   # floor | round | ceil
APP.setdefault("filters", {"periode":"Alle","search":"","tags":"","emoties":[]})
save_state(APP)  # ensure defaults saved

def _f(x):
    try:
        s = str(x).strip().replace(",", ".")
        return None if s=="" else float(s)
    except Exception:
        return None

def _short(txt: str, n=60):
    txt = str(txt or "")
    return txt if len(txt) <= n else txt[:n] + "…"

# ------- Topbar: Filters & Settings popovers -------
c1, c2, c3, c4 = st.columns([5, 2, 2, 3])
with c1:
    st.title("Journal")
with c2:
    with st.popover("🔎 Filters", use_container_width=True):
        filt = APP["filters"]
        filt["periode"] = st.selectbox("Periode", ["Alle","YTD","MTD","WTD"], index=["Alle","YTD","MTD","WTD"].index(filt.get("periode","Alle")))
        filt["search"]  = st.text_input("Zoek (Trade_ID of Tags)", value=filt.get("search",""))
        filt["tags"]    = st.text_input("Tags (comma)", value=filt.get("tags",""))
        filt["emoties"] = st.multiselect("Emoties", ["Kalm","Twijfel","Stress"], default=filt.get("emoties", []))
        cols = st.columns(2)
        if cols[0].button("Reset"):
            filt.update({"periode":"Alle","search":"","tags":"","emoties":[]})
        if cols[1].button("Toepassen"):
            APP["filters"] = filt; save_state(APP); st.rerun()
with c3:
    with st.popover("⚙️ Risk settings", use_container_width=True):
        st.caption("Deribit BTC-PERP (1 contract = $1)")
        risk_pct = st.number_input("Risk % (van account)", min_value=0.0, max_value=100.0, step=0.05, value=float(APP.get("risk_pct",1.0)*100)) / 100.0
        rounding = st.selectbox("Round contracts", ["floor","round","ceil"], index=["floor","round","ceil"].index(APP.get("risk_rounding","floor")))
        acct = st.number_input("Account (BTC) voor risk", min_value=0.0, step=0.000001, value=float(START_UI))
        if st.button("Opslaan (risk)", type="primary"):
            APP["risk_pct"] = float(risk_pct); APP["risk_rounding"] = rounding
            APP["account_for_risk"] = float(acct); save_state(APP); st.toast("Risk settings opgeslagen")
with c4:
    # Quick status
    last_save = get_last_save_ts()
    st.caption(f"💾 Laatste save: {last_save or '—'}")

st.divider()

# ------- Data load + per-rij auto velden (Risk/Contracts/RR) -------
df_raw = load_journal()
if df_raw is None or df_raw.empty:
    df_raw = pd.DataFrame(columns=ORDER)

# Zorg dat alle schema-kolommen bestaan
for col in ORDER:
    if col not in df_raw.columns:
        df_raw[col] = ""

# Auto-berekeningen per rij
def compute_row_autos(row: pd.Series) -> pd.Series:
    entry = _f(row.get(COL["ENTRY"]))
    sl    = _f(row.get(COL["SL"]))
    acct  = float(APP.get("account_for_risk", START_UI))
    risk_pct = float(APP.get("risk_pct", 0.01))
    rounding = str(APP.get("risk_rounding","floor"))
    risk_btc, contracts = compute_risk_contracts(acct, risk_pct, entry, sl, rounding=rounding)
    # RR (Plan)
    side = str(row.get(COL["SIDE"]) or "").strip().lower()
    tp_vals = [_f(row.get(COL["TP1"])), _f(row.get(COL["TP2"])), _f(row.get(COL["TP3"]))]
    sl_eq_entry = (entry is not None and sl is not None and entry == sl)
    rr_plan = None
    if not sl_eq_entry and entry is not None and sl is not None:
        cands = []
        for tp in tp_vals:
            if tp is None: continue
            if side == "short":
                rr = (entry - tp) / abs(entry - sl)
            else:  # default long
                rr = (tp - entry) / abs(entry - sl)
            cands.append(rr)
        rr_plan = max(cands) if cands else None
    # RR (Actueel) = (ΣTP-PNL − Fees) / risk_btc  (Exit negeren)
    pnl_tp = sum([x for x in [ _f(row.get(COL["PNL_TP1"])), _f(row.get(COL["PNL_TP2"])), _f(row.get(COL["PNL_TP3"])) ] if x is not None])
    fees = _f(row.get(COL["FEES"])) or 0.0
    rr_actual = None if not risk_btc else ( (pnl_tp - fees) / risk_btc )
    # Schrijf terug in zichtbare kolommen
    row[COL["RISK_BTC"]]      = "n.v.t." if risk_btc is None else f"{risk_btc:.6f}"
    row[COL["CONTRACT_SIZE"]] = "" if contracts is None else int(contracts)
    row[COL["RR_PLAN"]]       = "n.v.t." if rr_plan is None else f"{rr_plan:.2f}"
    # kleur doen we in dataframe styling; hier text
    row[COL["RR_ACTUAL"]]     = "n.v.t." if rr_actual is None else f"{rr_actual:.2f}"
    return row

df_auto = df_raw.apply(compute_row_autos, axis=1)

# ------- Filters toepassen (overlaywaarden) -------
filt = APP.get("filters", {"periode":"Alle","search":"","tags":"","emoties":[]})
df_filtered = apply_filters(df_auto, search=filt.get("search",""), tags_csv=filt.get("tags",""),
                            emoties=filt.get("emoties", []), periode=filt.get("periode","Alle"))

# ------- KPI-balk (delta's = laatste trade) -------
k = compute_kpis(df_filtered, start_btc=START_UI)
def _pct(x): return "—" if x is None else f"{x:.2f}%"

r1 = st.columns(4)
r1[0].metric("Startkapitaal (BTC)", format_btc(k["start"]))
r1[1].metric("Actueel kapitaal (BTC)", format_btc(k["actueel"]),
             delta=(format_btc(k["delta_actueel_btc"]) if k["delta_actueel_btc"]!=0 else None))
r1[2].metric("Totale PnL (BTC)", format_btc(k["pnl"]),
             delta=(format_btc(k["delta_pnl_btc"]) if k["delta_pnl_btc"]!=0 else None))
r1[3].metric("Totale Fees (BTC)", format_btc(k["fees"]),
             delta=(format_btc(k["delta_fees_btc"]) if k["delta_fees_btc"]!=0 else None))
r2 = st.columns(3)
roi_delta = (f'{k["delta_roi_pp"]:.2f} pp' if k["delta_roi_pp"] not in (None,0) else None)
r2[0].metric("ROI %", _pct(k["roi_pct"]), delta=roi_delta)
r2[1].metric("Winnende trades", f'{k["wins"]}')
r2[2].metric("Winrate %", _pct(k["winrate_pct"]), delta=(k["winrate_arrow"] if k.get("winrate_arrow") else None))

st.divider()
if df_filtered.empty:
    st.info("Nog geen trades in selectie.")
# ------- Zichtbare kolommen & tooltips -------
vis_cols = [
    COL["DATUM"], "ID", COL["SIDE"], COL["SETUP"],
    COL["RISK_BTC"], COL["CONTRACT_SIZE"], COL["RR_PLAN"], COL["RR_ACTUAL"],
    COL["ENTRY"], COL["SL"], COL["TP1"], COL["TP2"], COL["TP3"],
    COL["FEES"], COL["PNL_TP1"], COL["PNL_TP2"], COL["PNL_TP3"], COL["PNL_EXIT"],
    COL["EMOTIES"], COL["TAGS"], COL["SHOTS"],
]
df_view = df_filtered.copy()
df_view["ID"] = df_view[COL["TRADE_ID"]].astype(str)

for col in vis_cols:
    if col not in df_view.columns: df_view[col] = ""

# Kolom-config (tooltips/helptxt)
colcfg = {
    COL["RISK_BTC"]: st.column_config.TextColumn(COL["RISK_BTC"], help="BTC"),
    COL["CONTRACT_SIZE"]: st.column_config.NumberColumn(COL["CONTRACT_SIZE"], help="contracts", step=1),
    COL["FEES"]: st.column_config.NumberColumn(COL["FEES"], help="BTC"),
    COL["ENTRY"]: st.column_config.NumberColumn(COL["ENTRY"], help="prijs"),
    COL["SL"]:    st.column_config.NumberColumn(COL["SL"], help="prijs"),
    COL["TP1"]:   st.column_config.NumberColumn(COL["TP1"], help="prijs"),
    COL["TP2"]:   st.column_config.NumberColumn(COL["TP2"], help="prijs"),
    COL["TP3"]:   st.column_config.NumberColumn(COL["TP3"], help="prijs"),
    COL["RR_PLAN"]:   st.column_config.TextColumn(COL["RR_PLAN"], help="Max van TP’s; n.v.t. als SL=Entry of geen TP"),
    COL["RR_ACTUAL"]: st.column_config.TextColumn(COL["RR_ACTUAL"], help="(ΣTP-PNL − Fees) / risk_btc; Exit telt niet mee"),
}

# Bewerken toggle (keyboard-first: zet uit/aan)
edit_mode = st.toggle("✎ Bewerken/Toevoegen inschakelen", value=False, help="Zet aan om rijen inline te wijzigen of toe te voegen (ghost row).")
edited = st.data_editor(
    df_view[vis_cols].reset_index(drop=True),
    use_container_width=True,
    hide_index=True,
    column_config=colcfg,
    disabled=not edit_mode,
    num_rows=("dynamic" if edit_mode else "fixed"),  # ghost row
    key="journal_editor",
)

st.caption("Tip: Tab/Shift+Tab navigeert; Enter bevestigt cel; ‘✎ Bewerken’ aan voor ghost row / inline bewerken.")

# ------- Wijzigingen detecteren & opslaan -------
def _norm(s):  # normaliseer lege strings naar ""
    return "" if s is None else (str(s) if not isinstance(s, str) else s)

def df_keyed(df):
    # maak dictionary per Trade_ID
    m = {}
    for _, r in df.iterrows():
        tid = str(r.get("ID","")).strip() or str(r.get(COL["TRADE_ID"], "")).strip()
        if not tid: continue
        m[tid] = r
    return m

if edit_mode:
    colA, colB, colC = st.columns(3)
    do_save = colA.button("💾 Opslaan wijzigingen", type="primary")
    to_delete = colB.text_input("Verwijder Trade_ID (exact)")
    do_delete = colC.button("🗑️ Verwijderen")
    if do_delete and to_delete.strip():
        try:
            delete_entry(to_delete.strip())
            st.success(f"Verwijderd: {to_delete.strip()}")
            st.rerun()
        except Exception as e:
            st.error(str(e))

    if do_save:
        # Vergelijk met originele gefilterde set per ID (simpelste aanpak: schrijf wijzigingen rechtstreeks terug in journal df_raw)
        base_all = load_journal()
        base_map = df_keyed(df_view)
        new_map  = df_keyed(edited)

        # Updates + Adds
        for tid, row in new_map.items():
            exists = tid in base_map
            # Zet terug naar schema-kolommen
            out = {k: "" for k in ORDER}
            out.update({COL["TRADE_ID"]: tid})
            # Map zichtbare → dataset kolommen
            out[COL["DATUM"]] = pd.to_datetime(row.get(COL["DATUM"]) or pd.Timestamp.today()).strftime(DATE_FMT)
            out[COL["SIDE"]]  = str(row.get(COL["SIDE"]) or "").strip()
            out[COL["SETUP"]] = str(row.get(COL["SETUP"]) or "").strip()
            out[COL["ENTRY"]] = row.get(COL["ENTRY"], "")
            out[COL["SL"]]    = row.get(COL["SL"], "")
            out[COL["TP1"]]   = row.get(COL["TP1"], "")
            out[COL["TP2"]]   = row.get(COL["TP2"], "")
            out[COL["TP3"]]   = row.get(COL["TP3"], "")
            out[COL["FEES"]]  = row.get(COL["FEES"], "")
            out[COL["PNL_TP1"]] = row.get(COL["PNL_TP1"], "")
            out[COL["PNL_TP2"]] = row.get(COL["PNL_TP2"], "")
            out[COL["PNL_TP3"]] = row.get(COL["PNL_TP3"], "")
            out[COL["PNL_EXIT"]] = row.get(COL["PNL_Exit"], row.get(COL["PNL_EXIT"], ""))
            out[COL["EMOTIES"]]  = row.get(COL["EMOTIES"], "")
            out[COL["TAGS"]]     = row.get(COL["TAGS"], "")
            out[COL["SHOTS"]]    = row.get(COL["SHOTS"], "")
            # autos velden worden bij load weer berekend; toch meeschrijven ter volledigheid:
            out[COL["RISK_BTC"]]      = row.get(COL["RISK_BTC"], "")
            out[COL["CONTRACT_SIZE"]] = row.get(COL["CONTRACT_SIZE"], "")
            out[COL["RR_PLAN"]]       = row.get(COL["RR_PLAN"], "")
            out[COL["RR_ACTUAL"]]     = row.get(COL["RR_ACTUAL"], "")

            try:
                if exists:
                    update_entry(tid, out)
                else:
                    append_entry(out)
            except Exception as e:
                st.error(f"Kon {tid} niet opslaan: {e}")

        st.success("Wijzigingen opgeslagen ✅")
        if APP.get("gh_sync_enabled", False):
            ok, msg = github_sync.sync_now(); st.info(msg)
        st.rerun()

# ------- Export knop -------
if st.button("Exporteer zichtbare rijen (.csv)"):
    out = export_visible(df_filtered)
    st.success(f"Export voltooid: `{out}`")

# ------- Settings / Backup paneel onderaan (compact) -------
st.divider()
with st.expander("Settings & Back-up"):
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        start_val = st.number_input("Startkapitaal (BTC)", min_value=0.0, step=0.000001, value=float(START_UI))
        if st.button("Opslaan (Startkapitaal)"):
            APP["start_kapitaal"] = float(start_val); save_state(APP); st.success("Startkapitaal opgeslagen"); st.rerun()
    with c2:
        ok, msg = github_sync.test_connection(
            github_sync.GhSettings(APP.get("gh_sync_enabled", False), APP.get("gh_repo",""), APP.get("gh_branch","main"), APP.get("gh_dir","data"))
        )
        st.caption("GitHub: " + ("OK" if ok else "Niet geconfigureerd"))
        if st.button("☁️ Back-up nu"):
            save_state(APP)
            ok2, msg2 = github_sync.sync_now(force=True)
            st.success(msg2) if ok2 else st.error(msg2)
    with c3:
        blob = make_backup_zip()
        st.download_button("📦 Download back-up (.zip)", data=blob, file_name="bitpilot-backup.zip", mime="application/zip")
    with c4:
        st.caption("Herstel (lokaal)")
        ext = st.selectbox("Type", [".csv",".json"])
        choices = list_local_backups(ext=ext)
        if choices:
            idx = st.selectbox("Back-up", list(range(len(choices))), format_func=lambda i: choices[i].name)
            if st.button("♻️ Herstel"):
                ok3, msg3 = restore_from_backup(choices[int(idx)])
                st.success(msg3) if ok3 else st.error(msg3)
                st.rerun()
        else:
            st.caption("Geen lokale back-ups")

