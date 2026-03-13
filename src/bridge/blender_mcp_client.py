"""
Blender MCP bridge.

Connects to a running Blender MCP server over stdio and executes
generated `bpy` scripts using the `execute_blender_code` tool.
Also provides scene introspection via `get_scene_info`.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any

from mcp import ClientSession, StdioServerParameters, types  # type: ignore
from mcp.client.stdio import stdio_client  # type: ignore


@dataclass
class ExecutionResult:
    ok: bool
    stdout: str
    stderr: str


@dataclass
class SceneInfo:
    ok: bool
    data: dict
    error: str


def _extract_json_object(text: str) -> dict[str, Any]:
    """Best-effort parse for JSON object embedded in text."""
    stripped = text.strip()
    if not stripped:
        return {}

    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}") + 1
        if start != -1 and end > start:
            try:
                parsed = json.loads(stripped[start:end])
                return parsed if isinstance(parsed, dict) else {"value": parsed}
            except json.JSONDecodeError:
                return {"raw": stripped}
        return {"raw": stripped}


def _normalize_tool_payload(payload: Any) -> dict[str, Any]:
    """
    Normalize MCP call_tool result payload to a scene-info dict.

    Blender MCP commonly wraps tool output as:
    {"status": "success", "result": {...scene info...}}
    """
    if isinstance(payload, dict):
        result = payload.get("result")
        if isinstance(result, dict):
            return result
        return payload
    return {}


def _default_server_params() -> StdioServerParameters:
    """
    Build stdio server parameters for Blender MCP.

    On Windows, the recommended command is: cmd /c uvx blender-mcp
    Override via BLENDER_MCP_COMMAND / BLENDER_MCP_ARGS env vars.
    """
    cmd = os.environ.get("BLENDER_MCP_COMMAND")
    if cmd:
        args = os.environ.get("BLENDER_MCP_ARGS", "").split()
        return StdioServerParameters(command=cmd, args=args)

    return StdioServerParameters(
        command="cmd",
        args=["/c", "uvx", "blender-mcp"],
    )


def _ensure_build_invocation(script: str) -> str:
    """
    If the script defines a top-level function but never calls it, append a call.
    """
    import re

    match = re.search(r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", script)
    if not match:
        return script

    func_name = match.group(1)
    if script.count(f"{func_name}(") > 1:
        return script

    return script.rstrip() + f"\n\n{func_name}()\n"


async def _execute_async(script: str) -> ExecutionResult:
    params = _default_server_params()
    try:
        code = _ensure_build_invocation(script)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                result = await session.call_tool(
                    "execute_blender_code", arguments={"code": code}
                )

                stdout_parts: list[str] = []
                stderr_parts: list[str] = []

                for item in result.content:
                    if isinstance(item, types.TextContent):
                        stdout_parts.append(item.text)

                if result.isError:
                    stderr_parts.append(str(result.structuredContent))

                return ExecutionResult(
                    ok=not result.isError,
                    stdout="\n".join(stdout_parts).strip(),
                    stderr="\n".join(stderr_parts).strip(),
                )
    except Exception as e:
        return ExecutionResult(ok=False, stdout="", stderr=str(e))


def execute_in_blender(script: str) -> ExecutionResult:
    """Execute a bpy script inside Blender via Blender MCP."""
    return asyncio.run(_execute_async(script))


async def _get_scene_info_async() -> SceneInfo:
    params = _default_server_params()
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "get_scene_info",
                    arguments={"random_string": "inspect"},
                )
                # Prefer structured content when available.
                normalized = _normalize_tool_payload(result.structuredContent)
                # If we can see standard scene keys, treat this as success
                if isinstance(normalized, dict) and (
                    "objects" in normalized or "object_count" in normalized
                ):
                    return SceneInfo(ok=True, data=normalized, error="")

                for item in result.content:
                    if isinstance(item, types.TextContent):
                        parsed = _extract_json_object(item.text)
                        normalized = _normalize_tool_payload(parsed)
                        if isinstance(normalized, dict) and (
                            "objects" in normalized or "object_count" in normalized
                        ):
                            return SceneInfo(ok=True, data=normalized, error="")
                        return SceneInfo(ok=not result.isError, data=parsed, error="")
                return SceneInfo(ok=False, data={}, error="No text content in response")
    except Exception as e:
        return SceneInfo(ok=False, data={}, error=str(e))


def get_scene_info() -> SceneInfo:
    """Get current scene info from Blender via MCP."""
    return asyncio.run(_get_scene_info_async())


async def _get_object_info_async(object_name: str) -> SceneInfo:
    params = _default_server_params()
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "get_object_info",
                    arguments={"object_name": object_name},
                )
                for item in result.content:
                    if isinstance(item, types.TextContent):
                        try:
                            data = json.loads(item.text)
                        except json.JSONDecodeError:
                            data = {"raw": item.text}
                        return SceneInfo(ok=True, data=data, error="")
                return SceneInfo(ok=False, data={}, error="No text content in response")
    except Exception as e:
        return SceneInfo(ok=False, data={}, error=str(e))


def get_object_info(object_name: str) -> SceneInfo:
    """Get info about a specific object from Blender via MCP."""
    return asyncio.run(_get_object_info_async(object_name))
