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
    # GitHub backup settings (token komt uit secrets/env, NIET opslaan!)
    "gh_sync_enabled": False,
    "gh_repo": "",         # bv. "tborstdienstverlening-blip/bitpilot-cleaned"
    "gh_branch": "main",
    "gh_dir": "data",
    # status
    "last_sync_ts": "",    # ISO UTC
    "last_sync_msg": "Sync uit",
    "sync_pending": False,
}

def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"

def load_state() -> dict:
    p = _state_path()
    if p.exists():
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            # vul ontbrekende sleutels aan
            full = {**DEFAULT_STATE, **obj}
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
    # backup vorige versie (best effort)
    if p.exists():
        try:
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            (_bak_dir() / f"app_state_{ts}.json").write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass
    # schrijf nieuw
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

def mark_sync(status_text: str) -> None:
    st = load_state()
    st["last_sync_ts"] = _now_iso()
    st["last_sync_msg"] = status_text
    st["sync_pending"] = False
    save_state(st)

def mark_sync_pending() -> None:
    st = load_state()
    st["sync_pending"] = True
    save_state(st)
