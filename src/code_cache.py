"""Prompt-to-code cache — saves LLM API calls for identical prompts."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

import src.config as cfg

_CACHE_DIR = Path.home() / ".blendermcp" / "cache"
_MAX_ENTRIES = 200


def _cache_key(prompt: str) -> str:
    """SHA-256 hash of prompt + provider + model."""
    provider = cfg.LLM_PROVIDER
    model = cfg.GEMINI_MODEL if provider == "gemini" else cfg.OLLAMA_MODEL
    raw = f"{provider}:{model}:{prompt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_path(key: str) -> Path:
    return _CACHE_DIR / f"{key}.json"


def get_cached(prompt: str) -> Optional[str]:
    """Return cached bpy code for this prompt, or None if not cached."""
    try:
        path = _cache_path(_cache_key(prompt))
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("code")
    except Exception:
        return None


def save_to_cache(prompt: str, code: str) -> None:
    """Save generated code to cache."""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        key = _cache_key(prompt)
        data = {
            "prompt": prompt,
            "provider": cfg.LLM_PROVIDER,
            "model": cfg.GEMINI_MODEL if cfg.LLM_PROVIDER == "gemini" else cfg.OLLAMA_MODEL,
            "code": code,
            "timestamp": time.time(),
        }
        _cache_path(key).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        _enforce_max_entries()
    except Exception:
        pass


def _enforce_max_entries() -> None:
    """Delete oldest entries if cache exceeds max size."""
    try:
        entries = sorted(_CACHE_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
        while len(entries) > _MAX_ENTRIES:
            entries.pop(0).unlink(missing_ok=True)
    except Exception:
        pass


def clear_cache() -> int:
    """Clear all cached entries. Returns count of items removed."""
    count = 0
    try:
        for f in _CACHE_DIR.glob("*.json"):
            f.unlink(missing_ok=True)
            count += 1
    except Exception:
        pass
    return count


def cache_stats() -> Dict[str, Any]:
    """Return cache statistics."""
    count = 0
    size_bytes = 0
    try:
        for f in _CACHE_DIR.glob("*.json"):
            count += 1
            size_bytes += f.stat().st_size
    except Exception:
        pass
    return {"count": count, "size_mb": round(size_bytes / (1024 * 1024), 2)}
