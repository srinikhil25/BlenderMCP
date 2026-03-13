"""
Inspector agent.

Verifies that the Blender scene matches the ScenePlan by comparing
expected vs actual objects. Uses two strategies:
1. Primary: parse object names from the execution stdout (reliable).
2. Fallback: call get_scene_info via MCP (may fail depending on MCP response format).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Set

from src.bridge.blender_mcp_client import ExecutionResult, get_scene_info
from src.planner.geometry_planner import ScenePlan

# Infrastructure objects added by the builder (lights, camera, empties) —
# not part of the user's ScenePlan, so we exclude them from comparison.
INFRA_NAMES = frozenset({
    "Sun", "Fill", "Rim", "Camera", "CameraTarget",
})


@dataclass
class InspectionReport:
    ok: bool
    notes: str
    expected_count: int = 0
    actual_count: int = 0
    missing: List[str] = field(default_factory=list)
    extra: List[str] = field(default_factory=list)


def _parse_names_from_stdout(stdout: str) -> Set[str]:
    """
    Extract object names from the build() function's stdout.

    The generated script prints lines like:
        - ground: MESH at [0.0, 0.0, 0.0]
        - walls: MESH at [0.0, 0.0, 1.5]
    """
    names: Set[str] = set()
    for match in re.finditer(r"^\s*-\s+(.+?):\s+MESH\s+at\s+", stdout, re.MULTILINE):
        name = match.group(1).strip()
        if name and name not in INFRA_NAMES:
            names.add(name)
    return names


def _parse_names_from_scene_data(scene_data: dict) -> Set[str]:
    """Extract object names from MCP get_scene_info response (various formats)."""
    names: Set[str] = set()
    objects_list: list = []

    if isinstance(scene_data, dict):
        if "result" in scene_data and isinstance(scene_data["result"], dict):
            objects_list = scene_data["result"].get("objects", [])
        elif "objects" in scene_data:
            objects_list = scene_data.get("objects", [])

    for obj in objects_list:
        if isinstance(obj, dict):
            obj_name = obj.get("name", "")
            if obj_name and obj_name not in INFRA_NAMES:
                names.add(obj_name)
        elif isinstance(obj, str):
            if obj and obj not in INFRA_NAMES:
                names.add(obj)

    return names


class InspectorAgent:
    def inspect(self, plan: ScenePlan, exec_result: ExecutionResult) -> InspectionReport:
        """
        Inspect the Blender scene against the expected plan.

        Strategy:
        1. If execution failed, report failure immediately.
        2. Parse object names from execution stdout (most reliable).
        3. If stdout parsing fails, try MCP get_scene_info as fallback.
        """
        if not exec_result.ok:
            return InspectionReport(
                ok=False,
                notes=f"Execution failed: {exec_result.stderr}",
                expected_count=len(plan.components),
                actual_count=0,
                missing=[c.name for c in plan.components],
            )

        expected_names: Set[str] = {c.name for c in plan.components}

        # Strategy 1: Parse names from execution stdout (most reliable)
        actual_names = _parse_names_from_stdout(exec_result.stdout)

        # Strategy 2: Fallback to MCP get_scene_info if stdout gave nothing
        if not actual_names:
            try:
                scene_info = get_scene_info()
                actual_names = _parse_names_from_scene_data(scene_info.data)
            except Exception:
                pass  # MCP call failed, proceed with empty set

        missing = sorted(expected_names - actual_names)
        extra = sorted(actual_names - expected_names)

        notes_parts = []
        if missing:
            notes_parts.append(f"Missing objects: {', '.join(missing)}")
        if extra:
            notes_parts.append(f"Extra objects in scene: {', '.join(extra)}")
        if not notes_parts:
            notes_parts.append(f"All {len(expected_names)} expected objects found in scene.")

        return InspectionReport(
            ok=len(missing) == 0,
            notes="\n".join(notes_parts),
            expected_count=len(expected_names),
            actual_count=len(actual_names),
            missing=missing,
            extra=extra,
        )
