"""
Scene plan data models.

Defines the structured representation of a 3D scene that the planner
produces and the SceneBuilder consumes. Each ScenePlan contains a list
of SceneComponents, where each component maps to a single Blender
primitive with transforms, material, and optional modifiers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


SUPPORTED_PRIMITIVES = frozenset({
    "cube",
    "uv_sphere",
    "ico_sphere",
    "cylinder",
    "cone",
    "plane",
    "torus",
    "grid",
    "circle",
    "monkey",
})

SUPPORTED_MODIFIERS = frozenset({
    "bevel",
    "solidify",
    "subdivision",
    "array",
    "mirror",
    "boolean",
    "wireframe",
    "decimate",
})


@dataclass
class MaterialSpec:
    """Principled BSDF material specification."""
    color: Tuple[float, float, float] = (0.8, 0.8, 0.8)
    roughness: float = 0.5
    metallic: float = 0.0
    alpha: float = 1.0
    procedural_bump: bool = False  # Add noise-based bump for more realistic surfaces


@dataclass
class ModifierSpec:
    """A single modifier to apply to a component."""
    type: str
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SceneComponent:
    """A single object in the scene plan."""
    name: str
    primitive: str

    # Transform
    location: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0)  # degrees
    scale: Tuple[float, float, float] = (1.0, 1.0, 1.0)

    # Primitive-specific parameters (passed to bpy.ops.mesh.primitive_*_add)
    primitive_params: Dict[str, Any] = field(default_factory=dict)

    # Material
    material: Optional[MaterialSpec] = None

    # Modifiers (applied in order)
    modifiers: List[ModifierSpec] = field(default_factory=list)

    # Parenting
    parent: Optional[str] = None


@dataclass
class ScenePlan:
    """Complete scene plan with all components."""
    name: str
    description: str
    unit_scale: float = 1.0
    components: List[SceneComponent] = field(default_factory=list)
