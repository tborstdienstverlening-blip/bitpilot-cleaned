from __future__ import annotations

import time
from typing import Any, Dict

import pandas as pd
import streamlit as st

# Repo-modules (blijven ongewijzigd)
from schema import COL, ORDER, DATE_FMT
from utils_config import load_config
from journal_store import load_journal, get_last_save_ts
from import_export import export_visible
from app_state import load_state, save_state
from backup_utils import make_backup_zip
from kpi_utils import apply_filters

# Nieuwe modules (opsplitsing)
from services.pnl_service import compute_autos
from services.kpi_service import compute_kpis
from ui.kpi_bar import render_kpi_bar
from ui.journal_table import render_table


# ──────────────────────────────────────────────────────────────────────────────
# App meta
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="Bitpilot — Journal", layout="wide")

# ──────────────────────────────────────────────────────────────────────────────
# Config & app-state
# ──────────────────────────────────────────────────────────────────────────────
CFG: Dict[str, Any] = load_config()
APP: Dict[str, Any] = load_state()

START_UI: float = float(APP.get("start_kapitaal", CFG.get("START_KAPITAAL", 0)))
DEFAULT_RISK_PCT: float = (
    CFG.get("risk", {}).get("percent")
    if isinstance(CFG.get("risk"), dict)
    else CFG.get("RISK_PERCENT", 1.0)
)

APP.setdefault("filters", {"periode": "Alle", "search": "", "emoties": []})
save_state(APP)


# ──────────────────────────────────────────────────────────────────────────────
# Tabs
# ──────────────────────────────────────────────────────────────────────────────
tab_journal, tab_settings = st.tabs([" Journal", "⚙️ Settings"])


# =============================================================================
# SETTINGS (ongewijzigde UI/gedrag)
# =============================================================================
with tab_settings:
    st.subheader("Systeem")
    try:
        import healthcheck

        if hasattr(healthcheck, "report"):
            rep = healthcheck.report()
            s0, s1, s2, s3 = st.columns(4)
            s0.metric("Python", rep.get("python", "?"))
            s1.metric("Denominatie", rep.get("denom", "BTC"))
            s2.metric(
                "AI",
                "Online"
                if rep.get("ai", {}).get("online")
                else rep.get("ai", {}).get("reason", "Offline"),
            )
            s3.metric("Dirs OK", "✅" if rep.get("dirs_ok") else "⚠️")
    except Exception:
        st.caption("Healthcheck niet beschikbaar.")

    st.divider()
    st.subheader("Startkapitaal")
    start_val = st.number_input(
        "Startkapitaal (BTC)", min_value=0.0, step=0.000001, value=float(START_UI)
    )
    if st.button(" Opslaan (Startkapitaal)"):
        APP["start_kapitaal"] = float(start_val)
        save_state(APP)
        st.success("Startkapitaal opgeslagen")
        st.rerun()

    st.divider()
    st.subheader("Opslag & Back-up")
    st.caption("Paden: data/ en data/.bak/")
    cols = st.columns(3)
    if cols[0].button(" Snapshot maken (.zip → data/.bak/)"):
        blob = make_backup_zip()
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        fname = f"data/.bak/snapshot_{ts}.zip"
        with open(fname, "wb") as f:
            f.write(blob)
        APP["last_snapshot_ts"] = ts
        save_state(APP)
        st.success(f"Snapshot opgeslagen: {fname}")

    st.caption("Laatste snapshot: " + (APP.get("last_snapshot_ts", "—")))
    st.caption(f"Laatste save: {get_last_save_ts() or '—'}")
    st.caption(
        f"Laatste sync: {APP.get('last_sync_ts','—') or '—'} "
        f"({APP.get('last_sync_msg','Sync uit')})"
    )


# =============================================================================
# JOURNAL (regie + oproepen services/ui)
# =============================================================================
with tab_journal:
    # Header met Filters + badges (ongewijzigd)
    h1, h2, h3 = st.columns([4, 2, 3])
    with h1:
        st.subheader("Journal")
    with h2:
        with st.popover(" Filters", use_container_width=True):
            filt = APP["filters"]
            filt["periode"] = st.selectbox(
                "Periode",
                ["Alle", "YTD", "MTD", "WTD"],
                index=["Alle", "YTD", "MTD", "WTD"].index(filt.get("periode", "Alle")),
            )
            filt["search"] = st.text_input(
                "Zoek (Trade_ID)", value=filt.get("search", "")
            )
            filt["emoties"] = st.multiselect(
                "Emoties", ["Kalm", "Twijfel", "Stress"], default=filt.get("emoties", [])
            )
            cA, cB = st.columns(2)
            if cA.button("Reset"):
                filt.update({"periode": "Alle", "search": "", "emoties": []})
            if cB.button("Toepassen"):
                APP["filters"] = filt
                save_state(APP)
                st.rerun()
    with h3:
        from journal_store import get_last_save_ts
        st.caption(f" Laatste save: {get_last_save_ts() or '—'}")
        st.caption(
            f"☁️ Laatste sync: {APP.get('last_sync_ts','—') or '—'} "
            f"({APP.get('last_sync_msg','Sync uit')})"
        )

    st.divider()

    # Data laden & kolommen garanderen
    df_raw = load_journal()
    if df_raw is None or df_raw.empty:
        df_raw = pd.DataFrame(columns=ORDER)
    for col in ORDER:
        if col not in df_raw.columns:
            df_raw[col] = ""

    # Forceer tekstkolommen (voor vrij invoeren met komma/punt)
    TEXT_COLS = [COL["PLAN"], COL["NOTES"], COL["EMOTIES"], COL["SHOTS"], COL["SETUP"], COL["SIDE"]]
    for c in TEXT_COLS:
        if c in df_raw.columns:
            df_raw[c] = pd.Series(df_raw[c], dtype="string").fillna("")

    # Defaults
    if COL["RISK_PCT"] in df_raw.columns:
        df_raw[COL["RISK_PCT"]] = df_raw[COL["RISK_PCT"]].apply(
            lambda v: (DEFAULT_RISK_PCT if str(v).strip() == "" else v)
        )
    else:
        df_raw[COL["RISK_PCT"]] = DEFAULT_RISK_PCT
    if COL["CAP_TRADE"] not in df_raw.columns:
        df_raw[COL["CAP_TRADE"]] = ""

    # Zorg dat PNL_BTC bestaat (lokaal; geen schema-migratie)
    if "PNL_BTC" not in df_raw.columns:
        df_raw["PNL_BTC"] = 0.0

    # Autos (contract size, RR's, PNL's)
    df_auto = compute_autos(df_raw, DEFAULT_RISK_PCT)

    # Filters
    filt = APP.get("filters", {"periode": "Alle", "search": "", "emoties": []})
    df_filtered = apply_filters(
        df_auto,
        search=filt.get("search", ""),
        emoties=filt.get("emoties", []),
        periode=filt.get("periode", "Alle"),
    )

    # KPI's
    kpi = compute_kpis(df_filtered, START_UI)
    render_kpi_bar(START_UI, kpi)

    st.divider()

    if df_filtered.empty:
        st.info("Nog geen trades in selectie.")

    # View-data (ID string-kolom zoals voorheen)
    df_view = df_filtered.copy()
    df_view["ID"] = df_view[COL["TRADE_ID"]].astype(str)

    # Journal-tabel (inclusief edit/CRUD/ghost-row)
    render_table(df_view)

    # Export (ongewijzigd)
    if st.button("Exporteer zichtbare rijen (.csv)"):
        out = export_visible(df_filtered)
        st.success(f"Export voltooid: `{out}`")
