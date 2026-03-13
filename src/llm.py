"""LLM wrapper — generates bpy code from text prompts via Ollama."""

from __future__ import annotations

import re

import ollama

from src.config import OLLAMA_MODEL, OLLAMA_NUM_CTX

SYSTEM_PROMPT = """\
You are a Blender 5.1 Python expert. Generate bpy code to create 3D scenes.

OUTPUT: ONLY valid Python inside ```python fences. No explanations outside the code block.

TEMPLATE (copy this structure exactly):
```python
import bpy
import bmesh
import math
from mathutils import Vector, Matrix

def create_material(name, color, roughness=0.5, metallic=0.0):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat

def assign_mat(obj, mat):
    obj.data.materials.append(mat)

def create_scene():
    try:
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete()

        # ... create objects here ...

        count = len([o for o in bpy.data.objects if o.type == 'MESH'])
        print(f"SUCCESS: Created {count} objects")
    except Exception as e:
        print(f"ERROR: {e}")
        raise

create_scene()
```

CRITICAL BLENDER 5.1 RULES:
1. Materials: use ONLY the create_material() helper above. The "Principled BSDF" node already exists when use_nodes=True. NEVER call nodes.new("BSDF_PRINCIPLED") or nodes.new("ShaderNodeBsdfPrincipled").
2. Shade smooth: call bpy.ops.object.shade_smooth() right after creating each curved object (while it's still active).
3. There is NO primitive_sphere_add. Use primitive_uv_sphere_add.
4. Modifiers: obj.modifiers.new("name", 'TYPE'). Types: 'SUBSURF', 'BOOLEAN', 'ARRAY', 'MIRROR', 'SOLIDIFY', 'BEVEL'.
5. Booleans: mod.operation = 'DIFFERENCE'/'UNION'/'INTERSECT', mod.object = other_obj.
6. All coordinates Z-up. 1 unit = 1 meter. Objects sit ON ground (z >= 0).
7. DO NOT create cameras, lights, or ground planes — they are added automatically.
8. DO NOT import os, sys, subprocess, or use eval/exec/open.
9. For positioning: cube size=1 means 1m on each side. Location is the CENTER. A cube at z=0.5 with size=1 sits on the ground.
10. NEVER pass execution context as positional arg to bpy.ops calls.

PRIMITIVES (exact signatures):
- primitive_cube_add(size=2, location=(0,0,0))
- primitive_uv_sphere_add(radius=1, segments=32, ring_count=16, location=(0,0,0))
- primitive_ico_sphere_add(radius=1, subdivisions=2, location=(0,0,0))
- primitive_cylinder_add(radius=1, depth=2, vertices=32, location=(0,0,0))
- primitive_cone_add(radius1=1, radius2=0, depth=2, vertices=32, location=(0,0,0))
- primitive_torus_add(major_radius=1, minor_radius=0.25, location=(0,0,0))
- primitive_plane_add(size=2, location=(0,0,0))
- primitive_grid_add(x_subdivisions=10, y_subdivisions=10, size=2, location=(0,0,0))

EXAMPLE — "A simple wooden table":
```python
import bpy
import bmesh
import math
from mathutils import Vector, Matrix

def create_material(name, color, roughness=0.5, metallic=0.0):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat

def assign_mat(obj, mat):
    obj.data.materials.append(mat)

def create_scene():
    try:
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete()

        wood = create_material("Wood", (0.45, 0.25, 0.1), roughness=0.85)

        # Tabletop: 1.2m x 0.7m x 0.04m, top surface at 0.77m
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.77))
        top = bpy.context.active_object
        top.name = "Tabletop"
        top.scale = (1.2, 0.7, 0.04)
        assign_mat(top, wood)

        # Four legs: radius=0.03m, height=0.75m
        for x, y in [(-0.55, -0.30), (0.55, -0.30), (-0.55, 0.30), (0.55, 0.30)]:
            bpy.ops.mesh.primitive_cylinder_add(radius=0.03, depth=0.75, location=(x, y, 0.375))
            leg = bpy.context.active_object
            leg.name = f"Leg_{x:.1f}_{y:.1f}"
            assign_mat(leg, wood)

        count = len([o for o in bpy.data.objects if o.type == 'MESH'])
        print(f"SUCCESS: Created {count} objects")
    except Exception as e:
        print(f"ERROR: {e}")
        raise

create_scene()
```

EXAMPLE — "A desk with monitor, keyboard, and coffee mug":
```python
import bpy
import bmesh
import math
from mathutils import Vector, Matrix

def create_material(name, color, roughness=0.5, metallic=0.0):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat

def assign_mat(obj, mat):
    obj.data.materials.append(mat)

def create_scene():
    try:
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete()

        wood = create_material("DeskWood", (0.4, 0.25, 0.12), roughness=0.8)
        dark = create_material("DarkPlastic", (0.05, 0.05, 0.05), roughness=0.3)
        screen_mat = create_material("Screen", (0.15, 0.2, 0.3), roughness=0.1)
        silver = create_material("Silver", (0.7, 0.7, 0.72), roughness=0.2, metallic=0.9)
        ceramic = create_material("Ceramic", (0.9, 0.88, 0.85), roughness=0.6)
        key_mat = create_material("Keys", (0.15, 0.15, 0.15), roughness=0.4)

        # --- Desk: 1.4m x 0.7m, height 0.75m ---
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.75))
        desk = bpy.context.active_object
        desk.name = "Desk_Top"
        desk.scale = (1.4, 0.7, 0.04)
        assign_mat(desk, wood)

        for x, y in [(-0.65, -0.30), (0.65, -0.30), (-0.65, 0.30), (0.65, 0.30)]:
            bpy.ops.mesh.primitive_cylinder_add(radius=0.03, depth=0.73, location=(x, y, 0.365))
            leg = bpy.context.active_object
            leg.name = f"DeskLeg"
            assign_mat(leg, wood)

        # --- Monitor: screen + stand ---
        # Screen: 0.55m x 0.02m x 0.35m
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0.15, 1.15))
        screen = bpy.context.active_object
        screen.name = "Monitor_Screen"
        screen.scale = (0.55, 0.02, 0.35)
        assign_mat(screen, dark)

        # Screen face (slightly in front)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0.138, 1.15))
        face = bpy.context.active_object
        face.name = "Screen_Face"
        face.scale = (0.50, 0.005, 0.30)
        assign_mat(face, screen_mat)

        # Monitor stand neck
        bpy.ops.mesh.primitive_cylinder_add(radius=0.02, depth=0.18, location=(0, 0.15, 0.87))
        neck = bpy.context.active_object
        neck.name = "Monitor_Neck"
        assign_mat(neck, silver)

        # Monitor base
        bpy.ops.mesh.primitive_cylinder_add(radius=0.12, depth=0.02, location=(0, 0.15, 0.78))
        base = bpy.context.active_object
        base.name = "Monitor_Base"
        assign_mat(base, silver)

        # --- Keyboard: 0.4m x 0.13m x 0.015m ---
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -0.1, 0.785))
        kb = bpy.context.active_object
        kb.name = "Keyboard"
        kb.scale = (0.40, 0.13, 0.015)
        assign_mat(kb, key_mat)

        # --- Coffee mug ---
        bpy.ops.mesh.primitive_cylinder_add(radius=0.04, depth=0.1, location=(0.5, -0.05, 0.82))
        mug = bpy.context.active_object
        mug.name = "Mug"
        assign_mat(mug, ceramic)
        bpy.ops.object.shade_smooth()

        # Mug handle (torus, rotated)
        bpy.ops.mesh.primitive_torus_add(major_radius=0.03, minor_radius=0.006, location=(0.54, -0.05, 0.82))
        handle = bpy.context.active_object
        handle.name = "Mug_Handle"
        handle.rotation_euler = (0, math.radians(90), 0)
        assign_mat(handle, ceramic)
        bpy.ops.object.shade_smooth()

        count = len([o for o in bpy.data.objects if o.type == 'MESH'])
        print(f"SUCCESS: Created {count} objects")
    except Exception as e:
        print(f"ERROR: {e}")
        raise

create_scene()
```
"""


def generate_bpy_code(prompt: str, feedback: str = "") -> str:
    """Generate bpy Python code for the given prompt.

    Args:
        prompt: User's scene description.
        feedback: Optional error feedback from a previous attempt.

    Returns:
        Extracted Python code string.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    if feedback:
        messages.append({
            "role": "user",
            "content": (
                f"The previous code had this error in Blender:\n{feedback}\n\n"
                "Fix the error. Output the COMPLETE corrected script inside ```python fences."
            ),
        })

    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=messages,
        options={"num_ctx": OLLAMA_NUM_CTX},
    )

    raw = response["message"]["content"]
    return _extract_code(raw)


def _extract_code(text: str) -> str:
    """Extract Python code from LLM response, stripping think tags and fences."""
    # Remove <think>...</think> blocks (qwen3 extended thinking)
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

    # Extract from ```python ... ``` fences
    match = re.search(r"```python\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Try generic ``` fences
    match = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # No fences — return everything (might be raw code)
    return text.strip()
