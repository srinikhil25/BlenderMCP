"""
Core request runner: routes a prompt + project scope to the appropriate tool adapter.
"""

from __future__ import annotations

from typing import Any, Dict

from src.core.models import ProjectScope, ToolType
from src.loops.plan_build_inspect import plan_build_inspect


def run_request(prompt: str, scope: ProjectScope) -> Dict[str, Any]:
    """
    Entry point for external callers (CLI, HTTP API, UI).

    For now, only the Blender tool is implemented. Obsidian and Krita are
    reserved for future extensions.
    """
    if scope.tool is ToolType.BLENDER:
        result = plan_build_inspect(prompt)
        return {
            "tool": scope.tool.value,
            "scope": {
                "root_path": str(scope.root_path),
                "sub_scope": scope.sub_scope,
            },
            "result": {
                "plan_name": result["plan"].name,
                "plan_description": result["plan"].description,
                "plan_component_count": len(result["plan"].components),
                "verification": {
                    "ok": result["verification"].ok,
                    "notes": result["verification"].notes,
                },
                "execution": {
                    "ok": result["execution"].ok,
                    "stdout": result["execution"].stdout,
                    "stderr": result["execution"].stderr,
                },
                "inspection": {
                    "ok": result["inspection"].ok,
                    "notes": result["inspection"].notes,
                    "expected": result["inspection"].expected_count,
                    "actual": result["inspection"].actual_count,
                    "missing": result["inspection"].missing,
                },
                "script_preview": result.get("script_preview", "")[:2000],
            },
        }

    raise NotImplementedError(f"Tool {scope.tool.value!r} is not implemented yet.")
