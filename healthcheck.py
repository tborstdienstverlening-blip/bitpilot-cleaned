# healthcheck.py — zichtbaar, niet crashend
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import platform, sys
from compat import load_config, get_ai_status

NEEDED_DIRS = [Path("data"), Path("data/export"), Path("resources/screens")]

def ensure_dirs():
    for d in NEEDED_DIRS:
        d.mkdir(parents=True, exist_ok=True)

def report() -> dict:
    ensure_dirs()
    cfg = load_config()
    ai = get_ai_status(cfg)
    return {
        "time": datetime.utcnow().isoformat() + "Z",
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "ai": {"online": ai.online, "reason": ai.reason},
        "dirs_ok": all(d.exists() for d in NEEDED_DIRS),
    }
