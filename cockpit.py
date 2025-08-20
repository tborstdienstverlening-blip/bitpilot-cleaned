from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple, List

import pandas as pd
import streamlit as st

# Repo-modules
from schema import COL, ORDER, DATE_FMT
from utils_config import load_config
from journal_store import (
    load_journal,
    append_entry,
    update_entry,
    delete_entry,
    get_last_save_ts,
)
from import_export import export_visible
from app_state import load_state, save_state
from backup_utils import make_backup_zip
import github_sync
from kpi_utils import apply_filters
from risk_utils import contracts_from_row

# Nieuwe (alleen lokaal) kolomlabel zonder schema-wijziging
PNL_BTC_COL = "PNL_BTC"

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
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def _to_num(s: Any) -> Optional[float]:
    """Parse naar float; accepteert komma of punt. Lege/ongeldige waarden -> None."""
    try:
        t = str(s).strip().replace(",", ".")
        return None if t == "" else float(t)
    except Exception:
        return None


def _fmt_int_grouped(n: int | float) -> str:
    """Excel-achtige weergave met duizendtallen: 202596 -> '202,596'."""
    try:
        return f"{int(round(float(n))):,}"
    except Exception:
        return ""


def _fmt_num_3dec(x: Optional[float]) -> str:
    """Duizendscheiding + max 3 decimals; trim trailing nullen."""
    if x is None:
        return ""
    s = f"{float(x):,.3f}".rstrip("0").rstrip(".")
    return s


def _row_is_effectively_empty(row: pd.Series) -> bool:
    """Detecteer lege ghost-row zodat we die niet opslaan."""
    keys = [COL["SIDE"], COL["RISK_PCT"], COL["CAP_TRADE"], COL["ENTRY"], COL["SL"], COL["TP1"], COL["TP2"], COL["TP3"]]
    for k in keys:
        v = row.get(k, "")
        if isinstance(v, str):
            if v.strip() != "":
                return False
        elif pd.notna(v):
            return False
    return True


def _next_sequential_id(existing_ids: List[str]) -> str:
    """Bepaal volgende oplopende integer-ID als string ('1','2','3',...)."""
    ints = []
    for x in existing_ids:
        s = str(x).strip()
        if s.isdigit():
            ints.append(int(s))
    nxt = (max(ints) + 1) if ints else 1
    return str(nxt)


def _last_trade_info(df: pd.DataFrame) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[str], Optional[int], Optional[int]]:
    """
    Retourneert (last_pnl_exit, last_pnl_btc, last_fee, result_text, last_win_add, last_loss_add).
    result_text: 'Win'/'Loss'/'Break-even'/None
    """
    if df is None or df.empty:
        return None, None, None, None, None, None
    row = df.iloc[-1]
    last_pnl_exit = _to_num(row.get(COL["PNL_EXIT"])) or 0.0
    last_pnl_btc = _to_num(row.get(PNL_BTC_COL)) or 0.0
    last_fee = _to_num(row.get(COL["FEES"])) or 0.0
    res = "Win" if last_pnl_exit > 0 else ("Loss" if last_pnl_exit < 0 else "Break-even")
    win_add = 1 if last_pnl_exit > 0 else 0
    loss_add = 1 if last_pnl_exit < 0 else 0
    return last_pnl_exit, last_pnl_btc, last_fee, res, win_add, loss_add


# ──────────────────────────────────────────────────────────────────────────────
# Tabs
# ──────────────────────────────────────────────────────────────────────────────
tab_journal, tab_settings = st.tabs([" Journal", "⚙️ Settings"])

# =============================================================================
# SETTINGS
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
# JOURNAL
# =============================================================================
with tab_journal:
    # Header met Filters + badges
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

    # Forceer tekstkolommen naar string (voor TextColumn/komma-invoer)
    TEXT_COLS = [
        COL["PLAN"],
        COL["NOTES"],
        COL["EMOTIES"],
        COL["SHOTS"],
        COL["SETUP"],
        COL["SIDE"],
    ]
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

    # Voeg de nieuwe kolom PNL_BTC toe als niet aanwezig (zonder schema-wijziging)
    if PNL_BTC_COL not in df_raw.columns:
        df_raw[PNL_BTC_COL] = 0.0

    # ──────────────────────────────────────────────────────────────────────
    # Backend autos: Contract size + RR's + PNL_Exit (behoud) + PNL_BTC (nieuw)
    # ──────────────────────────────────────────────────────────────────────
    def _row_autos(row: pd.Series) -> pd.Series:
        # Contract Size
        entry = _to_num(row.get(COL["ENTRY"]))
        sl = _to_num(row.get(COL["SL"]))
        cap = _to_num(row.get(COL["CAP_TRADE"]))
        risk_pct_val = (
            _to_num(row.get(COL["RISK_PCT"]))
            if row.get(COL["RISK_PCT"]) is not None
            else DEFAULT_RISK_PCT
        )

        _, contracts = contracts_from_row(cap, risk_pct_val, entry, sl)
        row[COL["CONTRACT_SIZE"]] = "" if contracts is None else _fmt_int_grouped(contracts)

        # RR (Plan)
        side = (row.get(COL["SIDE"]) or "").strip().lower()
        tp1_price, tp2_price, tp3_price = (
            _to_num(row.get(COL["TP1"])),
            _to_num(row.get(COL["TP2"])),
            _to_num(row.get(COL["TP3"])),
        )
        rr_plan = None
        den = None
        if entry is not None and sl is not None:
            den = abs(entry - sl)
        if den is not None and den != 0:
            cands = []
            for tp in [tp1_price, tp2_price, tp3_price]:
                if tp is None:
                    continue
                if side == "short":
                    cands.append((entry - tp) / den)
                else:
                    cands.append((tp - entry) / den)
            rr_plan = max(cands) if cands else None
        row[COL["RR_PLAN"]] = "n.v.t." if rr_plan is None else f"{rr_plan:.2f}"

        # PnL velden (bewerkbare kolommen bestaan al: PNL_TP1..3 en PNL_Exit)
        pnl_tp1 = _to_num(row.get(COL["PNL_TP1"])) or 0.0
        pnl_tp2 = _to_num(row.get(COL["PNL_TP2"])) or 0.0
        pnl_tp3 = _to_num(row.get(COL["PNL_TP3"])) or 0.0

        # PNL_Exit: behoud bestaande waarde; vul alleen met 0.0 als leeg (GEEN herberekening forceren)
        pnl_exit_existing = _to_num(row.get(COL["PNL_EXIT"]))
        pnl_exit = 0.0 if pnl_exit_existing is None else pnl_exit_existing
        row[COL["PNL_EXIT"]] = pnl_exit  # zichtbaar als numeriek

        # ✅ NIEUW: PNL_BTC = TP1 + TP2 + TP3 + Exit
        pnl_btc = (pnl_tp1 or 0.0) + (pnl_tp2 or 0.0) + (pnl_tp3 or 0.0) + (pnl_exit or 0.0)
        row[PNL_BTC_COL] = pnl_btc

        # ✅ RR (Actueel) = PNL_BTC / (Kapitaal × Risk%/100) met guard
        row_risk_btc = None
        if (cap is not None) and (risk_pct_val is not None):
            try:
                row_risk_btc = float(cap) * (float(risk_pct_val) / 100.0)
            except Exception:
                row_risk_btc = None

        if row_risk_btc is None or row_risk_btc <= 0:
            row[COL["RR_ACTUAL"]] = "—"
        else:
            rr_actual_val = pnl_btc / row_risk_btc
            row[COL["RR_ACTUAL"]] = f"{rr_actual_val:.2f}"

        return row

    df_auto = df_raw.apply(_row_autos, axis=1)

    # Dtypes voor view:
    NUM_COLS = [
        COL["RISK_PCT"],
        COL["FEES"],
        COL["PNL_TP1"],
        COL["PNL_TP2"],
        COL["PNL_TP3"],
        COL["PNL_EXIT"],
        PNL_BTC_COL,
    ]
    for c in NUM_COLS:
        if c in df_auto.columns:
            df_auto[c] = pd.to_numeric(df_auto[c], errors="coerce")

    # Filters
    filt = APP.get("filters", {"periode": "Alle", "search": "", "emoties": []})
    df_filtered = apply_filters(
        df_auto,
        search=filt.get("search", ""),
        emoties=filt.get("emoties", []),
        periode=filt.get("periode", "Alle"),
    )

    # ──────────────────────────────────────────────────────────────────────
    # KPI-balk — (labels ongewijzigd), wiring: ΣPNL_BTC en Fees correct
    # ──────────────────────────────────────────────────────────────────────
    if not df_filtered.empty:
        fees_series = pd.to_numeric(df_filtered[COL["FEES"]], errors="coerce").fillna(0.0)
        pnl_btc_series = pd.to_numeric(df_filtered[PNL_BTC_COL], errors="coerce").fillna(0.0)

        fees_total = float(fees_series.sum())
        pnl_btc_total = float(pnl_btc_series.sum())           # Σ PNL_BTC (GEEN fees)
        acct_now = (START_UI + pnl_btc_total - fees_total) if START_UI is not None else None
        roi_pct = None if not START_UI else ((acct_now / START_UI - 1.0) * 100.0 if START_UI != 0 else None)

        # Laatste trade (voor badges)
        last_pnl_exit, last_pnl_btc, last_fee, last_result, last_win_add, last_loss_add = _last_trade_info(df_filtered)
        last_net = None if last_pnl_btc is None or last_fee is None else (last_pnl_btc - last_fee)
        last_roi_pp = None
        if START_UI and START_UI != 0 and last_net is not None:
            last_roi_pp = (last_net / START_UI) * 100.0

        # Wins/losses op basis van PNL_Exit (labels blijven gelijk)
        pnl_exit_vals = pd.to_numeric(df_filtered[COL["PNL_EXIT"]], errors="coerce").fillna(0.0)
        wins = int((pnl_exit_vals > 0).sum())
        losses = int((pnl_exit_vals < 0).sum())
        winrate_pct = (wins / max(wins + losses, 1) * 100.0) if (wins + losses) > 0 else None
    else:
        fees_total = 0.0
        pnl_btc_total = 0.0
        acct_now = START_UI
        roi_pct = None
        last_pnl_exit = None
        last_pnl_btc = None
        last_fee = None
        last_net = None
        last_roi_pp = None
        last_result = None
        last_win_add = None
        last_loss_add = None
        wins = 0
        losses = 0
        winrate_pct = None

    # Formatter helpers voor KPI deltas
    def _fmt_delta_num(x: Optional[float], suffix: str = "") -> Optional[str]:
        if x is None:
            return None
        sign = "+" if x > 0 else ""
        return f"{sign}{_fmt_num_3dec(x)}{(' ' + suffix) if suffix else ''}"

    def _fmt_roi_signed(pct: Optional[float]) -> str:
        if pct is None:
            return "—"
        sign = "+" if pct > 0 else ""
        return f"{sign}{pct:.2f}%"

    # KPI layout (8 tegels)
    r1 = st.columns(4)
    r2 = st.columns(4)

    # Rij 1
    r1[0].metric("Startkapitaal (BTC)", _fmt_num_3dec(START_UI))
    r1[1].metric(
        "Actueel kapitaal (BTC)",
        _fmt_num_3dec(acct_now),
        delta=_fmt_delta_num(last_net, "laatste trade"),
    )
    r1[2].metric(
        "Totale PnL (BTC)",
        _fmt_num_3dec(pnl_btc_total),   # Σ PNL_BTC (volgens ticket)
        delta=_fmt_delta_num(last_pnl_btc, "laatste trade"),
    )
    r1[3].metric(
        "Totale Fees (BTC)",
        _fmt_num_3dec(fees_total),
        delta=_fmt_delta_num(last_fee),
    )

    # Rij 2
    r2[0].metric("ROI %", _fmt_roi_signed(roi_pct), delta=(_fmt_roi_signed(last_roi_pp) if last_roi_pp is not None else None))
    r2[1].metric("Winnende trades", f"{wins}", delta=(f"+{last_win_add}" if last_win_add is not None else None))
    r2[2].metric("Verloren trades", f"{losses}", delta=(f"+{last_loss_add}" if last_loss_add is not None else None))
    last_result_text = "—" if last_result is None else f"Laatst: {last_result}"
    r2[3].metric("Winrate %", ("—" if winrate_pct is None else f"{winrate_pct:.2f}%"), delta=last_result_text)

    st.divider()

    if df_filtered.empty:
        st.info("Nog geen trades in selectie.")

    # Definitieve zichtbare kolommen (niets verwijderen of hernoemen)
    # Plaatsing: … TP1 | TP2 | TP3 | PNL_Exit | PNL_BTC | Fees | Plan | …
    vis_cols = [
        COL["DATUM"],
        "ID",
        COL["SIDE"],
        COL["SETUP"],
        COL["RISK_PCT"],
        COL["CAP_TRADE"],
        COL["CONTRACT_SIZE"],
        COL["RR_PLAN"],
        COL["RR_ACTUAL"],
        COL["ENTRY"],
        COL["SL"],
        COL["TP1"],
        COL["TP2"],
        COL["TP3"],
        COL["PNL_TP1"],
        COL["PNL_TP2"],
        COL["PNL_TP3"],
        COL["PNL_EXIT"],
        PNL_BTC_COL,
        COL["FEES"],
        COL["PLAN"],
        COL["NOTES"],
        COL["EMOTIES"],
        COL["SHOTS"],
    ]

    df_view = df_filtered.copy()
    df_view["ID"] = df_view[COL["TRADE_ID"]].astype(str)

    for col in vis_cols:
        if col not in df_view.columns:
            df_view[col] = "" if col != PNL_BTC_COL else 0.0

    # Inputs met komma/punt als TEXT laten (prijzen/kapitaal)
    for c in [COL["CAP_TRADE"], COL["ENTRY"], COL["SL"], COL["TP1"], COL["TP2"], COL["TP3"]]:
        if c in df_view.columns:
            df_view[c] = pd.Series(df_view[c], dtype="string").fillna("")

    # Kolomconfig
    colcfg = {
        COL["SIDE"]: st.column_config.SelectboxColumn(
            COL["SIDE"], options=["Long", "Short"], help="Richting van de trade"
        ),
        COL["RISK_PCT"]: st.column_config.NumberColumn(
            COL["RISK_PCT"], help="percentage van Kapitaal (trade)", min_value=0.1, max_value=5.0, step=0.1
        ),
        COL["CAP_TRADE"]: st.column_config.TextColumn(COL["CAP_TRADE"], help="BTC — accepteert '.' of ','"),
        COL["ENTRY"]: st.column_config.TextColumn(COL["ENTRY"], help="prijs — accepteert '.' of ','"),
        COL["SL"]: st.column_config.TextColumn(COL["SL"], help="prijs — accepteert '.' of ','"),
        COL["TP1"]: st.column_config.TextColumn(COL["TP1"], help="prijs — accepteert '.' of ','"),
        COL["TP2"]: st.column_config.TextColumn(COL["TP2"], help="prijs — accepteert '.' of ','"),
        COL["TP3"]: st.column_config.TextColumn(COL["TP3"], help="prijs — accepteert '.' of ','"),
        COL["CONTRACT_SIZE"]: st.column_config.TextColumn(
            COL["CONTRACT_SIZE"], help="contracts (Deribit $1/contract) — auto"
        ),
        COL["RR_PLAN"]: st.column_config.TextColumn(
            COL["RR_PLAN"], help="Max van TP’s; n.v.t. als SL=Entry of geen TP"
        ),
        COL["RR_ACTUAL"]: st.column_config.TextColumn(
            COL["RR_ACTUAL"], help="(ΣPNL_BTC / (Cap×Risk%)) — 2 dec"
        ),
        # PnL NumberColumns (bewerkbaar) + Exit (bewerkbaar) + BTC (read-only)
        COL["PNL_TP1"]: st.column_config.NumberColumn(COL["PNL_TP1"], help="pnl (BTC)"),
        COL["PNL_TP2"]: st.column_config.NumberColumn(COL["PNL_TP2"], help="pnl (BTC)"),
        COL["PNL_TP3"]: st.column_config.NumberColumn(COL["PNL_TP3"], help="pnl (BTC)"),
        COL["PNL_EXIT"]: st.column_config.NumberColumn(COL["PNL_EXIT"], help="pnl (BTC)"),
        PNL_BTC_COL: st.column_config.NumberColumn(PNL_BTC_COL, help="TP1+TP2+TP3+Exit (BTC)", disabled=True),
        COL["FEES"]: st.column_config.NumberColumn(COL["FEES"], help="fees (BTC)"),
        COL["PLAN"]: st.column_config.TextColumn(COL["PLAN"]),
        COL["NOTES"]: st.column_config.TextColumn(COL["NOTES"]),
    }

    edit_mode = st.toggle(
        "✎ Bewerken/Toevoegen inschakelen",
        value=False,
        help="Zet aan om rijen inline te wijzigen of toe te voegen (ghost row).",
    )

    if edit_mode:
        # Editable view
        edited = st.data_editor(
            df_view[vis_cols].reset_index(drop=True),
            use_container_width=True,
            hide_index=True,
            column_config=colcfg,
            disabled=False,
            num_rows="dynamic",  # ghost row
            key="journal_editor",
        )
    else:
        # Read-only view met kleur op PNL_TP1, PNL_TP2, PNL_TP3, PNL_Exit, PNL_BTC
        df_show = df_view[vis_cols].copy()
        for c in [COL["PNL_TP1"], COL["PNL_TP2"], COL["PNL_TP3"], COL["PNL_EXIT"], PNL_BTC_COL]:
            df_show[c] = pd.to_numeric(df_show[c], errors="coerce")

        def _cell_color(v):
            if pd.isna(v):
                return ""
            if v > 0:
                return "background-color: #0f5132; color: white;"  # groen
            if v < 0:
                return "background-color: #842029; color: white;"  # rood
            return ""  # 0 of leeg => neutraal

        styler = (
            df_show.style
            .applymap(_cell_color, subset=[COL["PNL_TP1"], COL["PNL_TP2"], COL["PNL_TP3"], COL["PNL_EXIT"], PNL_BTC_COL])
            .format({
                COL["PNL_TP1"]: lambda x: "" if pd.isna(x) else _fmt_num_3dec(float(x)),
                COL["PNL_TP2"]: lambda x: "" if pd.isna(x) else _fmt_num_3dec(float(x)),
                COL["PNL_TP3"]: lambda x: "" if pd.isna(x) else _fmt_num_3dec(float(x)),
                COL["PNL_EXIT"]: lambda x: "" if pd.isna(x) else _fmt_num_3dec(float(x)),
                PNL_BTC_COL:   lambda x: "" if pd.isna(x) else _fmt_num_3dec(float(x)),
            })
        )
        st.dataframe(styler, use_container_width=True, hide_index=True)
        edited = df_view[vis_cols].reset_index(drop=True)

    # Plan/Notities bewerken
    with st.expander(" Plan/Notities bewerken"):
        all_ids = df_filtered[COL["TRADE_ID"]].astype(str).tolist()
        sel_id = st.selectbox("Kies Trade_ID", ["(geen)"] + all_ids, index=0)
        if sel_id != "(geen)":
            base_row = (
                df_filtered[df_filtered[COL["TRADE_ID"]].astype(str) == sel_id]
                .iloc[0]
                .to_dict()
            )
            plan_txt = st.text_area("Plan", value=str(base_row.get(COL["PLAN"], "")), height=160)
            notes_txt = st.text_area("Notities", value=str(base_row.get(COL["NOTES"], "")), height=160)
            if st.button(" Bewaar Plan/Notities", type="primary"):
                try:
                    payload = base_row.copy()
                    payload[COL["PLAN"]] = plan_txt
                    payload[COL["NOTES"]] = notes_txt
                    update_entry(sel_id, payload)
                    st.success("Plan/Notities opgeslagen ✅")
                    st.rerun()
                except Exception as e:
                    st.error(f"Opslaan mislukt: {e}")

    # CRUD helpers
    def _map_row_to_payload(r: pd.Series, base_row: dict) -> dict:
        out = {k: base_row.get(k, "") for k in ORDER}
        out[COL["TRADE_ID"]] = str(r.get("ID", base_row.get(COL["TRADE_ID"], ""))).strip()
        # Datum
        out[COL["DATUM"]] = pd.to_datetime(
            r.get(COL["DATUM"]) or base_row.get(COL["DATUM"]) or pd.Timestamp.today()
        ).strftime(DATE_FMT)
        # Scalar velden
        out[COL["SIDE"]] = str(r.get(COL["SIDE"], base_row.get(COL["SIDE"], ""))).strip()
        out[COL["SETUP"]] = str(r.get(COL["SETUP"], base_row.get(COL["SETUP"], ""))).strip()
        out[COL["RISK_PCT"]] = r.get(COL["RISK_PCT"], base_row.get(COL["RISK_PCT"], DEFAULT_RISK_PCT))
        # String-velden (bewust rauw voor komma/punt)
        out[COL["CAP_TRADE"]] = r.get(COL["CAP_TRADE"], base_row.get(COL["CAP_TRADE"], ""))
        out[COL["ENTRY"]] = r.get(COL["ENTRY"], base_row.get(COL["ENTRY"], ""))
        out[COL["SL"]] = r.get(COL["SL"], base_row.get(COL["SL"], ""))
        out[COL["TP1"]] = r.get(COL["TP1"], base_row.get(COL["TP1"], ""))
        out[COL["TP2"]] = r.get(COL["TP2"], base_row.get(COL["TP2"], ""))
        out[COL["TP3"]] = r.get(COL["TP3"], base_row.get(COL["TP3"], ""))
        # PnL (bewerkbaar) + Exit (bewerkbaar) — sla rauw op
        out[COL["PNL_TP1"]] = r.get(COL["PNL_TP1"], base_row.get(COL["PNL_TP1"], ""))
        out[COL["PNL_TP2"]] = r.get(COL["PNL_TP2"], base_row.get(COL["PNL_TP2"], ""))
        out[COL["PNL_TP3"]] = r.get(COL["PNL_TP3"], base_row.get(COL["PNL_TP3"], ""))
        out[COL["PNL_EXIT"]] = r.get(COL["PNL_EXIT"], base_row.get(COL["PNL_EXIT"], ""))
        # Afgeleiden/overig
        out[COL["CONTRACT_SIZE"]] = r.get(COL["CONTRACT_SIZE"], base_row.get(COL["CONTRACT_SIZE"], ""))
        out[COL["RR_PLAN"]] = r.get(COL["RR_PLAN"], base_row.get(COL["RR_PLAN"], ""))
        # RR_ACTUAL wordt afgeleid — maar sla de huidige tekst veilig op (geen schemawijziging)
        out[COL["RR_ACTUAL"]] = r.get(COL["RR_ACTUAL"], base_row.get(COL["RR_ACTUAL"], ""))
        # Fees
        out[COL["FEES"]] = r.get(COL["FEES"], base_row.get(COL["FEES"], ""))
        # Free text
        out[COL["PLAN"]] = r.get(COL["PLAN"], base_row.get(COL["PLAN"], ""))
        out[COL["NOTES"]] = r.get(COL["NOTES"], base_row.get(COL["NOTES"], ""))
        out[COL["EMOTIES"]] = r.get(COL["EMOTIES"], base_row.get(COL["EMOTIES"], ""))
        out[COL["SHOTS"]] = r.get(COL["SHOTS"], base_row.get(COL["SHOTS"], ""))
        return out

    # Snapshot bestaande rijen (key = Trade_ID)
    base_map = {str(r[COL["TRADE_ID"]]): r.to_dict()
                for _, r in df_view.iterrows()
                if str(r[COL["TRADE_ID"]]).strip()}

    # Opslaan/Verwijderen
    if edit_mode:
        cA, cB, cC = st.columns(3)
        do_save = cA.button(" Opslaan wijzigingen", type="primary")
        del_id = cB.text_input("Verwijder Trade_ID (exact)")
        do_del = cC.button("️ Verwijderen")

        if do_del and del_id.strip():
            try:
                delete_entry(del_id.strip())
                st.success(f"Verwijderd: {del_id.strip()}")
                st.rerun()
            except Exception as e:
                st.error(f"Verwijderen mislukt: {e}")

        if do_save:
            ok_all = True
            appended = 0
            updated = 0
            skipped_empty = 0

            existing_ids = [str(x).strip() for x in base_map.keys() if str(x).strip()]
            df_ed = edited if isinstance(edited, pd.DataFrame) else pd.DataFrame(edited)

            for idx, row in df_ed.iterrows():
                if _row_is_effectively_empty(row):
                    skipped_empty += 1
                    continue

                raw_tid = str(row.get("ID", "") or "").strip()
                is_existing = raw_tid != "" and (raw_tid in base_map)

                if is_existing:
                    base_row = base_map.get(raw_tid, {k: "" for k in ORDER})
                    payload = _map_row_to_payload(row, base_row)
                    try:
                        update_entry(raw_tid, payload)
                        updated += 1
                    except Exception as e:
                        ok_all = False
                        st.error(f"Opslaan mislukt (update {raw_tid}): {e}")
                else:
                    # Append-only pad + oplopend ID
                    new_id = _next_sequential_id(existing_ids)
                    existing_ids.append(new_id)
                    row = row.copy()
                    row["ID"] = new_id
                    base_row = {k: "" for k in ORDER}
                    base_row[COL["TRADE_ID"]] = new_id
                    payload = _map_row_to_payload(row, base_row)
                    payload[COL["TRADE_ID"]] = new_id
                    try:
                        append_entry(payload)
                        appended += 1
                    except Exception as e:
                        ok_all = False
                        st.error(f"Opslaan mislukt (append {new_id}): {e}")

            if ok_all:
                msg_bits = []
                if appended:
                    msg_bits.append(f"{appended} toegevoegd")
                if updated:
                    msg_bits.append(f"{updated} gewijzigd")
                if skipped_empty:
                    msg_bits.append(f"{skipped_empty} leeg overgeslagen")
                st.success("Wijzigingen opgeslagen ✅ " + (" · ".join(msg_bits) if msg_bits else ""))

                if APP.get("gh_sync_enabled", False):
                    ok, msg = github_sync.sync_now()
                    st.info(msg)

                st.rerun()

    # Export
    if st.button("Exporteer zichtbare rijen (.csv)"):
        out = export_visible(df_filtered)
        st.success(f"Export voltooid: `{out}`")

