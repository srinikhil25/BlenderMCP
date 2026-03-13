"""
Deterministic bpy script generator.

Converts a ScenePlan into a Blender Python script string that uses
bpy.ops.mesh.primitive_*_add for each component. No LLM is involved.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

from src.planner.geometry_planner import (
    ScenePlan,
    SceneComponent,
    ModifierSpec,
)

PRIMITIVE_OPS = {
    "cube": "bpy.ops.mesh.primitive_cube_add",
    "uv_sphere": "bpy.ops.mesh.primitive_uv_sphere_add",
    "ico_sphere": "bpy.ops.mesh.primitive_ico_sphere_add",
    "cylinder": "bpy.ops.mesh.primitive_cylinder_add",
    "cone": "bpy.ops.mesh.primitive_cone_add",
    "plane": "bpy.ops.mesh.primitive_plane_add",
    "torus": "bpy.ops.mesh.primitive_torus_add",
    "grid": "bpy.ops.mesh.primitive_grid_add",
    "circle": "bpy.ops.mesh.primitive_circle_add",
    "monkey": "bpy.ops.mesh.primitive_monkey_add",
}

# Primitives that should get smooth shading by default
SMOOTH_SHADING_PRIMITIVES = frozenset({
    "uv_sphere", "ico_sphere", "cylinder", "cone", "torus",
})

MODIFIER_TYPES = {
    "bevel": "BEVEL",
    "solidify": "SOLIDIFY",
    "subdivision": "SUBSURF",
    "array": "ARRAY",
    "mirror": "MIRROR",
    "boolean": "BOOLEAN",
    "wireframe": "WIREFRAME",
    "decimate": "DECIMATE",
}


def build_script(plan: ScenePlan) -> str:
    """Convert a ScenePlan into a complete bpy script string."""
    lines: List[str] = []

    lines.append("import bpy")
    lines.append("import math")
    lines.append("import mathutils")
    lines.append("")

    # --- Helper: cleanup ---
    lines.append("def cleanup_scene():")
    lines.append("    for name in ['Cube', 'Light', 'Camera']:")
    lines.append("        obj = bpy.data.objects.get(name)")
    lines.append("        if obj:")
    lines.append("            bpy.data.objects.remove(obj, do_unlink=True)")
    lines.append("")

    # --- Helper: material ---
    lines.append("def create_material(name, color, roughness=0.5, metallic=0.0, alpha=1.0):")
    lines.append("    mat = bpy.data.materials.new(name=name)")
    lines.append("    mat.use_nodes = True")
    lines.append("    bsdf = mat.node_tree.nodes.get('Principled BSDF')")
    lines.append("    if bsdf:")
    lines.append("        bsdf.inputs['Base Color'].default_value = (*color, alpha)")
    lines.append("        bsdf.inputs['Roughness'].default_value = roughness")
    lines.append("        bsdf.inputs['Metallic'].default_value = metallic")
    lines.append("    return mat")
    lines.append("")
    lines.append("def create_material_with_bump(name, color, roughness=0.5, metallic=0.0, alpha=1.0):")
    lines.append("    mat = create_material(name, color, roughness, metallic, alpha)")
    lines.append("    nodes = mat.node_tree.nodes")
    lines.append("    links = mat.node_tree.links")
    lines.append("    bsdf = nodes.get('Principled BSDF')")
    lines.append("    if not bsdf:")
    lines.append("        return mat")
    lines.append("    noise = nodes.new('ShaderNodeTexNoise')")
    lines.append("    noise.inputs['Scale'].default_value = 5.0")
    lines.append("    noise.location = (bsdf.location.x - 280, bsdf.location.y)")
    lines.append("    bump = nodes.new('ShaderNodeBump')")
    lines.append("    bump.inputs['Strength'].default_value = 0.08")
    lines.append("    bump.inputs['Distance'].default_value = 0.02")
    lines.append("    bump.location = (bsdf.location.x - 140, bsdf.location.y)")
    lines.append("    links.new(noise.outputs['Fac'], bump.inputs['Height'])")
    lines.append("    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])")
    lines.append("    return mat")
    lines.append("")

    # --- Helper: sanity check ---
    lines.append("def sanity_check(obj, expected_name):")
    lines.append("    if obj is None:")
    lines.append("        raise ValueError(f'Failed to create object: {expected_name}')")
    lines.append("    if obj.type == 'MESH' and obj.dimensions.length < 1e-6:")
    lines.append("        print(f'Warning: {expected_name} has near-zero dimensions')")
    lines.append("")

    # --- Main build ---
    lines.append("def build():")
    lines.append("    try:")
    lines.append(f"        # Scene: {_safe(plan.name)}")
    lines.append(f"        # {_safe(plan.description)}")
    lines.append("")
    lines.append("        cleanup_scene()")
    lines.append(f"        bpy.context.scene.unit_settings.scale_length = {plan.unit_scale}")
    lines.append("")
    lines.append("        created_objects = {}")
    lines.append("")

    for comp in plan.components:
        lines.extend(_build_component(comp))
        lines.append("")

    # Parenting pass
    has_parents = any(c.parent for c in plan.components)
    if has_parents:
        lines.append("        # Parenting")
        for comp in plan.components:
            if comp.parent:
                p = _safe(comp.parent)
                n = _safe(comp.name)
                lines.append(f"        if '{p}' in created_objects and '{n}' in created_objects:")
                lines.append(f"            created_objects['{n}'].parent = created_objects['{p}']")
        lines.append("")

    lines.append(f"        print(f'Created {{len(created_objects)}} objects')")
    lines.append("        for name, obj in created_objects.items():")
    lines.append("            print(f'  - {name}: {obj.type} at {list(obj.location)}')")
    lines.append("")
    lines.extend(_build_lighting_and_camera())
    lines.append("")
    lines.extend(_build_world_environment())
    lines.append("")
    lines.extend(_build_render_settings())
    lines.append("")

    # Shadow catcher for ground/floor planes
    lines.extend(_build_shadow_catchers(plan))
    lines.append("")

    # Frame the viewport so the user sees the scene
    lines.extend(_build_viewport_framing())
    lines.append("")

    lines.append("    except Exception as e:")
    lines.append("        print(f'Error building scene: {e}')")
    lines.append("        raise")
    lines.append("")
    lines.append("")
    lines.append("build()")

    return "\n".join(lines)


def _safe(s: str) -> str:
    """Escape a string for safe embedding in generated code."""
    return s.replace("'", "\\'").replace("\n", " ")


def _fmt_tuple(t: tuple) -> str:
    """Format a tuple for embedding in generated code."""
    return f"({', '.join(repr(v) for v in t)})"


def _build_component(comp: SceneComponent) -> List[str]:
    """Generate lines for creating one component."""
    lines: List[str] = []
    ind = "        "
    name = _safe(comp.name)

    lines.append(f"{ind}# --- {name} ---")

    # Build the primitive_add call
    op = PRIMITIVE_OPS.get(comp.primitive, PRIMITIVE_OPS["cube"])
    params: Dict[str, str] = {}

    # Location
    params["location"] = _fmt_tuple(comp.location)

    # Rotation (degrees -> radians)
    rot_rad = tuple(round(math.radians(d), 6) for d in comp.rotation)
    if any(r != 0 for r in rot_rad):
        params["rotation"] = _fmt_tuple(rot_rad)

    # Default size=1 for cubes and planes so scale maps directly to meters
    if comp.primitive in ("cube", "plane") and "size" not in comp.primitive_params:
        params["size"] = "1"

    # Primitive-specific params
    for k, v in comp.primitive_params.items():
        if isinstance(v, (list, tuple)):
            params[k] = _fmt_tuple(tuple(v))
        else:
            params[k] = repr(v)

    param_str = ", ".join(f"{k}={v}" for k, v in params.items())
    lines.append(f"{ind}{op}({param_str})")
    lines.append(f"{ind}obj = bpy.context.active_object")
    lines.append(f"{ind}obj.name = '{name}'")

    # Smooth shading for curved primitives
    if comp.primitive in SMOOTH_SHADING_PRIMITIVES:
        lines.append(f"{ind}bpy.ops.object.shade_smooth()")

    # Scale
    if comp.scale != (1.0, 1.0, 1.0):
        lines.append(f"{ind}obj.scale = {_fmt_tuple(comp.scale)}")

    # Material
    if comp.material:
        mat = comp.material
        mat_name = f"mat_{name}"
        color_t = _fmt_tuple(mat.color)
        use_bump = getattr(mat, "procedural_bump", False)
        if use_bump:
            lines.append(
                f"{ind}mat = create_material_with_bump('{mat_name}', {color_t}, "
                f"roughness={mat.roughness}, metallic={mat.metallic})"
            )
        else:
            lines.append(
                f"{ind}mat = create_material('{mat_name}', {color_t}, "
                f"roughness={mat.roughness}, metallic={mat.metallic})"
            )
        lines.append(f"{ind}obj.data.materials.append(mat)")

    # Modifiers
    for mod in comp.modifiers:
        lines.extend(_build_modifier(name, mod, ind))

    # Auto-smooth for cubes with bevel (softens bevel edges while keeping flat faces)
    if comp.primitive == "cube" and any(m.type == "bevel" for m in comp.modifiers):
        lines.append(f"{ind}try:")
        lines.append(f"{ind}    bpy.ops.object.shade_auto_smooth()  # Blender 4.x")
        lines.append(f"{ind}except Exception:")
        lines.append(f"{ind}    obj.data.use_auto_smooth = True")
        lines.append(f"{ind}    obj.data.auto_smooth_angle = 0.523599")

    # Sanity check + store
    lines.append(f"{ind}sanity_check(obj, '{name}')")
    lines.append(f"{ind}created_objects['{name}'] = obj")

    return lines


def _build_modifier(comp_name: str, mod: ModifierSpec, ind: str) -> List[str]:
    """Generate lines for adding a modifier."""
    lines: List[str] = []
    blender_type = MODIFIER_TYPES.get(mod.type)
    if not blender_type:
        lines.append(f"{ind}# Skipped unsupported modifier: {mod.type}")
        return lines

    var = f"mod_{mod.type}"
    lines.append(f"{ind}{var} = obj.modifiers.new(name='{mod.type}_{comp_name}', type='{blender_type}')")

    for param_name, param_value in mod.params.items():
        if mod.type == "array" and param_name == "offset":
            v = tuple(param_value) if isinstance(param_value, list) else param_value
            lines.append(f"{ind}{var}.use_constant_offset = True")
            lines.append(f"{ind}{var}.constant_offset_displace = {_fmt_tuple(v)}")
        elif mod.type == "array" and param_name == "count":
            lines.append(f"{ind}{var}.count = {param_value}")
        elif mod.type == "bevel" and param_name == "width":
            lines.append(f"{ind}{var}.width = {param_value}")
        elif mod.type == "bevel" and param_name == "segments":
            lines.append(f"{ind}{var}.segments = {param_value}")
        elif mod.type == "solidify" and param_name == "thickness":
            lines.append(f"{ind}{var}.thickness = {param_value}")
        elif mod.type == "subdivision" and param_name in ("levels", "render_levels"):
            lines.append(f"{ind}{var}.{param_name} = {param_value}")
        elif mod.type == "mirror" and param_name == "axis":
            for ax in ["X", "Y", "Z"]:
                val = ax in str(param_value).upper()
                lines.append(f"{ind}{var}.use_{ax.lower()} = {val}")
        elif mod.type == "boolean" and param_name == "operation":
            lines.append(f"{ind}{var}.operation = '{param_value}'")
        elif mod.type == "boolean" and param_name == "target":
            tgt = _safe(str(param_value))
            lines.append(f"{ind}if '{tgt}' in created_objects:")
            lines.append(f"{ind}    {var}.object = created_objects['{tgt}']")
        elif mod.type == "wireframe" and param_name == "thickness":
            lines.append(f"{ind}{var}.thickness = {param_value}")
        elif mod.type == "decimate" and param_name == "ratio":
            lines.append(f"{ind}{var}.ratio = {param_value}")
        else:
            lines.append(f"{ind}try:")
            lines.append(f"{ind}    {var}.{param_name} = {param_value!r}")
            lines.append(f"{ind}except AttributeError:")
            lines.append(f"{ind}    print(f'Warning: modifier {mod.type} has no attr {param_name}')")

    return lines


def _build_lighting_and_camera() -> List[str]:
    """Generate lines for three-point lighting and dynamic camera framing."""
    ind = "        "
    lines: List[str] = []
    lines.append(f"{ind}# --- Lighting & camera ---")

    # Sun (main key light from upper right)
    lines.append(f"{ind}bpy.ops.object.light_add(type='SUN', location=(5, 5, 12))")
    lines.append(f"{ind}sun = bpy.context.active_object")
    lines.append(f"{ind}sun.name = 'Sun'")
    lines.append(f"{ind}sun.data.energy = 3.0")
    lines.append(f"{ind}sun.rotation_euler = (0.7, 0, 0.8)")

    # Fill light (softer, from the other side)
    lines.append(f"{ind}bpy.ops.object.light_add(type='AREA', location=(-4, -3, 6))")
    lines.append(f"{ind}fill = bpy.context.active_object")
    lines.append(f"{ind}fill.name = 'Fill'")
    lines.append(f"{ind}fill.data.energy = 150")
    lines.append(f"{ind}fill.data.size = 4")
    lines.append(f"{ind}fill.rotation_euler = (0.9, 0, -0.5)")

    # Rim light (behind/above for depth separation)
    lines.append(f"{ind}bpy.ops.object.light_add(type='SPOT', location=(-3, 5, 8))")
    lines.append(f"{ind}rim = bpy.context.active_object")
    lines.append(f"{ind}rim.name = 'Rim'")
    lines.append(f"{ind}rim.data.energy = 500")
    lines.append(f"{ind}rim.data.spot_size = 1.2")
    lines.append(f"{ind}rim.rotation_euler = (0.6, 0, -2.5)")

    # Dynamic camera: compute bounding box EXCLUDING ground planes
    # Ground planes are large flat surfaces that would push the camera too far away
    lines.append(f"{ind}# Dynamic camera framing (exclude ground planes)")
    lines.append(f"{ind}ground_names = {{'ground', 'floor', 'ground_plane', 'floor_plane'}}")
    lines.append(f"{ind}scene_coords = []")
    lines.append(f"{ind}for obj in bpy.data.objects:")
    lines.append(f"{ind}    if obj.type == 'MESH' and obj.name.lower() not in ground_names:")
    lines.append(f"{ind}        for corner in obj.bound_box:")
    lines.append(f"{ind}            world_corner = obj.matrix_world @ mathutils.Vector(corner)")
    lines.append(f"{ind}            scene_coords.append(world_corner)")
    lines.append(f"{ind}# Fallback: if only ground planes exist, include everything")
    lines.append(f"{ind}if not scene_coords:")
    lines.append(f"{ind}    for obj in bpy.data.objects:")
    lines.append(f"{ind}        if obj.type == 'MESH':")
    lines.append(f"{ind}            for corner in obj.bound_box:")
    lines.append(f"{ind}                world_corner = obj.matrix_world @ mathutils.Vector(corner)")
    lines.append(f"{ind}                scene_coords.append(world_corner)")
    lines.append(f"{ind}if scene_coords:")
    lines.append(f"{ind}    bbox_min = mathutils.Vector((min(c[0] for c in scene_coords), min(c[1] for c in scene_coords), min(c[2] for c in scene_coords)))")
    lines.append(f"{ind}    bbox_max = mathutils.Vector((max(c[0] for c in scene_coords), max(c[1] for c in scene_coords), max(c[2] for c in scene_coords)))")
    lines.append(f"{ind}    center = (bbox_min + bbox_max) / 2")
    lines.append(f"{ind}    max_dim = max(bbox_max[i] - bbox_min[i] for i in range(3))")
    lines.append(f"{ind}    distance = max(max_dim * 1.8, 4.0)")
    lines.append(f"{ind}    cam_location = center + mathutils.Vector((distance * 0.7, -distance * 0.7, distance * 0.5))")
    lines.append(f"{ind}else:")
    lines.append(f"{ind}    center = mathutils.Vector((0, 0, 1))")
    lines.append(f"{ind}    cam_location = mathutils.Vector((8, -8, 6))")

    # Create empty target at scene center
    lines.append(f"{ind}bpy.ops.object.empty_add(location=tuple(center))")
    lines.append(f"{ind}target = bpy.context.active_object")
    lines.append(f"{ind}target.name = 'CameraTarget'")
    lines.append(f"{ind}target.hide_viewport = True")
    lines.append(f"{ind}target.hide_render = True")

    # Create camera with TRACK_TO constraint
    lines.append(f"{ind}bpy.ops.object.camera_add(location=tuple(cam_location))")
    lines.append(f"{ind}cam = bpy.context.active_object")
    lines.append(f"{ind}cam.name = 'Camera'")
    lines.append(f"{ind}track = cam.constraints.new(type='TRACK_TO')")
    lines.append(f"{ind}track.target = target")
    lines.append(f"{ind}track.track_axis = 'TRACK_NEGATIVE_Z'")
    lines.append(f"{ind}track.up_axis = 'UP_Y'")
    lines.append(f"{ind}bpy.context.scene.camera = cam")

    return lines


def _build_world_environment() -> List[str]:
    """Generate lines for a gradient sky world environment."""
    ind = "        "
    lines: List[str] = []
    lines.append(f"{ind}# --- World environment (gradient sky) ---")
    lines.append(f"{ind}world = bpy.data.worlds.get('World')")
    lines.append(f"{ind}if not world:")
    lines.append(f"{ind}    world = bpy.data.worlds.new('World')")
    lines.append(f"{ind}bpy.context.scene.world = world")
    lines.append(f"{ind}world.use_nodes = True")
    lines.append(f"{ind}nodes = world.node_tree.nodes")
    lines.append(f"{ind}links = world.node_tree.links")
    lines.append(f"{ind}nodes.clear()")
    # Texture coordinate
    lines.append(f"{ind}tex_coord = nodes.new('ShaderNodeTexCoord')")
    lines.append(f"{ind}tex_coord.location = (-800, 300)")
    # Mapping (rotate to make gradient vertical)
    lines.append(f"{ind}mapping = nodes.new('ShaderNodeMapping')")
    lines.append(f"{ind}mapping.location = (-600, 300)")
    # Gradient texture
    lines.append(f"{ind}gradient = nodes.new('ShaderNodeTexGradient')")
    lines.append(f"{ind}gradient.gradient_type = 'LINEAR'")
    lines.append(f"{ind}gradient.location = (-400, 300)")
    # Color ramp (sky blue at top → lighter near horizon → soft ground)
    lines.append(f"{ind}ramp = nodes.new('ShaderNodeValToRGB')")
    lines.append(f"{ind}ramp.location = (-200, 300)")
    lines.append(f"{ind}ramp.color_ramp.elements[0].position = 0.0")
    lines.append(f"{ind}ramp.color_ramp.elements[0].color = (0.8, 0.85, 0.9, 1.0)")  # horizon
    lines.append(f"{ind}ramp.color_ramp.elements[1].position = 1.0")
    lines.append(f"{ind}ramp.color_ramp.elements[1].color = (0.33, 0.55, 0.85, 1.0)")  # sky blue
    # Add a middle stop for soft white near horizon
    lines.append(f"{ind}mid = ramp.color_ramp.elements.new(0.45)")
    lines.append(f"{ind}mid.color = (0.9, 0.92, 0.95, 1.0)")
    # Background node
    lines.append(f"{ind}bg = nodes.new('ShaderNodeBackground')")
    lines.append(f"{ind}bg.inputs['Strength'].default_value = 1.0")
    lines.append(f"{ind}bg.location = (100, 300)")
    # Output
    lines.append(f"{ind}output = nodes.new('ShaderNodeOutputWorld')")
    lines.append(f"{ind}output.location = (300, 300)")
    # Link chain
    lines.append(f"{ind}links.new(tex_coord.outputs['Generated'], mapping.inputs['Vector'])")
    lines.append(f"{ind}links.new(mapping.outputs['Vector'], gradient.inputs['Vector'])")
    lines.append(f"{ind}links.new(gradient.outputs['Color'], ramp.inputs['Fac'])")
    lines.append(f"{ind}links.new(ramp.outputs['Color'], bg.inputs['Color'])")
    lines.append(f"{ind}links.new(bg.outputs['Background'], output.inputs['Surface'])")
    return lines


def _build_render_settings() -> List[str]:
    """Generate lines for Eevee render configuration."""
    ind = "        "
    lines: List[str] = []
    lines.append(f"{ind}# --- Render settings (Eevee) ---")
    lines.append(f"{ind}scene = bpy.context.scene")
    # Use Eevee (BLENDER_EEVEE_NEXT for Blender 4.x, fallback to BLENDER_EEVEE)
    lines.append(f"{ind}try:")
    lines.append(f"{ind}    scene.render.engine = 'BLENDER_EEVEE_NEXT'")
    lines.append(f"{ind}except Exception:")
    lines.append(f"{ind}    scene.render.engine = 'BLENDER_EEVEE'")
    # Resolution
    lines.append(f"{ind}scene.render.resolution_x = 1920")
    lines.append(f"{ind}scene.render.resolution_y = 1080")
    # Ambient Occlusion
    lines.append(f"{ind}try:")
    lines.append(f"{ind}    scene.eevee.use_gtao = True")
    lines.append(f"{ind}    scene.eevee.gtao_distance = 1.0")
    lines.append(f"{ind}except Exception:")
    lines.append(f"{ind}    pass")
    # Screen Space Reflections
    lines.append(f"{ind}try:")
    lines.append(f"{ind}    scene.eevee.use_ssr = True")
    lines.append(f"{ind}    scene.eevee.use_ssr_refraction = True")
    lines.append(f"{ind}except Exception:")
    lines.append(f"{ind}    pass")
    # Color management - Filmic for better dynamic range
    lines.append(f"{ind}scene.view_settings.view_transform = 'Filmic'")
    lines.append(f"{ind}try:")
    lines.append(f"{ind}    scene.view_settings.look = 'Medium High Contrast'")
    lines.append(f"{ind}except Exception:")
    lines.append(f"{ind}    pass")
    lines.append(f"{ind}scene.render.film_transparent = False")
    return lines


def _build_shadow_catchers(plan: ScenePlan) -> List[str]:
    """Mark ground/floor planes as shadow catchers for cleaner renders."""
    ind = "        "
    lines: List[str] = []
    ground_names = []
    for comp in plan.components:
        is_ground = (
            comp.name.lower() in ("ground", "floor", "ground_plane", "floor_plane")
            or (comp.primitive == "plane" and abs(comp.location[2]) < 0.05)
        )
        if is_ground:
            ground_names.append(_safe(comp.name))

    if ground_names:
        lines.append(f"{ind}# --- Shadow catchers ---")
        for gname in ground_names:
            lines.append(f"{ind}ground_obj = created_objects.get('{gname}')")
            lines.append(f"{ind}if ground_obj:")
            lines.append(f"{ind}    try:")
            lines.append(f"{ind}        ground_obj.is_shadow_catcher = True")
            lines.append(f"{ind}    except Exception:")
            lines.append(f"{ind}        pass  # shadow catcher not supported in this Blender version")
    return lines


def _build_viewport_framing() -> List[str]:
    """Frame the viewport on the scene content (excluding ground planes)."""
    ind = "        "
    lines: List[str] = []
    lines.append(f"{ind}# --- Frame viewport on scene content ---")
    lines.append(f"{ind}try:")
    lines.append(f"{ind}    # Select non-ground objects for framing")
    lines.append(f"{ind}    bpy.ops.object.select_all(action='DESELECT')")
    lines.append(f"{ind}    _ground = {{'ground', 'floor', 'ground_plane', 'floor_plane'}}")
    lines.append(f"{ind}    for obj in bpy.data.objects:")
    lines.append(f"{ind}        if obj.type == 'MESH' and obj.name.lower() not in _ground:")
    lines.append(f"{ind}            obj.select_set(True)")
    lines.append(f"{ind}    # Frame selected in 3D viewport")
    lines.append(f"{ind}    for area in bpy.context.screen.areas:")
    lines.append(f"{ind}        if area.type == 'VIEW_3D':")
    lines.append(f"{ind}            for region in area.regions:")
    lines.append(f"{ind}                if region.type == 'WINDOW':")
    lines.append(f"{ind}                    with bpy.context.temp_override(area=area, region=region):")
    lines.append(f"{ind}                        bpy.ops.view3d.view_selected()")
    lines.append(f"{ind}                    break")
    lines.append(f"{ind}            break")
    lines.append(f"{ind}    bpy.ops.object.select_all(action='DESELECT')")
    lines.append(f"{ind}except Exception:")
    lines.append(f"{ind}    pass  # viewport framing not available (e.g. running headless)")
    return lines
