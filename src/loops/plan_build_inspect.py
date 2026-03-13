"""
Top-level Plan-Build-Inspect loop.

Pipeline:
1. PlannerAgent: prompt -> ScenePlan (LLM decomposes into components)
2. AlignPlan: deterministic alignment fix (snap components together)
3. SceneBuilder: ScenePlan -> bpy script (deterministic, no LLM)
4. verify_bpy_script: static safety check
5. execute_in_blender: run via MCP
6. InspectorAgent: verify scene state via MCP
"""

from src.agents.planner_agent import PlannerAgent
from src.agents.inspector_agent import InspectorAgent
from src.codegen.scene_builder import build_script
from src.codegen.verify_script import verify_bpy_script
from src.bridge.blender_mcp_client import execute_in_blender
from src.planner.align_plan import align_plan


def plan_build_inspect(prompt: str):
    # Step 1: Plan (LLM decomposes prompt into primitive components)
    planner = PlannerAgent()
    plan = planner.plan(prompt)

    # Step 2: Align (deterministic fix for LLM coordinate errors)
    plan, alignment_log = align_plan(plan)
    if alignment_log:
        print("--- Alignment adjustments ---")
        for msg in alignment_log:
            print(f"  {msg}")
        print()

    # Step 3: Build script deterministically from the plan
    script = build_script(plan)

    # Step 4: Verify (safety net for the deterministic output)
    verification = verify_bpy_script(script)

    # Step 5: Execute in Blender via MCP
    exec_result = execute_in_blender(script)

    # Step 6: Inspect (compare expected objects vs actual scene state)
    inspector = InspectorAgent()
    inspection = inspector.inspect(plan, exec_result)

    return {
        "plan": plan,
        "script_preview": script[:2000],
        "verification": verification,
        "execution": exec_result,
        "inspection": inspection,
    }
