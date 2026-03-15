"""Friendly error messages for common failure modes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class FriendlyError:
    title: str
    message: str
    suggestion: str


# (pattern_substring, FriendlyError) — checked in order, first match wins
_ERROR_MAP: List[Tuple[str, FriendlyError]] = [
    # Connection / Blender not running
    ("connection refused", FriendlyError(
        "Blender Not Connected",
        "Cannot connect to Blender.",
        "Make sure Blender is open and the blender-mcp addon is running.",
    )),
    ("winError 2", FriendlyError(
        "MCP Server Not Found",
        "The blender-mcp server could not be started.",
        "Run: pip install blender-mcp   (or: uvx blender-mcp)",
    )),
    ("no such file", FriendlyError(
        "MCP Server Not Found",
        "The blender-mcp command was not found.",
        "Make sure blender-mcp is installed: pip install blender-mcp",
    )),

    # Gemini API
    ("gemini api key not set", FriendlyError(
        "API Key Missing",
        "Gemini API key is not configured.",
        "Set GEMINI_API_KEY in your .env file or environment variables.\n"
        "Get a free key at: https://aistudio.google.com/apikey",
    )),
    ("429", FriendlyError(
        "Rate Limit Exceeded",
        "Gemini API daily quota exhausted.",
        "Wait for quota reset (midnight Pacific) or switch to Ollama provider.",
    )),
    ("quota", FriendlyError(
        "Rate Limit Exceeded",
        "Gemini API quota exceeded.",
        "Wait for quota reset or switch to Ollama in the provider dropdown.",
    )),

    # Ollama / GPU
    ("cuda_host buffer", FriendlyError(
        "GPU Memory Error",
        "The model is too large for your GPU.",
        "Switch to Gemini (free, cloud) or use a smaller model like qwen2.5-coder:7b.",
    )),
    ("out of memory", FriendlyError(
        "GPU Memory Error",
        "GPU ran out of memory.",
        "Switch to Gemini provider or reduce model size in Settings.",
    )),
    ("model '", FriendlyError(
        "Model Not Found",
        "The Ollama model is not downloaded.",
        "Run: ollama pull <model-name>   or switch to Gemini provider.",
    )),
    ("status code: 404", FriendlyError(
        "Model Not Found",
        "Ollama model not available.",
        "Run: ollama pull qwen2.5-coder:7b",
    )),

    # Safety
    ("blocked import", FriendlyError(
        "Safety Violation",
        "The generated code used a blocked import.",
        "Try rephrasing your prompt. Avoid mentioning files, system, or network.",
    )),
    ("blocked call", FriendlyError(
        "Safety Violation",
        "The generated code used a blocked function.",
        "Try rephrasing your prompt with different wording.",
    )),

    # Blender execution
    ("attributeerror", FriendlyError(
        "Blender API Error",
        "The generated code used an incorrect Blender API call.",
        "This will auto-retry. If it persists, try a simpler prompt.",
    )),
    ("typeerror", FriendlyError(
        "Blender Code Error",
        "The generated code had a type error.",
        "This will auto-retry with the error feedback.",
    )),

    # Timeout
    ("timeout", FriendlyError(
        "Timeout",
        "The operation took too long.",
        "Try a simpler prompt or check your network/Ollama server.",
    )),
]


def get_friendly_error(raw_error: str) -> FriendlyError | None:
    """Match a raw error string to a friendly message. Returns None if no match."""
    lower = raw_error.lower()
    for pattern, friendly in _ERROR_MAP:
        if pattern.lower() in lower:
            return friendly
    return None
