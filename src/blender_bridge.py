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


async def _call_tool(
    tool_name: str,
    arguments: dict,
    lenient: bool = False,
    timeout: float | None = None,
) -> ExecutionResult:
    """Open an MCP connection, call one tool, return the result.

    If *lenient* is True, skip heuristic error-marker scanning in stdout.
    If *timeout* is set (seconds), abort after that duration.
    """
    params = _server_params()
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # Wrap the tool call with an optional timeout
                if timeout:
                    call_coro = session.call_tool(tool_name, arguments=arguments)
                    result = await asyncio.wait_for(call_coro, timeout=timeout)
                else:
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
                if not has_error and not lenient and "SUCCESS:" not in stdout:
                    stdout_lower = stdout.lower()
                    error_markers = [
                        "error:", "traceback (", "exception:", "could not be found",
                        "attributeerror", "typeerror", "nameerror", "syntaxerror",
                    ]
                    if any(m in stdout_lower for m in error_markers):
                        has_error = True
                        stderr = stdout

                return ExecutionResult(ok=not has_error, stdout=stdout, stderr=stderr)
    except asyncio.TimeoutError:
        secs = int(timeout) if timeout else "?"
        return ExecutionResult(
            ok=False, stdout="",
            stderr=f"Operation timed out after {secs}s. The scene may be too complex or Blender is unresponsive.",
        )
    except Exception as e:
        return ExecutionResult(ok=False, stdout="", stderr=str(e))


def execute_code(code: str, timeout: float | None = None) -> ExecutionResult:
    """Execute a bpy script in Blender via MCP."""
    from src.config import BLENDER_EXEC_TIMEOUT
    t = timeout or BLENDER_EXEC_TIMEOUT
    return asyncio.run(_call_tool("execute_blender_code", {"code": code}, timeout=t))


def get_scene_info() -> ExecutionResult:
    """Get scene info from Blender via MCP."""
    return asyncio.run(_call_tool(
        "get_scene_info", {"random_string": "inspect"}, lenient=True, timeout=15,
    ))


def ping_blender() -> bool:
    """Quick connectivity check — returns True if Blender responds."""
    result = asyncio.run(_call_tool(
        "execute_blender_code",
        {"code": "import bpy; print('SUCCESS: PONG', len(bpy.data.objects), 'objects')"},
        timeout=10,
    ))
    return result.ok


def render_preview(output_path: str, width: int = 960, height: int = 540) -> ExecutionResult:
    """Render the current scene to an image file via MCP."""
    from src.config import RENDER_TIMEOUT
    # Use forward slashes to avoid Windows unicode escape issues in Blender Python
    safe_path = output_path.replace("\\", "/")
    render_code = f'''\
import bpy

# Store original settings
scene = bpy.context.scene
orig_x = scene.render.resolution_x
orig_y = scene.render.resolution_y
orig_pct = scene.render.resolution_percentage
orig_path = scene.render.filepath

# Set preview resolution
scene.render.resolution_x = {width}
scene.render.resolution_y = {height}
scene.render.resolution_percentage = 100
scene.render.filepath = "{safe_path}"
scene.render.image_settings.file_format = 'PNG'

# Render
bpy.ops.render.render(write_still=True)

# Restore original settings
scene.render.resolution_x = orig_x
scene.render.resolution_y = orig_y
scene.render.resolution_percentage = orig_pct
scene.render.filepath = orig_path

print("SUCCESS: Preview rendered")
'''
    return asyncio.run(_call_tool(
        "execute_blender_code", {"code": render_code}, timeout=RENDER_TIMEOUT,
    ))
