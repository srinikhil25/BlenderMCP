"""LLM wrapper — generates bpy code from text prompts via Gemini or Ollama."""

from __future__ import annotations

import os
import re
import threading

import src.config as cfg
from src.code_cache import get_cached, save_to_cache

SYSTEM_PROMPT = """\
You are a Blender 5.1 Python expert specializing in photorealistic 3D scenes.
Generate bpy code that renders beautifully with Cycles ray-tracing.

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

def create_pbr_material(name, color, roughness=0.5, metallic=0.0, bump_scale=5.0, bump_strength=0.1):
    \"\"\"Create a PBR material with procedural bump/noise for realism.\"\"\"
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic

    # Color variation via noise
    noise = nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = bump_scale
    noise.inputs['Detail'].default_value = 6.0
    noise.location = (bsdf.location.x - 500, bsdf.location.y)

    mix = nodes.new('ShaderNodeMixRGB')
    mix.blend_type = 'MULTIPLY'
    mix.inputs['Fac'].default_value = 0.15
    mix.inputs[1].default_value = (*color, 1.0)
    mix.location = (bsdf.location.x - 250, bsdf.location.y)
    links.new(noise.outputs['Color'], mix.inputs[2])
    links.new(mix.outputs['Color'], bsdf.inputs['Base Color'])

    # Bump map for surface texture
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = bump_strength
    bump.inputs['Distance'].default_value = 0.02
    bump.location = (bsdf.location.x - 250, bsdf.location.y - 300)

    noise2 = nodes.new('ShaderNodeTexNoise')
    noise2.inputs['Scale'].default_value = bump_scale * 3
    noise2.inputs['Detail'].default_value = 8.0
    noise2.location = (bsdf.location.x - 500, bsdf.location.y - 300)
    links.new(noise2.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    return mat

def create_wood_material(name, color=(0.4, 0.22, 0.08), roughness=0.7):
    \"\"\"Realistic wood with grain pattern.\"\"\"
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = roughness

    # Wood grain via wave texture
    coord = nodes.new('ShaderNodeTexCoord')
    coord.location = (-800, 0)
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (8, 1, 1)
    mapping.location = (-600, 0)
    links.new(coord.outputs['Object'], mapping.inputs['Vector'])

    wave = nodes.new('ShaderNodeTexWave')
    wave.wave_type = 'RINGS'
    wave.inputs['Scale'].default_value = 3.0
    wave.inputs['Distortion'].default_value = 4.0
    wave.inputs['Detail'].default_value = 3.0
    wave.location = (-400, 0)
    links.new(mapping.outputs['Vector'], wave.inputs['Vector'])

    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.location = (-200, 0)
    ramp.color_ramp.elements[0].color = (*[c * 0.7 for c in color], 1.0)
    ramp.color_ramp.elements[1].color = (*[c * 1.3 for c in color], 1.0)
    links.new(wave.outputs['Fac'], ramp.inputs['Fac'])
    links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])

    # Subtle bump
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.05
    bump.location = (-200, -300)
    links.new(wave.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    return mat

def create_glass_material(name, color=(0.9, 0.95, 1.0), ior=1.45):
    \"\"\"Transparent glass material.\"\"\"
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.0
    bsdf.inputs["Metallic"].default_value = 0.0
    bsdf.inputs["IOR"].default_value = ior
    bsdf.inputs["Transmission Weight"].default_value = 1.0
    return mat

def create_emission_material(name, color=(1.0, 0.9, 0.7), strength=5.0):
    \"\"\"Glowing/emissive material (for screens, lamps, fire).\"\"\"
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Emission Color"].default_value = (*color, 1.0)
    bsdf.inputs["Emission Strength"].default_value = strength
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
1. Materials: use the helpers above. The "Principled BSDF" node already exists when use_nodes=True. NEVER call nodes.new("BSDF_PRINCIPLED") or nodes.new("ShaderNodeBsdfPrincipled").
2. USE create_pbr_material() for most surfaces — it adds procedural bump/noise for realism.
3. USE create_wood_material() for any wood surface — it creates realistic grain.
4. USE create_glass_material() for windows, bottles, lenses.
5. USE create_emission_material() for screens, lamps, glowing objects.
6. USE create_material() for simple/flat surfaces only.
7. Shade smooth: call bpy.ops.object.shade_smooth() right after creating each curved object.
8. Add SUBDIVISION SURFACE modifier (level 2) to curved objects for smoother geometry.
9. Add BEVEL modifier (width=0.005, segments=2) to hard-edged objects for realistic edges.
10. There is NO primitive_sphere_add. Use primitive_uv_sphere_add.
11. Modifiers: obj.modifiers.new("name", 'TYPE'). Types: 'SUBSURF', 'BOOLEAN', 'ARRAY', 'MIRROR', 'SOLIDIFY', 'BEVEL'.
12. All coordinates Z-up. 1 unit = 1 meter. Objects sit ON ground (z >= 0).
13. DO NOT create cameras, lights, or ground planes — they are added automatically.
14. DO NOT import os, sys, subprocess, or use eval/exec/open.
15. For positioning: cube size=1 means 1m each side. Location is CENTER. Cube at z=0.5, size=1 sits on ground.
16. NEVER pass execution context as positional arg to bpy.ops calls.
17. Wave Texture node: wave_type ONLY accepts 'BANDS' or 'RINGS' (NOT 'SAW'). wave_profile ONLY accepts 'SIN' or 'SAW'. Do NOT confuse these two properties.

MATERIAL GUIDE (use realistic PBR values):
- Wood: create_wood_material("Oak", (0.45, 0.25, 0.1), roughness=0.7)
- Metal: create_pbr_material("Steel", (0.6, 0.6, 0.62), roughness=0.2, metallic=1.0, bump_strength=0.02)
- Concrete: create_pbr_material("Concrete", (0.5, 0.48, 0.45), roughness=0.9, bump_scale=3.0, bump_strength=0.15)
- Fabric: create_pbr_material("Fabric", (0.3, 0.15, 0.1), roughness=0.95, bump_scale=15.0, bump_strength=0.08)
- Plastic: create_pbr_material("Plastic", (0.8, 0.1, 0.1), roughness=0.3, bump_strength=0.01)
- Ceramic: create_pbr_material("Ceramic", (0.9, 0.88, 0.85), roughness=0.4, bump_strength=0.02)
- Brick: create_pbr_material("Brick", (0.55, 0.25, 0.15), roughness=0.85, bump_scale=4.0, bump_strength=0.2)
- Glass: create_glass_material("Glass")
- Screen glow: create_emission_material("ScreenGlow", (0.6, 0.8, 1.0), strength=3.0)

PRIMITIVES (exact signatures):
- primitive_cube_add(size=2, location=(0,0,0))
- primitive_uv_sphere_add(radius=1, segments=32, ring_count=16, location=(0,0,0))
- primitive_ico_sphere_add(radius=1, subdivisions=2, location=(0,0,0))
- primitive_cylinder_add(radius=1, depth=2, vertices=32, location=(0,0,0))
- primitive_cone_add(radius1=1, radius2=0, depth=2, vertices=32, location=(0,0,0))
- primitive_torus_add(major_radius=1, minor_radius=0.25, location=(0,0,0))
- primitive_plane_add(size=2, location=(0,0,0))
- primitive_grid_add(x_subdivisions=10, y_subdivisions=10, size=2, location=(0,0,0))

EXAMPLE — "A wooden desk with monitor and coffee mug" (photorealistic):
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

def create_pbr_material(name, color, roughness=0.5, metallic=0.0, bump_scale=5.0, bump_strength=0.1):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    noise = nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = bump_scale
    noise.inputs['Detail'].default_value = 6.0
    noise.location = (bsdf.location.x - 500, bsdf.location.y)
    mix = nodes.new('ShaderNodeMixRGB')
    mix.blend_type = 'MULTIPLY'
    mix.inputs['Fac'].default_value = 0.15
    mix.inputs[1].default_value = (*color, 1.0)
    mix.location = (bsdf.location.x - 250, bsdf.location.y)
    links.new(noise.outputs['Color'], mix.inputs[2])
    links.new(mix.outputs['Color'], bsdf.inputs['Base Color'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = bump_strength
    bump.inputs['Distance'].default_value = 0.02
    bump.location = (bsdf.location.x - 250, bsdf.location.y - 300)
    noise2 = nodes.new('ShaderNodeTexNoise')
    noise2.inputs['Scale'].default_value = bump_scale * 3
    noise2.inputs['Detail'].default_value = 8.0
    noise2.location = (bsdf.location.x - 500, bsdf.location.y - 300)
    links.new(noise2.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    return mat

def create_wood_material(name, color=(0.4, 0.22, 0.08), roughness=0.7):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = roughness
    coord = nodes.new('ShaderNodeTexCoord')
    coord.location = (-800, 0)
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (8, 1, 1)
    mapping.location = (-600, 0)
    links.new(coord.outputs['Object'], mapping.inputs['Vector'])
    wave = nodes.new('ShaderNodeTexWave')
    wave.wave_type = 'RINGS'
    wave.inputs['Scale'].default_value = 3.0
    wave.inputs['Distortion'].default_value = 4.0
    wave.inputs['Detail'].default_value = 3.0
    wave.location = (-400, 0)
    links.new(mapping.outputs['Vector'], wave.inputs['Vector'])
    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.location = (-200, 0)
    ramp.color_ramp.elements[0].color = (*[c * 0.7 for c in color], 1.0)
    ramp.color_ramp.elements[1].color = (*[c * 1.3 for c in color], 1.0)
    links.new(wave.outputs['Fac'], ramp.inputs['Fac'])
    links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.05
    bump.location = (-200, -300)
    links.new(wave.outputs['Fac'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    return mat

def create_emission_material(name, color=(1.0, 0.9, 0.7), strength=5.0):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Emission Color"].default_value = (*color, 1.0)
    bsdf.inputs["Emission Strength"].default_value = strength
    return mat

def assign_mat(obj, mat):
    obj.data.materials.append(mat)

def create_scene():
    try:
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete()

        # Materials
        wood = create_wood_material("DeskWood", (0.4, 0.25, 0.12))
        dark = create_pbr_material("DarkPlastic", (0.02, 0.02, 0.02), roughness=0.25, bump_strength=0.01)
        screen_glow = create_emission_material("ScreenGlow", (0.5, 0.7, 1.0), strength=3.0)
        silver = create_pbr_material("BrushedMetal", (0.7, 0.7, 0.72), roughness=0.15, metallic=1.0, bump_strength=0.02)
        ceramic = create_pbr_material("Ceramic", (0.92, 0.88, 0.82), roughness=0.4, bump_strength=0.02)
        key_mat = create_pbr_material("Keys", (0.08, 0.08, 0.08), roughness=0.35, bump_scale=20, bump_strength=0.03)

        # --- Desk ---
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.75))
        desk = bpy.context.active_object
        desk.name = "Desk_Top"
        desk.scale = (1.4, 0.7, 0.04)
        bev = desk.modifiers.new("Bevel", 'BEVEL')
        bev.width = 0.005
        bev.segments = 2
        assign_mat(desk, wood)

        for i, (x, y) in enumerate([(-0.65, -0.30), (0.65, -0.30), (-0.65, 0.30), (0.65, 0.30)]):
            bpy.ops.mesh.primitive_cylinder_add(radius=0.03, depth=0.73, location=(x, y, 0.365))
            leg = bpy.context.active_object
            leg.name = f"DeskLeg_{i}"
            assign_mat(leg, wood)
            bpy.ops.object.shade_smooth()

        # --- Monitor ---
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0.15, 1.15))
        screen = bpy.context.active_object
        screen.name = "Monitor_Body"
        screen.scale = (0.55, 0.02, 0.35)
        bev = screen.modifiers.new("Bevel", 'BEVEL')
        bev.width = 0.003
        bev.segments = 2
        assign_mat(screen, dark)

        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0.138, 1.15))
        face = bpy.context.active_object
        face.name = "Screen_Glow"
        face.scale = (0.50, 0.003, 0.30)
        assign_mat(face, screen_glow)

        bpy.ops.mesh.primitive_cylinder_add(radius=0.02, depth=0.18, location=(0, 0.15, 0.87))
        neck = bpy.context.active_object
        neck.name = "Monitor_Neck"
        assign_mat(neck, silver)
        bpy.ops.object.shade_smooth()

        bpy.ops.mesh.primitive_cylinder_add(radius=0.12, depth=0.015, location=(0, 0.15, 0.78))
        base = bpy.context.active_object
        base.name = "Monitor_Base"
        assign_mat(base, silver)
        bpy.ops.object.shade_smooth()

        # --- Keyboard ---
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -0.1, 0.785))
        kb = bpy.context.active_object
        kb.name = "Keyboard"
        kb.scale = (0.40, 0.13, 0.012)
        bev = kb.modifiers.new("Bevel", 'BEVEL')
        bev.width = 0.003
        bev.segments = 2
        assign_mat(kb, key_mat)

        # --- Coffee mug (with subdivision for smoothness) ---
        bpy.ops.mesh.primitive_cylinder_add(radius=0.04, depth=0.1, location=(0.5, -0.05, 0.82))
        mug = bpy.context.active_object
        mug.name = "Mug"
        sub = mug.modifiers.new("Subdiv", 'SUBSURF')
        sub.levels = 2
        assign_mat(mug, ceramic)
        bpy.ops.object.shade_smooth()

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


MODIFY_PROMPT = """\
The Blender scene already contains these objects:
{scene_context}

IMPORTANT: Do NOT delete or clear existing objects. Do NOT call select_all/delete.
Only ADD new objects or MODIFY existing ones based on the user's request.
Keep all existing objects in place. Add the new elements the user asks for.
Use the same create_material() and assign_mat() helpers.
Output the COMPLETE script inside ```python fences.
"""


def generate_bpy_code(
    prompt: str, feedback: str = "", scene_context: str = "",
) -> tuple[str, bool]:
    """Generate bpy Python code for the given prompt.

    Args:
        prompt: User's scene description.
        feedback: Optional error feedback from a previous attempt.
        scene_context: Optional current scene state (for modify mode).

    Returns:
        Tuple of (code_string, was_cached).
    """
    # Check cache (skip if retrying with feedback or modifying)
    if not feedback and not scene_context:
        cached = get_cached(prompt)
        if cached:
            return cached, True

    if cfg.LLM_PROVIDER == "gemini":
        code = _generate_gemini(prompt, feedback, scene_context)
    else:
        code = _generate_ollama(prompt, feedback, scene_context)

    # Save to cache (only first successful generation, not retries/modify)
    if not feedback and not scene_context:
        save_to_cache(prompt, code)

    return code, False


def _build_user_message(prompt: str, feedback: str, scene_context: str) -> str:
    """Construct the user message with optional modify context and feedback."""
    parts = []

    if scene_context:
        parts.append(MODIFY_PROMPT.format(scene_context=scene_context))

    parts.append(prompt)

    if feedback:
        parts.append(
            f"\n\nThe previous code had this error in Blender:\n{feedback}\n\n"
            "Fix the error. Output the COMPLETE corrected script inside ```python fences."
        )

    return "\n\n".join(parts)


def _generate_gemini(prompt: str, feedback: str = "", scene_context: str = "") -> str:
    """Generate code using Google Gemini API (free tier)."""
    from google import genai

    api_key = cfg.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "Gemini API key not set. Get a free key at https://aistudio.google.com/apikey\n"
            "Then set GEMINI_API_KEY in config.py or as an environment variable."
        )

    client = genai.Client(api_key=api_key)
    user_msg = _build_user_message(prompt, feedback, scene_context)

    # Run with timeout
    result_container: list = []
    error_container: list = []

    def _call() -> None:
        try:
            response = client.models.generate_content(
                model=cfg.GEMINI_MODEL,
                contents=user_msg,
                config=genai.types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                ),
            )
            result_container.append(response.text)
        except Exception as e:
            error_container.append(e)

    thread = threading.Thread(target=_call, daemon=True)
    thread.start()
    thread.join(timeout=cfg.LLM_TIMEOUT)

    if thread.is_alive():
        raise RuntimeError(
            f"Gemini API timed out after {cfg.LLM_TIMEOUT}s. "
            "Try a simpler prompt or check your internet connection."
        )
    if error_container:
        raise error_container[0]
    if not result_container:
        raise RuntimeError("Gemini returned no response.")

    return _extract_code(result_container[0])


def _generate_ollama(prompt: str, feedback: str = "", scene_context: str = "") -> str:
    """Generate code using local Ollama model."""
    import ollama

    user_msg = _build_user_message(prompt, feedback, scene_context)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    # Run with timeout
    result_container: list = []
    error_container: list = []

    def _call() -> None:
        try:
            response = ollama.chat(
                model=cfg.OLLAMA_MODEL,
                messages=messages,
                options={"num_ctx": cfg.OLLAMA_NUM_CTX},
            )
            result_container.append(response["message"]["content"])
        except Exception as e:
            error_container.append(e)

    thread = threading.Thread(target=_call, daemon=True)
    thread.start()
    thread.join(timeout=cfg.LLM_TIMEOUT)

    if thread.is_alive():
        raise RuntimeError(
            f"Ollama timed out after {cfg.LLM_TIMEOUT}s. "
            "The model may be too large for your hardware."
        )
    if error_container:
        raise error_container[0]
    if not result_container:
        raise RuntimeError("Ollama returned no response.")

    return _extract_code(result_container[0])


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
