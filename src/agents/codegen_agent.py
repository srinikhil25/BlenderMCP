"""
Code generation agent (LLM-backed).

Turns a `GeometryPlan` into an executable Blender 4.0+ `bpy` script.
"""

from __future__ import annotations

import json
from dataclasses import asdict

from smolagents import LiteLLMModel, ToolCallingAgent  # type: ignore

from src.agents.ollama_utils import extract_text_content, ollama_model_id, text_block_messages
from src.codegen.verify_script import verify_bpy_script, VerificationResult
from src.config import model_config
from src.planner.geometry_planner import GeometryPlan


SYSTEM_PROMPT = """
You are a Blender 4.0+ procedural modeling code generator.

You receive a JSON plan for an inorganic structure. You must output ONLY Python code
that can run inside Blender (bpy), headless, without manual UI actions.

Hard requirements:
- Use Blender 4.0+ `bpy`.
- Prefer data-block manipulation; avoid `bpy.ops` except for simple scene cleanup if necessary.
- Wrap the top-level build in try/except and print meaningful errors before re-raising.
- Set `scene.unit_settings.scale_length` from plan.parameters.unit_scale (default 1.0).
- Create every mesh via `bpy.data.meshes.new(...)`, every object via `bpy.data.objects.new(..., mesh)`, and link each to the scene with `bpy.context.scene.collection.objects.link(obj)`. Do not rely on `bpy.ops.mesh.primitive_*` for the main structure.
- Include a `sanity_check(obj)` function. It must reject missing/zero-dimension objects.
- When building geometry:
  - Use a regular Mesh with `mesh.from_pydata(verts, edges, faces)` and then assign it to an object.
  - Do NOT use `bmesh.edges.new` or `bmesh.faces.new` in this generated code.
- NEVER call `from_pydata` on a BMesh object (that API does not exist).
- If you use the `random` module (e.g. for placement or variation), add `import random` at the top.
- For mesh.from_pydata(verts, edges, faces): verts and faces must be consistent—every index in faces must be a valid index into verts (e.g. 5 verts = indices 0–4 only).
- Do NOT include markdown fences or explanations. Only code.
"""


class CodegenAgent:
    def __init__(self, api_base: str = "http://127.0.0.1:11434"):
        model = LiteLLMModel(
            model_id=ollama_model_id(model_config.codegen_model),
            api_base=api_base,
            num_ctx=8192,
            flatten_messages_as_text=True,
        )
        self._agent = ToolCallingAgent(
            model=model,
            tools=[],
            name="codegen_agent",
            description="Generates bpy scripts from structured geometry plans.",
        )

    def _prompt_for_plan(self, plan: GeometryPlan) -> str:
        # Keep the plan payload small and deterministic.
        payload = asdict(plan)
        return json.dumps(payload, ensure_ascii=False)

    def _strip_markdown_fences(self, text: str) -> str:
        """
        LLMs sometimes wrap code in ``` or ```python fences.
        Blender needs raw Python, so strip a single outer fence if present.
        """
        s = text.strip()
        if s.startswith("```"):
            # Remove leading ```...\\n
            first_nl = s.find("\n")
            if first_nl != -1:
                s = s[first_nl + 1 :]
        if s.endswith("```"):
            s = s[:-3]
        return s.strip()

    def _generate_once(self, plan: GeometryPlan, extra_instructions: str = "") -> str:
        user = self._prompt_for_plan(plan)
        if extra_instructions:
            user = user + "\n\n" + extra_instructions
        messages = text_block_messages(SYSTEM_PROMPT, user)
        response = self._agent.model.generate(messages)  # type: ignore[attr-defined]
        raw = extract_text_content(response)
        return self._strip_markdown_fences(raw)

    def generate(self, plan: GeometryPlan) -> tuple[str, VerificationResult]:
        """
        Pure LLM-based codegen with static verification.

        Strategy:
        - Attempt up to 3 LLM generations.
        - After each, run the static verifier.
        - Return the first script that passes verification, or the last attempt
          (even if it fails). Never fall back to hard-coded geometry.
        """
        last_script = ""
        last_verdict: VerificationResult | None = None

        for _ in range(3):
            extra = ""
            if last_verdict is not None and not last_verdict.ok:
                extra = (
                    "Improve the previous script to satisfy ALL verifier findings "
                    "below. Output ONLY corrected Python code. Do not change the "
                    "overall structure if not needed.\n\n"
                    f"{last_verdict.notes}"
                )

            script = self._generate_once(plan, extra_instructions=extra)
            verdict = verify_bpy_script(script)
            last_script, last_verdict = script, verdict

            if verdict.ok:
                break

        assert last_verdict is not None
        return last_script, last_verdict

