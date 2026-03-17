"""Configuration for KritaMCP — AI-powered 2D art generation.

Inherits shared LLM settings from src.config, adds image-specific settings.
"""

from __future__ import annotations

import json
from pathlib import Path

import src.config as shared_cfg

# ── Paths ─────────────────────────────────────────────────────────────
KRITA_DIR = Path.home() / ".blendermcp" / "krita"
SETTINGS_FILE = KRITA_DIR / "settings.json"
OUTPUT_DIR = KRITA_DIR / "output"
HISTORY_DIR = KRITA_DIR / "history"

# Ensure directories exist
KRITA_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

# ── Defaults ──────────────────────────────────────────────────────────
DEFAULTS: dict = {
    "output_dir": str(OUTPUT_DIR),
    "default_style": "photorealistic",
    "default_resolution": "1024x1024",
    "image_model": "gemini-2.5-flash-image",
    "auto_save": True,
    "save_prompt_metadata": True,
}

# ── Image Generation Models (ranked by quality) ──────────────────────
IMAGE_MODELS = {
    "gemini-2.5-flash-image": {
        "name": "Gemini 2.5 Flash Image",
        "description": "Fast, good quality",
        "supports_edit": True,
    },
    "gemini-3-pro-image-preview": {
        "name": "Gemini 3 Pro Image",
        "description": "High quality, slower",
        "supports_edit": True,
    },
    "gemini-3.1-flash-image-preview": {
        "name": "Gemini 3.1 Flash Image",
        "description": "Latest, balanced",
        "supports_edit": True,
    },
}

# ── Style Presets ─────────────────────────────────────────────────────
STYLE_PRESETS = {
    "photorealistic": {
        "name": "Photorealistic",
        "suffix": "photorealistic, 8k resolution, highly detailed, sharp focus, "
                  "professional photography, natural lighting",
    },
    "digital_art": {
        "name": "Digital Art",
        "suffix": "digital art, vibrant colors, detailed illustration, "
                  "professional digital painting, artstation quality",
    },
    "watercolor": {
        "name": "Watercolor",
        "suffix": "watercolor painting style, soft brushstrokes, "
                  "delicate washes, artistic, traditional media feel",
    },
    "oil_painting": {
        "name": "Oil Painting",
        "suffix": "oil painting style, rich textures, visible brushstrokes, "
                  "classical art technique, museum quality",
    },
    "anime": {
        "name": "Anime / Manga",
        "suffix": "anime style, clean linework, cel shading, "
                  "vibrant colors, Japanese animation aesthetic",
    },
    "pixel_art": {
        "name": "Pixel Art",
        "suffix": "pixel art style, retro 16-bit aesthetic, "
                  "clean pixels, limited color palette, nostalgic",
    },
    "sketch": {
        "name": "Pencil Sketch",
        "suffix": "pencil sketch, graphite drawing, detailed linework, "
                  "hand-drawn feel, artistic crosshatching",
    },
    "concept_art": {
        "name": "Concept Art",
        "suffix": "concept art, professional game/film design, "
                  "dramatic lighting, epic composition, matte painting quality",
    },
    "minimalist": {
        "name": "Minimalist",
        "suffix": "minimalist design, clean lines, simple shapes, "
                  "limited color palette, modern aesthetic",
    },
    "poster": {
        "name": "Poster Design",
        "suffix": "professional poster design, bold typography area, "
                  "eye-catching composition, graphic design, print ready",
    },
    "none": {
        "name": "No Style (Raw)",
        "suffix": "",
    },
}

# ── Resolution Presets ────────────────────────────────────────────────
RESOLUTION_PRESETS = {
    "512x512": {"name": "512×512 (Small)", "w": 512, "h": 512},
    "768x768": {"name": "768×768 (Medium)", "w": 768, "h": 768},
    "1024x1024": {"name": "1024×1024 (Large)", "w": 1024, "h": 1024},
    "1024x768": {"name": "1024×768 (Landscape)", "w": 1024, "h": 768},
    "768x1024": {"name": "768×1024 (Portrait)", "w": 768, "h": 1024},
    "1920x1080": {"name": "1920×1080 (Full HD)", "w": 1920, "h": 1080},
}

# ── Runtime state (loaded from settings) ─────────────────────────────
OUTPUT_PATH: str = DEFAULTS["output_dir"]
DEFAULT_STYLE: str = DEFAULTS["default_style"]
DEFAULT_RESOLUTION: str = DEFAULTS["default_resolution"]
IMAGE_MODEL: str = DEFAULTS["image_model"]
AUTO_SAVE: bool = DEFAULTS["auto_save"]
SAVE_PROMPT_METADATA: bool = DEFAULTS["save_prompt_metadata"]


def load_settings() -> dict:
    """Load settings from disk."""
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            return {**DEFAULTS, **data}
        except Exception:
            pass
    return dict(DEFAULTS)


def save_settings(settings: dict) -> None:
    """Persist settings to disk."""
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def apply_settings(settings: dict) -> None:
    """Apply loaded settings to module-level config."""
    global OUTPUT_PATH, DEFAULT_STYLE, DEFAULT_RESOLUTION
    global IMAGE_MODEL, AUTO_SAVE, SAVE_PROMPT_METADATA

    OUTPUT_PATH = settings.get("output_dir", DEFAULTS["output_dir"])
    DEFAULT_STYLE = settings.get("default_style", DEFAULTS["default_style"])
    DEFAULT_RESOLUTION = settings.get("default_resolution", DEFAULTS["default_resolution"])
    IMAGE_MODEL = settings.get("image_model", DEFAULTS["image_model"])
    AUTO_SAVE = settings.get("auto_save", DEFAULTS["auto_save"])
    SAVE_PROMPT_METADATA = settings.get("save_prompt_metadata", DEFAULTS["save_prompt_metadata"])
