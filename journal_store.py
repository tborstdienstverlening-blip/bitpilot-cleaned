from __future__ import annotations
import os
import time
import pandas as pd
from pathlib import Path
from typing import Dict, Any, Tuple

from schema import COL, ORDER
from utils_config import load_config

DATA_DIR = Path("data")
BAK_DIR  = DATA_DIR / ".bak"
CSV_PATH = DATA_DIR / "journal_entries.csv"

def _ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BAK_DIR.mkdir(parents=True, exist_ok=True)

def _now_ts() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())

def _backup_name() -> Path:
    return BAK_DIR / f"journal_{_now_ts()}.csv"

def _atomic_write_csv(df: pd.DataFrame, path: Path):
    tmp = path.with_suffix(".tmp")
    df.to_csv(tmp, index=False)
    os.replace(tmp, path)

def _create_seed_if_missing():
    if not CSV_PATH.exists():
        _ensure_dirs()
        # schrijf alleen header in ORDER
        pd.DataFrame(columns=ORDER).to_csv(CSV_PATH, index=False)

def load_journal() -> pd.DataFrame:
    _create_seed_if_missing()
    try:
        # alles als string inladen om type-gedoe te voorkomen
        df = pd.read_csv(CSV_PATH, dtype=str, keep_default_na=False)
    except Exception:
        # fallback leeg
        df = pd.DataFrame(columns=ORDER)
    # garandeer alle kolommen
    for c in ORDER:
        if c not in df.columns:
            df[c] = ""
    # zet NIETS op NaN; alles string
    for c in df.columns:
        df[c] = df[c].astype(str)
    # kolomvolgorde
    df = df[ORDER]
    return df

def save_journal(df: pd.DataFrame) -> None:
    _ensure_dirs()
    # backup
    try:
        df.to_csv(_backup_name(), index=False)
    except Exception:
        # backup is best-effort
        pass
    # atomic write
    _atomic_write_csv(df[ORDER], CSV_PATH)

def _gen_trade_id(df: pd.DataFrame) -> str:
    # T-YYYYMMDD-###
    today = time.strftime("%Y%m%d", time.gmtime())
    prefix = f"T-{today}-"
    # pak hoogste teller
    existing = df[COL["TRADE_ID"]].astype(str)
    nums = []
    for tid in existing:
        if tid.startswith(prefix):
            try:
                nums.append(int(tid.split("-")[-1]))
            except Exception:
                pass
    n = max(nums) + 1 if nums else 1
    return f"{prefix}{n:03d}"

def _clean_payload(df_cols, payload: Dict[str, Any]) -> Dict[str, Any]:
    # map naar alle kolommen, leeg op ""
    clean = {k: payload.get(k, "") for k in df_cols}
    # geen NaN
    for k, v in clean.items():
        clean[k] = "" if v is None else v
    return clean

def append_entry(payload: Dict[str, Any]) -> str:
    df = load_journal()
    # Trade_ID
    tid = str(payload.get(COL["TRADE_ID"], "")).strip()
    if not tid:
        tid = _gen_trade_id(df)
    # duplicate check
    if (df[COL["TRADE_ID"]].astype(str) == tid).any():
        raise ValueError(f"Trade_ID bestaat al: {tid}")

    # volledige rij mappen op bestaande kolommen → voorkomt FutureWarning
    row_full = {k: "" for k in df.columns}
    for k, v in payload.items():
        if k in row_full:
            row_full[k] = v if v is not None else ""

    row_full[COL["TRADE_ID"]] = tid

    df = pd.concat([df, pd.DataFrame([row_full])], ignore_index=True)
    # zorg dat alle kolommen bestaan en op volgorde zijn
    for c in ORDER:
        if c not in df.columns:
            df[c] = ""
    df = df[ORDER]
    save_journal(df)
    return tid

def update_entry(trade_id: str, updates: Dict[str, Any]) -> None:
    df = load_journal()
    mask = (df[COL["TRADE_ID"]].astype(str) == str(trade_id))
    if not mask.any():
        raise ValueError(f"Onbekende Trade_ID: {trade_id}")

    idx = df.index[mask][0]
    # update alleen bekende kolommen
    for k, v in updates.items():
        if k in df.columns:
            df.at[idx, k] = "" if v is None else v

    # kolommen afdwingen + volgorde
    for c in ORDER:
        if c not in df.columns:
            df[c] = ""
    df = df[ORDER]
    save_journal(df)

def delete_entry(trade_id: str) -> None:
    df = load_journal()
    mask = (df[COL["TRADE_ID"]].astype(str) == str(trade_id))
    if not mask.any():
        raise ValueError(f"Onbekende Trade_ID: {trade_id}")
    df = df[~mask].copy()
    # op orde houden
    for c in ORDER:
        if c not in df.columns:
            df[c] = ""
    df = df[ORDER]
    save_journal(df)

def get_last_save_ts() -> str | None:
    try:
        ts = os.path.getmtime(CSV_PATH)
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))
    except Exception:
        return None
