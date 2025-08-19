# coach_engine.py — AI-CRUD poortjes (werkt zonder API key; schrijft via journal_store)
from __future__ import annotations
from datetime import datetime
import pandas as pd
from schema import COL, ORDER
from journal_store import load_journal, append_entry, update_entry
from utils_config import load_config
from pathlib import Path

def _ensure_notes_path() -> Path:
    cfg = load_config()
    p = Path(cfg["DATA_DIR"]) / "ai_notes.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        pd.DataFrame(columns=["timestamp","trade_id","mode","text"]).to_csv(p, index=False)
    return p

def ai_add_trade(payload: dict) -> str:
    """Voeg trade toe vanuit AI-payload; valideer kolommen; defaults invullen."""
    row = {c: payload.get(c, "") for c in ORDER}
    return append_entry(row)

def ai_update_trade(trade_id: str, payload: dict) -> None:
    updates = {k: v for k, v in payload.items() if k in ORDER}
    update_entry(trade_id, updates)

def ai_get_open_trades() -> pd.DataFrame:
    """Voorbeeld: trades zonder definitieve uitkomst (Win_Loss leeg)."""
    df = load_journal()
    return df[df[COL["WIN"]].astype(str).str.strip() == ""]

def ai_log_note(trade_id: str, text: str, mode: str = "coach") -> None:
    p = _ensure_notes_path()
    ts = datetime.utcnow().isoformat() + "Z"
    note = pd.DataFrame([{"timestamp": ts, "trade_id": trade_id, "mode": mode, "text": text}])
    try:
        cur = pd.read_csv(p)
    except Exception:
        cur = pd.DataFrame(columns=["timestamp","trade_id","mode","text"])
    cur = pd.concat([cur, note], ignore_index=True)
    cur.to_csv(p, index=False)
