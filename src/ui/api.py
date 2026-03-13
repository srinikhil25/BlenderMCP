"""
Minimal FastAPI server exposing the agent as an HTTP API.

Usage (from project root, after installing requirements):

    uvicorn src.ui.api:app --reload

Then POST a request like:

    {
      "tool": "blender",
      "root_path": "D:/BlenderMCP",
      "sub_scope": null,
      "prompt": "Create a house with plants"
    }
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from pydantic import BaseModel, Field

from src.core.models import ProjectScope, ToolType
from src.core.runner import run_request


class RunRequest(BaseModel):
    tool: ToolType = Field(description="Target tool: blender | obsidian | krita")
    root_path: str = Field(description="Root path for the project")
    sub_scope: Optional[str] = Field(
        default=None,
        description="Optional sub-scope within the project",
    )
    prompt: str = Field(description="Natural language instruction for the agent")


class RunResponse(BaseModel):
    tool: str
    scope: Dict[str, Any]
    result: Dict[str, Any]


app = FastAPI(title="Local Creative Agent API", version="0.2.0")


@app.get("/tools", response_model=List[str])
def list_tools() -> List[str]:
    """List supported tools."""
    return [t.value for t in ToolType]


@app.post("/run", response_model=RunResponse)
def run(run_req: RunRequest) -> RunResponse:
    """Run the Plan-Build-Inspect loop for the selected tool and project."""
    scope = ProjectScope(
        tool=run_req.tool,
        root_path=Path(run_req.root_path),
        sub_scope=run_req.sub_scope,
    )
    payload = run_request(run_req.prompt, scope)
    return RunResponse(**payload)
