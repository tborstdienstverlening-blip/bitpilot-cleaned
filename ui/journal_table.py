# ui/journal_table.py
from __future__ import annotations
from typing import Dict, Any, List
import pandas as pd
import streamlit as st

from schema import COL, ORDER, DATE_FMT
from utils.colors import cell_style_color
from services.pnl_service import to_num
from app_state import load_state, save_state
from journal_store import append_entry, update_entry, delete_entry
from utils.ids import key as keygen


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
    # Scalar velden
    out[COL["SIDE"]] = str(r.get(COL["SIDE"], base_row.get(COL["SIDE"], ""))).strip()
    out[COL["SETUP"]] = str(r.get(COL["SETUP"], base_row.get(COL["SETUP"], ""))).strip()
    out[COL["RISK_PCT"]] = r.get(COL["RISK_PCT"], base_row.get(COL["RISK_PCT"], ""))
    # Ruwe strings (EU inset): prijzen en velden
    out[COL["CAP_TRADE"]] = r.get(COL["CAP_TRADE"], base_row.get(COL["CAP_TRADE"], ""))
    out[COL["ENTRY"]] = r.get(COL["ENTRY"], base_row.get(COL["ENTRY"], ""))
    out[COL["SL"]] = r.get(COL["SL"], base_row.get(COL["SL"], ""))
    out[COL["TP1"]] = r.get(COL["TP1"], base_row.get(COL["TP1"], ""))
    out[COL["TP2"]] = r.get(COL["TP2"], base_row.get(COL["TP2"], ""))
    out[COL["TP3"]] = r.get(COL["TP3"], base_row.get(COL["TP3"], ""))

    # PNL invoervelden: normaliseer (EU->dot), leeg -> 0.0
    for k in (COL["PNL_TP1"], COL["PNL_TP2"], COL["PNL_TP3"], COL["PNL_EXIT"]):
        val = to_num(r.get(k))
        out[k] = 0.0 if val is None else float(val)

    # Overig
    out[COL["CONTRACT_SIZE"]] = r.get(COL["CONTRACT_SIZE"], base_row.get(COL["CONTRACT_SIZE"], ""))
    out[COL["RR_PLAN"]] = r.get(COL["RR_PLAN"], base_row.get(COL["RR_PLAN"], ""))
    out[COL["RR_ACTUAL"]] = r.get(COL["RR_ACTUAL"], base_row.get(COL["RR_ACTUAL"], ""))  # afgeleid, maar veilig opslaan
    out[COL["FEES"]] = r.get(COL["FEES"], base_row.get(COL["FEES"], ""))
    out[COL["PLAN"]] = r.get(COL["PLAN"], base_row.get(COL["PLAN"], ""))
    out[COL["NOTES"]] = r.get(COL["NOTES"], base_row.get(COL["NOTES"], ""))
    out[COL["EMOTIES"]] = r.get(COL["EMOTIES"], base_row.get(COL["EMOTIES"], ""))
    out[COL["SHOTS"]] = r.get(COL["SHOTS"], base_row.get(COL["SHOTS"], ""))
    return out


def render_table(df_view: pd.DataFrame) -> None:
    """
    Rendert de Journal-tabel (read-only en edit-mode) incl. CRUD/ghost-row.
    Kolomvolgorde/labels/kleur exact gelijk aan 07d.
    """
    # Definitieve zichtbare kolommen
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
        "PNL_BTC",
        COL["FEES"],
        COL["PLAN"],
        COL["NOTES"],
        COL["EMOTIES"],
        COL["SHOTS"],
    ]
    for col in vis_cols:
        if col not in df_view.columns:
            df_view[col] = "" if col not in ("PNL_BTC", COL["PNL_TP1"], COL["PNL_TP2"], COL["PNL_TP3"], COL["PNL_EXIT"]) else 0.0

    # Vrije tekstinvoer voor prijsvelden (EU/punt)
    for c in [COL["CAP_TRADE"], COL["ENTRY"], COL["SL"], COL["TP1"], COL["TP2"], COL["TP3"]]:
        if c in df_view.columns:
            df_view[c] = pd.Series(df_view[c], dtype="string").fillna("")

    # 🔧 Belangrijk: bied PNL_TP1/2/3 en PNL_Exit als strings aan voor TextColumn
    for c in [COL["PNL_TP1"], COL["PNL_TP2"], COL["PNL_TP3"], COL["PNL_EXIT"]]:
        if c in df_view.columns:
            df_view[c] = pd.Series(df_view[c]).astype("string").fillna("")

    # Kolomconfig exact als 07d
    colcfg = {
        COL["SIDE"]: st.column_config.SelectboxColumn(COL["SIDE"], options=["Long", "Short"], help="Richting van de trade"),
        COL["RISK_PCT"]: st.column_config.NumberColumn(COL["RISK_PCT"], help="percentage van Kapitaal (trade)", min_value=0.1, max_value=5.0, step=0.1),
        COL["CAP_TRADE"]: st.column_config.TextColumn(COL["CAP_TRADE"], help="BTC — accepteert '.' of ','"),
        COL["ENTRY"]: st.column_config.TextColumn(COL["ENTRY"], help="prijs — accepteert '.' of ','"),
        COL["SL"]: st.column_config.TextColumn(COL["SL"], help="prijs — accepteert '.' of ','"),
        COL["TP1"]: st.column_config.TextColumn(COL["TP1"], help="prijs — accepteert '.' of ','"),
        COL["TP2"]: st.column_config.TextColumn(COL["TP2"], help="prijs — accepteert '.' of ','"),
        COL["TP3"]: st.column_config.TextColumn(COL["TP3"], help="prijs — accepteert '.' of ','"),
        COL["CONTRACT_SIZE"]: st.column_config.TextColumn(COL["CONTRACT_SIZE"], help="contracts (Deribit $1/contract) — auto"),
        COL["RR_PLAN"]: st.column_config.TextColumn(COL["RR_PLAN"], help="Max van TP’s; n.v.t. als SL=Entry of geen TP"),
        COL["RR_ACTUAL"]: st.column_config.TextColumn(COL["RR_ACTUAL"], help="(ΣPNL_BTC / (Cap×Risk%)) — 2 dec"),
        COL["PNL_TP1"]: st.column_config.TextColumn(COL["PNL_TP1"], help="pnl (BTC) — accepteert '.' of ','"),
        COL["PNL_TP2"]: st.column_config.TextColumn(COL["PNL_TP2"], help="pnl (BTC) — accepteert '.' of ','"),
        COL["PNL_TP3"]: st.column_config.TextColumn(COL["PNL_TP3"], help="pnl (BTC) — accepteert '.' of ','"),
        COL["PNL_EXIT"]: st.column_config.TextColumn(COL["PNL_EXIT"], help="pnl (BTC) — accepteert '.' of ','"),
        "PNL_BTC": st.column_config.NumberColumn("PNL_BTC", help="TP1+TP2+TP3+Exit (BTC)", disabled=True),
        COL["FEES"]: st.column_config.NumberColumn(COL["FEES"], help="fees (BTC)"),
        COL["PLAN"]: st.column_config.TextColumn(COL["PLAN"]),
        COL["NOTES"]: st.column_config.TextColumn(COL["NOTES"]),
    }

    edit_mode = st.toggle("✎ Bewerken/Toevoegen inschakelen", value=False, help="Zet aan om rijen inline te wijzigen of toe te voegen (ghost row).", key=keygen("toggle_edit"))

    if edit_mode:
        edited = st.data_editor(
            df_view[vis_cols].reset_index(drop=True),
            use_container_width=True,
            hide_index=True,
            column_config=colcfg,
            disabled=False,
            num_rows="dynamic",
            key=keygen("journal_editor"),
        )
    else:
        # Read-only view met Styler.map (geen FutureWarning)
        df_show = df_view[vis_cols].copy()
        for c in [COL["PNL_TP1"], COL["PNL_TP2"], COL["PNL_TP3"], COL["PNL_EXIT"], "PNL_BTC"]:
            df_show[c] = pd.to_numeric(df_show[c], errors="coerce")

        styler = (
            df_show.style
            .map(cell_style_color, subset=[COL["PNL_TP1"], COL["PNL_TP2"], COL["PNL_TP3"], COL["PNL_EXIT"], "PNL_BTC"])
            .format({
                COL["PNL_TP1"]: lambda x: "" if pd.isna(x) else f"{float(x):,.3f}".rstrip("0").rstrip("."),
                COL["PNL_TP2"]: lambda x: "" if pd.isna(x) else f"{float(x):,.3f}".rstrip("0").rstrip("."),
                COL["PNL_TP3"]: lambda x: "" if pd.isna(x) else f"{float(x):,.3f}".rstrip("0").rstrip("."),
                COL["PNL_EXIT"]: lambda x: "" if pd.isna(x) else f"{float(x):,.3f}".rstrip("0").rstrip("."),
                "PNL_BTC":     lambda x: "" if pd.isna(x) else f"{float(x):,.3f}".rstrip("0").rstrip("."),
            })
        )
        st.dataframe(styler, use_container_width=True, hide_index=True)
        edited = df_view[vis_cols].reset_index(drop=True)

    # CRUD controls
    app = load_state()
    base_map = {str(r[COL["TRADE_ID"]]): r.to_dict() for _, r in df_view.iterrows() if str(r[COL["TRADE_ID"]]).strip()}

    if edit_mode:
        cA, cB, cC = st.columns(3)
        do_save = cA.button(" Opslaan wijzigingen", type="primary", key=keygen("btn_save"))
        del_id = cB.text_input("Verwijder Trade_ID (exact)", key=keygen("inp_del_id"))
        do_del = cC.button("️ Verwijderen", key=keygen("btn_del"))

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
                    row = row.copy()
                    row["ID"] = new_id
                    base_row = {k: "" for k in ORDER}
                    base_row[COL["TRADE_ID"]] = new_id
                    payload = map_row_to_payload(row, base_row)
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

                if app.get("gh_sync_enabled", False):
                    import github_sync
                    ok, msg = github_sync.sync_now()
                    st.info(msg)

                st.rerun()
