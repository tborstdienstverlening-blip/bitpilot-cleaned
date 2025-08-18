# compat.py — veilige compat-laag
from __future__ import annotations
import importlib, logging, os

logger = logging.getLogger("bitpilot.compat")
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
    logger.addHandler(h)
logger.setLevel(logging.INFO)

def load_config() -> dict:
    cfg = {}
    # .env
    try:
        from dotenv import load_dotenv
        load_dotenv(override=False)
    except Exception:
        logger.info("dotenv niet beschikbaar — sla .env over")
    # TOML
    if os.path.exists("config.toml"):
        try:
            import tomllib  # py3.11+
            import io
            with open("config.toml", "rb") as f:
                cfg.update(tomllib.load(f))
        except ModuleNotFoundError:
            try:
                import tomli
                with open("config.toml", "rb") as f:
                    cfg.update(tomli.load(f))
            except Exception as e:
                logger.warning(f"TOML niet geladen: {e}")
        except Exception as e:
            logger.warning(f"TOML niet geladen: {e}")
    # env overschrijft
    for k, v in os.environ.items():
        if k.startswith("BITPILOT_") or k in ("OPENAI_API_KEY",):
            cfg[k] = v
    return cfg

def safe_import(module_name: str, fallback=None):
    try:
        return importlib.import_module(module_name)
    except Exception as e:
        logger.warning(f"Module '{module_name}' niet gevonden ({e}); gebruik fallback.")
        return fallback

# AI stubs
from dataclasses import dataclass
@dataclass
class AIStatus:
    online: bool
    reason: str

def get_ai_status(cfg: dict) -> AIStatus:
    key = cfg.get("OPENAI_API_KEY") or cfg.get("BITPILOT_OPENAI_API_KEY")
    if key and key.strip():
        return AIStatus(True, "OpenAI key gevonden")
    return AIStatus(False, "Geen API key — AI Offline (stub)")

def ai_analyze_stub(prompt: str) -> str:
    return "🔧 AI Offline (stub): voeg een geldige OPENAI_API_KEY toe in Streamlit Secrets of .env."
