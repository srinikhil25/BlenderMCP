"""
Global configuration for the Local Creative Agent.

Centralizes model names and MCP endpoints for easier tuning.
"""

from dataclasses import dataclass


@dataclass
class ModelConfig:
    """Single-model setup tuned for 8GB VRAM (e.g. RTX 4060)."""
    planner_model: str = "qwen2.5-coder:14b"
    inspector_model: str = "qwen2.5-coder:14b"


@dataclass
class MCPConfig:
    blender_server_id: str = "blender-mcp"


model_config = ModelConfig()
mcp_config = MCPConfig()

# --- GUI pipeline settings ---
# For 8GB VRAM: "qwen2.5-coder:14b" (best code quality) or "qwen3:14b" (best reasoning)
# For 16GB+ VRAM: "qwen3:32b" (best overall)
# Fallback for low VRAM: "qwen3:8b"
OLLAMA_MODEL = "qwen2.5-coder:14b"
OLLAMA_NUM_CTX = 12288  # larger context for complex scenes

# Retry settings
MAX_RETRIES = 2  # retries after initial attempt (3 total)

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
