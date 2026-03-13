"""Desktop GUI for BlenderMCP — Tkinter application."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import scrolledtext

from src.config import MAX_RETRIES
from src.llm import generate_bpy_code
from src.safety import validate_code
from src.blender_bridge import execute_code, get_scene_info
from src.scene_setup import generate_camera_lighting_code


# --- Colors ---
BG_DARK = "#1e293b"
BG_LIGHT = "#f8fafc"
BG_LOG = "#0f172a"
FG_LOG = "#e2e8f0"
ACCENT = "#0d9488"
ACCENT_HOVER = "#0f766e"
FG_DARK = "#f1f5f9"
FG_BODY = "#1e293b"
FONT_BODY = ("Segoe UI", 11)
FONT_MONO = ("Consolas", 10)
FONT_HEADER = ("Segoe UI", 14, "bold")
FONT_STATUS = ("Segoe UI", 10)


class BlenderMCPApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("BlenderMCP")
        self.geometry("720x580")
        self.minsize(600, 480)
        self.configure(bg=BG_LIGHT)
        self._build_ui()

    def _build_ui(self) -> None:
        # --- Header ---
        header = tk.Frame(self, bg=BG_DARK, height=48)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(
            header, text="BlenderMCP  -  Text to 3D", font=FONT_HEADER,
            bg=BG_DARK, fg=FG_DARK,
        ).pack(side=tk.LEFT, padx=16, pady=8)

        # --- Body ---
        body = tk.Frame(self, bg=BG_LIGHT, padx=16, pady=12)
        body.pack(fill=tk.BOTH, expand=True)

        tk.Label(body, text="Describe your scene:", font=FONT_BODY, bg=BG_LIGHT, fg=FG_BODY).pack(anchor=tk.W)

        self._prompt = tk.Text(body, height=4, font=FONT_BODY, wrap=tk.WORD, relief=tk.SOLID, bd=1)
        self._prompt.pack(fill=tk.X, pady=(4, 8))
        self._prompt.bind("<Return>", self._on_enter)

        # Buttons row
        btn_frame = tk.Frame(body, bg=BG_LIGHT)
        btn_frame.pack(fill=tk.X, pady=(0, 8))

        self._gen_btn = tk.Button(
            btn_frame, text="Generate Scene", font=FONT_BODY,
            bg=ACCENT, fg="white", activebackground=ACCENT_HOVER,
            activeforeground="white", relief=tk.FLAT, padx=16, pady=6,
            cursor="hand2", command=self._on_generate,
        )
        self._gen_btn.pack(side=tk.LEFT)

        tk.Button(
            btn_frame, text="Clear Log", font=FONT_STATUS,
            bg="#e2e8f0", fg=FG_BODY, relief=tk.FLAT, padx=10, pady=4,
            cursor="hand2", command=self._clear_log,
        ).pack(side=tk.RIGHT)

        # Status
        self._status_var = tk.StringVar(value="Ready")
        tk.Label(
            body, textvariable=self._status_var, font=FONT_STATUS,
            bg=BG_LIGHT, fg="#64748b", anchor=tk.W,
        ).pack(fill=tk.X, pady=(0, 4))

        # Log
        tk.Label(body, text="Log:", font=FONT_BODY, bg=BG_LIGHT, fg=FG_BODY).pack(anchor=tk.W)
        self._log = scrolledtext.ScrolledText(
            body, height=14, font=FONT_MONO, bg=BG_LOG, fg=FG_LOG,
            insertbackground=FG_LOG, relief=tk.SOLID, bd=1, state=tk.DISABLED,
            wrap=tk.WORD,
        )
        self._log.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

    def _on_enter(self, event: tk.Event) -> str:
        """Handle Enter key — generate unless Shift is held."""
        if not (event.state & 0x1):  # Shift not held
            self._on_generate()
            return "break"
        return ""

    def _on_generate(self) -> None:
        prompt = self._prompt.get("1.0", tk.END).strip()
        if not prompt:
            return
        self._gen_btn.configure(state=tk.DISABLED)
        self._set_status("Starting...")
        threading.Thread(target=self._run_pipeline, args=(prompt,), daemon=True).start()

    def _run_pipeline(self, prompt: str) -> None:
        """Full pipeline: LLM -> safety -> execute -> validate -> scene setup."""
        try:
            code = self._step_generate(prompt)
            if code is None:
                return

            ok = self._step_execute(code, prompt)
            if not ok:
                return

            # Validate scene and optionally refine
            self._step_validate_scene(prompt)

            self._step_scene_setup()
            self._set_status("Done")
            self._log_msg("Scene complete!")

        except Exception as e:
            self._log_msg(f"Unexpected error: {e}")
            self._set_status("Error")
        finally:
            self.after(0, lambda: self._gen_btn.configure(state=tk.NORMAL))

    def _step_generate(self, prompt: str) -> str | None:
        """Generate and validate code, with retries on safety failures."""
        feedback = ""
        for attempt in range(1 + MAX_RETRIES):
            label = f"(attempt {attempt + 1})" if attempt > 0 else ""
            self._set_status(f"Generating code... {label}")
            self._log_msg(f"Generating bpy code{' ' + label if label else ''}...")

            try:
                code = generate_bpy_code(prompt, feedback=feedback)
            except Exception as e:
                self._log_msg(f"LLM error: {e}")
                self._set_status("LLM error")
                return None

            self._log_msg(f"Generated {len(code.splitlines())} lines")

            # Safety check
            result = validate_code(code)
            if result.ok:
                self._log_msg("Safety check: PASSED")
                return code

            self._log_msg(f"Safety check: FAILED ({len(result.violations)} violations)")
            for v in result.violations:
                self._log_msg(f"  - {v}")

            feedback = (
                "Your previous code had safety violations:\n"
                + "\n".join(f"- {v}" for v in result.violations)
                + "\n\nFix these issues. Only use allowed imports: bpy, bmesh, math, mathutils, random, colorsys."
                + "\nDo NOT use os, sys, subprocess, eval, exec, open, or any file I/O."
                + "\nOutput the complete fixed script."
            )

        self._log_msg("All attempts failed safety checks.")
        self._set_status("Safety check failed")
        return None

    def _step_execute(self, code: str, prompt: str) -> bool:
        """Execute code in Blender, with retries on execution failures."""
        feedback = ""
        current_code = code
        for attempt in range(1 + MAX_RETRIES):
            label = f"(attempt {attempt + 1})" if attempt > 0 else ""
            self._set_status(f"Running in Blender... {label}")
            self._log_msg(f"Executing in Blender{' ' + label if label else ''}...")

            result = execute_code(current_code)

            if result.stdout:
                for line in result.stdout.splitlines():
                    self._log_msg(f"  {line}")

            if result.ok:
                self._log_msg("Execution: OK")
                return True

            self._log_msg(f"Execution error: {result.stderr}")

            # Retry: regenerate with error feedback
            feedback = (
                f"Your code produced an error when run in Blender:\n{result.stderr}\n\n"
                "Fix the error and regenerate the complete script."
            )
            self._set_status(f"Retrying after error... {label}")
            self._log_msg("Regenerating with error feedback...")

            try:
                current_code = generate_bpy_code(prompt, feedback=feedback)
            except Exception as e:
                self._log_msg(f"LLM error on retry: {e}")
                break

            safety = validate_code(current_code)
            if not safety.ok:
                self._log_msg(f"Retry failed safety: {safety.violations}")
                break

        self._log_msg("All execution attempts failed.")
        self._set_status("Execution failed")
        return False

    def _step_validate_scene(self, prompt: str) -> None:
        """Inspect the scene and check for common issues."""
        self._set_status("Inspecting scene...")
        self._log_msg("Validating scene...")

        info = get_scene_info()
        if not info.ok or not info.stdout:
            self._log_msg("  Could not inspect scene (non-critical)")
            return

        scene_text = info.stdout
        issues = []

        # Check: any mesh objects created?
        if "mesh" not in scene_text.lower() and "MESH" not in scene_text:
            issues.append("No mesh objects found in scene")

        # Check: objects at very high z (floating)
        # Simple heuristic: look for z > 10 in the scene info
        import re as _re
        z_values = _re.findall(r"z[=:]\s*(-?[\d.]+)", scene_text, _re.IGNORECASE)
        for z_str in z_values:
            try:
                z = float(z_str)
                if z > 15:
                    issues.append(f"Object at extreme height z={z:.1f} — may be floating")
                    break
            except ValueError:
                pass

        if issues:
            self._log_msg(f"  Issues found: {'; '.join(issues)}")
        else:
            obj_count = scene_text.count("MESH") or scene_text.count("mesh")
            self._log_msg(f"  Scene looks good ({obj_count} mesh objects)")

    def _step_scene_setup(self) -> None:
        """Add camera, lights, ground, and render settings."""
        self._set_status("Setting up camera and lighting...")
        self._log_msg("Adding camera, lights, ground...")

        cam_code = generate_camera_lighting_code()
        result = execute_code(cam_code)

        if result.ok:
            self._log_msg("Camera and lighting: OK")
        else:
            self._log_msg(f"Scene setup warning: {result.stderr}")

    # --- GUI helpers (thread-safe) ---

    def _log_msg(self, msg: str) -> None:
        self.after(0, self._append_log, msg)

    def _append_log(self, msg: str) -> None:
        self._log.configure(state=tk.NORMAL)
        self._log.insert(tk.END, f"> {msg}\n")
        self._log.see(tk.END)
        self._log.configure(state=tk.DISABLED)

    def _set_status(self, msg: str) -> None:
        self.after(0, self._status_var.set, msg)

    def _clear_log(self) -> None:
        self._log.configure(state=tk.NORMAL)
        self._log.delete("1.0", tk.END)
        self._log.configure(state=tk.DISABLED)
        self._status_var.set("Ready")
