"""
Global configuration for the Local Creative Agent.

Centralizes model names and MCP endpoints for easier tuning.
"""

from dataclasses import dataclass


@dataclass
class ModelConfig:
    """Single-model setup tuned for 8GB VRAM (e.g. RTX 4060)."""
    planner_model: str = "qwen3:8b"
    inspector_model: str = "qwen3:8b"


@dataclass
class MCPConfig:
    blender_server_id: str = "blender-mcp"


model_config = ModelConfig()
mcp_config = MCPConfig()
