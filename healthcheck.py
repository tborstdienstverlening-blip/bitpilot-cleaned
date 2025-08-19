# healthcheck.py — zichtbaar, niet-crashend health-blok
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import platform, sys, os
from utils_config import load_config, format_btc

def _needed_dirs(cfg):
    return [Path(cfg["DATA_DIR"]), Path(cfg["EXPORT_DIR"]), Path(cfg["SHOTS_DIR"])]

def _ensure_dirs(cfg):
    for d in _needed_dirs(cfg):
        d.mkdir(parents=True, exist_ok=True)

def _ai_status():
    key = os.getenv("OPENAI_API_KEY", "")
    return (False, "Offline (stub)") if not key else (True, "Online")

def report() -> dict:
    cfg = load_config()
    _ensure_dirs(cfg)
    ai_online, ai_reason = _ai_status()
    start = cfg.get("START_KAPITAAL", 0)
    denom = cfg.get("DENOM", "BTC")
    start_fmt = format_btc(start) if denom == "BTC" else str(start)
    return {
        "time": datetime.utcnow().isoformat() + "Z",
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "dirs_ok": all(d.exists() for d in _needed_dirs(cfg)),
        "denom": denom,
        "start_kapitaal": start,
        "start_kapitaal_fmt": start_fmt,
        "ai": {"online": ai_online, "reason": ai_reason},
    }
