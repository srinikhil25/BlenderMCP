"""
Global configuration for the Local Creative Agent.

Centralizes model names and MCP endpoints for easier tuning.
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()  # loads .env from project root


@dataclass
class ModelConfig:
    """Single-model setup tuned for 8GB VRAM (e.g. RTX 4060)."""
    planner_model: str = "qwen2.5-coder:7b"
    inspector_model: str = "qwen2.5-coder:7b"


@dataclass
class MCPConfig:
    blender_server_id: str = "blender-mcp"


model_config = ModelConfig()
mcp_config = MCPConfig()

# --- Load persistent user settings (from ~/.blendermcp/settings.json) ---
try:
    from src.settings import load_settings as _load_settings, DEFAULTS as _DEFAULTS
    _saved = _load_settings()
except Exception:
    _saved = {}
    _DEFAULTS = {}

# --- LLM Provider ---
# "gemini" = Google Gemini API (free, cloud, best quality)
# "ollama" = Local Ollama (offline, needs GPU)
LLM_PROVIDER = _saved.get("llm_provider", "gemini")

# --- Gemini settings ---
GEMINI_API_KEY = ""  # leave empty to use env var GEMINI_API_KEY
GEMINI_MODEL = _saved.get("gemini_model", "gemini-2.5-flash")

# --- Ollama settings (local fallback) ---
OLLAMA_MODEL = _saved.get("ollama_model", "qwen2.5-coder:7b")
OLLAMA_NUM_CTX = _saved.get("ollama_num_ctx", 8192)

# Retry settings
MAX_RETRIES = _saved.get("max_retries", 2)

# Blender MCP command
BLENDER_MCP_CMD = "cmd"
BLENDER_MCP_ARGS = ["/c", "uvx", "blender-mcp"]

# Safety: allowed imports in LLM-generated code
ALLOWED_IMPORTS = frozenset({
    "bpy", "bmesh", "math", "mathutils", "random", "colorsys",
})

# Safety: allowed bpy.ops submodules
ALLOWED_BPY_OPS = frozenset({
    "mesh", "object", "curve", "surface",
})

# Safety: blocked bpy.ops submodules
BLOCKED_BPY_OPS_PREFIXES = frozenset({
    "bpy.ops.wm", "bpy.ops.render", "bpy.ops.export_scene",
    "bpy.ops.import_scene", "bpy.ops.file", "bpy.ops.screen",
    "bpy.ops.preferences", "bpy.ops.ed",
})

# Safety: blocked function calls
BLOCKED_BUILTINS = frozenset({
    "eval", "exec", "compile", "__import__", "open", "input",
    "exit", "quit", "globals", "locals", "breakpoint",
})

# Safety: blocked attribute access roots
BLOCKED_ATTRIBUTES = frozenset({
    "os", "sys", "subprocess", "shutil", "pathlib", "socket",
    "http", "urllib", "ctypes", "importlib", "pickle",
})
