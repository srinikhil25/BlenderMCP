"""Image generation engine for KritaMCP.

Primary: Gemini AI image generation (text → image)
Secondary: LLM-generated Python PIL code for procedural art
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import threading
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

import src.config as cfg
from src.krita import config as krita_cfg
from src.krita.config import STYLE_PRESETS

# ── Cache directory ──────────────────────────────────────────────────
CACHE_DIR = krita_cfg.KRITA_DIR / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _build_styled_prompt(prompt: str, style: str) -> str:
    """Enhance the user prompt with style-specific suffixes."""
    preset = STYLE_PRESETS.get(style, STYLE_PRESETS["none"])
    suffix = preset.get("suffix", "")

    if suffix:
        return f"{prompt}. Style: {suffix}"
    return prompt


def _cache_key(prompt: str, style: str, model: str) -> str:
    """Generate a cache key for the prompt + style + model combination."""
    raw = f"{model}:{style}:{prompt}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _get_cached_image(key: str) -> Optional[bytes]:
    """Check if we have a cached image for this prompt."""
    cache_file = CACHE_DIR / f"{key}.png"
    if cache_file.exists():
        return cache_file.read_bytes()
    return None


def _save_cached_image(key: str, image_data: bytes) -> None:
    """Save generated image to cache."""
    cache_file = CACHE_DIR / f"{key}.png"
    cache_file.write_bytes(image_data)

    # LRU cleanup — keep max 100 cached images
    cache_files = sorted(CACHE_DIR.glob("*.png"), key=lambda f: f.stat().st_mtime)
    while len(cache_files) > 100:
        cache_files[0].unlink()
        cache_files.pop(0)


# ── Gemini Image Generation ─────────────────────────────────────────

def generate_image(
    prompt: str,
    style: str = "photorealistic",
    model: str = "",
    skip_cache: bool = False,
) -> tuple[bytes, str, bool]:
    """Generate an image from a text prompt using Gemini.

    Returns:
        Tuple of (image_bytes, mime_type, was_cached).
    """
    if not model:
        model = krita_cfg.IMAGE_MODEL

    styled_prompt = _build_styled_prompt(prompt, style)

    # Check cache first
    if not skip_cache:
        key = _cache_key(prompt, style, model)
        cached = _get_cached_image(key)
        if cached:
            return cached, "image/png", True

    # Call Gemini API
    image_data, mime_type = _generate_gemini_image(styled_prompt, model)

    # Cache the result
    if not skip_cache:
        key = _cache_key(prompt, style, model)
        _save_cached_image(key, image_data)

    return image_data, mime_type, False


def _generate_gemini_image(prompt: str, model: str) -> tuple[bytes, str]:
    """Call Gemini API to generate an image.

    Returns:
        Tuple of (image_bytes, mime_type).
    """
    from google import genai

    api_key = cfg.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "No Gemini API key configured. Set GEMINI_API_KEY in your .env file."
        )

    client = genai.Client(api_key=api_key)

    # Thread-based timeout (same pattern as Blender/Obsidian LLM)
    result_holder: dict = {}

    def _call():
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                ),
            )
            result_holder["response"] = response
        except Exception as e:
            result_holder["error"] = e

    thread = threading.Thread(target=_call, daemon=True)
    thread.start()
    thread.join(timeout=cfg.LLM_TIMEOUT)

    if thread.is_alive():
        raise RuntimeError(
            f"Image generation timed out after {cfg.LLM_TIMEOUT}s. "
            "Try a simpler prompt or check your connection."
        )

    if "error" in result_holder:
        raise result_holder["error"]

    response = result_holder.get("response")
    if not response or not response.candidates:
        raise RuntimeError("Gemini returned no response. The prompt may have been blocked.")

    # Extract image from response parts
    image_data = None
    mime_type = "image/png"
    text_response = ""

    for part in response.candidates[0].content.parts:
        if hasattr(part, "inline_data") and part.inline_data:
            image_data = part.inline_data.data
            mime_type = part.inline_data.mime_type or "image/png"
        elif hasattr(part, "text") and part.text:
            text_response = part.text

    if not image_data:
        msg = "Gemini did not return an image."
        if text_response:
            msg += f" Response: {text_response[:200]}"
        raise RuntimeError(msg)

    # Convert to PNG if needed (Gemini might return JPEG)
    if mime_type != "image/png":
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(image_data))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            image_data = buf.getvalue()
            mime_type = "image/png"
        except ImportError:
            pass  # Keep original format if PIL not available

    return image_data, mime_type


# ── Image Editing / Variation ────────────────────────────────────────

def edit_image(
    original_image: bytes,
    edit_prompt: str,
    style: str = "none",
    model: str = "",
) -> tuple[bytes, str, bool]:
    """Edit an existing image based on a text description.

    Uses Gemini's multimodal input: image + text → new image.

    Returns:
        Tuple of (image_bytes, mime_type, was_cached=False).
    """
    if not model:
        model = krita_cfg.IMAGE_MODEL

    styled_prompt = _build_styled_prompt(edit_prompt, style)

    from google import genai

    api_key = cfg.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("No Gemini API key configured.")

    client = genai.Client(api_key=api_key)

    # Build multimodal content: image + text instruction
    image_part = genai.types.Part(
        inline_data=genai.types.Blob(
            mime_type="image/png",
            data=original_image,
        )
    )
    text_part = genai.types.Part(text=f"Edit this image: {styled_prompt}")

    result_holder: dict = {}

    def _call():
        try:
            response = client.models.generate_content(
                model=model,
                contents=[image_part, text_part],
                config=genai.types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"],
                ),
            )
            result_holder["response"] = response
        except Exception as e:
            result_holder["error"] = e

    thread = threading.Thread(target=_call, daemon=True)
    thread.start()
    thread.join(timeout=cfg.LLM_TIMEOUT)

    if thread.is_alive():
        raise RuntimeError(f"Image edit timed out after {cfg.LLM_TIMEOUT}s.")
    if "error" in result_holder:
        raise result_holder["error"]

    response = result_holder.get("response")
    if not response or not response.candidates:
        raise RuntimeError("Gemini returned no response for edit.")

    # Extract image
    for part in response.candidates[0].content.parts:
        if hasattr(part, "inline_data") and part.inline_data:
            data = part.inline_data.data
            mime = part.inline_data.mime_type or "image/png"
            # Convert to PNG
            if mime != "image/png":
                try:
                    from PIL import Image
                    img = Image.open(io.BytesIO(data))
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    data = buf.getvalue()
                except ImportError:
                    pass
            return data, "image/png", False

    raise RuntimeError("Gemini did not return an edited image.")


# ── History / Metadata ───────────────────────────────────────────────

def save_to_history(
    image_data: bytes,
    prompt: str,
    style: str,
    model: str,
    filename: str = "",
) -> Path:
    """Save generated image + metadata to history folder.

    Returns:
        Path to the saved image file.
    """
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    if not filename:
        # Create a safe filename from prompt
        safe = "".join(c if c.isalnum() or c in " -_" else "" for c in prompt)[:50].strip()
        safe = safe.replace(" ", "_") or "image"
        filename = f"{timestamp}_{safe}.png"

    img_path = krita_cfg.HISTORY_DIR / filename
    img_path.write_bytes(image_data)

    # Save metadata alongside
    if krita_cfg.SAVE_PROMPT_METADATA:
        meta = {
            "prompt": prompt,
            "style": style,
            "model": model,
            "timestamp": timestamp,
            "size_bytes": len(image_data),
        }
        meta_path = img_path.with_suffix(".json")
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return img_path


def list_history() -> list[dict]:
    """List all images in history, newest first."""
    items = []
    for png_file in sorted(krita_cfg.HISTORY_DIR.glob("*.png"), reverse=True):
        meta_file = png_file.with_suffix(".json")
        meta = {}
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        items.append({
            "path": png_file,
            "filename": png_file.name,
            "prompt": meta.get("prompt", "Unknown"),
            "style": meta.get("style", ""),
            "timestamp": meta.get("timestamp", ""),
            "size_bytes": meta.get("size_bytes", png_file.stat().st_size),
        })
    return items


def clear_cache() -> int:
    """Clear the image cache. Returns number of files removed."""
    count = 0
    for f in CACHE_DIR.glob("*.png"):
        f.unlink()
        count += 1
    return count


def cache_stats() -> dict:
    """Get cache statistics."""
    files = list(CACHE_DIR.glob("*.png"))
    total_bytes = sum(f.stat().st_size for f in files)
    return {
        "entries": len(files),
        "total_mb": round(total_bytes / (1024 * 1024), 2),
    }
