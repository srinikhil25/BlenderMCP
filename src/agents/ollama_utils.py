"""
Shared helpers for using Ollama-backed models through smolagents/LiteLLM.
"""

from __future__ import annotations

from typing import Any, Dict, List


def ollama_model_id(name: str) -> str:
    """LiteLLM expects an `ollama/` prefix for Ollama models."""
    return name if name.startswith("ollama/") else f"ollama/{name}"


def text_block_messages(system: str, user: str) -> List[Dict[str, Any]]:
    """
    Build messages compatible with smolagents when flatten_messages_as_text=True.
    """
    return [
        {"role": "system", "content": [{"type": "text", "text": system}]},
        {"role": "user", "content": [{"type": "text", "text": user}]},
    ]


def extract_text_content(response: Any) -> str:
    """
    smolagents model.generate() returns a ChatMessage with `.content`.
    Be defensive and coerce into a string.
    """
    raw = getattr(response, "content", response)
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    return str(raw)
