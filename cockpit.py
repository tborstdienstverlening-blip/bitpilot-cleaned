from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import streamlit as st

# Project imports (bestaande modules in je repo)
from schema import COL, ORDER, DATE_FMT
from utils_config import load_config, format_btc
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
from kpi_utils import apply_filters  # compute_kpis niet strikt nodig hier
from risk_utils import contracts_from_row


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


def _next_sequential_id(existing_ids: list[str]) -> str:
    """Bepaal volgende oplopende integer-ID als string ('1','2','3',...)."""
    ints = []
    for x in existing_ids:
        s = str(x).strip()
        if s.isdigit():
            ints.append(int(s))
    nxt = (max(ints) + 1) if ints else 1
    return str(nxt)


def _pnl_exit_from_tps(row: pd.Series) -> Optional[float]:
    """Stel PNL_Exit automatisch gelijk aan laatste geldige TP-waarde met prioriteit TP3 > TP2 > TP1."""
    for key in (COL["PNL_TP3"], COL["PNL_TP2"], COL["PNL_TP1"]):
        v = _to_num(row.get(key))
        if v is not None:
            return v
    return _to_num(row.get(COL["PNL_EXIT"]))  # behoud bestaande als TP's leeg zijn


def _exit_color_symbol(pnl_exit: Optional[float]) -> str:
    if pnl_exit is None:
        return "—"
    if pnl_exit > 0:
        return "🟩"
    if pnl_exit < 0:
        return "🟥"
    return "—"


def _last_trade_view(df: pd.DataFrame) -> Tuple[Optional[float], Optional[str]]:
    """
    Haal info van de laatste rij in de (gefilterde) journal:
    - return (pnl_exit_last, result_text) waarbij result_text 'Win'/'Loss'/'Break-even' is.
    - Als niet beschikbaar -> (None, None)
    """
    if df is None or df.empty:
        return None, None
    row = df.iloc[-1]
    pnl = _to_num(row.get(COL["PNL_EXIT"]))
    if pnl is None:
        return None, None
    if pnl > 0:
        return pnl, "Win"
    if pnl < 0:
        return pnl, "Loss"
    return 0.0, "Break-even"


def _sum_pnl_net(df: pd.DataFrame) -> float:
    """Σ (PNL_Exit of TP-som) − Fees over df."""
    if df is None or df.empty:
        return 0.0
    pnl_vals = []
    for _, r in df.iterrows():
        pnl_exit = _to_num(r.get(COL["PNL_EXIT"]))
        if pnl_exit is None:
            tpsum = sum([x for x in (_to_num(r.get(COL["PNL_TP1"])),
                                     _to_num(r.get(COL["PNL_TP2"])),
                                     _to_num(r.get(COL["PNL_TP3"]))) if x is not None])
        else:
            tpsum = pnl_exit
        fees = _to_num(r.get(COL["FEES"])) or 0.0
        pnl_vals.append((tpsum or 0.0) - fees)
    return float(sum(pnl_vals))


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

    # ──────────────────────────────────────────────────────────────────────
    # Backend autos: Contract size + RR's + PNL_Exit kleur (alleen rij-velden)
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
        tp1, tp2, tp3 = (
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
            for tp in [tp1, tp2, tp3]:
                if tp is None:
                    continue
                if side == "short":
                    cands.append((entry - tp) / den)
                else:
                    cands.append((tp - entry) / den)
            rr_plan = max(cands) if cands else None
        row[COL["RR_PLAN"]] = "n.v.t." if rr_plan is None else f"{rr_plan:.2f}"

        # PNL Exit automatisch koppelen aan TP's (TP3 > TP2 > TP1)
        pnl_exit_auto = _pnl_exit_from_tps(row)
        row[COL["PNL_EXIT"]] = "" if pnl_exit_auto is None else pnl_exit_auto

        # Kleurindicatie
        row["Exit kleur"] = _exit_color_symbol(_to_num(row.get(COL["PNL_EXIT"])))

        # RR (Actueel) — NETTO met rij-risk (Kapitaal×Risk%) obv TP's (al dan niet via Exit)
        risk_btc, _ = contracts_from_row(cap, risk_pct_val, entry, sl)
        pnl_for_rr = _to_num(row.get(COL["PNL_EXIT"]))
        if pnl_for_rr is None:
            pnl_for_rr = sum([x for x in (tp1, tp2, tp3) if x is not None]) or None
        fees = _to_num(row.get(COL["FEES"])) or 0.0
        rr_actual = None
        if risk_btc not in (None, 0) and pnl_for_rr is not None:
            rr_actual = (pnl_for_rr - fees) / risk_btc
        row[COL["RR_ACTUAL"]] = "n.v.t." if rr_actual is None else f"{rr_actual:.2f}"

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
    # KPI-balk — cumulatief + laatste trade
    # ──────────────────────────────────────────────────────────────────────
    pnl_cum = _sum_pnl_net(df_filtered)
    acct_now = (START_UI + pnl_cum) if START_UI is not None else None
    roi_pct = None
    if START_UI and START_UI != 0:
        roi_pct = (acct_now / START_UI - 1.0) * 100.0 if acct_now is not None else None

    last_pnl, last_result = _last_trade_view(df_filtered)
    last_roi_pp = None
    if START_UI and START_UI != 0 and last_pnl is not None:
        last_roi_pp = (last_pnl / START_UI) * 100.0

    # Winrate cumulatief
    wins = int(((df_filtered[COL["PNL_EXIT"]].astype(float) > 0).fillna(False)).sum())
    losses = int(((df_filtered[COL["PNL_EXIT"]].astype(float) < 0).fillna(False)).sum())
    total_trades = wins + losses + int(((df_filtered[COL["PNL_EXIT"]].astype(float) == 0).fillna(False)).sum())
    winrate_pct = (wins / total_trades * 100.0) if total_trades > 0 else None

    def _fmt_delta(v, fmt_fn):
        return None if v is None else fmt_fn(v)

    r1 = st.columns(4)
    # Accountwaarde
    acct_text = "—" if acct_now is None else format_btc(acct_now)
    acct_delta = None if last_pnl is None else f"+{format_btc(last_pnl)}" if last_pnl > 0 else format_btc(last_pnl)
    r1[0].metric("Accountwaarde (BTC)", acct_text, delta=acct_delta)

    # ROI
    roi_text = "—" if roi_pct is None else f"{roi_pct:.2f}%"
    roi_delta = None if last_roi_pp is None else (f"+{last_roi_pp:.2f}%"
                                                  if last_roi_pp > 0 else f"{last_roi_pp:.2f}%")
    r1[1].metric("ROI %", roi_text, delta=roi_delta)

    # PnL cumulatief
    pnl_text = format_btc(pnl_cum)
    pnl_delta = None if last_pnl is None else (f"+{format_btc(last_pnl)}" if last_pnl > 0 else format_btc(last_pnl))
    r1[2].metric("Totale PnL (BTC)", pnl_text, delta=pnl_delta)

    # Winrate
    winrate_text = "—" if winrate_pct is None else f"{winrate_pct:.2f}%"
    last_result_text = None if last_result is None else f"Laatst: {last_result}"
    r1[3].metric("Winrate %", winrate_text, delta=last_result_text)

    st.divider()

    if df_filtered.empty:
        st.info("Nog geen trades in selectie.")

    # Definitieve zichtbare kolommen (zonder Risk (BTC))
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
        COL["PNL_EXIT"],
        "Exit kleur",
        COL["FEES"],
        COL["PNL_TP1"],
        COL["PNL_TP2"],
        COL["PNL_TP3"],
        COL["PLAN"],
        COL["NOTES"],
        COL["EMOTIES"],
        COL["SHOTS"],
    ]

    df_view = df_filtered.copy()
    # Toon ID-kolom altijd vanuit Trade_ID
    df_view["ID"] = df_view[COL["TRADE_ID"]].astype(str)

    for col in vis_cols:
        if col not in df_view.columns:
            df_view[col] = ""

    # Inputs die komma/punt moeten accepteren als TEXT houden
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
            COL["RR_ACTUAL"], help="(ΣTP-PNL − Fees) / (Kapitaal×Risk%) — Exit telt niet mee"
        ),
        COL["PNL_EXIT"]: st.column_config.NumberColumn(COL["PNL_EXIT"], help="auto vanuit TP’s; overschrijfbaar"),
        "Exit kleur": st.column_config.TextColumn("Exit kleur", help="🟩 positief · 🟥 negatief · — geen"),
        COL["PLAN"]: st.column_config.TextColumn(COL["PLAN"]),
        COL["NOTES"]: st.column_config.TextColumn(COL["NOTES"]),
        COL["FEES"]: st.column_config.NumberColumn(COL["FEES"], help="fees (BTC)"),
        COL["PNL_TP1"]: st.column_config.NumberColumn(COL["PNL_TP1"], help="pnl (BTC)"),
        COL["PNL_TP2"]: st.column_config.NumberColumn(COL["PNL_TP2"], help="pnl (BTC)"),
        COL["PNL_TP3"]: st.column_config.NumberColumn(COL["PNL_TP3"], help="pnl (BTC)"),
    }

    edit_mode = st.toggle(
        "✎ Bewerken/Toevoegen inschakelen",
        value=False,
        help="Zet aan om rijen inline te wijzigen of toe te voegen (ghost row).",
    )

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

    # Uitklap voor Plan/Notities
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
        # PNL Exit: afgeleid van TP's, maar eindwaarde mag zichtbaar blijven
        pnl_exit_auto = _pnl_exit_from_tps(r)
        out[COL["PNL_EXIT"]] = "" if pnl_exit_auto is None else pnl_exit_auto
        # Afgeleiden/overig
        out[COL["CONTRACT_SIZE"]] = r.get(COL["CONTRACT_SIZE"], base_row.get(COL["CONTRACT_SIZE"], ""))
        out[COL["RR_PLAN"]] = r.get(COL["RR_PLAN"], base_row.get(COL["RR_PLAN"], ""))
        out[COL["RR_ACTUAL"]] = r.get(COL["RR_ACTUAL"], base_row.get(COL["RR_ACTUAL"], ""))
        # PnL/fees
        out[COL["FEES"]] = r.get(COL["FEES"], base_row.get(COL["FEES"], ""))
        out[COL["PNL_TP1"]] = r.get(COL["PNL_TP1"], base_row.get(COL["PNL_TP1"], ""))
        out[COL["PNL_TP2"]] = r.get(COL["PNL_TP2"], base_row.get(COL["PNL_TP2"], ""))
        out[COL["PNL_TP3"]] = r.get(COL["PNL_TP3"], base_row.get(COL["PNL_TP3"], ""))
        # Free text
        out[COL["PLAN"]] = r.get(COL["PLAN"], base_row.get(COL["PLAN"], ""))
        out[COL["NOTES"]] = r.get(COL["NOTES"], base_row.get(COL["NOTES"], ""))
        out[COL["EMOTIES"]] = r.get(COL["EMOTIES"], base_row.get(COL["EMOTIES"], ""))
        out[COL["SHOTS"]] = r.get(COL["SHOTS"], base_row.get(COL["SHOTS"], ""))
        return out

    # Snapshot van bestaande rijen (key = Trade_ID)
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

            # verzamel bestaande numerieke ID's voor sequentieel bepalen
            existing_ids = [str(x).strip() for x in base_map.keys() if str(x).strip()]

            for idx, row in edited.iterrows():
                # Sla lege ghost-row over
                if _row_is_effectively_empty(row):
                    skipped_empty += 1
                    continue

                raw_tid = str(row.get("ID", "") or "").strip()
                is_existing = raw_tid != "" and (raw_tid in base_map)

                if is_existing:
                    # UPDATE bestaande rij
                    base_row = base_map.get(raw_tid, {k: "" for k in ORDER})
                    payload = _map_row_to_payload(row, base_row)
                    try:
                        update_entry(raw_tid, payload)
                        updated += 1
                    except Exception as e:
                        ok_all = False
                        st.error(f"Opslaan mislukt (update {raw_tid}): {e}")
                else:
                    # ✅ APPEND-ONLY — nieuwe sequentiële ID
                    new_id = _next_sequential_id(existing_ids)
                    existing_ids.append(new_id)  # reserveer
                    row = row.copy()
                    row["ID"] = new_id
                    base_row = {k: "" for k in ORDER}
                    base_row[COL["TRADE_ID"]] = new_id
                    payload = _map_row_to_payload(row, base_row)
                    payload[COL["TRADE_ID"]] = new_id  # hard-assign
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
