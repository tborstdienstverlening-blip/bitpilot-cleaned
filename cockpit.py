from __future__ import annotations
import time
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
from risk_utils import compute_risk_contracts_backend

st.set_page_config(page_title="Bitpilot — Journal", layout="wide")

# ---------- Config & app-state ----------
CFG = load_config()
APP = load_state()

START_UI = float(APP.get("start_kapitaal", CFG.get("START_KAPITAAL", 0)))
# risk-config (backend only)
RISK_PERCENT = (CFG.get("risk", {}).get("percent") 
                if isinstance(CFG.get("risk"), dict) else CFG.get("RISK_PERCENT", 1.0))
RISK_ROUND   = (CFG.get("risk", {}).get("rounding") 
                if isinstance(CFG.get("risk"), dict) else CFG.get("RISK_ROUNDING", "floor"))

# filters in state
APP.setdefault("filters", {"periode":"Alle","search":"","tags":"","emoties":[]})
save_state(APP)

def _to_num(s):
    try:
        t = str(s).strip().replace(",", ".")
        return None if t=="" else float(t)
    except Exception:
        return None

def _short(txt: str, n=60):
    txt = str(txt or "")
    return txt if len(txt) <= n else txt[:n] + "…"

# ---------- Helpers ----------
def _compute_global_actueel():
    # actueel kapitaal op basis van HELE dataset (on-gefilterd)
    df_all = with_pnl_total(load_journal())
    # som PNL_Total (ΣTP of fallback Exit) en Fees
    pnl_total  = pd.to_numeric(df_all.get(COL["PNL_TOTAL"], 0), errors="coerce").fillna(0).sum()
    fees_total = pd.to_numeric(df_all.get(COL["FEES"], 0),      errors="coerce").fillna(0).sum()
    return float(START_UI) + float(pnl_total) - float(fees_total)

# ---------- Tabs ----------
tabs = st.tabs(["📓 Journal", "⚙️ Settings"])
tab_journal, tab_settings = tabs[0], tabs[1]

# ---------- Header row per tab ----------
with tab_journal:
    h1, h2, h3 = st.columns([4,2,3])
    with h1:
        st.subheader("Journal")
    with h2:
        with st.popover("🔎 Filters", use_container_width=True):
            filt = APP["filters"]
            filt["periode"] = st.selectbox("Periode", ["Alle","YTD","MTD","WTD"], index=["Alle","YTD","MTD","WTD"].index(filt.get("periode","Alle")))
            filt["search"]  = st.text_input("Zoek (Trade_ID of Tags)", value=filt.get("search",""))
            filt["tags"]    = st.text_input("Tags (comma)", value=filt.get("tags",""))
            filt["emoties"] = st.multiselect("Emoties", ["Kalm","Twijfel","Stress"], default=filt.get("emoties", []))
            cA, cB = st.columns(2)
            if cA.button("Reset"):
                filt.update({"periode":"Alle","search":"","tags":"","emoties":[]})
            if cB.button("Toepassen"):
                APP["filters"] = filt; save_state(APP); st.rerun()
    with h3:
        # badges rechts
        last_save = get_last_save_ts()
        last_sync_ts = APP.get("last_sync_ts", "")
        last_sync_msg = APP.get("last_sync_msg", "Sync uit")
        st.caption(f"💾 Laatste save: {last_save or '—'}")
        st.caption(f"☁️ Laatste sync: {last_sync_ts or '—'} ({last_sync_msg})")

    st.divider()

    # ---------- Data laden ----------
    df_raw = load_journal()
    if df_raw is None or df_raw.empty:
        df_raw = pd.DataFrame(columns=ORDER)
    # alle kolommen garanderen
    for col in ORDER:
        if col not in df_raw.columns:
            df_raw[col] = ""

    # ---------- Backend auto: Risk & Contracts & RR's ----------
    def _row_autos(row: pd.Series) -> pd.Series:
        entry = _to_num(row.get(COL["ENTRY"]))
        sl    = _to_num(row.get(COL["SL"]))
        acct  = _compute_global_actueel()  # volledige dataset
        risk_btc, contracts = compute_risk_contracts_backend(acct, RISK_PERCENT, entry, sl, RISK_ROUND)
        # RR (Plan)
        side = (row.get(COL["SIDE"]) or "").strip().lower()
        tp1, tp2, tp3 = _to_num(row.get(COL["TP1"])), _to_num(row.get(COL["TP2"])), _to_num(row.get(COL["TP3"]))
        rr_plan = None
        if entry is not None and sl is not None and entry != sl:
            cands = []
            for tp in [tp1, tp2, tp3]:
                if tp is None: continue
                if side == "short":
                    cands.append((entry - tp) / abs(entry - sl))
                else:  # long (default)
                    cands.append((tp - entry) / abs(entry - sl))
            rr_plan = max(cands) if cands else None
        # RR (Actueel) — PNL_Exit telt NIET mee
        pnl_tp = sum([x for x in [_to_num(row.get(COL["PNL_TP1"])),
                                  _to_num(row.get(COL["PNL_TP2"])),
                                  _to_num(row.get(COL["PNL_TP3"]))] if x is not None])
        fees = _to_num(row.get(COL["FEES"])) or 0.0
        rr_actual = None
        if risk_btc not in (None, 0) and pnl_tp is not None:
            rr_actual = (pnl_tp - fees) / risk_btc

        row[COL["RISK_BTC"]]      = "n.v.t." if risk_btc is None else f"{risk_btc:.6f}"
        row[COL["CONTRACT_SIZE"]] = "" if contracts is None else int(contracts)
        row[COL["RR_PLAN"]]       = "n.v.t." if rr_plan is None else f"{rr_plan:.2f}"
        row[COL["RR_ACTUAL"]]     = "n.v.t." if rr_actual is None else f"{rr_actual:.2f}"
        return row

    df_auto = df_raw.apply(_row_autos, axis=1)

    # ---------- Filters ----------
    filt = APP.get("filters", {"periode":"Alle","search":"","tags":"","emoties":[]})
    df_filtered = apply_filters(df_auto,
                                search=filt.get("search",""),
                                tags_csv=filt.get("tags",""),
                                emoties=filt.get("emoties", []),
                                periode=filt.get("periode","Alle"))

    # ---------- KPI-balk ----------
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
    r2 = st.columns(4)
    roi_delta = (f'{k["delta_roi_pp"]:.2f} pp' if k["delta_roi_pp"] not in (None,0) else None)
    r2[0].metric("ROI %", _pct(k["roi_pct"]), delta=roi_delta)
    r2[1].metric("Winnende trades", f'{k["wins"]}')
    r2[2].metric("Verloren trades", f'{k["losses"]}')
    r2[3].metric("Winrate %", _pct(k["winrate_pct"]), delta=(k["winrate_arrow"] if k.get("winrate_arrow") else None))

    st.divider()
    if df_filtered.empty:
        st.info("Nog geen trades in selectie.")

    # ---------- Zichtbare kolommen ----------
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

    # kolomconfig (Richting = chips via SelectboxColumn)
    colcfg = {
        COL["SIDE"]:  st.column_config.SelectboxColumn(COL["SIDE"], options=["Long","Short"], help="Richting van de trade"),
        COL["RISK_BTC"]:      st.column_config.TextColumn(COL["RISK_BTC"], help="BTC"),
        COL["CONTRACT_SIZE"]: st.column_config.NumberColumn(COL["CONTRACT_SIZE"], help="contracts", step=1),
        COL["FEES"]:  st.column_config.NumberColumn(COL["FEES"], help="BTC"),
        COL["ENTRY"]: st.column_config.NumberColumn(COL["ENTRY"], help="prijs"),
        COL["SL"]:    st.column_config.NumberColumn(COL["SL"], help="prijs"),
        COL["TP1"]:   st.column_config.NumberColumn(COL["TP1"], help="prijs"),
        COL["TP2"]:   st.column_config.NumberColumn(COL["TP2"], help="prijs"),
        COL["TP3"]:   st.column_config.NumberColumn(COL["TP3"], help="prijs"),
        COL["RR_PLAN"]:   st.column_config.TextColumn(COL["RR_PLAN"], help="Max van TP’s; n.v.t. als SL=Entry of geen TP"),
        COL["RR_ACTUAL"]: st.column_config.TextColumn(COL["RR_ACTUAL"], help="(ΣTP-PNL − Fees)/Risk; Exit telt niet mee"),
    }

    edit_mode = st.toggle("✎ Bewerken/Toevoegen inschakelen", value=False,
                          help="Zet aan om rijen inline te wijzigen of toe te voegen (ghost row).")
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

    # ---------- Wijzigingen opslaan ----------
    def _map_row_to_schema(r: pd.Series) -> dict:
        out = {k: "" for k in ORDER}
        tid = str(r.get("ID","")).strip() or str(r.get(COL["TRADE_ID"], "")).strip()
        out[COL["TRADE_ID"]] = tid
        out[COL["DATUM"]] = pd.to_datetime(r.get(COL["DATUM"]) or pd.Timestamp.today()).strftime(DATE_FMT)
        out[COL["SIDE"]]  = str(r.get(COL["SIDE"]) or "").strip()
        out[COL["SETUP"]] = str(r.get(COL["SETUP"]) or "").strip()
        out[COL["ENTRY"]] = r.get(COL["ENTRY"], "")
        out[COL["SL"]]    = r.get(COL["SL"], "")
        out[COL["TP1"]]   = r.get(COL["TP1"], "")
        out[COL["TP2"]]   = r.get(COL["TP2"], "")
        out[COL["TP3"]]   = r.get(COL["TP3"], "")
        out[COL["FEES"]]  = r.get(COL["FEES"], "")
        out[COL["PNL_TP1"]] = r.get(COL["PNL_TP1"], "")
        out[COL["PNL_TP2"]] = r.get(COL["PNL_TP2"], "")
        out[COL["PNL_TP3"]] = r.get(COL["PNL_TP3"], "")
        out[COL["PNL_EXIT"]] = r.get(COL["PNL_Exit"], r.get(COL["PNL_EXIT"], ""))
        out[COL["EMOTIES"]]  = r.get(COL["EMOTIES"], "")
        out[COL["TAGS"]]     = r.get(COL["TAGS"], "")
        out[COL["SHOTS"]]    = r.get(COL["SHOTS"], "")
        # autos meeschrijven (worden toch op load herberekend)
        out[COL["RISK_BTC"]]      = r.get(COL["RISK_BTC"], "")
        out[COL["CONTRACT_SIZE"]] = r.get(COL["CONTRACT_SIZE"], "")
        out[COL["RR_PLAN"]]       = r.get(COL["RR_PLAN"], "")
        out[COL["RR_ACTUAL"]]     = r.get(COL["RR_ACTUAL"], "")
        return out

    def _keyed(df_):
        m = {}
        for _, r in df_.iterrows():
            tid = str(r.get("ID","")).strip() or str(r.get(COL["TRADE_ID"], "")).strip()
            if tid: m[tid] = r
        return m

    if edit_mode:
        cA, cB, cC = st.columns(3)
        do_save = cA.button("💾 Opslaan wijzigingen", type="primary")
        del_id  = cB.text_input("Verwijder Trade_ID (exact)")
        do_del  = cC.button("🗑️ Verwijderen")

        if do_del and del_id.strip():
            try:
                delete_entry(del_id.strip())
                st.success(f"Verwijderd: {del_id.strip()}")
                APP["last_save_ts"] = get_last_save_ts(); save_state(APP)
                st.rerun()
            except Exception as e:
                st.error(f"Opslaan mislukt: {e}")

        if do_save:
            base_all = load_journal()
            base_map = _keyed(df_view)
            new_map  = _keyed(edited)

            # Updates + Adds
            ok_all = True
            for tid, row in new_map.items():
                payload = _map_row_to_schema(row)
                try:
                    if tid in base_map:
                        update_entry(tid, payload)
                    else:
                        append_entry(payload)
                except Exception as e:
                    ok_all = False
                    st.error(f"Opslaan mislukt ({tid}): {e}")

            if ok_all:
                st.success("Wijzigingen opgeslagen ✅")
                APP["last_save_ts"] = get_last_save_ts(); save_state(APP)
                if APP.get("gh_sync_enabled", False):
                    ok, msg = github_sync.sync_now(); st.info(msg)
                st.rerun()

    # export
    if st.button("Exporteer zichtbare rijen (.csv)"):
        out = export_visible(df_filtered)
        st.success(f"Export voltooid: `{out}`")

# ---------- SETTINGS TAB ----------
with tab_settings:
    st.subheader("Systeem")
    # Optioneel: healthcheck module, maar we tonen simpele info als fallback
    try:
        import healthcheck
        if hasattr(healthcheck, "report"):
            rep = healthcheck.report()
            s0, s1, s2, s3 = st.columns(4)
            s0.metric("Python", rep.get("python","?"))
            s1.metric("Denominatie", rep.get("denom","BTC"))
            s2.metric("AI", "Online" if rep.get("ai",{}).get("online") else rep.get("ai",{}).get("reason","Offline"))
            s3.metric("Dirs OK", "✅" if rep.get("dirs_ok") else "⚠️")
    except Exception:
        st.caption("Healthcheck niet beschikbaar.")

    st.divider()
    st.subheader("Opslag & Back-up")
    st.caption("Paden: data/ en data/.bak/")
    cols = st.columns(3)
    if cols[0].button("📸 Snapshot maken (.zip naar data/.bak/)"):
        blob = make_backup_zip()
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        fname = f"data/.bak/snapshot_{ts}.zip"
        with open(fname, "wb") as f:
            f.write(blob)
        APP["last_snapshot_ts"] = ts; save_state(APP)
        st.success(f"Snapshot opgeslagen: {fname}")
    st.caption("Laatste snapshot: " + (APP.get("last_snapshot_ts","—")))

    # GitHub status tonen (read-only)
    last_sync_ts = APP.get("last_sync_ts","")
    last_sync_msg = APP.get("last_sync_msg","Sync uit")
    st.caption(f"Laatste sync: {last_sync_ts or '—'} ({last_sync_msg})")
