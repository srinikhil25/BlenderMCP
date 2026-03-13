"""
Shared core models for multi-tool operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ToolType(str, Enum):
    BLENDER = "blender"
    OBSIDIAN = "obsidian"
    KRITA = "krita"


@dataclass
class ProjectScope:
    """
    Describes the current tool + project the agent is allowed to touch.

    Examples:
    - Blender: blend_path + collection_name
    - Obsidian: vault_path + folder
    - Krita: document_path + optional layer group
    """

    tool: ToolType
    root_path: Path
    sub_scope: str | None = None  # e.g. collection, folder, layer group


