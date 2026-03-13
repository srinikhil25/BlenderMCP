"""
One-click launcher for AI Scene Builder (Option B: zero steps).

Starts:
  1. Ollama (bundled or system) so the planner LLM is available
  2. Plan-build API (FastAPI) on http://127.0.0.1:8765
  3. Blender with the AI Scene Builder addon installed and ready

User flow: double-click this (or the packaged exe) → Blender opens → type prompt → Plan & Build.

Usage:
  From repo root with venv active:
    python launcher/run_oneclick.py

  Environment (optional):
    OLLAMA_EXE       Path to ollama executable (default: ollama from PATH)
    BLENDER_EXE      Path to Blender executable (default: search common paths)
    API_PORT         Plan-build API port (default: 8765)
    SKIP_OLLAMA      Set to 1 to skip starting Ollama (e.g. already running)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

# Project root (parent of launcher/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
ADDON_SOURCE = PROJECT_ROOT / "addon_ai_scene"
API_PORT = int(os.environ.get("API_PORT", "8765"))
SKIP_OLLAMA = os.environ.get("SKIP_OLLAMA", "").strip().lower() in ("1", "true", "yes")


def find_ollama() -> str | None:
    exe = os.environ.get("OLLAMA_EXE")
    if exe and Path(exe).exists():
        return exe
    # Bundled: launcher/ollama/ollama.exe or similar
    bundled = PROJECT_ROOT / "launcher" / "ollama" / "ollama.exe"
    if bundled.exists():
        return str(bundled)
    # System PATH
    which = "where" if sys.platform == "win32" else "which"
    try:
        out = subprocess.run([which, "ollama"], capture_output=True, text=True, timeout=5)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip().splitlines()[0].strip()
    except Exception:
        pass
    return None


def find_blender() -> str | None:
    exe = os.environ.get("BLENDER_EXE")
    if exe and Path(exe).exists():
        return exe
    # Common Windows paths
    if sys.platform == "win32":
        for base in [
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Blender Foundation" / "Blender 4.2",
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Blender Foundation" / "Blender 4.1",
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Blender Foundation" / "Blender 4.0",
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "Blender Foundation" / "Blender 3.6",
        ]:
            candidate = base / "blender.exe"
            if candidate.exists():
                return str(candidate)
        # Portable / bundled
        bundled = PROJECT_ROOT / "launcher" / "blender" / "blender.exe"
        if bundled.exists():
            return str(bundled)
    else:
        try:
            out = subprocess.run(["which", "blender"], capture_output=True, text=True, timeout=5)
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip().splitlines()[0].strip()
        except Exception:
            pass
    return None


def get_blender_addons_dir(blender_exe: str) -> Path | None:
    """Return the scripts/addons directory for this Blender install."""
    exe_path = Path(blender_exe).resolve()
    # Blender 4.x: .../Blender 4.2/blender.exe -> .../Blender 4.2/4.2/scripts/addons
    base = exe_path.parent
    for sub in ("4.2", "4.1", "4.0", "3.6", "3.5"):
        addons = base / sub / "scripts" / "addons"
        if addons.is_dir():
            return addons
    # Fallback: same folder as exe
    addons = base / "scripts" / "addons"
    if addons.is_dir():
        return addons
    return base / "scripts" / "addons"


def install_addon(blender_exe: str) -> bool:
    """Copy addon_ai_scene into Blender's addons directory."""
    if not ADDON_SOURCE.is_dir():
        print("Addon source not found:", ADDON_SOURCE)
        return False
    addons_dir = get_blender_addons_dir(blender_exe)
    if not addons_dir:
        print("Could not find Blender addons directory")
        return False
    addons_dir.mkdir(parents=True, exist_ok=True)
    dest = addons_dir / "addon_ai_scene"
    try:
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(ADDON_SOURCE, dest)
        print("Addon installed at", dest)
        return True
    except Exception as e:
        print("Failed to install addon:", e)
        return False


def start_ollama(ollama_exe: str) -> subprocess.Popen | None:
    """Start ollama serve in background."""
    try:
        proc = subprocess.Popen(
            [ollama_exe, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(Path(ollama_exe).parent),
        )
        print("Ollama started (PID %s)" % proc.pid)
        return proc
    except Exception as e:
        print("Failed to start Ollama:", e)
        return None


def wait_for_ollama(timeout: float = 30.0) -> bool:
    import urllib.request
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        try:
            urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def run_api_server(port: int) -> None:
    """Run FastAPI plan_build server (blocking)."""
    sys.path.insert(0, str(PROJECT_ROOT))
    from src.api.plan_build_api import run_api
    run_api(host="127.0.0.1", port=port)


def main() -> int:
    print("AI Scene Builder – one-click launcher")
    print("Project root:", PROJECT_ROOT)

    # 1) Ollama
    ollama_proc = None
    if not SKIP_OLLAMA:
        ollama_exe = find_ollama()
        if ollama_exe:
            ollama_proc = start_ollama(ollama_exe)
            if ollama_proc and not wait_for_ollama():
                print("Ollama did not become ready in time; continuing anyway.")
        else:
            print("Ollama not found. Set OLLAMA_EXE or add ollama to PATH. API will still run.")
    else:
        print("Skipping Ollama (SKIP_OLLAMA=1)")

    # 2) Plan-build API in background thread
    def run_api_thread():
        run_api_server(API_PORT)

    api_thread = threading.Thread(target=run_api_thread, daemon=True)
    api_thread.start()
    time.sleep(1.0)
    print("Plan-build API on http://127.0.0.1:%s" % API_PORT)

    # 3) Blender
    blender_exe = find_blender()
    if not blender_exe:
        print("Blender not found. Install Blender or set BLENDER_EXE.")
        return 1
    print("Blender:", blender_exe)

    if not install_addon(blender_exe):
        print("Addon install failed; continuing. Enable 'AI Scene Builder' manually in Blender add-ons.")

    # Launch Blender with startup script to enable addon (idempotent)
    enable_script = PROJECT_ROOT / "launcher" / "enable_addon_once.py"
    launch_cmd = [blender_exe]
    if enable_script.exists():
        launch_cmd.extend(["-P", str(enable_script)])
    try:
        subprocess.Popen(launch_cmd, cwd=str(PROJECT_ROOT))
        print("Blender launched. Open sidebar (N) > AI Scene Builder, type a prompt, then Plan & Build.")
    except Exception as e:
        print("Failed to start Blender:", e)
        return 1

    if ollama_proc:
        try:
            ollama_proc.wait()
        except KeyboardInterrupt:
            ollama_proc.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
