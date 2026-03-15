"""Prompt history — persistent across sessions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

MAX_HISTORY = 50
_HISTORY_DIR = Path.home() / ".blendermcp"
_HISTORY_FILE = _HISTORY_DIR / "history.json"


def load_history() -> List[str]:
    """Load prompt history from disk. Returns empty list if none."""
    try:
        if _HISTORY_FILE.exists():
            data = json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data[-MAX_HISTORY:]
    except Exception:
        pass
    return []


def save_prompt(prompt: str, history: List[str] | None = None) -> List[str]:
    """Append a prompt to history and persist. Returns updated history."""
    if history is None:
        history = load_history()

    # Don't duplicate consecutive entries
    if history and history[-1] == prompt:
        return history

    history.append(prompt)
    history = history[-MAX_HISTORY:]

    try:
        _HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        _HISTORY_FILE.write_text(
            json.dumps(history, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass

    return history
