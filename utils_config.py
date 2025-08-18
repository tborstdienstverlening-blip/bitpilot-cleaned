# utils_config.py
from __future__ import annotations
from pathlib import Path
import json

ROOT = Path.cwd()
CFG = ROOT / "config.json"

try:
    import tomllib as _toml  # Python 3.11+
except Exception:
    _toml = None
CFG_TOML = ROOT / "config.toml"

_default = {
    "theme": {
        "mode": "auto",
        "primary": "#1f6feb",
        "badge": {"macro": "#3b82f6", "ok": "#10b981", "warn": "#f59e0b", "err": "#ef4444"},
        "grey": {"muted": "#6b7280", "low": "#9ca3af", "med": "#6b7280", "high": "#374151"},
    },
    "paths": {"screens_base": "resources/screenshots", "snapshots": "data/snapshots"},
    "backups": {"keep": 20},
    "retrieval": {
        "n_trades": 10,
        "max_ctx_tokens": {"routine": 1500, "deep": 3500},
        "userindex_weights": {"ta": 0.4, "live": 0.2, "post": 0.2, "notes": 0.2},
    },
    "models": {"routine": "gpt-4o-mini", "deep": "gpt-5-mini"},
    "prices_per_1k": {},
    "copilot": {
        "plantrouw_min": 60,
        "rr_min": 1.5,
        "auto_monitor_interval_min": 30,
        "max_ai_calls_per_session": 10,
        "auto_preflight": True,
        "public_price_feed": False,
    },
}

def _deep_merge(d: dict, default: dict) -> dict:
    for k, v in default.items():
        if k not in d:
            d[k] = v
        elif isinstance(v, dict) and isinstance(d.get(k), dict):
            _deep_merge(d[k], v)
    return d

def load_config() -> dict:
    """Lees config.toml (indien aanwezig) + override met config.json, merge met defaults."""
    data = {}
    if CFG_TOML.exists() and _toml is not None:
        try:
            data = _toml.loads(CFG_TOML.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    if CFG.exists():
        try:
            j = json.loads(CFG.read_text(encoding="utf-8") or "{}")
            if isinstance(j, dict):
                data.update(j)
        except Exception:
            pass
    return _deep_merge(data, _default.copy())

def save_config(cfg: dict) -> None:
    CFG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
