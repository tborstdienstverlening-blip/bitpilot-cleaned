# ui/journal_table.py
from __future__ import annotations

from typing import List
import math
import re
from decimal import Decimal, InvalidOperation
import pandas as pd
import streamlit as st

from schema import COL, ORDER, DATE_FMT
from utils.colors import cell_style_color
from services.pnl_service import to_num
from app_state import load_state, save_state
from journal_store import append_entry, update_entry, delete_entry
from utils.ids import key as keygen

# Alle PNL-kolommen + Fees met 8 decimalen
_PNL_INPUT_COLS = [COL["PNL_TP1"], COL["PNL_TP2"], COL["PNL_TP3"], COL["PNL_EXIT"]]
_PNL_SHOW_COLS  = [*_PNL_INPUT_COLS, "PNL_BTC", COL["FEES"]]

def _as_float(s):
    """EU/EN string -> float (accepteert ',' of '.')"""
    if isinstance(s, (int, float)):
        if isinstance(s, float) and (math.isnan(s) or math.isinf(s)):
            return None
        return float(s)
    try:
        t = str(s).strip()
        if t == "":
            return None
        # verwijder spaties en vreemde separators
        t = t.replace(" ", "").replace("\u00A0", "")
        t = re.sub(r"[’'_]", "", t)
        # als zowel . als , voorkomen en , is de laatste -> . = thousands, , = decimals
        if "," in t and "." in t and t.rfind(",") > t.rfind("."):
            t = t.replace(".", "")
            t = t.replace(",", ".")
        else:
            t = t.replace(",", ".")
        return float(Decimal(t))
    except (InvalidOperation, ValueError):
        return None

def _format_fixed8(x) -> str:
    if pd.isna(x) or x is None:
        return ""
    try:
        return f"{float(x):.8f}"
    except Exception:
        return ""

def row_is_empty(row: pd.Series) -> bool:
    keys = [COL["SIDE"], COL["RISK_PCT"], COL["CAP_TRADE"], COL["ENTRY"], COL["SL"], COL["TP1"], COL["TP2"], COL["TP3"]]
    for k in keys:
        v = row.get(k, "")
        if isinstance(v, str):
            if v.strip() != "":
                return False
        elif pd.notna(v):
            return False
    return True

def next_sequential_id(existing_ids: List[str]) -> str:
    ints = []
    for x in existing_ids:
        s = str(x).strip()
        if s.isdigit():
            ints.append(int(s))
    nxt = (max(ints) + 1) if ints else 1
    return str(nxt)

def map_row_to_payload(r: pd.Series, base_row: dict) -> dict:
    out = {k: base_row.get(k, "") for k in ORDER}
    out[COL["TRADE_ID"]] = str(r.get("ID", base_row.get(COL["TRADE_ID"], ""))).strip()

    # Datum
    out[COL["DATUM"]] = pd.to_datetime(
        r.get(COL["DATUM"]) or base_row.get(COL["DATUM"]) or pd.Timestamp.today()
    ).strftime(DATE_FMT)

    # Scalars
    out[COL["SIDE"]]     = str(r.get(COL["SIDE"],  base_row.get(COL["SIDE"],  ""))).strip()
    out[COL["SETUP"]]    = str(r.get(COL["SETUP"], base_row.get(COL["SETUP"], ""))).strip()
    out[COL["RISK_PCT"]] = r.get(COL["RISK_PCT"], base_row.get(COL["RISK_PCT"], ""))

    # Vrije strings (prijzen/kapitaal)
    out[COL["CAP_TRADE"]] = r.get(COL["CAP_TRADE"], base_row.get(COL["CAP_TRADE"], ""))
    out[COL["ENTRY"]]     = r.get(COL["ENTRY"],     base_row.get(COL["ENTRY"],     ""))
    out[COL["SL"]]        = r.get(COL["SL"],        base_row.get(COL["SL"],        ""))
    out[COL["TP1"]]       = r.get(COL["TP1"],       base_row.get(COL["TP1"],       ""))
    out[COL["TP2"]]       = r.get(COL["TP2"],       base_row.get(COL["TP2"],       ""))
    out[COL["TP3"]]       = r.get(COL["TP3"],       base_row.get(COL["TP3"],       ""))

    # PNL invoervelden: EU -> float; leeg -> 0.0
    for k in _PNL_INPUT_COLS:
        val = to_num(r.get(k))
        out[k] = 0.0 if val is None else float(val)

    # Overig (Fees laten we ongewijzigd opslaan zoals in je bestaande flow)
    out[COL["CONTRACT_SIZE"]] = r.get(COL["CONTRACT_SIZE"], base_row.get(COL["CONTRACT_SIZE"], ""))
    out[COL["RR_PLAN"]] = r.get(COL["RR_PLAN"], base_row.get(COL["RR_PLAN"], ""))
    out[COL["RR_ACTUAL"]] = r.get(COL["RR_ACTUAL"], base_row.get(COL["RR_ACTUAL"], ""))
    out[COL["FEES"]] = r.get(COL["FEES"], base_row.get(COL["FEES"], ""))
    out[COL["PLAN"]]   = r.get(COL["PLAN"],   base_row.get(COL["PLAN"],   ""))
    out[COL["NOTES"]]  = r.get(COL["NOTES"],  base_row.get(COL["NOTES"],  ""))
    out[COL["EMOTIES"]] = r.get(COL["EMOTIES"], base_row.get(COL["EMOTIES"], ""))
    out[COL["SHOTS"]]  = r.get(COL["SHOTS"],  base_row.get(COL["SHOTS"],  ""))

    return out

def render_table(df_view: pd.DataFrame) -> None:
    """
    Journal-tabel met read-only en edit-mode + CRUD/ghost-row.

    Fixes:
      - Fees: TextColumn -> je kunt nu '0,00050000' invoeren (ook '.')
      - PNL_BTC weergave = TP1+TP2+TP3+Exit − Fees (UI-only), onafgerond
      - 8 decimalen voor PNL-kolommen en Fees in beide modi
      - Toggle 'Bewerken' verandert geen waarden t.o.v. read-only
    """
    df_view = df_view.copy()

    # Definitieve zichtbare kolommen
    vis_cols = [
        COL["DATUM"], "ID", COL["SIDE"], COL["SETUP"], COL["RISK_PCT"], COL["CAP_TRADE"], COL["CONTRACT_SIZE"],
        COL["RR_PLAN"], COL["RR_ACTUAL"], COL["ENTRY"], COL["SL"], COL["TP1"], COL["TP2"], COL["TP3"],
        COL["PNL_TP1"], COL["PNL_TP2"], COL["PNL_TP3"], COL["PNL_EXIT"], "PNL_BTC", COL["FEES"],
        COL["PLAN"], COL["NOTES"], COL["EMOTIES"], COL["SHOTS"],
    ]
    for col in vis_cols:
        if col not in df_view.columns:
            df_view[col] = "" if col not in ("PNL_BTC", *_PNL_INPUT_COLS) else 0.0

    # Vrije tekstinvoer voor prijsvelden (EU/punt)
    for c in [COL["CAP_TRADE"], COL["ENTRY"], COL["SL"], COL["TP1"], COL["TP2"], COL["TP3"]]:
        if c in df_view.columns:
            df_view[c] = pd.Series(df_view[c], dtype="string").fillna("")

    # PNL input-kolommen als string (TextColumn), voorgeladen op 8 dec
    for c in _PNL_INPUT_COLS:
        if c in df_view.columns:
            df_view[c] = pd.Series(df_view[c]).map(lambda v: _format_fixed8(_as_float(v))).astype("string")

    # Fees óók als string (TextColumn) voor komma-invoer
    if COL["FEES"] in df_view.columns:
        df_view[COL["FEES"]] = pd.Series(df_view[COL["FEES"]]).map(lambda v: _format_fixed8(_as_float(v))).astype("string")

    # Kolomconfig
    colcfg = {
        COL["SIDE"]:     st.column_config.SelectboxColumn(COL["SIDE"], options=["Long", "Short"], help="Richting van de trade"),
        COL["RISK_PCT"]: st.column_config.NumberColumn(COL["RISK_PCT"], help="percentage van Kapitaal (trade)", min_value=0.1, max_value=5.0, step=0.1),
        COL["CAP_TRADE"]: st.column_config.TextColumn(COL["CAP_TRADE"], help="BTC — accepteert '.' of ','"),
        COL["ENTRY"]:     st.column_config.TextColumn(COL["ENTRY"], help="prijs — accepteert '.' of ','"),
        COL["SL"]:        st.column_config.TextColumn(COL["SL"], help="prijs — accepteert '.' of ','"),
        COL["TP1"]:       st.column_config.TextColumn(COL["TP1"], help="prijs — accepteert '.' of ','"),
        COL["TP2"]:       st.column_config.TextColumn(COL["TP2"], help="prijs — accepteert '.' of ','"),
        COL["TP3"]:       st.column_config.TextColumn(COL["TP3"], help="prijs — accepteert '.' of ','"),
        COL["CONTRACT_SIZE"]: st.column_config.TextColumn(COL["CONTRACT_SIZE"], help="contracts (Deribit $1/contract) — auto"),
        COL["RR_PLAN"]:   st.column_config.TextColumn(COL["RR_PLAN"], help="Max van TP’s; n.v.t."),
        COL["RR_ACTUAL"]: st.column_config.TextColumn(COL["RR_ACTUAL"], help="(ΣPNL_BTC / (Cap×Risk%)) — 2 dec"),
        COL["PNL_TP1"]:   st.column_config.TextColumn(COL["PNL_TP1"], help="pnl (BTC) — accepteert '.' of ','"),
        COL["PNL_TP2"]:   st.column_config.TextColumn(COL["PNL_TP2"], help="pnl (BTC) — accepteert '.' of ','"),
        COL["PNL_TP3"]:   st.column_config.TextColumn(COL["PNL_TP3"], help="pnl (BTC) — accepteert '.' of ','"),
        COL["PNL_EXIT"]:  st.column_config.TextColumn(COL["PNL_EXIT"], help="pnl (BTC) — accepteert '.' of ','"),
        "PNL_BTC":        st.column_config.NumberColumn("PNL_BTC", help="TP1+TP2+TP3+Exit (BTC)", disabled=True, format="%.8f"),
        # Belangrijk: Fees als TextColumn (nu kun je , of . type’n)
        COL["FEES"]:      st.column_config.TextColumn(COL["FEES"], help="fees (BTC) — accepteert '.' of ','"),
        COL["PLAN"]:      st.column_config.TextColumn(COL["PLAN"]),
        COL["NOTES"]:     st.column_config.TextColumn(COL["NOTES"]),
    }

    edit_mode = st.toggle(
        "✎ Bewerken/Toevoegen inschakelen",
        value=False,
        help="Zet aan om rijen inline te wijzigen of toe te voegen (ghost row).",
        key=keygen("toggle_edit"),
    )

    if edit_mode:
        # Editor-view
        df_edit = df_view[vis_cols].reset_index(drop=True).copy()

        # Parse alle PNL inputs + Fees via EU/EN parser voor berekening
        fees = df_edit[COL["FEES"]].map(_as_float).fillna(0.0)
        tp1  = df_edit[COL["PNL_TP1"]].map(_as_float).fillna(0.0)
        tp2  = df_edit[COL["PNL_TP2"]].map(_as_float).fillna(0.0)
        tp3  = df_edit[COL["PNL_TP3"]].map(_as_float).fillna(0.0)
        pex  = df_edit[COL["PNL_EXIT"]].map(_as_float).fillna(0.0)
        df_edit["PNL_BTC"] = (tp1 + tp2 + tp3 + pex - fees).astype(float)

        edited = st.data_editor(
            df_edit,
            use_container_width=True,
            hide_index=True,
            column_config=colcfg,
            disabled=False,
            num_rows="dynamic",
            key=keygen("journal_editor"),
        )
    else:
        # Read-only view met dezelfde waarden (8 dec)
        df_show = df_view[vis_cols].copy()

        # Parse naar numeriek voor berekening + formatting
        for c in _PNL_SHOW_COLS:
            if c in df_show.columns:
                df_show[c] = df_show[c].map(_as_float)

        fees = df_show[COL["FEES"]].fillna(0.0)
        tp1  = df_show[COL["PNL_TP1"]].fillna(0.0)
        tp2  = df_show[COL["PNL_TP2"]].fillna(0.0)
        tp3  = df_show[COL["PNL_TP3"]].fillna(0.0)
        pex  = df_show[COL["PNL_EXIT"]].fillna(0.0)
        df_show["PNL_BTC"] = (tp1 + tp2 + tp3 + pex - fees).astype(float)

        # Kleur & vaste formatting (8 dec, geen e-notatie), incl. Fees
        styler = (
            df_show.style
            .map(cell_style_color, subset=[COL["PNL_TP1"], COL["PNL_TP2"], COL["PNL_TP3"], COL["PNL_EXIT"], "PNL_BTC"])
            .format({
                COL["PNL_TP1"]: _format_fixed8,
                COL["PNL_TP2"]: _format_fixed8,
                COL["PNL_TP3"]: _format_fixed8,
                COL["PNL_EXIT"]: _format_fixed8,
                "PNL_BTC":      _format_fixed8,
                COL["FEES"]:    _format_fixed8,
            })
        )
        st.dataframe(styler, use_container_width=True, hide_index=True)

        edited = df_view[vis_cols].reset_index(drop=True)  # voor CRUD-blok

    # CRUD controls (ongewijzigd)
    app = load_state()
    base_map = {str(r[COL["TRADE_ID"]]): r.to_dict() for _, r in df_view.iterrows() if str(r[COL["TRADE_ID"]]).strip()}

    if edit_mode:
        cA, cB, cC = st.columns(3)
        do_save = cA.button(" Opslaan wijzigingen", type="primary", key=keygen("btn_save"))
        del_id  = cB.text_input("Verwijder Trade_ID (exact)", key=keygen("inp_del_id"))
        do_del  = cC.button("️ Verwijderen", key=keygen("btn_del"))

        if do_del and del_id.strip():
            try:
                delete_entry(del_id.strip())
                st.success(f"Verwijderd: {del_id.strip()}")
                st.rerun()
            except Exception as e:
                st.error(f"Verwijderen mislukt: {e}")

        if do_save:
            ok_all = True
            appended = updated = skipped_empty = 0
            existing_ids = [str(x).strip() for x in base_map.keys() if str(x).strip()]
            df_ed = edited if isinstance(edited, pd.DataFrame) else pd.DataFrame(edited)

            for _, row in df_ed.iterrows():
                if row_is_empty(row):
                    skipped_empty += 1
                    continue

                raw_tid = str(row.get("ID", "") or "").strip()
                is_existing = raw_tid != "" and (raw_tid in base_map)

                if is_existing:
                    base_row = base_map.get(raw_tid, {k: "" for k in ORDER})
                    payload = map_row_to_payload(row, base_row)
                    try:
                        update_entry(raw_tid, payload)
                        updated += 1
                    except Exception as e:
                        ok_all = False
                        st.error(f"Opslaan mislukt (update {raw_tid}): {e}")
                else:
                    new_id = next_sequential_id(existing_ids)
                    existing_ids.append(new_id)
                    row = row.copy(); row["ID"] = new_id
                    base_row = {k: "" for k in ORDER}; base_row[COL["TRADE_ID"]] = new_id
                    payload = map_row_to_payload(row, base_row); payload[COL["TRADE_ID"]] = new_id
                    try:
                        append_entry(payload)
                        appended += 1
                    except Exception as e:
                        ok_all = False
                        st.error(f"Opslaan mislukt (append {new_id}): {e}")

            if ok_all:
                bits = []
                if appended: bits.append(f"{appended} toegevoegd")
                if updated:  bits.append(f"{updated} gewijzigd")
                if skipped_empty: bits.append(f"{skipped_empty} leeg overgeslagen")
                st.success("Wijzigingen opgeslagen ✅ " + (" · ".join(bits) if bits else ""))

                if app.get("gh_sync_enabled", False):
                    import github_sync
                    ok, msg = github_sync.sync_now()
                    st.info(msg)

                st.rerun()

