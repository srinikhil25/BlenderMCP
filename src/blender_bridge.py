"""Blender MCP bridge — execute code and inspect scenes in Blender."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client

from src.config import BLENDER_MCP_CMD, BLENDER_MCP_ARGS


@dataclass
class ExecutionResult:
    ok: bool
    stdout: str
    stderr: str


def _server_params() -> StdioServerParameters:
    return StdioServerParameters(command=BLENDER_MCP_CMD, args=BLENDER_MCP_ARGS)


async def _call_tool(tool_name: str, arguments: dict) -> ExecutionResult:
    """Open an MCP connection, call one tool, return the result."""
    params = _server_params()
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments=arguments)

                stdout_parts: list[str] = []
                for item in result.content:
                    if isinstance(item, types.TextContent):
                        stdout_parts.append(item.text)

                stdout = "\n".join(stdout_parts).strip()
                stderr = ""
                if result.isError:
                    stderr = str(result.structuredContent or "execution error")

                # Detect errors reported in stdout (blender-mcp often does this)
                has_error = result.isError
                if not has_error and "SUCCESS:" not in stdout:
                    stdout_lower = stdout.lower()
                    error_markers = [
                        "error:", "traceback (", "exception:", "could not be found",
                        "attributeerror", "typeerror", "nameerror", "syntaxerror",
                    ]
                    if any(m in stdout_lower for m in error_markers):
                        has_error = True
                        stderr = stdout

                return ExecutionResult(ok=not has_error, stdout=stdout, stderr=stderr)
    except Exception as e:
        return ExecutionResult(ok=False, stdout="", stderr=str(e))


def execute_code(code: str) -> ExecutionResult:
    """Execute a bpy script in Blender via MCP."""
    return asyncio.run(_call_tool("execute_blender_code", {"code": code}))


def get_scene_info() -> ExecutionResult:
    """Get scene info from Blender via MCP."""
    return asyncio.run(_call_tool("get_scene_info", {"random_string": "inspect"}))
