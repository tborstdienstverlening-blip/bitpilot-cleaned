from __future__ import annotations
import time
import streamlit as st
import pandas as pd

from schema import COL, ORDER, DATE_FMT, SETUP_OPTS
from utils_config import load_config, format_btc
from journal_store import load_journal, append_entry, update_entry, delete_entry, get_last_save_ts
from import_export import export_visible
from app_state import load_state, save_state
from backup_utils import make_backup_zip
import github_sync

from kpi_utils import apply_filters, compute_kpis
from risk_utils import contracts_from_row

st.set_page_config(page_title="Bitpilot — Journal", layout="wide")

# ---------- Config & app-state ----------
CFG = load_config()
APP = load_state()

START_UI = float(APP.get("start_kapitaal", CFG.get("START_KAPITAAL", 0)))
DEFAULT_RISK_PCT = (CFG.get("risk", {}).get("percent")
                    if isinstance(CFG.get("risk"), dict) else CFG.get("RISK_PERCENT", 1.0))

APP.setdefault("filters", {"periode":"Alle","search":"","emoties":[]})
save_state(APP)

def _to_num(s):
    try:
        t = str(s).strip().replace(",", ".")
        return None if t=="" else float(t)
    except Exception:
        return None

# ---------- Tabs ----------
tab_journal, tab_settings = st.tabs(["📓 Journal", "⚙️ Settings"])

# ========================================
# SETTINGS
# ========================================
with tab_settings:
    st.subheader("Systeem")
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
    st.subheader("Startkapitaal")
    start_val = st.number_input("Startkapitaal (BTC)", min_value=0.0, step=0.000001, value=float(START_UI))
    if st.button("💾 Opslaan (Startkapitaal)"):
        APP["start_kapitaal"] = float(start_val); save_state(APP)
        st.success("Startkapitaal opgeslagen"); st.rerun()

    st.divider()
    st.subheader("Opslag & Back-up")
    st.caption("Paden: data/ en data/.bak/")
    cols = st.columns(3)
    if cols[0].button("📸 Snapshot maken (.zip → data/.bak/)"):
        blob = make_backup_zip()
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        fname = f"data/.bak/snapshot_{ts}.zip"
        with open(fname, "wb") as f:
            f.write(blob)
        APP["last_snapshot_ts"] = ts; save_state(APP)
        st.success(f"Snapshot opgeslagen: {fname}")
    st.caption("Laatste snapshot: " + (APP.get("last_snapshot_ts","—")))
    st.caption(f"Laatste save: {get_last_save_ts() or '—'}")
    st.caption(f"Laatste sync: {APP.get('last_sync_ts','—') or '—'} ({APP.get('last_sync_msg','Sync uit')})")

# ========================================
# JOURNAL
# ========================================
with tab_journal:
    # Header met Filters + badges
    h1, h2, h3 = st.columns([4,2,3])
    with h1: st.subheader("Journal")
    with h2:
        with st.popover("🔎 Filters", use_container_width=True):
            filt = APP["filters"]
            filt["periode"] = st.selectbox("Periode", ["Alle","YTD","MTD","WTD"], index=["Alle","YTD","MTD","WTD"].index(filt.get("periode","Alle")))
            filt["search"]  = st.text_input("Zoek (Trade_ID)", value=filt.get("search",""))
            filt["emoties"] = st.multiselect("Emoties", ["Kalm","Twijfel","Stress"], default=filt.get("emoties", []))
            cA, cB = st.columns(2)
            if cA.button("Reset"):
                filt.update({"periode":"Alle","search":"","emoties":[]})
            if cB.button("Toepassen"):
                APP["filters"] = filt; save_state(APP); st.rerun()
    with h3:
        st.caption(f"💾 Laatste save: {get_last_save_ts() or '—'}")
        st.caption(f"☁️ Laatste sync: {APP.get('last_sync_ts','—') or '—'} ({APP.get('last_sync_msg','Sync uit')})")

    st.divider()

    # Data laden & kolommen garanderen
    df_raw = load_journal()
    if df_raw is None or df_raw.empty:
        df_raw = pd.DataFrame(columns=ORDER)
    for col in ORDER:
        if col not in df_raw.columns:
            df_raw[col] = ""

    # ---- DTYPE FIX: forceer tekstkolommen naar string (voor TextColumn)
    TEXT_COLS = [
        COL["PLAN"], COL["NOTES"], COL["EMOTIES"], COL["SHOTS"],
        COL["SETUP"], COL["SIDE"]
    ]
    for c in TEXT_COLS:
        if c in df_raw.columns:
            df_raw[c] = pd.Series(df_raw[c], dtype="string").fillna("")

    # Default Risk % en Kapitaal (trade) initialiseren indien leeg
    if COL["RISK_PCT"] in df_raw.columns:
        df_raw[COL["RISK_PCT"]] = df_raw[COL["RISK_PCT"]].apply(lambda v: (DEFAULT_RISK_PCT if str(v).strip()=="" else v))
    else:
        df_raw[COL["RISK_PCT"]] = DEFAULT_RISK_PCT
    if COL["CAP_TRADE"] not in df_raw.columns:
        df_raw[COL["CAP_TRADE"]] = ""

    # Backend autos: Contract size + RR's (alleen rij-velden)
    def _row_autos(row: pd.Series) -> pd.Series:
        entry = _to_num(row.get(COL["ENTRY"]))
        sl    = _to_num(row.get(COL["SL"]))
        cap   = _to_num(row.get(COL["CAP_TRADE"]))
        risk_pct_val = _to_num(row.get(COL["RISK_PCT"])) if row.get(COL["RISK_PCT"]) is not None else DEFAULT_RISK_PCT

        # ✅ schaalfix + nearest afronding
        risk_btc, contracts = contracts_from_row(cap, risk_pct_val, entry, sl)
        row[COL["CONTRACT_SIZE"]] = None if contracts is None else int(contracts)

        # RR (Plan)
        side = (row.get(COL["SIDE"]) or "").strip().lower()
        tp1, tp2, tp3 = _to_num(row.get(COL["TP1"])), _to_num(row.get(COL["TP2"])), _to_num(row.get(COL["TP3"]))
        rr_plan = None
        den = None
        if entry is not None and sl is not None:
            den = abs(entry - sl)
        if den is not None and den != 0:
            cands = []
            for tp in [tp1, tp2, tp3]:
                if tp is None: continue
                if side == "short":
                    cands.append((entry - tp) / den)
                else:
                    cands.append((tp - entry) / den)
            rr_plan = max(cands) if cands else None
        row[COL["RR_PLAN"]] = "n.v.t." if rr_plan is None else f"{rr_plan:.2f}"

        # RR (Actueel) — NETTO met rij-risk (Kapitaal×Risk%)
        pnl_tp = sum([x for x in [_to_num(row.get(COL["PNL_TP1"])),
                                  _to_num(row.get(COL["PNL_TP2"])),
                                  _to_num(row.get(COL["PNL_TP3"]))] if x is not None])
        fees = _to_num(row.get(COL["FEES"])) or 0.0
        rr_actual = None
        if risk_btc not in (None, 0) and pnl_tp is not None:
            rr_actual = (pnl_tp - fees) / risk_btc
        row[COL["RR_ACTUAL"]] = "n.v.t." if rr_actual is None else f"{rr_actual:.2f}"

        return row

    df_auto = df_raw.apply(_row_autos, axis=1)

    # Converteer numerieke kolommen naar numeriek dtype (voor NumberColumn-compat)
    NUM_COLS = [COL["RISK_PCT"], COL["CAP_TRADE"], COL["CONTRACT_SIZE"],
                COL["ENTRY"], COL["SL"], COL["TP1"], COL["TP2"], COL["TP3"],
                COL["FEES"], COL["PNL_TP1"], COL["PNL_TP2"], COL["PNL_TP3"], COL["PNL_EXIT"]]
    for c in NUM_COLS:
        if c in df_auto.columns:
            df_auto[c] = pd.to_numeric(df_auto[c], errors="coerce")
    # Contract size als Int64 (nullable)
    if COL["CONTRACT_SIZE"] in df_auto.columns:
        df_auto[COL["CONTRACT_SIZE"]] = df_auto[COL["CONTRACT_SIZE"]].astype("Int64")

    # Filters toepassen (geen Tags)
    filt = APP.get("filters", {"periode":"Alle","search":"","emoties":[]})
    df_filtered = apply_filters(df_auto, search=filt.get("search",""),
                                emoties=filt.get("emoties", []),
                                periode=filt.get("periode","Alle"))

    # KPI-balk (NETTO: Σ[coalesce(ΣTP, Exit, 0) − Fees])
    from kpi_utils import compute_kpis  # late import to be safe
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

    # Definitieve zichtbare kolommen (zonder Risk (BTC))
    vis_cols = [
        COL["DATUM"], "ID", COL["SIDE"], COL["SETUP"],
        COL["RISK_PCT"], COL["CAP_TRADE"], COL["CONTRACT_SIZE"],
        COL["RR_PLAN"], COL["RR_ACTUAL"],
        COL["ENTRY"], COL["SL"], COL["TP1"], COL["TP2"], COL["TP3"],
        COL["FEES"], COL["PNL_TP1"], COL["PNL_TP2"], COL["PNL_TP3"], COL["PNL_EXIT"],
        COL["PLAN"], COL["NOTES"], COL["EMOTIES"], COL["SHOTS"],
    ]
    df_view = df_filtered.copy()
    df_view["ID"] = df_view[COL["TRADE_ID"]].astype(str)
    for col in vis_cols:
        if col not in df_view.columns: df_view[col] = ""

    # kolomconfig & tooltips
    colcfg = {
        COL["SIDE"]:  st.column_config.SelectboxColumn(COL["SIDE"], options=["Long","Short"], help="Richting van de trade"),
        COL["RISK_PCT"]: st.column_config.NumberColumn(COL["RISK_PCT"], help="percentage van Kapitaal (trade)", min_value=0.1, max_value=5.0, step=0.1),
        COL["CAP_TRADE"]: st.column_config.NumberColumn(COL["CAP_TRADE"], help="BTC"),
        COL["CONTRACT_SIZE"]: st.column_config.NumberColumn(COL["CONTRACT_SIZE"], help="contracts (Deribit $1/contract)", step=1, disabled=True),
        COL["ENTRY"]: st.column_config.NumberColumn(COL["ENTRY"], help="prijs"),
        COL["SL"]:    st.column_config.NumberColumn(COL["SL"], help="prijs"),
        COL["TP1"]:   st.column_config.NumberColumn(COL["TP1"], help="prijs"),
        COL["TP2"]:   st.column_config.NumberColumn(COL["TP2"], help="prijs"),
        COL["TP3"]:   st.column_config.NumberColumn(COL["TP3"], help="prijs"),
        COL["RR_PLAN"]:   st.column_config.TextColumn(COL["RR_PLAN"], help="Max van TP’s; n.v.t. als SL=Entry of geen TP"),
        COL["RR_ACTUAL"]: st.column_config.TextColumn(COL["RR_ACTUAL"], help="(ΣTP-PNL − Fees) / (Kapitaal×Risk%) — Exit telt niet mee"),
        COL["PLAN"]:  st.column_config.TextColumn(COL["PLAN"], help="Volledige tekst is te bewerken in de bewerker hieronder"),
        COL["NOTES"]: st.column_config.TextColumn(COL["NOTES"], help="Volledige tekst is te bewerken in de bewerker hieronder"),
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
    st.caption("Tip: zet ‘✎ Bewerken’ aan voor ghost row / inline edits.")

    # Plan/Notities bewerker (uitklap)
    with st.expander("🧾 Plan/Notities bewerken"):
        all_ids = df_filtered[COL["TRADE_ID"]].astype(str).tolist()
        sel_id = st.selectbox("Kies Trade_ID", ["(geen)"] + all_ids, index=0)
        if sel_id != "(geen)":
            base_row = df_filtered[df_filtered[COL["TRADE_ID"]].astype(str) == sel_id].iloc[0].to_dict()
            plan_txt = st.text_area("Plan", value=str(base_row.get(COL["PLAN"], "")), height=160)
            notes_txt= st.text_area("Notities", value=str(base_row.get(COL["NOTES"], "")), height=160)
            if st.button("💾 Bewaar Plan/Notities", type="primary"):
                try:
                    payload = base_row.copy()
                    payload[COL["PLAN"]]  = plan_txt
                    payload[COL["NOTES"]] = notes_txt
                    update_entry(sel_id, payload)
                    st.success("Plan/Notities opgeslagen ✅")
                    st.rerun()
                except Exception as e:
                    st.error(f"Opslaan mislukt: {e}")

    # Opslaan/Verwijderen
    def _map_row_to_payload(r: pd.Series, base_row: dict) -> dict:
        out = {k: base_row.get(k, "") for k in ORDER}
        tid = str(r.get("ID","")).strip() or str(base_row.get(COL["TRADE_ID"], "")).strip()
        out[COL["TRADE_ID"]] = tid
        out[COL["DATUM"]] = pd.to_datetime(r.get(COL["DATUM"]) or base_row.get(COL["DATUM"]) or pd.Timestamp.today()).strftime(DATE_FMT)
        out[COL["SIDE"]]  = str(r.get(COL["SIDE"], base_row.get(COL["SIDE"], ""))).strip()
        out[COL["SETUP"]] = str(r.get(COL["SETUP"], base_row.get(COL["SETUP"], ""))).strip()
        out[COL["RISK_PCT"]] = r.get(COL["RISK_PCT"], base_row.get(COL["RISK_PCT"], DEFAULT_RISK_PCT))
        out[COL["CAP_TRADE"]] = r.get(COL["CAP_TRADE"], base_row.get(COL["CAP_TRADE"], ""))
        out[COL["CONTRACT_SIZE"]] = r.get(COL["CONTRACT_SIZE"], base_row.get(COL["CONTRACT_SIZE"], ""))
        out[COL["RR_PLAN"]]   = r.get(COL["RR_PLAN"], base_row.get(COL["RR_PLAN"], ""))
        out[COL["RR_ACTUAL"]] = r.get(COL["RR_ACTUAL"], base_row.get(COL["RR_ACTUAL"], ""))

        out[COL["ENTRY"]] = r.get(COL["ENTRY"], base_row.get(COL["ENTRY"], ""))
        out[COL["SL"]]    = r.get(COL["SL"], base_row.get(COL["SL"], ""))
        out[COL["TP1"]]   = r.get(COL["TP1"], base_row.get(COL["TP1"], ""))
        out[COL["TP2"]]   = r.get(COL["TP2"], base_row.get(COL["TP2"], ""))
        out[COL["TP3"]]   = r.get(COL["TP3"], base_row.get(COL["TP3"], ""))

        out[COL["FEES"]]     = r.get(COL["FEES"], base_row.get(COL["FEES"], ""))
        out[COL["PNL_TP1"]]  = r.get(COL["PNL_TP1"], base_row.get(COL["PNL_TP1"], ""))
        out[COL["PNL_TP2"]]  = r.get(COL["PNL_TP2"], base_row.get(COL["PNL_TP2"], ""))
        out[COL["PNL_TP3"]]  = r.get(COL["PNL_TP3"], base_row.get(COL["PNL_TP3"], ""))
        out[COL["PNL_EXIT"]] = r.get(COL["PNL_EXIT"], base_row.get(COL["PNL_EXIT"], ""))  # safe

        out[COL["PLAN"]]   = r.get(COL["PLAN"], base_row.get(COL["PLAN"], ""))
        out[COL["NOTES"]]  = r.get(COL["NOTES"], base_row.get(COL["NOTES"], ""))
        out[COL["EMOTIES"]]= r.get(COL["EMOTIES"], base_row.get(COL["EMOTIES"], ""))
        out[COL["SHOTS"]]  = r.get(COL["SHOTS"], base_row.get(COL["SHOTS"], ""))
        return out

    base_map = { str(r[COL["TRADE_ID"]]): r.to_dict() for _, r in df_view.iterrows() }

    if edit_mode:
        cA, cB, cC = st.columns(3)
        do_save = cA.button("💾 Opslaan wijzigingen", type="primary")
        del_id  = cB.text_input("Verwijder Trade_ID (exact)")
        do_del  = cC.button("🗑️ Verwijderen")

        if do_del and del_id.strip():
            try:
                delete_entry(del_id.strip())
                st.success(f"Verwijderd: {del_id.strip()}")
                st.rerun()
            except Exception as e:
                st.error(f"Opslaan mislukt: {e}")

        if do_save:
            ok_all = True
            for idx, row in edited.iterrows():
                tid = str(row.get("ID","")).strip()
                base_row = base_map.get(tid, {k:"" for k in ORDER})
                payload = _map_row_to_payload(row, base_row)
                try:
                    if tid in base_map:
                        update_entry(tid, payload)
                    else:
                        append_entry(payload)
                except Exception as e:
                    ok_all = False
                    st.error(f"Opslaan mislukt ({tid or f'row#{idx+1}'}): {e}")
            if ok_all:
                st.success("Wijzigingen opgeslagen ✅")
                if APP.get("gh_sync_enabled", False):
                    ok, msg = github_sync.sync_now(); st.info(msg)
                st.rerun()

    # Export
    if st.button("Exporteer zichtbare rijen (.csv)"):
        out = export_visible(df_filtered)
        st.success(f"Export voltooid: `{out}`")
