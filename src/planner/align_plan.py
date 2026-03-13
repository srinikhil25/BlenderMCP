"""
Deterministic alignment post-processor.

Runs after the LLM generates a ScenePlan and before the SceneBuilder
generates code. Fixes alignment gaps by snapping components together
based on spatial relationships.

Small models (7B) cannot compute precise floating-point coordinates.
This module compensates by:
1. Computing axis-aligned bounding boxes for each component
2. Detecting embedded components (windows in walls, eyes in head)
3. Processing bottom-up: snapping each component to its support surface
4. Moving embedded children with their parent

Example: if the LLM places a roof at z=3.5 but the wall top is at z=3.0,
this module detects the 0.5m gap and snaps the roof down to z=3.0.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from src.planner.geometry_planner import SceneComponent, ScenePlan


@dataclass
class BBox:
    """Axis-aligned bounding box."""
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float

    @property
    def z_center(self) -> float:
        return (self.z_min + self.z_max) / 2

    @property
    def width(self) -> float:
        return self.x_max - self.x_min

    @property
    def depth(self) -> float:
        return self.y_max - self.y_min

    @property
    def height(self) -> float:
        return self.z_max - self.z_min


# Maximum gap (meters) that will be auto-closed by snapping.
# Gaps larger than this are assumed intentional (separate object groups).
MAX_GAP = 3.0

# Minimum gap (meters) to trigger snapping.
# Gaps smaller than this are considered "close enough".
MIN_GAP = 0.02

# Support detection tolerance: how far above our bottom the support top
# can be and still count as "support below us" (handles minor overlaps).
SUPPORT_TOLERANCE = 0.5


def _calc_bbox(comp: SceneComponent) -> BBox:
    """
    Calculate axis-aligned bounding box for a component.

    Ignores rotation (AABB with rotation would need all 8 rotated corners).
    For most scenes, rotation doesn't significantly affect Z-extent.
    """
    x, y, z = comp.location
    sx, sy, sz = comp.scale
    params = comp.primitive_params

    if comp.primitive in ("cube",):
        # Builder adds size=1 default for cubes
        size = float(params.get("size", 1.0))
        half = size / 2
        return BBox(
            x - half * sx, x + half * sx,
            y - half * sy, y + half * sy,
            z - half * sz, z + half * sz,
        )

    elif comp.primitive == "plane":
        size = float(params.get("size", 1.0))
        half = size / 2
        return BBox(
            x - half * sx, x + half * sx,
            y - half * sy, y + half * sy,
            z, z,  # planes are flat
        )

    elif comp.primitive in ("uv_sphere", "ico_sphere"):
        r = float(params.get("radius", 1.0))
        return BBox(
            x - r * sx, x + r * sx,
            y - r * sy, y + r * sy,
            z - r * sz, z + r * sz,
        )

    elif comp.primitive == "cylinder":
        r = float(params.get("radius", 1.0))
        d = float(params.get("depth", 2.0))
        half_h = d / 2
        return BBox(
            x - r * sx, x + r * sx,
            y - r * sy, y + r * sy,
            z - half_h * sz, z + half_h * sz,
        )

    elif comp.primitive == "cone":
        r1 = float(params.get("radius1", 1.0))
        r2 = float(params.get("radius2", 0.0))
        d = float(params.get("depth", 2.0))
        max_r = max(r1, r2)
        half_h = d / 2
        return BBox(
            x - max_r * sx, x + max_r * sx,
            y - max_r * sy, y + max_r * sy,
            z - half_h * sz, z + half_h * sz,
        )

    elif comp.primitive == "torus":
        major = float(params.get("major_radius", 1.0))
        minor = float(params.get("minor_radius", 0.25))
        outer = major + minor
        return BBox(
            x - outer * sx, x + outer * sx,
            y - outer * sy, y + outer * sy,
            z - minor * sz, z + minor * sz,
        )

    else:
        # Generic fallback: treat scale as half-extents
        return BBox(
            x - sx, x + sx,
            y - sy, y + sy,
            z - sz, z + sz,
        )


def _shift_bbox_z(bbox: BBox, delta: float) -> BBox:
    """Return a new BBox shifted vertically by delta."""
    return BBox(
        bbox.x_min, bbox.x_max,
        bbox.y_min, bbox.y_max,
        bbox.z_min + delta, bbox.z_max + delta,
    )


def _xy_overlaps(a: BBox, b: BBox) -> bool:
    """
    Check if two bounding boxes are spatially related in the XY plane.

    Uses two strategies:
    1. Standard overlap with 30% margin (handles most cases)
    2. Center proximity: XY centers within the larger component's extent
       (handles cases like table legs outside the tabletop projection)
    """
    a_w = max(a.width, 0.1)
    a_d = max(a.depth, 0.1)
    b_w = max(b.width, 0.1)
    b_d = max(b.depth, 0.1)

    # Strategy 1: Overlap with proportional margin
    margin_x = max(a_w, b_w) * 0.3
    margin_y = max(a_d, b_d) * 0.3

    if (
        a.x_min - margin_x < b.x_max
        and a.x_max + margin_x > b.x_min
        and a.y_min - margin_y < b.y_max
        and a.y_max + margin_y > b.y_min
    ):
        return True

    # Strategy 2: Center proximity — XY centers within the larger extent
    ax = (a.x_min + a.x_max) / 2
    ay = (a.y_min + a.y_max) / 2
    bx = (b.x_min + b.x_max) / 2
    by = (b.y_min + b.y_max) / 2

    max_x_extent = max(a_w, b_w)
    max_y_extent = max(a_d, b_d)

    return abs(ax - bx) < max_x_extent and abs(ay - by) < max_y_extent


def _is_ground(comp: SceneComponent) -> bool:
    """Check if a component is a ground plane (should not be moved)."""
    return (
        comp.name.lower() in ("ground", "floor", "ground_plane", "floor_plane")
        or (comp.primitive == "plane" and abs(comp.location[2]) < 0.05)
    )


def _is_vertically_embedded(child: BBox, parent: BBox) -> bool:
    """
    Check if child is vertically embedded inside parent.

    A component is "embedded" if more than 50% of its height overlaps
    with another (larger) component. Examples: window in wall, eye in head.
    Embedded components should move with their parent, not be snapped independently.
    """
    z_overlap = min(child.z_max, parent.z_max) - max(child.z_min, parent.z_min)
    if z_overlap <= 0:
        return False
    child_height = max(child.height, 0.01)
    return z_overlap > child_height * 0.5


def align_plan(plan: ScenePlan) -> Tuple[ScenePlan, List[str]]:
    """
    Fix alignment gaps in a ScenePlan by snapping components together.

    Returns:
        Tuple of (aligned ScenePlan, list of adjustment log messages)

    Algorithm:
    1. Calculate bounding boxes for all components
    2. Detect embedded components (windows in walls, eyes in head)
    3. Process bottom-up: for each non-embedded component, find its
       support surface and snap to close any vertical gap
    4. Move embedded children by the same delta as their parent
    5. Clamp any component that ended up below ground to z_min=0
    """
    if len(plan.components) < 2:
        return plan, []

    log: List[str] = []

    # Step 1: Calculate bounding boxes
    bounds: Dict[str, BBox] = {}
    for comp in plan.components:
        bounds[comp.name] = _calc_bbox(comp)

    # Step 2: Detect embeddings (child inside parent)
    embedded_in: Dict[str, str] = {}  # child_name -> parent_name
    for comp in plan.components:
        if _is_ground(comp):
            continue
        b = bounds[comp.name]
        best_parent: Optional[str] = None
        best_parent_vol = float("inf")

        for other in plan.components:
            if other.name == comp.name or _is_ground(other):
                continue
            ob = bounds[other.name]

            if _is_vertically_embedded(b, ob) and _xy_overlaps(b, ob):
                # Parent must be larger than child
                parent_vol = ob.width * ob.depth * max(ob.height, 0.01)
                child_vol = b.width * b.depth * max(b.height, 0.01)
                if parent_vol > child_vol and parent_vol < best_parent_vol:
                    best_parent = other.name
                    best_parent_vol = parent_vol

        if best_parent:
            embedded_in[comp.name] = best_parent

    # Step 3: Process bottom-up — snap non-embedded components to their support
    z_deltas: Dict[str, float] = {c.name: 0.0 for c in plan.components}

    comps_sorted = sorted(plan.components, key=lambda c: bounds[c.name].z_min)

    for comp in comps_sorted:
        if _is_ground(comp) or comp.name in embedded_in:
            continue

        b = bounds[comp.name]

        # Find best support: the highest z_max below us with XY overlap
        support_top = 0.0  # default support is ground at z=0
        support_name = "ground"

        for other in comps_sorted:
            if other.name == comp.name or other.name in embedded_in:
                continue
            ob = bounds[other.name]
            # Support's top must be at or below our bottom (with tolerance)
            if ob.z_max <= b.z_min + SUPPORT_TOLERANCE and ob.z_max > support_top:
                if _xy_overlaps(b, ob):
                    support_top = ob.z_max
                    support_name = other.name

        # Calculate gap between our bottom and support top
        gap = b.z_min - support_top

        if gap > MIN_GAP and gap < MAX_GAP:
            z_deltas[comp.name] = -gap
            bounds[comp.name] = _shift_bbox_z(bounds[comp.name], -gap)
            log.append(
                f"Snapped '{comp.name}' down {gap:.2f}m "
                f"(closed gap to '{support_name}')"
            )

    # Step 4: Apply parent deltas to embedded children
    for child_name, parent_name in embedded_in.items():
        parent_delta = z_deltas.get(parent_name, 0.0)
        if abs(parent_delta) > 0.001:
            z_deltas[child_name] = parent_delta

            # Check if child ends up below ground after parent move
            child_comp = next(c for c in plan.components if c.name == child_name)
            child_bbox = bounds[child_name]
            new_z_min = child_bbox.z_min + parent_delta

            if new_z_min < -0.01:
                # Clamp to ground level
                extra = -new_z_min
                z_deltas[child_name] = parent_delta + extra
                log.append(
                    f"Moved '{child_name}' with parent '{parent_name}' "
                    f"and clamped to ground"
                )
            else:
                log.append(
                    f"Moved '{child_name}' with parent '{parent_name}' "
                    f"(delta {parent_delta:.2f}m)"
                )

    # Step 5: Build new plan with adjusted locations
    new_components: List[SceneComponent] = []
    for comp in plan.components:
        delta = z_deltas[comp.name]
        if abs(delta) > 0.001:
            new_loc = (comp.location[0], comp.location[1], comp.location[2] + delta)
        else:
            new_loc = comp.location

        new_components.append(SceneComponent(
            name=comp.name,
            primitive=comp.primitive,
            location=new_loc,
            rotation=comp.rotation,
            scale=comp.scale,
            primitive_params=dict(comp.primitive_params),
            material=comp.material,
            modifiers=list(comp.modifiers),
            parent=comp.parent,
        ))

    aligned_plan = ScenePlan(
        name=plan.name,
        description=plan.description,
        unit_scale=plan.unit_scale,
        components=new_components,
    )

    return aligned_plan, log
