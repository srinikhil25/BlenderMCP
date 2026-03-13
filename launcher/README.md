# One-click launcher (Option B: zero steps for novices)

The launcher starts Ollama (if available), the plan-build API, and Blender with the **AI Scene Builder** addon. The user only opens one app and prompts inside Blender.

## Quick run (you have Ollama + Blender installed)

From repo root with venv active:

```bash
python launcher/run_oneclick.py
```

- **Ollama** — Started automatically (or use existing). Ensure the planner model is pulled: `ollama pull qwen2.5-coder:7b`.
- **API** — Runs at `http://127.0.0.1:8765` (override with `API_PORT`).
- **Blender** — Launched with the addon installed; startup script enables the addon on first run.

In Blender: press **N** → tab **AI Scene Builder** → type e.g. "Create a house with plants" → **Plan & Build**.

## Environment variables

| Variable       | Purpose |
|----------------|--------|
| `OLLAMA_EXE`   | Path to `ollama` (default: from PATH or `launcher/ollama/ollama.exe`) |
| `BLENDER_EXE`  | Path to Blender executable (default: search common install paths) |
| `API_PORT`     | Plan-build API port (default: `8765`) |
| `SKIP_OLLAMA`  | Set to `1` to skip starting Ollama (e.g. already running) |

## Bundling for true zero steps (no user install)

To ship a single “double-click” experience with **no** separate install of Ollama or Blender:

1. **Bundle Ollama**
   - Place Ollama binary in `launcher/ollama/` (e.g. `ollama.exe` on Windows).
   - On first run the launcher starts it; optionally run `ollama pull qwen2.5-coder:7b` once from an installer or first-run script.

2. **Bundle Blender**
   - Use a [portable Blender](https://www.blender.org/download/) build and put it under `launcher/blender/` (e.g. `launcher/blender/blender.exe`).
   - The launcher will use it if `BLENDER_EXE` is unset and this path exists.

3. **Package the launcher**
   - Use PyInstaller (or similar) to build a single executable from `run_oneclick.py`, including the project root so that `addon_ai_scene` and `src` are available (e.g. as data files or bundled in the exe).
   - The exe should:
     - Start Ollama from the bundled path (or `OLLAMA_EXE`).
     - Start the plan-build API (e.g. in a thread or subprocess).
     - Start Blender (bundled or from `BLENDER_EXE`), install the addon, and run with `-P launcher/enable_addon_once.py`.

4. **Installer (optional)**
   - A simple installer can: unpack Blender + Ollama + your exe into a folder, run `ollama pull qwen2.5-coder:7b` once, and create a desktop shortcut to the launcher exe. After that, the user only double-clicks the shortcut.

## Addon-only (no launcher)

If the launcher is not used, someone can still use the addon with the API running separately:

1. Install the addon: copy `addon_ai_scene` into Blender’s `scripts/addons` (or install from zip).
2. Start the plan-build API: `uvicorn src.api.plan_build_api:app --host 127.0.0.1 --port 8765`.
3. In Blender: enable **AI Scene Builder**, set prompt, click **Plan & Build**.

The addon’s **API URL** in the panel defaults to `http://127.0.0.1:8765`; change it if your API runs elsewhere.
