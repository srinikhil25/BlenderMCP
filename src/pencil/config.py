"""Configuration for PencilMCP — AI-powered UI/UX design generation."""

from __future__ import annotations

import json
from pathlib import Path

import src.config as shared_cfg

# ── Paths ─────────────────────────────────────────────────────────────
PENCIL_DIR = Path.home() / ".blendermcp" / "pencil"
SETTINGS_FILE = PENCIL_DIR / "settings.json"
OUTPUT_DIR = PENCIL_DIR / "output"
HISTORY_DIR = PENCIL_DIR / "history"

PENCIL_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

# ── Defaults ──────────────────────────────────────────────────────────
DEFAULTS: dict = {
    "output_dir": str(OUTPUT_DIR),
    "default_framework": "html_css",
    "default_style_system": "tailwind",
    "auto_preview": True,
    "auto_save": True,
}

# ── Framework / Output Formats ────────────────────────────────────────
FRAMEWORKS = {
    "html_css": {
        "name": "HTML + CSS",
        "extension": ".html",
        "description": "Standalone HTML with inline/embedded CSS",
    },
    "react_tailwind": {
        "name": "React + Tailwind",
        "extension": ".jsx",
        "description": "React component with Tailwind CSS classes",
    },
    "vue_tailwind": {
        "name": "Vue + Tailwind",
        "extension": ".vue",
        "description": "Vue 3 SFC with Tailwind CSS",
    },
    "html_bootstrap": {
        "name": "HTML + Bootstrap",
        "extension": ".html",
        "description": "HTML with Bootstrap 5 framework",
    },
    "svelte": {
        "name": "Svelte",
        "extension": ".svelte",
        "description": "Svelte component",
    },
}

# ── Design Type Presets ───────────────────────────────────────────────
DESIGN_TYPES = {
    "landing_page": {
        "name": "Landing Page",
        "description": "Full marketing/product landing page",
        "prompt_hint": "Create a complete landing page with hero section, features, "
                       "testimonials, pricing, and footer. Include navigation.",
    },
    "dashboard": {
        "name": "Dashboard",
        "description": "Admin/analytics dashboard with charts and stats",
        "prompt_hint": "Create a dashboard layout with sidebar navigation, stats cards, "
                       "chart placeholders, and data tables. Use a clean, modern look.",
    },
    "form": {
        "name": "Form / Input",
        "description": "Form design — login, signup, contact, survey",
        "prompt_hint": "Create a well-designed form with proper labels, validation states, "
                       "and a clean layout. Include submit/cancel buttons.",
    },
    "card_grid": {
        "name": "Card Grid",
        "description": "Grid of cards — products, articles, team members",
        "prompt_hint": "Create a responsive card grid with images, titles, descriptions, "
                       "and action buttons. Include filters or categories.",
    },
    "navbar": {
        "name": "Navigation Bar",
        "description": "Header/navbar with logo, links, and mobile menu",
        "prompt_hint": "Create a responsive navigation bar with logo, menu links, "
                       "search bar, and mobile hamburger menu.",
    },
    "component": {
        "name": "UI Component",
        "description": "Single reusable component — button, modal, tooltip",
        "prompt_hint": "Create a polished, reusable UI component with proper states "
                       "(hover, active, disabled). Show multiple variants.",
    },
    "wireframe": {
        "name": "Wireframe",
        "description": "Low-fidelity wireframe sketch",
        "prompt_hint": "Create a wireframe using simple shapes, gray boxes, and placeholder text. "
                       "Focus on layout and information hierarchy, not visual polish.",
    },
    "email": {
        "name": "Email Template",
        "description": "HTML email template",
        "prompt_hint": "Create an HTML email template using tables for layout (email-safe). "
                       "600px max width, inline styles only.",
    },
    "mobile": {
        "name": "Mobile Screen",
        "description": "Mobile app screen design",
        "prompt_hint": "Create a mobile app screen (375px width). Include a status bar, "
                       "navigation, and content area. Use mobile-friendly touch targets.",
    },
    "full_page": {
        "name": "Full Page (Custom)",
        "description": "Any custom full-page design",
        "prompt_hint": "",
    },
}

# ── Color Themes ──────────────────────────────────────────────────────
COLOR_THEMES = {
    "modern_dark": {
        "name": "Modern Dark",
        "hint": "Dark background (#0f172a), light text, blue/purple accents",
    },
    "clean_light": {
        "name": "Clean Light",
        "hint": "White/light gray background, dark text, blue accents",
    },
    "warm_neutral": {
        "name": "Warm Neutral",
        "hint": "Warm beige/cream background, brown/orange accents, cozy feel",
    },
    "vibrant": {
        "name": "Vibrant",
        "hint": "Bold, saturated colors, gradients, eye-catching design",
    },
    "monochrome": {
        "name": "Monochrome",
        "hint": "Black, white, and shades of gray only. Elegant and minimal",
    },
    "glassmorphism": {
        "name": "Glassmorphism",
        "hint": "Frosted glass effect, backdrop blur, subtle transparency, gradient backgrounds",
    },
    "custom": {
        "name": "Custom (from prompt)",
        "hint": "",
    },
}

# ── Runtime state ─────────────────────────────────────────────────────
OUTPUT_PATH: str = DEFAULTS["output_dir"]
DEFAULT_FRAMEWORK: str = DEFAULTS["default_framework"]
DEFAULT_STYLE_SYSTEM: str = DEFAULTS["default_style_system"]
AUTO_PREVIEW: bool = DEFAULTS["auto_preview"]
AUTO_SAVE: bool = DEFAULTS["auto_save"]


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            return {**DEFAULTS, **data}
        except Exception:
            pass
    return dict(DEFAULTS)


def save_settings(settings: dict) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def apply_settings(settings: dict) -> None:
    global OUTPUT_PATH, DEFAULT_FRAMEWORK, DEFAULT_STYLE_SYSTEM
    global AUTO_PREVIEW, AUTO_SAVE

    OUTPUT_PATH = settings.get("output_dir", DEFAULTS["output_dir"])
    DEFAULT_FRAMEWORK = settings.get("default_framework", DEFAULTS["default_framework"])
    DEFAULT_STYLE_SYSTEM = settings.get("default_style_system", DEFAULTS["default_style_system"])
    AUTO_PREVIEW = settings.get("auto_preview", DEFAULTS["auto_preview"])
    AUTO_SAVE = settings.get("auto_save", DEFAULTS["auto_save"])
