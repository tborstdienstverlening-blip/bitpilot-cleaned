# utils_config.py — config loader: config.toml -> .env -> defaults
from __future__ import annotations
import os
from pathlib import Path

def _load_toml():
    cfg = {}
    if Path("config.toml").exists():
        try:
            import tomllib  # py 3.11+
            with open("config.toml","rb") as f: cfg.update(tomllib.load(f))
        except ModuleNotFoundError:
            import tomli
            with open("config.toml","rb") as f: cfg.update(tomli.load(f))
        except Exception:
            pass
    return cfg

def load_config():
    cfg = _load_toml()
    try:
        from dotenv import load_dotenv
        load_dotenv(override=False)
    except Exception:
        pass

    # env overschrijft toml; anders defaults
    cfg["START_KAPITAAL"] = int(os.getenv("START_KAPITAAL", cfg.get("START_KAPITAAL", 0)))
    cfg["DATA_DIR"]   = os.getenv("BITPILOT_DATA_DIR",   cfg.get("DATA_DIR", "data"))
    cfg["EXPORT_DIR"] = os.getenv("BITPILOT_EXPORT_DIR", cfg.get("EXPORT_DIR", "data/export"))
    cfg["SHOTS_DIR"]  = os.getenv("BITPILOT_SHOTS_DIR",  cfg.get("SHOTS_DIR", "resources/screens"))

    # mappen aanmaken (geen crash)
    for p in (cfg["DATA_DIR"], cfg["EXPORT_DIR"], cfg["SHOTS_DIR"]):
        Path(p).mkdir(parents=True, exist_ok=True)
    return cfg
