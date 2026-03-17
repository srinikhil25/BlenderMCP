"""LLM engine for PencilMCP — generates UI code from text descriptions."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

import src.config as cfg
from src.pencil import config as pencil_cfg

# ── Cache ─────────────────────────────────────────────────────────────
CACHE_DIR = pencil_cfg.PENCIL_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ── System Prompts ────────────────────────────────────────────────────

SYSTEM_PROMPT_HTML = """You are an expert UI/UX designer and frontend developer.
You generate complete, production-ready HTML files with embedded CSS from text descriptions.

RULES:
1. Output ONLY the complete HTML code — no explanations, no markdown fences, no commentary.
2. The HTML must be a complete document: <!DOCTYPE html>, <html>, <head> with <style>, <body>.
3. Use modern CSS: flexbox, grid, CSS variables, transitions, hover effects.
4. Make designs RESPONSIVE — use media queries for mobile/tablet/desktop.
5. Use a consistent color scheme throughout. Define colors as CSS variables in :root.
6. Include realistic placeholder content — real-looking text, not "Lorem ipsum" everywhere.
7. Use professional typography — system font stack or Google Fonts via CDN link.
8. Add subtle animations/transitions for interactive elements (buttons, cards, links).
9. Include proper semantic HTML: <header>, <nav>, <main>, <section>, <footer>.
10. For icons, use simple SVG inline or Unicode symbols — do NOT require external icon libraries.
11. All styles must be in a <style> tag in <head> — no external CSS files.
12. Add box-shadow, border-radius, and spacing that looks polished and modern.
13. If the design includes images, use placeholder divs with background colors and aspect ratios.
14. The page should look COMPLETE and professional, not like a skeleton or wireframe (unless wireframe is specifically requested).
15. For charts/graphs, use CSS-only visualizations (bars, progress rings) or placeholder boxes.
"""

SYSTEM_PROMPT_REACT = """You are an expert React developer and UI/UX designer.
You generate complete, production-ready React components with Tailwind CSS.

RULES:
1. Output ONLY the JSX code — no explanations, no markdown fences, no commentary.
2. Use functional components with hooks where needed.
3. Use Tailwind CSS utility classes for all styling.
4. Make components responsive: use sm:, md:, lg: breakpoint prefixes.
5. Include realistic placeholder content — not just "Lorem ipsum".
6. Use proper TypeScript-compatible patterns (even if writing JSX).
7. Export the component as default.
8. For icons, use inline SVG or simple Unicode — no external icon libraries.
9. Include hover/focus states with Tailwind: hover:, focus:, active:.
10. Add proper accessibility: aria labels, semantic elements, keyboard navigation.
11. For images, use placeholder divs with bg-gray-200 and aspect ratios.
12. The component should be self-contained — no external imports besides React.
"""

SYSTEM_PROMPT_VUE = """You are an expert Vue.js developer and UI/UX designer.
You generate complete Vue 3 Single File Components with Tailwind CSS.

RULES:
1. Output ONLY the .vue SFC code — no explanations, no markdown fences.
2. Use <script setup> with Composition API.
3. Use Tailwind CSS utility classes for styling.
4. Make components responsive with Tailwind breakpoints.
5. Include realistic placeholder content.
6. Use proper TypeScript-compatible patterns.
7. For icons, use inline SVG or Unicode symbols.
8. The component should be self-contained.
"""

SYSTEM_PROMPTS = {
    "html_css": SYSTEM_PROMPT_HTML,
    "html_bootstrap": SYSTEM_PROMPT_HTML,  # same base, user prompt adds Bootstrap
    "react_tailwind": SYSTEM_PROMPT_REACT,
    "vue_tailwind": SYSTEM_PROMPT_VUE,
    "svelte": SYSTEM_PROMPT_REACT,  # similar patterns
}


def _build_full_prompt(
    description: str,
    design_type: str,
    framework: str,
    color_theme: str,
) -> str:
    """Build the full user prompt with design type hints and theme.

    Uses TOON format for structured config data to save ~30% tokens.
    """
    from src.toon import encode_key_value

    # TOON-encode the design configuration (compact key-value pairs)
    config_data = {}

    dt = pencil_cfg.DESIGN_TYPES.get(design_type, {})
    if dt.get("name"):
        config_data["design_type"] = dt["name"]
    if dt.get("prompt_hint"):
        config_data["type_hint"] = dt["prompt_hint"]

    ct = pencil_cfg.COLOR_THEMES.get(color_theme, {})
    if ct.get("name"):
        config_data["color_theme"] = ct["name"]
    if ct.get("hint"):
        config_data["theme_hint"] = ct["hint"]

    config_data["framework"] = framework

    parts = []
    # TOON-encoded config block
    parts.append(f"--- design_config ---\n{encode_key_value(config_data)}")

    # Framework-specific hints (plain text — these are instructions, not data)
    if framework == "html_bootstrap":
        parts.append(
            "Use Bootstrap 5 via CDN. Include the Bootstrap CSS and JS links in <head>. "
            "Use Bootstrap classes: container, row, col, btn, card, navbar, etc."
        )
    elif framework == "react_tailwind":
        parts.append("Generate a React functional component using Tailwind CSS classes.")
    elif framework == "vue_tailwind":
        parts.append("Generate a Vue 3 SFC using <script setup> and Tailwind CSS.")
    elif framework == "svelte":
        parts.append("Generate a Svelte component.")

    # User description (main prompt)
    parts.append(f"Design description: {description}")

    return "\n\n".join(parts)


def _cache_key(prompt: str, framework: str, design_type: str, theme: str) -> str:
    raw = f"{framework}:{design_type}:{theme}:{prompt}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _get_cached(key: str) -> Optional[str]:
    cache_file = CACHE_DIR / f"{key}.txt"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")
    return None


def _save_cache(key: str, code: str) -> None:
    cache_file = CACHE_DIR / f"{key}.txt"
    cache_file.write_text(code, encoding="utf-8")
    # LRU cleanup
    files = sorted(CACHE_DIR.glob("*.txt"), key=lambda f: f.stat().st_mtime)
    while len(files) > 100:
        files[0].unlink()
        files.pop(0)


def generate_ui_code(
    description: str,
    design_type: str = "full_page",
    framework: str = "html_css",
    color_theme: str = "clean_light",
    existing_code: str = "",
    skip_cache: bool = False,
) -> tuple[str, bool]:
    """Generate UI code from a text description.

    Returns:
        Tuple of (code_string, was_cached).
    """
    full_prompt = _build_full_prompt(description, design_type, framework, color_theme)

    # Modify mode
    if existing_code:
        full_prompt += (
            f"\n\nHere is the existing code to modify/improve:\n"
            f"```\n{existing_code}\n```\n"
            f"Apply the requested changes while keeping the overall structure."
        )
        skip_cache = True

    # Check cache
    if not skip_cache:
        key = _cache_key(description, framework, design_type, color_theme)
        cached = _get_cached(key)
        if cached:
            return cached, True

    # Generate via LLM
    system = SYSTEM_PROMPTS.get(framework, SYSTEM_PROMPT_HTML)
    code = _call_gemini(system, full_prompt)

    # Clean up — strip markdown fences if LLM added them
    code = _strip_code_fences(code)

    # Cache
    if not skip_cache:
        key = _cache_key(description, framework, design_type, color_theme)
        _save_cache(key, code)

    return code, False


def _call_gemini(system: str, prompt: str) -> str:
    """Call Gemini API with system + user prompt."""
    from google import genai

    api_key = cfg.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("No Gemini API key. Set GEMINI_API_KEY in .env file.")

    client = genai.Client(api_key=api_key)
    model = cfg.GEMINI_MODEL

    result_holder: dict = {}

    def _call():
        try:
            response = client.models.generate_content(
                model=model,
                contents=f"{system}\n\n---\n\n{prompt}",
            )
            result_holder["text"] = response.text
        except Exception as e:
            result_holder["error"] = e

    thread = threading.Thread(target=_call, daemon=True)
    thread.start()
    thread.join(timeout=cfg.LLM_TIMEOUT)

    if thread.is_alive():
        raise RuntimeError(f"LLM timed out after {cfg.LLM_TIMEOUT}s.")
    if "error" in result_holder:
        raise result_holder["error"]

    text = result_holder.get("text", "")
    if not text:
        raise RuntimeError("LLM returned empty response.")

    return text


def _strip_code_fences(code: str) -> str:
    """Remove markdown code fences if present."""
    code = code.strip()
    # Remove ```html ... ``` or ```jsx ... ``` etc.
    if code.startswith("```"):
        first_newline = code.index("\n") if "\n" in code else len(code)
        code = code[first_newline + 1:]
    if code.endswith("```"):
        code = code[:-3]
    return code.strip()


# ── History ───────────────────────────────────────────────────────────

def save_to_history(
    code: str,
    prompt: str,
    design_type: str,
    framework: str,
    color_theme: str,
) -> Path:
    """Save generated code + metadata to history."""
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if c.isalnum() or c in " -_" else "" for c in prompt)[:40].strip()
    safe = safe.replace(" ", "_") or "design"
    ext = pencil_cfg.FRAMEWORKS.get(framework, {}).get("extension", ".html")
    filename = f"{timestamp}_{safe}{ext}"

    code_path = pencil_cfg.HISTORY_DIR / filename
    code_path.write_text(code, encoding="utf-8")

    meta = {
        "prompt": prompt,
        "design_type": design_type,
        "framework": framework,
        "color_theme": color_theme,
        "timestamp": timestamp,
    }
    meta_path = code_path.with_suffix(".json")
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return code_path


def list_history() -> list[dict]:
    """List all designs in history, newest first."""
    items = []
    for meta_file in sorted(pencil_cfg.HISTORY_DIR.glob("*.json"), reverse=True):
        code_file = None
        # Find matching code file
        stem = meta_file.stem
        for ext in [".html", ".jsx", ".vue", ".svelte"]:
            candidate = meta_file.with_suffix(ext)
            if candidate.exists():
                code_file = candidate
                break

        if not code_file:
            continue

        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except Exception:
            meta = {}

        items.append({
            "path": code_file,
            "filename": code_file.name,
            "prompt": meta.get("prompt", "Unknown"),
            "design_type": meta.get("design_type", ""),
            "framework": meta.get("framework", ""),
            "timestamp": meta.get("timestamp", ""),
        })
    return items


def clear_cache() -> int:
    count = 0
    for f in CACHE_DIR.glob("*.txt"):
        f.unlink()
        count += 1
    return count


def cache_stats() -> dict:
    files = list(CACHE_DIR.glob("*.txt"))
    total_bytes = sum(f.stat().st_size for f in files)
    return {"entries": len(files), "total_kb": round(total_bytes / 1024, 1)}
