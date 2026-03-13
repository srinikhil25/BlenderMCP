"""AST-based safety validator for LLM-generated bpy code."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import List

from src.config import (
    ALLOWED_IMPORTS,
    ALLOWED_BPY_OPS,
    BLOCKED_BPY_OPS_PREFIXES,
    BLOCKED_BUILTINS,
    BLOCKED_ATTRIBUTES,
)


@dataclass
class ValidationResult:
    ok: bool
    violations: List[str] = field(default_factory=list)


class _SafetyVisitor(ast.NodeVisitor):
    """Walks the AST and collects safety violations."""

    def __init__(self) -> None:
        self.violations: List[str] = []

    def _add(self, msg: str) -> None:
        self.violations.append(msg)

    # --- Import checks ---

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root not in ALLOWED_IMPORTS:
                self._add(f"Blocked import: `{alias.name}`")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            root = node.module.split(".")[0]
            if root not in ALLOWED_IMPORTS:
                self._add(f"Blocked import: `from {node.module}`")
        self.generic_visit(node)

    # --- Function call checks ---

    def visit_Call(self, node: ast.Call) -> None:
        name = _get_call_name(node)
        if name:
            # Check blocked builtins
            bare = name.split(".")[-1]
            if bare in BLOCKED_BUILTINS:
                self._add(f"Blocked call: `{name}()`")

            # Check bpy.ops submodule restrictions
            if name.startswith("bpy.ops."):
                parts = name.split(".")
                if len(parts) >= 3:
                    submod = parts[2]
                    full_prefix = f"bpy.ops.{submod}"
                    if full_prefix in BLOCKED_BPY_OPS_PREFIXES:
                        self._add(f"Blocked bpy.ops call: `{name}()`")
                    elif submod not in ALLOWED_BPY_OPS:
                        self._add(f"Disallowed bpy.ops module: `{full_prefix}`")

            # Check blocked attribute roots in calls (os.system, etc.)
            root = name.split(".")[0]
            if root in BLOCKED_ATTRIBUTES:
                self._add(f"Blocked call: `{name}()`")

        self.generic_visit(node)

    # --- Attribute access checks ---

    def visit_Attribute(self, node: ast.Attribute) -> None:
        chain = _get_attr_chain(node)
        if chain:
            root = chain.split(".")[0]
            if root in BLOCKED_ATTRIBUTES:
                self._add(f"Blocked attribute access: `{chain}`")

            # Block bpy.app, bpy.utils, bpy.path
            if chain.startswith("bpy.") and not chain.startswith("bpy.ops."):
                second = chain.split(".")[1] if "." in chain[4:] else ""
                if second in ("app", "utils", "path"):
                    self._add(f"Blocked bpy access: `{chain}`")

        self.generic_visit(node)


def _get_call_name(node: ast.Call) -> str | None:
    """Extract dotted name from a Call node (e.g. 'bpy.ops.mesh.primitive_cube_add')."""
    return _get_attr_chain(node.func) if isinstance(node.func, ast.Attribute) else (
        node.func.id if isinstance(node.func, ast.Name) else None
    )


def _get_attr_chain(node: ast.expr) -> str | None:
    """Build dotted name from nested Attribute nodes."""
    parts: List[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    return None


def validate_code(code: str) -> ValidationResult:
    """Validate LLM-generated code against safety rules.

    Returns ValidationResult with ok=True if safe, or a list of violations.
    """
    if not code or not code.strip():
        return ValidationResult(ok=False, violations=["Empty code"])

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return ValidationResult(ok=False, violations=[f"Syntax error: {e}"])

    visitor = _SafetyVisitor()
    visitor.visit(tree)

    return ValidationResult(
        ok=len(visitor.violations) == 0,
        violations=visitor.violations,
    )
