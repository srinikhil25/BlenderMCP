"""Configuration for Obsidian MCP tool."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

# Shared LLM settings (reuse from main config)
import src.config as _cfg

LLM_PROVIDER = _cfg.LLM_PROVIDER
GEMINI_API_KEY = _cfg.GEMINI_API_KEY
GEMINI_MODEL = _cfg.GEMINI_MODEL
OLLAMA_MODEL = _cfg.OLLAMA_MODEL
OLLAMA_NUM_CTX = _cfg.OLLAMA_NUM_CTX
LLM_TIMEOUT = _cfg.LLM_TIMEOUT

# Obsidian-specific settings
_SETTINGS_DIR = Path.home() / ".blendermcp" / "obsidian"
_SETTINGS_FILE = _SETTINGS_DIR / "settings.json"

# Default vault path — user sets this on first launch
VAULT_PATH: str = ""

# Note generation settings
DEFAULT_TEMPLATE = "standard"  # "standard", "cornell", "zettelkasten", "meeting", "research"
AUTO_LINK = True        # Auto-detect and create [[wiki-links]]
AUTO_TAGS = True        # Auto-generate #tags from content
FRONTMATTER = True      # Add YAML frontmatter to notes

DEFAULTS: Dict[str, Any] = {
    "vault_path": "",
    "template": "standard",
    "auto_link": True,
    "auto_tags": True,
    "frontmatter": True,
}


def load_settings() -> Dict[str, Any]:
    """Load Obsidian-specific settings."""
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
    """Persist Obsidian settings to disk."""
    try:
        _SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        _SETTINGS_FILE.write_text(
            json.dumps(settings, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def apply_settings(settings: Dict[str, Any]) -> None:
    """Push settings into module-level variables."""
    global VAULT_PATH, DEFAULT_TEMPLATE, AUTO_LINK, AUTO_TAGS, FRONTMATTER
    VAULT_PATH = settings.get("vault_path", "")
    DEFAULT_TEMPLATE = settings.get("template", "standard")
    AUTO_LINK = settings.get("auto_link", True)
    AUTO_TAGS = settings.get("auto_tags", True)
    FRONTMATTER = settings.get("frontmatter", True)


# Load on import
_saved = load_settings()
apply_settings(_saved)
