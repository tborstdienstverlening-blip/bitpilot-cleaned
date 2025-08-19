# app_state.py — UI-state + settings persist + backups
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
from utils_config import load_config

def _cfg(): return load_config()

def _state_path() -> Path:
    return Path(_cfg()["DATA_DIR"]) / "app_state.json"

def _bak_dir() -> Path:
    d = Path(_cfg()["DATA_DIR"]) / ".bak"
    d.mkdir(parents=True, exist_ok=True)
    return d

DEFAULT_STATE = {
    "start_kapitaal": 0.0,
    # GitHub backup settings (token uit secrets/env, NIET opslaan!)
    "gh_sync_enabled": False,
    "gh_repo": "",
    "gh_branch": "main",
    "gh_dir": "data",
    # KPI-instellingen
    "rolling_n": 20,  # R0.2-04: Rolling winrate window
    # status
    "last_sync_ts": "",
    "last_sync_msg": "Sync uit",
    "sync_pending": False,
}

def load_state() -> dict:
    p = _state_path()
    if p.exists():
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            full = {**DEFAULT_STATE, **obj}
            # sanity
            try:
                full["rolling_n"] = int(full.get("rolling_n", 20)) or 20
            except Exception:
                full["rolling_n"] = 20
            return full
        except Exception:
            pass
    # fallback: config.toml
    cfg = _cfg()
    st = dict(DEFAULT_STATE)
    st["start_kapitaal"] = float(cfg.get("START_KAPITAAL", 0))
    return st

def save_state(state: dict) -> None:
    p = _state_path()
    # backup (best-effort)
    if p.exists():
        try:
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            (_bak_dir() / f"app_state_{ts}.json").write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
