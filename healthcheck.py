# healthcheck.py — zichtbaar, niet-crashend health-blok
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import platform, sys, os
from utils_config import load_config

NEEDED_DIRS = lambda cfg: [Path(cfg["DATA_DIR"]), Path(cfg["EXPORT_DIR"]), Path(cfg["SHOTS_DIR"])]

def ensure_dirs(cfg):
    for d in NEEDED_DIRS(cfg):
        d.mkdir(parents=True, exist_ok=True)

def ai_status():
    key = os.getenv("OPENAI_API_KEY", "")
    return (False, "Offline (stub)") if not key else (True, "Online")

def report() -> dict:
    cfg = load_config()
    ensure_dirs(cfg)
    ai_online, ai_reason = ai_status()
    return {
        "time": datetime.utcnow().isoformat() + "Z",
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "dirs_ok": all(d.exists() for d in NEELED_DIRS(cfg)) if False else all(d.exists() for d in NEEDED_DIRS(cfg)),
        "start_kapitaal": cfg.get("START_KAPITAAL", 0),
        "ai": {"online": ai_online, "reason": ai_reason},
    }
