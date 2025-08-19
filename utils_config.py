# utils_config.py — config loader: config.toml -> .env -> defaults (crash-vrij)
from __future__ import annotations
import os
from pathlib import Path

def _load_toml() -> dict:
    cfg = {}
    if Path("config.toml").exists():
        try:
            import tomllib  # py 3.11+
            with open("config.toml","rb") as f:
                cfg.update(tomllib.load(f))
        except ModuleNotFoundError:
            try:
                import tomli
                with open("config.toml","rb") as f:
                    cfg.update(tomli.load(f))
            except Exception:
                pass
        except Exception:
            pass
    return cfg

def load_config() -> dict:
    cfg = _load_toml()
    # .env (optioneel)
    try:
        from dotenv import load_dotenv
        load_dotenv(override=False)
    except Exception:
        pass

    # env overschrijft toml; daarna defaults
    cfg["START_KAPITAAL"] = int(os.getenv("START_KAPITAAL", cfg.get("START_KAPITAAL", 0)))
    cfg["DATA_DIR"]   = os.getenv("BITPILOT_DATA_DIR",   cfg.get("DATA_DIR", "data"))
    cfg["EXPORT_DIR"] = os.getenv("BITPILOT_EXPORT_DIR", cfg.get("EXPORT_DIR", "data/export"))
    cfg["SHOTS_DIR"]  = os.getenv("BITPILOT_SHOTS_DIR",  cfg.get("SHOTS_DIR", "resources/screens"))

    # R0.2-03 BTC
    cfg["DENOM"]        = os.getenv("DENOM",        cfg.get("DENOM", "BTC"))
    cfg["BTC_DECIMALS"] = int(os.getenv("BTC_DECIMALS", cfg.get("BTC_DECIMALS", 6)))

    # mappen aanmaken (geen crash)
    for p in (cfg["DATA_DIR"], cfg["EXPORT_DIR"], cfg["SHOTS_DIR"]):
        Path(p).mkdir(parents=True, exist_ok=True)
    return cfg

def format_btc(x: float, decimals: int | None = None) -> str:
    """Formatteer getal als BTC string met vaste decimalen."""
    cfg = load_config()
    d = cfg.get("BTC_DECIMALS", 6) if decimals is None else decimals
    try:
        val = float(x)
    except Exception:
        return "—"
    return f"Ƀ {val:.{d}f}"
