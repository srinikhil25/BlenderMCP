## Blender Generative 3D (CLI-first, MCP-ready)

This project lets you say things like **"Draw a home"** and have Blender generate a simple 3D structure for you using Python (`bpy`).  
The first step is a **CLI application**; its core logic is designed so it can later be wrapped as an **MCP server tool**.

---

### 1. Prerequisites

- **Blender 4.0+** installed.
- Blender executable available on your `PATH` as `blender`, **or** an environment variable `BLENDER_PATH` pointing to it (e.g. `C:\Program Files\Blender Foundation\Blender 4.0\blender.exe`).
- **Python 3.10+** on your system (this project runs *outside* Blender and calls Blender as a subprocess).

Install Python dependencies:

```bash
pip install -r requirements.txt
```

---

### 2. Usage: "Draw a home"

From the project root:

```bash
python app.py "Draw a home"
```

What this does:

- Parses the prompt (currently checks for keywords like `home` / `house`).
- Generates a temporary Blender Python script that:
  - Clears the scene.
  - Creates a simple **foundation**, **walls**, **roof**, and **boolean cutouts** for **windows** and **doors**.
  - Applies simple BSDF materials.
- Launches Blender in **background mode** to execute that script.

After it runs:

- Re-open Blender normally and load the most recent project, or
- Modify `app.py` to open Blender in GUI mode instead of `--background` if you want it interactive.

---

### 3. Configuration

You can configure how Blender is invoked via environment variables:

- **`BLENDER_PATH`**: explicit path to Blender executable.

Example (PowerShell):

```powershell
$env:BLENDER_PATH = "C:\Program Files\Blender Foundation\Blender 4.0\blender.exe"
python app.py "Draw a home"
```

---

### 4. MCP Integration (Next Step)

This repo currently exposes the logic as a **CLI app**.  
To turn it into a full **MCP server**, you would:

- Wrap the core function `generate_structure_from_prompt(prompt: str)` in an MCP tool.
- Expose a tool like `create_3d_structure` that:
  - Takes a natural-language prompt.
  - Calls the same script-generation logic.
  - Invokes Blender and returns a status message or output file path.

The Blender-side logic (mesh creation, materials, cleanup) already follows the rules in `.cursorrules`, so it can be reused directly in an MCP server implementation.

---

### 5. Known Limitations

- Only a **basic "home"** shape is supported right now.
- No complex floor plans or furniture yet.
- No robust prompt parsing; this is a proof-of-concept you can extend.

