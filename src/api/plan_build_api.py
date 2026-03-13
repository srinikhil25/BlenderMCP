"""
Plan-Build HTTP API (no MCP).

Used by the one-click launcher: addon in Blender POSTs prompt here,
gets back the bpy script and runs it inside Blender.
"""

from __future__ import annotations

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.agents.planner_agent import PlannerAgent
from src.codegen.scene_builder import build_script
from src.codegen.verify_script import verify_bpy_script


class PlanBuildRequest(BaseModel):
    prompt: str


class PlanBuildResponse(BaseModel):
    ok: bool
    script: str
    plan_name: str
    component_count: int
    verification_notes: str
    error: str | None = None


def plan_build_return_script(prompt: str) -> PlanBuildResponse:
    """Plan from prompt, build bpy script, verify; return script (no execution)."""
    try:
        planner = PlannerAgent()
        plan = planner.plan(prompt)
        script = build_script(plan)
        verification = verify_bpy_script(script)
        return PlanBuildResponse(
            ok=verification.ok,
            script=script,
            plan_name=plan.name,
            component_count=len(plan.components),
            verification_notes=verification.notes,
            error=None,
        )
    except Exception as e:
        return PlanBuildResponse(
            ok=False,
            script="",
            plan_name="",
            component_count=0,
            verification_notes="",
            error=str(e),
        )


app = FastAPI(title="Blender AI Scene Builder API", version="1.0.0")


@app.post("/plan_build", response_model=PlanBuildResponse)
def plan_build(req: PlanBuildRequest):
    """Generate bpy script from a text prompt. Caller runs the script inside Blender."""
    out = plan_build_return_script(req.prompt)
    if out.error and not out.script:
        raise HTTPException(status_code=500, detail=out.error)
    return out


@app.get("/health")
def health():
    return {"status": "ok"}


def run_api(host: str = "127.0.0.1", port: int = 8765):
    uvicorn.run(app, host=host, port=port, log_level="info")
