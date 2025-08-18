# cockpit.py — C0-04 Bootfix (no features)
from __future__ import annotations
import streamlit as st
import pandas as pd

from compat import safe_import, load_config, get_ai_status, ai_analyze_stub
from schema import COL, REQUIRED_ORDER, DATE_FMT
from import_export import read_entries, write_entries
from stats_utils import kpi_count, kpi_winrate, kpi_avg_r

# Optionele modules (zacht geladen)
theme_manager = safe_import("theme_manager")
events_ui = safe_import("events_ui")
coach_engine = safe_import("coach_engine")
copilot = safe_import("copilot")
healthcheck = safe_import("healthcheck")

st.set_page_config(page_title="Bitpilot Cockpit", layout="wide")

# Thema
if theme_manager and hasattr(theme_manager, "inject_theme_css"):
    theme_manager.inject_theme_css()

# Sidebar filters (unieke keys)
st.sidebar.title("⚙️ Filters")
st.sidebar.selectbox("Portefeuille", ["Alle","LT","Swing"], key="flt_portfolio")
st.sidebar.selectbox("Periode", ["Alle","YTD","MTD","WTD"], key="flt_periode")
st.sidebar.multiselect("Categorie", ["BTC","Equities","FX","Commodities"], key="flt_categorie")
st.sidebar.text_input("🔖 Tags (comma)", key="flt_tags")
st.sidebar.multiselect("Emoties", ["Kalm","Twijfel","Stress"], key="flt_emoties")
st.sidebar.button("Reset filters", key="flt_reset")

st.title("🚀 Bitpilot — Cockpit (C0-04 Bootfix)")

# Healthcheck
if healthcheck and hasattr(healthcheck, "report"):
    rep = healthcheck.report()
    c0, c1, c2, c3 = st.columns(4)
    c0.markdown(f"**Python**: `{rep.get('python','?')}`")
    c1.markdown(f"**Platform**: `{rep.get('platform','?')}`")
    ai_ok = rep.get("ai",{}).get("online", False)
    c2.markdown("**AI**: ✅ Online" if ai_ok else f"**AI**: ⚠️ Offline — {rep.get('ai',{}).get('reason','')}")
    c3.markdown("**Dirs**: ✅" if rep.get("dirs_ok") else "**Dirs**: ⚠️ aangemaakt")
else:
    st.info("Healthcheck niet beschikbaar (compat).")

st.divider()

tab_journal, tab_ai, tab_events = st.tabs(["📓 Journal", "🤖 AI", "📅 Events"])

# Journal — read-only tabel + KPI's (geen crashes bij lege data)
with tab_journal:
    df = read_entries()
    k0, k1, k2 = st.columns(3)
    k0.metric("Journal entries", kpi_count(df))
    k1.metric("Win rate", kpi_winrate(df))
    k2.metric("R gemiddeld", kpi_avg_r(df))
    st.dataframe(df, use_container_width=True)

# AI — stub als geen key
with tab_ai:
    cfg = load_config()
    ai_status = get_ai_status(cfg)
    q = st.text_area("Vraag of setup", key="ai_prompt")
    if st.button("Analyseer", key="ai_analyse"):
        if ai_status.online and copilot and hasattr(copilot, "analyze"):
            st.write(copilot.analyze(q))
        else:
            st.write(ai_analyze_stub(q))

# Events — alleen renderen als module er is
with tab_events:
    if events_ui and hasattr(events_ui, "render_events"):
        events_ui.render_events()
    else:
        st.info("Events-module niet beschikbaar (compat-stub).")

st.caption("C0-04 Bootfix — app start stabiel zonder harde afhankelijkheden.")
