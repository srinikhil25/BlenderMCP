"""
Planner agent (LLM-backed).

Translates user prompts into ScenePlan objects by asking the LLM
to decompose the scene into primitive components.

Uses Ollama's native structured output (format parameter with JSON Schema)
to guarantee valid JSON every time — no more parsing failures.
"""

from __future__ import annotations

import json
import re
import warnings
from typing import Any, Dict, List, Optional, Tuple

import ollama

from src.config import model_config
from src.planner.geometry_planner import (
    MaterialSpec,
    ModifierSpec,
    SceneComponent,
    ScenePlan,
    SUPPORTED_MODIFIERS,
    SUPPORTED_PRIMITIVES,
)

MAX_COMPONENTS = 30

# ---------------------------------------------------------------------------
# JSON Schema for Ollama structured output.
# Constrains the model to ONLY output valid ScenePlan JSON at the token level.
# ---------------------------------------------------------------------------
SCENE_PLAN_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "unit_scale": {"type": "number"},
        "components": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "primitive": {
                        "type": "string",
                        "enum": sorted(SUPPORTED_PRIMITIVES),
                    },
                    "location": {
                        "type": "array",
                        "items": {"type": "number"},
                    },
                    "rotation": {
                        "type": "array",
                        "items": {"type": "number"},
                    },
                    "scale": {
                        "type": "array",
                        "items": {"type": "number"},
                    },
                    "primitive_params": {"type": "object"},
                    "material": {
                        "type": "object",
                        "properties": {
                            "color": {
                                "type": "array",
                                "items": {"type": "number"},
                            },
                            "roughness": {"type": "number"},
                            "metallic": {"type": "number"},
                            "alpha": {"type": "number"},
                            "procedural_bump": {"type": "boolean"},
                        },
                    },
                    "modifiers": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string"},
                                "params": {"type": "object"},
                            },
                            "required": ["type"],
                        },
                    },
                    "parent": {
                        "type": ["string", "null"],
                    },
                },
                "required": ["name", "primitive", "location"],
            },
        },
    },
    "required": ["name", "description", "components"],
}

# ---------------------------------------------------------------------------
# System prompt with rules and few-shot examples
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are a 3D scene planner for Blender. Given a user prompt describing a 3D scene or object, \
decompose it into primitive shapes and output STRICT JSON matching the schema below.

Output ONLY the JSON object. No markdown fences, no explanations, no code.

JSON Schema:
{
  "name": "short_snake_case_name",
  "description": "One sentence describing the scene",
  "unit_scale": 1.0,
  "components": [
    {
      "name": "unique_part_name",
      "primitive": "cube|uv_sphere|ico_sphere|cylinder|cone|plane|torus|grid",
      "location": [x, y, z],
      "rotation": [rx, ry, rz],
      "scale": [sx, sy, sz],
      "primitive_params": { ... },
      "material": {"color": [r, g, b], "roughness": 0.5, "metallic": 0.0, "procedural_bump": false},
      "modifiers": [{"type": "modifier_type", "params": { ... }}],
      "parent": "other_component_name_or_null"
    }
  ]
}

Supported primitives and their primitive_params:
- cube: {"size": 2.0}
- uv_sphere: {"radius": 1.0, "segments": 32, "ring_count": 16}
- ico_sphere: {"radius": 1.0, "subdivisions": 2}
- cylinder: {"radius": 1.0, "depth": 2.0, "vertices": 32}
- cone: {"radius1": 1.0, "radius2": 0.0, "depth": 2.0, "vertices": 32}
- plane: {"size": 2.0}
- torus: {"major_radius": 1.0, "minor_radius": 0.25}
- grid: {"x_subdivisions": 10, "y_subdivisions": 10, "size": 2.0}

Supported modifiers: bevel, solidify, subdivision, array, mirror, boolean, wireframe, decimate.

Modifier params (use for realism):
- bevel: {"width": 0.02-0.05, "segments": 2} — softens sharp edges on cubes/boxes.
- subdivision: {"levels": 1} or {"render_levels": 2} — smoother spheres and organic shapes.

Rules:
- Every component MUST have name, primitive, and location.
- rotation is in DEGREES (default [0,0,0]).
- scale defaults to [1,1,1]. The builder sets cube/plane size=1 automatically, so scale [W,D,H] directly gives meters. For example, scale [4,3,3] = a 4m x 3m x 3m box.
- 1 unit = 1 meter. Use real-world proportions.
- Keep total component count under 20 for best results.
- Decompose ANY complex object into multiple primitives. Think creatively: a car = body (cube) + wheels (cylinders) + windshield (cube). A chair = seat (cube) + legs (cylinders) + backrest (cube). A tree = trunk (cylinder) + foliage (uv_spheres). A lamp = base (cylinder) + shade (cone).
- ALWAYS include a "ground" plane named "ground" at location [0,0,0] with scale [10,10,1] as the FIRST component. Set its material to an appropriate ground color with procedural_bump: true.
- ALWAYS add a bevel modifier with {"width": 0.02, "segments": 2} to any cube/box-shaped object. Real objects never have perfectly sharp edges.
- Add a subdivision modifier with {"levels": 1} to spheres and organic shapes for smoother surfaces.
- Set "procedural_bump": true for natural and rough surfaces (ground, wood, stone, concrete, fabric, bark, etc.). Keep it false for smooth surfaces (glass, metal, plastic).
- ALIGNMENT IS CRITICAL: Parts must touch with no visible gaps. For cubes with size=1, z_min = location.z - scale.z/2. To stack B on top of A: B.location.z = A.z_max + B_half_height. Example: walls at z=1.5 with scale_z=3 have z_max=3.0, so a roof with depth=1.5 goes at z=3.75 (z_min=3.0, touching wall top).
- For organic clusters (foliage, bushes, clouds, piles), use 4–6 small overlapping uv_spheres at slightly varying positions and radii to create natural-looking groups. Add subdivision modifier to each.
- For tapered shapes (vases, pots, lamp shades, funnels), use a cone with radius1 != radius2.
- Colors are RGB floats 0.0-1.0. Use realistic, muted colors — avoid pure saturated colors.
- Do NOT output Python code. Only JSON.

Example 1 - "Create a simple table":
{"name":"simple_table","description":"A wooden table with four legs","unit_scale":1.0,"components":[{"name":"tabletop","primitive":"cube","location":[0,0,0.77],"scale":[1.2,0.7,0.04],"modifiers":[{"type":"bevel","params":{"width":0.02,"segments":2}}],"material":{"color":[0.55,0.35,0.17],"roughness":0.7,"metallic":0.0,"procedural_bump":true}},{"name":"leg_fl","primitive":"cylinder","location":[-0.55,-0.30,0.375],"primitive_params":{"radius":0.04,"depth":0.75},"material":{"color":[0.55,0.35,0.17],"roughness":0.7,"metallic":0.0}},{"name":"leg_fr","primitive":"cylinder","location":[0.55,-0.30,0.375],"primitive_params":{"radius":0.04,"depth":0.75},"material":{"color":[0.55,0.35,0.17],"roughness":0.7,"metallic":0.0}},{"name":"leg_bl","primitive":"cylinder","location":[-0.55,0.30,0.375],"primitive_params":{"radius":0.04,"depth":0.75},"material":{"color":[0.55,0.35,0.17],"roughness":0.7,"metallic":0.0}},{"name":"leg_br","primitive":"cylinder","location":[0.55,0.30,0.375],"primitive_params":{"radius":0.04,"depth":0.75},"material":{"color":[0.55,0.35,0.17],"roughness":0.7,"metallic":0.0}}]}

Example 2 - "Create a house with plants" (ground plane + correctly aligned components):
{"name":"house_with_garden","description":"A simple house with a pitched roof and potted plants on a ground plane","unit_scale":1.0,"components":[{"name":"ground","primitive":"plane","location":[0,0,0],"scale":[10,10,1],"material":{"color":[0.3,0.35,0.25],"roughness":0.95,"metallic":0.0,"procedural_bump":true}},{"name":"walls","primitive":"cube","location":[0,0,1.5],"scale":[4,3,3],"modifiers":[{"type":"bevel","params":{"width":0.02,"segments":2}}],"material":{"color":[0.85,0.78,0.65],"roughness":0.9,"metallic":0.0,"procedural_bump":true}},{"name":"roof","primitive":"cone","location":[0,0,3.75],"primitive_params":{"radius1":3.0,"radius2":0,"depth":1.5,"vertices":4},"rotation":[0,0,45],"material":{"color":[0.6,0.15,0.1],"roughness":0.8,"metallic":0.0}},{"name":"door","primitive":"cube","location":[0,-1.51,1.0],"scale":[0.8,0.05,2.0],"material":{"color":[0.4,0.25,0.12],"roughness":0.7,"metallic":0.0,"procedural_bump":true}},{"name":"window_left","primitive":"cube","location":[-1.2,-1.51,2.2],"scale":[0.6,0.03,0.6],"material":{"color":[0.6,0.8,0.9],"roughness":0.1,"metallic":0.0}},{"name":"window_right","primitive":"cube","location":[1.2,-1.51,2.2],"scale":[0.6,0.03,0.6],"material":{"color":[0.6,0.8,0.9],"roughness":0.1,"metallic":0.0}},{"name":"pot_1","primitive":"cone","location":[3,-1,0.2],"primitive_params":{"radius1":0.22,"radius2":0.18,"depth":0.4,"vertices":24},"material":{"color":[0.6,0.3,0.15],"roughness":0.9,"metallic":0.0}},{"name":"plant_1_a","primitive":"uv_sphere","location":[3,-1,0.58],"primitive_params":{"radius":0.26},"modifiers":[{"type":"subdivision","params":{"levels":1}}],"material":{"color":[0.15,0.55,0.1],"roughness":0.9,"metallic":0.0}},{"name":"plant_1_b","primitive":"uv_sphere","location":[3.07,-0.96,0.64],"primitive_params":{"radius":0.22},"modifiers":[{"type":"subdivision","params":{"levels":1}}],"material":{"color":[0.18,0.58,0.12],"roughness":0.9,"metallic":0.0}},{"name":"plant_1_c","primitive":"uv_sphere","location":[2.94,-1.05,0.52],"primitive_params":{"radius":0.2},"modifiers":[{"type":"subdivision","params":{"levels":1}}],"material":{"color":[0.15,0.55,0.1],"roughness":0.9,"metallic":0.0}},{"name":"plant_1_d","primitive":"uv_sphere","location":[3.04,-1.08,0.68],"primitive_params":{"radius":0.24},"modifiers":[{"type":"subdivision","params":{"levels":1}}],"material":{"color":[0.2,0.6,0.12],"roughness":0.9,"metallic":0.0}},{"name":"pot_2","primitive":"cone","location":[3,1,0.2],"primitive_params":{"radius1":0.22,"radius2":0.18,"depth":0.4,"vertices":24},"material":{"color":[0.6,0.3,0.15],"roughness":0.9,"metallic":0.0}},{"name":"plant_2_a","primitive":"uv_sphere","location":[3,1,0.6],"primitive_params":{"radius":0.25},"modifiers":[{"type":"subdivision","params":{"levels":1}}],"material":{"color":[0.2,0.6,0.15],"roughness":0.9,"metallic":0.0}},{"name":"plant_2_b","primitive":"uv_sphere","location":[3.06,1.05,0.55],"primitive_params":{"radius":0.22},"modifiers":[{"type":"subdivision","params":{"levels":1}}],"material":{"color":[0.22,0.58,0.14],"roughness":0.9,"metallic":0.0}},{"name":"plant_2_c","primitive":"uv_sphere","location":[2.95,0.96,0.66],"primitive_params":{"radius":0.2},"modifiers":[{"type":"subdivision","params":{"levels":1}}],"material":{"color":[0.2,0.6,0.15],"roughness":0.9,"metallic":0.0}},{"name":"plant_2_d","primitive":"uv_sphere","location":[3.05,1.02,0.62],"primitive_params":{"radius":0.23},"modifiers":[{"type":"subdivision","params":{"levels":1}}],"material":{"color":[0.18,0.62,0.16],"roughness":0.9,"metallic":0.0}}]}

Example 3 - "Make a snowman":
{"name":"snowman","description":"A classic three-ball snowman with carrot nose and coal eyes","unit_scale":1.0,"components":[{"name":"body_bottom","primitive":"uv_sphere","location":[0,0,0.6],"primitive_params":{"radius":0.6},"material":{"color":[0.95,0.95,0.97],"roughness":0.9,"metallic":0.0}},{"name":"body_middle","primitive":"uv_sphere","location":[0,0,1.5],"primitive_params":{"radius":0.45},"material":{"color":[0.95,0.95,0.97],"roughness":0.9,"metallic":0.0}},{"name":"head","primitive":"uv_sphere","location":[0,0,2.2],"primitive_params":{"radius":0.3},"material":{"color":[0.95,0.95,0.97],"roughness":0.9,"metallic":0.0}},{"name":"nose","primitive":"cone","location":[0,-0.3,2.25],"primitive_params":{"radius1":0.04,"depth":0.25},"rotation":[90,0,0],"material":{"color":[0.9,0.4,0.05],"roughness":0.7,"metallic":0.0}},{"name":"eye_left","primitive":"uv_sphere","location":[-0.1,-0.25,2.35],"primitive_params":{"radius":0.03},"material":{"color":[0.05,0.05,0.05],"roughness":0.5,"metallic":0.0}},{"name":"eye_right","primitive":"uv_sphere","location":[0.1,-0.25,2.35],"primitive_params":{"radius":0.03},"material":{"color":[0.05,0.05,0.05],"roughness":0.5,"metallic":0.0}}]}

Example 4 - "A table on the ground" (ground plane + bevel for realism):
{"name":"table_on_ground","description":"A wooden table on a ground plane","unit_scale":1.0,"components":[{"name":"ground","primitive":"plane","location":[0,0,0],"scale":[10,10,1],"material":{"color":[0.3,0.35,0.25],"roughness":0.95,"metallic":0.0,"procedural_bump":true}},{"name":"tabletop","primitive":"cube","location":[0,0,0.77],"scale":[1.2,0.7,0.04],"modifiers":[{"type":"bevel","params":{"width":0.02,"segments":2}}],"material":{"color":[0.55,0.35,0.17],"roughness":0.7,"metallic":0.0,"procedural_bump":true}},{"name":"leg_fl","primitive":"cylinder","location":[-0.55,-0.30,0.375],"primitive_params":{"radius":0.04,"depth":0.75},"material":{"color":[0.55,0.35,0.17],"roughness":0.7,"metallic":0.0}},{"name":"leg_fr","primitive":"cylinder","location":[0.55,-0.30,0.375],"primitive_params":{"radius":0.04,"depth":0.75},"material":{"color":[0.55,0.35,0.17],"roughness":0.7,"metallic":0.0}},{"name":"leg_bl","primitive":"cylinder","location":[-0.55,0.30,0.375],"primitive_params":{"radius":0.04,"depth":0.75},"material":{"color":[0.55,0.35,0.17],"roughness":0.7,"metallic":0.0}},{"name":"leg_br","primitive":"cylinder","location":[0.55,0.30,0.375],"primitive_params":{"radius":0.04,"depth":0.75},"material":{"color":[0.55,0.35,0.17],"roughness":0.7,"metallic":0.0}}]}
"""


class PlannerAgent:
    def __init__(self):
        self._model = model_config.planner_model
        # Verify model is available
        try:
            ollama.show(self._model)
        except Exception:
            warnings.warn(
                f"Model '{self._model}' not found in Ollama. "
                f"Run: ollama pull {self._model}",
                UserWarning,
                stacklevel=2,
            )

    def _plan_with_llm(self, prompt: str, feedback: str = "") -> ScenePlan:
        """
        Single LLM call using Ollama's native structured output.

        The `format` parameter constrains the model's output to valid JSON
        matching our ScenePlan schema at the token level — no parsing failures.
        """
        user_msg = prompt
        if feedback:
            user_msg = f"{prompt}\n\nIMPORTANT: {feedback}"

        response = ollama.chat(
            model=self._model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            format=SCENE_PLAN_SCHEMA,
            options={
                "temperature": 0,       # deterministic output
                "num_ctx": 8192,        # context window
            },
        )

        raw_json = response.message.content
        return self._parse_scene_plan(raw_json)

    def _parse_scene_plan(self, raw_json: str) -> ScenePlan:
        """Parse and validate JSON into a ScenePlan."""
        data = json.loads(raw_json)

        components: List[SceneComponent] = []
        for i, comp_data in enumerate(data.get("components", [])):
            if i >= MAX_COMPONENTS:
                warnings.warn(f"Truncated plan to {MAX_COMPONENTS} components", stacklevel=2)
                break

            primitive = comp_data.get("primitive", "cube")
            if primitive not in SUPPORTED_PRIMITIVES:
                raise ValueError(f"Unsupported primitive: {primitive!r}")

            # Parse material
            mat_data = comp_data.get("material")
            material = None
            if mat_data and isinstance(mat_data, dict):
                color = _to_float_tuple(mat_data.get("color", [0.8, 0.8, 0.8]), 3)
                material = MaterialSpec(
                    color=color,
                    roughness=float(mat_data.get("roughness", 0.5)),
                    metallic=float(mat_data.get("metallic", 0.0)),
                    alpha=float(mat_data.get("alpha", 1.0)),
                    procedural_bump=bool(mat_data.get("procedural_bump", False)),
                )

            # Parse modifiers
            modifiers: List[ModifierSpec] = []
            for mod_data in comp_data.get("modifiers", []):
                if isinstance(mod_data, dict):
                    mod_type = mod_data.get("type", "")
                    if mod_type in SUPPORTED_MODIFIERS:
                        modifiers.append(ModifierSpec(
                            type=mod_type,
                            params=mod_data.get("params", {}),
                        ))

            components.append(SceneComponent(
                name=comp_data.get("name", f"component_{i}"),
                primitive=primitive,
                location=_to_float_tuple(comp_data.get("location", [0, 0, 0]), 3),
                rotation=_to_float_tuple(comp_data.get("rotation", [0, 0, 0]), 3),
                scale=_to_float_tuple(comp_data.get("scale", [1, 1, 1]), 3),
                primitive_params=comp_data.get("primitive_params", {}),
                material=material,
                modifiers=modifiers,
                parent=comp_data.get("parent"),
            ))

        return ScenePlan(
            name=data.get("name", "scene"),
            description=data.get("description", ""),
            unit_scale=float(data.get("unit_scale", 1.0)),
            components=components,
        )

    def plan(self, prompt: str) -> ScenePlan:
        """
        Main planning entrypoint.

        Tries the LLM up to 3 times with error feedback, then falls back
        to a minimal single-component plan.
        """
        last_error: Optional[str] = None

        for attempt in range(3):
            try:
                feedback = ""
                if last_error:
                    feedback = (
                        f"Your previous output was invalid: {last_error}. "
                        "Output ONLY a valid JSON object matching the schema. "
                        "No markdown, no code, no explanations."
                    )
                return self._plan_with_llm(prompt, feedback=feedback)
            except Exception as e:
                last_error = str(e)
                if attempt < 2:
                    continue

        warnings.warn(
            f"Planner LLM failed after 3 attempts ({last_error!r}), using fallback. "
            "Check Ollama is running and model is pulled.",
            UserWarning,
            stacklevel=2,
        )
        return self._fallback_plan(prompt)

    def _fallback_plan(self, prompt: str) -> ScenePlan:
        """Minimal single-component fallback plan."""
        name = re.sub(r"[^a-z0-9]+", "_", prompt.lower().strip())[:40].strip("_") or "object"
        return ScenePlan(
            name=name,
            description=f"Fallback: {prompt}",
            unit_scale=1.0,
            components=[
                SceneComponent(
                    name=name,
                    primitive="uv_sphere",
                    location=(0.0, 0.0, 1.0),
                    primitive_params={"radius": 1.0},
                    material=MaterialSpec(color=(0.5, 0.5, 0.8)),
                ),
            ],
        )


def _to_float_tuple(val: Any, size: int) -> Tuple[float, ...]:
    """Coerce a value into a tuple of floats."""
    if isinstance(val, (list, tuple)):
        result = [float(v) for v in val[:size]]
        while len(result) < size:
            result.append(0.0)
        return tuple(result)
    return tuple(0.0 for _ in range(size))
