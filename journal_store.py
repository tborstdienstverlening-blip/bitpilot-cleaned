# journal_store.py — centrale opslag + CRUD + backups + save-marker
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import pandas as pd
from schema import COL, ORDER, DATE_FMT
from utils_config import load_config

def _cfg(): return load_config()

def _csv_path() -> Path:
    return Path(_cfg()["DATA_DIR"]) / "journal_entries.csv"

def _bak_dir() -> Path:
    return Path(_cfg()["DATA_DIR"]) / ".bak"

def _save_marker_path() -> Path:
    return Path(_cfg()["DATA_DIR"]) / ".last_save.txt"

def _ensure_seed():
    csv = _csv_path()
    csv.parent.mkdir(parents=True, exist_ok=True)
    if not csv.exists():
        pd.DataFrame(columns=ORDER).to_csv(csv, index=False)

def _touch_save_marker():
    try:
        _save_marker_path().write_text(datetime.utcnow().isoformat() + "Z", encoding="utf-8")
    except Exception:
        pass

def get_last_save_ts() -> str:
    p = _save_marker_path()
    return p.read_text(encoding="utf-8") if p.exists() else ""

def load_journal() -> pd.DataFrame:
    _ensure_seed()
    try:
        df = pd.read_csv(_csv_path())
    except Exception:
        # probeer laatste geldige backup
        df = _load_last_good_backup()
    for col in ORDER:
        if col not in df.columns:
            df[col] = ""
    return df[ORDER]

def _load_last_good_backup() -> pd.DataFrame:
    bd = _bak_dir()
    bd.mkdir(parents=True, exist_ok=True)
    cands = sorted(bd.glob("journal_*.csv"), reverse=True)
    for f in cands:
        try:
            df = pd.read_csv(f)
            return df
        except Exception:
            continue
    return pd.DataFrame(columns=ORDER)

def _backup(df: pd.DataFrame):
    try:
        bd = _bak_dir()
        bd.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        out = bd / f"journal_{ts}.csv"
        df.to_csv(out, index=False)
    except Exception:
        pass

def save_journal(df: pd.DataFrame) -> None:
    _ensure_seed()
    _backup(df)  # backup vóór schrijven
    tmp = _csv_path().with_suffix(".csv.tmp")
    df[ORDER].to_csv(tmp, index=False)
    tmp.replace(_csv_path())  # atomic rename
    _touch_save_marker()

def _today_prefix() -> str:
    return datetime.utcnow().strftime("T-%Y%m%d-")

def _next_id(df: pd.DataFrame) -> str:
    prefix = _today_prefix()
    existing = [str(tid) for tid in df[COL["TRADE_ID"]].astype(str).tolist()]
    nums = [int(x.split("-")[-1]) for x in existing if x.startswith(prefix) and x.split("-")[-1].isdigit()]
    nxt = (max(nums) + 1) if nums else 1
    return f"{prefix}{nxt:03d}"

def append_entry(row: dict) -> str:
    df = load_journal()
    clean = {c: row.get(c, "") for c in ORDER}
    tid = str(clean.get(COL["TRADE_ID"], "")).strip()
    if not tid:
        tid = _next_id(df)
        clean[COL["TRADE_ID"]] = tid
    if (df[COL["TRADE_ID"]].astype(str) == tid).any():
        raise ValueError(f"Trade_ID bestaat al: {tid}")
    df = pd.concat([df, pd.DataFrame([clean])], ignore_index=True)
    save_journal(df)
    return tid

def update_entry(trade_id: str, updates: dict) -> None:
    df = load_journal()
    mask = df[COL["TRADE_ID"]].astype(str) == str(trade_id)
    if not mask.any():
        raise ValueError(f"Trade_ID niet gevonden: {trade_id}")
    for k, v in updates.items():
        if k in ORDER:
            df.loc[mask, k] = v
    save_journal(df)

def delete_entry(trade_id: str) -> None:
    df = load_journal()
    mask = df[COL["TRADE_ID"]].astype(str) == str(trade_id)
    if not mask.any():
        raise ValueError(f"Trade_ID niet gevonden: {trade_id}")
    df = df.loc[~mask].copy()
    save_journal(df)

