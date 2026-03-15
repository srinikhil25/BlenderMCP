"""Persistent user settings — stored in ~/.blendermcp/settings.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

_SETTINGS_DIR = Path.home() / ".blendermcp"
_SETTINGS_FILE = _SETTINGS_DIR / "settings.json"

# Default values (must match config.py defaults)
DEFAULTS: Dict[str, Any] = {
    "llm_provider": "gemini",
    "gemini_model": "gemini-2.5-flash",
    "ollama_model": "qwen2.5-coder:7b",
    "ollama_num_ctx": 8192,
    "max_retries": 2,
    "render_width": 960,
    "render_height": 540,
    "renderer": "cycles",
}


def load_settings() -> Dict[str, Any]:
    """Load saved settings, falling back to defaults for missing keys."""
    settings = dict(DEFAULTS)
    try:
        if _SETTINGS_FILE.exists():
            saved = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                for key in DEFAULTS:
                    if key in saved:
                        settings[key] = saved[key]
    except Exception:
        pass
    return settings


def save_settings(settings: Dict[str, Any]) -> None:
    """Persist settings to disk."""
    try:
        _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        _SETTINGS_FILE.write_text(
            json.dumps(settings, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def apply_to_config(settings: Dict[str, Any]) -> None:
    """Push settings values into the runtime config module."""
    import src.config as cfg

    cfg.LLM_PROVIDER = settings.get("llm_provider", DEFAULTS["llm_provider"])
    cfg.GEMINI_MODEL = settings.get("gemini_model", DEFAULTS["gemini_model"])
    cfg.OLLAMA_MODEL = settings.get("ollama_model", DEFAULTS["ollama_model"])
    cfg.OLLAMA_NUM_CTX = settings.get("ollama_num_ctx", DEFAULTS["ollama_num_ctx"])
    cfg.MAX_RETRIES = settings.get("max_retries", DEFAULTS["max_retries"])
