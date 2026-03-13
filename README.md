# Local Creative Agent

A **local-first, multi-tool creative engineering agent** that plans, builds, and inspects artifacts using free, open-source tools. You pick a tool and a project, type what you want, and the agent generates and runs the right operations.

## Two ways to run

| Audience | Flow | What you need |
|----------|------|----------------|
| **Complete novices** | One-click launcher → Blender opens → prompt in sidebar → **Plan & Build** | Ollama + Blender (or [bundle everything](launcher/README.md)); no MCP, no terminal. |
| **Developers / power users** | Desktop app, CLI, or MCP | Same + Blender MCP addon + `uvx blender-mcp` for inspect. |

## Quick start (one-click, no MCP)

1. **Install once:** [Ollama](https://ollama.com), [Blender](https://www.blender.org/download/), then:
   ```bash
   ollama pull qwen2.5-coder:7b
   ```
2. **Clone and install deps:**
   ```bash
   git clone <repo>
   cd BlenderMCP
   python -m venv venv
   venv\Scripts\activate   # Windows
   pip install -r requirements.txt
   ```
3. **Run the launcher:**
   ```bash
   python launcher/run_oneclick.py
   ```
   Blender opens with the **AI Scene Builder** addon. Press **N** → tab **AI Scene Builder** → type a prompt (e.g. *Create a house with plants*) → **Plan & Build**.

For bundling Blender + Ollama so users only double-click one app, see [launcher/README.md](launcher/README.md).

## Architecture

The agent uses a **Plan → Build → Inspect** pipeline:

1. **Plan (LLM):** The user's prompt is decomposed into a structured `ScenePlan` — a list of primitive 3D components (cubes, spheres, cylinders, cones, etc.) with positions, rotations, scales, materials, and modifiers. The LLM outputs JSON only, never code.

2. **Build (Deterministic):** A `SceneBuilder` converts the `ScenePlan` into a reliable `bpy` script using `bpy.ops.mesh.primitive_*_add`. No LLM involved in code generation.

3. **Inspect (optional, MCP):** When using the CLI/desktop with MCP, the inspector calls Blender's `get_scene_info` via MCP to verify expected objects.

### Supported tools

- **Blender** — Procedural 3D structures (implemented)
- **Obsidian** — Knowledge graphs and markdown (planned)
- **Krita** — Layered 2D compositions (planned)

## Running (all options)

- **One-click (novices)** — Launcher starts Ollama, plan-build API, and Blender; you only prompt in Blender.
  ```bash
  python launcher/run_oneclick.py
  ```

- **Desktop app** — Pick Blender (or other tool), enter prompt, click Run. Uses MCP if Blender MCP is running.
  ```bash
  python -m src.ui.desktop
  ```

- **CLI** — Plan, build, execute in Blender via MCP, then inspect.
  ```bash
  python -m src.main "Create a house with plants"
  ```
  Requires `uvx blender-mcp` and Blender with the Blender MCP addon.

- **Plan-build API only** — For the addon or custom UIs. No MCP.
  ```bash
  uvicorn src.api.plan_build_api:app --host 127.0.0.1 --port 8765
  ```
  Then `POST /plan_build` with `{"prompt": "Create a snowman"}`; returns `{ "script", "plan_name", ... }`.

- **Legacy HTTP API**
  ```bash
  uvicorn src.ui.api:app --reload
  ```
  Then `POST /run` with JSON: `{ "tool": "blender", "root_path": ".", "prompt": "..." }`.

## Setup (for CLI / desktop / MCP)

For the **one-click** flow you only need Ollama + Blender + the repo (see Quick start above). For **CLI** or **desktop app** with Blender MCP:

- Install Blender 4.x and the **Blender MCP** addon; start the addon’s socket server.
- In a terminal: `uvx blender-mcp` (keep it running).

Override MCP/Blender via env: `BLENDER_MCP_COMMAND`, `BLENDER_MCP_ARGS`, `BLENDER_EXE`. See [launcher/README.md](launcher/README.md) for `OLLAMA_EXE`, `API_PORT`, etc.

## How it works

When you type "Create a house with plants", the LLM produces:
```json
{
  "components": [
    {"name": "walls", "primitive": "cube", "location": [0,0,1.5], "scale": [2,1.5,1.5], "material": {"color": [0.85,0.78,0.65]}},
    {"name": "roof", "primitive": "cone", "location": [0,0,3.5], ...},
    {"name": "door", "primitive": "cube", ...},
    {"name": "plant_1", "primitive": "uv_sphere", ...},
    ...
  ]
}
```

The SceneBuilder then deterministically generates reliable `bpy` code that creates each primitive, applies materials, and sets up the scene.

## Configuration

- **Models** — `src/config.py`: `planner_model` (default: `qwen2.5-coder:7b`).
- **Blender MCP** — Env: `BLENDER_MCP_COMMAND`, `BLENDER_MCP_ARGS`.
- **One-click launcher** — Env: `OLLAMA_EXE`, `BLENDER_EXE`, `API_PORT`, `SKIP_OLLAMA`. See [launcher/README.md](launcher/README.md).
