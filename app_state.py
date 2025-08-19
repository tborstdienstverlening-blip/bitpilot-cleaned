# app_state.py — eenvoudige UI-state persist + backups
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
from utils_config import load_config

def _state_path() -> Path:
    cfg = load_config()
    p = Path(cfg["DATA_DIR"]) / "app_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

def _bak_dir() -> Path:
    cfg = load_config()
    d = Path(cfg["DATA_DIR"]) / ".bak"
    d.mkdir(parents=True, exist_ok=True)
    return d

def load_state() -> dict:
    sp = _state_path()
    if sp.exists():
        try:
            return json.loads(sp.read_text(encoding="utf-8"))
        except Exception:
            pass
    # fallback op config.toml
    cfg = load_config()
    return {"start_kapitaal": cfg.get("START_KAPITAAL", 0)}

def save_state(state: dict) -> None:
    sp = _state_path()
    # backup vorige versie (best effort)
    if sp.exists():
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            (_bak_dir() / f"app_state_{ts}.json").write_text(sp.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            pass
    sp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
