"""Desktop GUI for BlenderMCP — Text to 3D with render preview."""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext

from PIL import Image, ImageTk

import src.config as cfg
from src.blender_bridge import execute_code, get_scene_info, ping_blender, render_preview
from src.error_messages import get_friendly_error
from src.history import load_history, save_prompt
from src.llm import generate_bpy_code
from src.prompt_enricher import enrich_prompt
from src.prompt_examples import EXAMPLES
from src.render_history import save_render, load_history as load_render_history, RenderEntry
from src.safety import validate_code
from src.scene_setup import generate_camera_lighting_code
from src.code_cache import cache_stats, clear_cache
from src.settings import load_settings, save_settings, apply_to_config, DEFAULTS

# ── Colours ──────────────────────────────────────────────────────────
BG_DARK = "#1e293b"
BG_MID = "#334155"
BG_LIGHT = "#f8fafc"
BG_LOG = "#0f172a"
FG_LOG = "#e2e8f0"
ACCENT = "#0d9488"
ACCENT_HOVER = "#0f766e"
FG_DARK = "#f1f5f9"
FG_BODY = "#1e293b"
FG_MUTED = "#64748b"
BG_PREVIEW = "#111827"

STEP_DONE = "#22c55e"
STEP_ACTIVE = ACCENT
STEP_FAIL = "#ef4444"
STEP_PENDING = "#475569"

FONT_BODY = ("Segoe UI", 11)
FONT_MONO = ("Consolas", 10)
FONT_HEADER = ("Segoe UI", 14, "bold")
FONT_STATUS = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 9)
FONT_TINY = ("Segoe UI", 8)

# Pipeline step names
PIPELINE_STEPS = ["Generate", "Safety", "Execute", "Setup", "Render"]


# ── Application ──────────────────────────────────────────────────────
class BlenderMCPApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("BlenderMCP — Text to 3D")
        self.geometry("1120x720")
        self.minsize(900, 600)
        self.configure(bg=BG_LIGHT)

        # State
        self._preview_image = None  # keep PIL ref to prevent GC
        self._preview_path = os.path.join(tempfile.gettempdir(), "blendermcp_preview.png")
        self._history: list[str] = load_history()
        self._history_idx: int = len(self._history)  # points past end = "new"
        self._cancel_event = threading.Event()
        self._generating = False
        self._current_prompt = ""
        self._blender_ok = False

        # Load persistent settings
        saved = load_settings()
        apply_to_config(saved)

        self._build_ui()
        self._check_blender_connection()

    # ── UI Construction ──────────────────────────────────────────────

    def _build_ui(self) -> None:
        # ── Header bar ──
        header = tk.Frame(self, bg=BG_DARK, height=48)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        tk.Label(
            header, text="BlenderMCP  —  Text to 3D", font=FONT_HEADER,
            bg=BG_DARK, fg=FG_DARK,
        ).pack(side=tk.LEFT, padx=16, pady=8)

        # Right side of header: connection dot + provider + settings
        right_hdr = tk.Frame(header, bg=BG_DARK)
        right_hdr.pack(side=tk.RIGHT, padx=12, pady=8)

        # Settings gear
        settings_btn = tk.Button(
            right_hdr, text="\u2699", font=("Segoe UI", 14),
            bg=BG_DARK, fg="#94a3b8", bd=0, cursor="hand2",
            activebackground=BG_DARK, activeforeground=FG_DARK,
            command=self._open_settings,
        )
        settings_btn.pack(side=tk.RIGHT, padx=(8, 0))

        # Render history gallery button
        history_btn = tk.Button(
            right_hdr, text="\U0001f5bc", font=("Segoe UI", 12),
            bg=BG_DARK, fg="#94a3b8", bd=0, cursor="hand2",
            activebackground=BG_DARK, activeforeground=FG_DARK,
            command=self._open_render_history,
        )
        history_btn.pack(side=tk.RIGHT, padx=(4, 0))

        # Provider selector
        self._provider_var = tk.StringVar(value=cfg.LLM_PROVIDER)
        prov_frame = tk.Frame(right_hdr, bg=BG_DARK)
        prov_frame.pack(side=tk.RIGHT, padx=(0, 4))
        tk.Label(prov_frame, text="LLM:", font=FONT_SMALL, bg=BG_DARK, fg="#94a3b8").pack(side=tk.LEFT)
        prov_menu = tk.OptionMenu(prov_frame, self._provider_var, "gemini", "ollama", command=self._on_provider_change)
        prov_menu.configure(font=FONT_SMALL, bg=BG_MID, fg=FG_DARK, activebackground="#475569",
                            activeforeground=FG_DARK, highlightthickness=0, relief=tk.FLAT)
        prov_menu.pack(side=tk.LEFT)

        # Connection indicator
        self._conn_var = tk.StringVar(value="\u25cf Checking...")
        self._conn_label = tk.Label(
            right_hdr, textvariable=self._conn_var, font=FONT_SMALL,
            bg=BG_DARK, fg="#94a3b8",
        )
        self._conn_label.pack(side=tk.RIGHT, padx=(0, 12))

        # ── Body: PanedWindow (resizable columns) ──
        paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg="#cbd5e1", sashwidth=5, sashrelief=tk.FLAT)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        # ── Left column: prompt + controls + log ──
        left = tk.Frame(paned, bg=BG_LIGHT)
        paned.add(left, minsize=350, width=500)

        # Prompt label + tips
        prompt_hdr = tk.Frame(left, bg=BG_LIGHT)
        prompt_hdr.pack(fill=tk.X, padx=8, pady=(8, 0))
        tk.Label(prompt_hdr, text="Describe your scene:", font=FONT_BODY, bg=BG_LIGHT, fg=FG_BODY).pack(side=tk.LEFT)

        # Tips button
        tips_btn = tk.Button(
            prompt_hdr, text="?", font=FONT_TINY, bg="#e2e8f0", fg=FG_MUTED,
            bd=0, padx=4, pady=0, cursor="hand2", command=self._show_tips,
        )
        tips_btn.pack(side=tk.LEFT, padx=(6, 0))

        # History navigation
        hist_frame = tk.Frame(prompt_hdr, bg=BG_LIGHT)
        hist_frame.pack(side=tk.RIGHT)
        tk.Button(hist_frame, text="\u25c0", font=FONT_SMALL, bg="#e2e8f0", fg=FG_BODY,
                  bd=0, padx=4, cursor="hand2", command=self._history_prev).pack(side=tk.LEFT, padx=1)
        tk.Button(hist_frame, text="\u25b6", font=FONT_SMALL, bg="#e2e8f0", fg=FG_BODY,
                  bd=0, padx=4, cursor="hand2", command=self._history_next).pack(side=tk.LEFT, padx=1)

        # Prompt text area
        self._prompt = tk.Text(left, height=3, font=FONT_BODY, wrap=tk.WORD, relief=tk.SOLID, bd=1)
        self._prompt.pack(fill=tk.X, padx=8, pady=(4, 6))
        self._prompt.bind("<Return>", self._on_enter)

        # ── Buttons row ──
        btn_frame = tk.Frame(left, bg=BG_LIGHT)
        btn_frame.pack(fill=tk.X, padx=8, pady=(0, 4))

        self._gen_btn = tk.Button(
            btn_frame, text="Generate Scene", font=FONT_BODY,
            bg=ACCENT, fg="white", activebackground=ACCENT_HOVER,
            activeforeground="white", relief=tk.FLAT, padx=14, pady=5,
            cursor="hand2", command=self._on_generate,
        )
        self._gen_btn.pack(side=tk.LEFT)

        # Examples dropdown
        self._examples_btn = tk.Menubutton(
            btn_frame, text="Examples \u25bc", font=FONT_STATUS,
            bg="#6366f1", fg="white", activebackground="#4f46e5",
            activeforeground="white", relief=tk.FLAT, padx=10, pady=5,
            cursor="hand2",
        )
        self._examples_btn.pack(side=tk.LEFT, padx=(6, 0))
        examples_menu = tk.Menu(self._examples_btn, tearoff=False, font=FONT_SMALL)
        for category, prompts in EXAMPLES.items():
            sub = tk.Menu(examples_menu, tearoff=False, font=FONT_SMALL)
            for p in prompts:
                sub.add_command(label=p, command=lambda txt=p: self._insert_example(txt))
            examples_menu.add_cascade(label=category, menu=sub)
        self._examples_btn.configure(menu=examples_menu)

        # Mode toggle
        self._mode_var = tk.StringVar(value="new")
        mode_frame = tk.Frame(btn_frame, bg=BG_LIGHT)
        mode_frame.pack(side=tk.LEFT, padx=(12, 0))
        tk.Radiobutton(mode_frame, text="New", variable=self._mode_var, value="new",
                        font=FONT_SMALL, bg=BG_LIGHT, fg=FG_BODY, selectcolor=BG_LIGHT,
                        activebackground=BG_LIGHT).pack(side=tk.LEFT)
        tk.Radiobutton(mode_frame, text="Modify", variable=self._mode_var, value="modify",
                        font=FONT_SMALL, bg=BG_LIGHT, fg=FG_BODY, selectcolor=BG_LIGHT,
                        activebackground=BG_LIGHT).pack(side=tk.LEFT)

        # Renderer selector
        self._renderer_var = tk.StringVar(value="cycles")
        rend_frame = tk.Frame(btn_frame, bg=BG_LIGHT)
        rend_frame.pack(side=tk.LEFT, padx=(12, 0))
        tk.Label(rend_frame, text="Render:", font=FONT_TINY, bg=BG_LIGHT, fg=FG_MUTED).pack(side=tk.LEFT)
        tk.Radiobutton(rend_frame, text="Cycles", variable=self._renderer_var, value="cycles",
                        font=FONT_TINY, bg=BG_LIGHT, fg=FG_BODY, selectcolor=BG_LIGHT,
                        activebackground=BG_LIGHT).pack(side=tk.LEFT)
        tk.Radiobutton(rend_frame, text="EEVEE", variable=self._renderer_var, value="eevee",
                        font=FONT_TINY, bg=BG_LIGHT, fg=FG_BODY, selectcolor=BG_LIGHT,
                        activebackground=BG_LIGHT).pack(side=tk.LEFT)

        # Quality preset selector
        self._quality_var = tk.StringVar(value=cfg.RENDER_QUALITY)
        qual_frame = tk.Frame(btn_frame, bg=BG_LIGHT)
        qual_frame.pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(qual_frame, text="Quality:", font=FONT_TINY, bg=BG_LIGHT, fg=FG_MUTED).pack(side=tk.LEFT)
        qual_menu = tk.OptionMenu(qual_frame, self._quality_var, "draft", "standard", "high")
        qual_menu.configure(font=FONT_TINY, bg="#e2e8f0", fg=FG_BODY,
                            highlightthickness=0, relief=tk.FLAT)
        qual_menu["menu"].configure(font=FONT_TINY)
        qual_menu.pack(side=tk.LEFT)

        # Right-side buttons
        tk.Button(btn_frame, text="Copy Log", font=FONT_TINY, bg="#e2e8f0", fg=FG_BODY,
                  relief=tk.FLAT, padx=6, pady=3, cursor="hand2",
                  command=self._copy_log).pack(side=tk.RIGHT, padx=(4, 0))
        tk.Button(btn_frame, text="Clear", font=FONT_TINY, bg="#e2e8f0", fg=FG_BODY,
                  relief=tk.FLAT, padx=6, pady=3, cursor="hand2",
                  command=self._clear_log).pack(side=tk.RIGHT)

        # ── Pipeline progress indicator ──
        self._step_labels: list[tk.Label] = []
        prog_frame = tk.Frame(left, bg=BG_LIGHT)
        prog_frame.pack(fill=tk.X, padx=8, pady=(0, 6))

        for i, name in enumerate(PIPELINE_STEPS):
            if i > 0:
                tk.Label(prog_frame, text="\u2192", font=FONT_TINY, bg=BG_LIGHT, fg="#94a3b8").pack(side=tk.LEFT, padx=2)
            lbl = tk.Label(prog_frame, text=name, font=FONT_TINY, bg="#e2e8f0", fg=STEP_PENDING,
                           padx=6, pady=1, relief=tk.FLAT)
            lbl.pack(side=tk.LEFT, padx=1)
            self._step_labels.append(lbl)

        # Status text
        self._status_var = tk.StringVar(value="Ready")
        tk.Label(left, textvariable=self._status_var, font=FONT_SMALL, bg=BG_LIGHT, fg=FG_MUTED,
                 anchor=tk.W).pack(fill=tk.X, padx=8)

        # ── Log ──
        tk.Label(left, text="Log:", font=FONT_STATUS, bg=BG_LIGHT, fg=FG_BODY).pack(anchor=tk.W, padx=8, pady=(4, 0))
        self._log = scrolledtext.ScrolledText(
            left, height=12, font=FONT_MONO, bg=BG_LOG, fg=FG_LOG,
            insertbackground=FG_LOG, relief=tk.SOLID, bd=1, state=tk.DISABLED, wrap=tk.WORD,
        )
        self._log.pack(fill=tk.BOTH, expand=True, padx=8, pady=(2, 8))

        # Log tags for colored output
        self._log.tag_configure("error", foreground="#ef4444")
        self._log.tag_configure("success", foreground="#22c55e")
        self._log.tag_configure("step", foreground=ACCENT, font=("Consolas", 10, "bold"))
        self._log.tag_configure("info", foreground=FG_LOG)

        # ── Right column: preview ──
        right = tk.Frame(paned, bg=BG_PREVIEW, bd=1, relief=tk.SOLID)
        paned.add(right, minsize=300)

        # Preview header with save button
        prev_hdr = tk.Frame(right, bg="#1f2937")
        prev_hdr.pack(fill=tk.X)
        tk.Label(prev_hdr, text="Render Preview", font=FONT_BODY, bg="#1f2937", fg="#d1d5db").pack(side=tk.LEFT, padx=10, pady=6)

        self._render_status = tk.StringVar(value="No render yet")
        tk.Label(prev_hdr, textvariable=self._render_status, font=FONT_TINY, bg="#1f2937", fg="#6b7280").pack(side=tk.LEFT, padx=4)

        # Save and Re-render buttons
        tk.Button(prev_hdr, text="Save Image", font=FONT_TINY, bg="#1f2937", fg="#9ca3af",
                  bd=0, padx=6, cursor="hand2", activebackground="#374151", activeforeground="#d1d5db",
                  command=self._save_image).pack(side=tk.RIGHT, padx=(0, 10), pady=6)
        self._render_btn = tk.Button(
            prev_hdr, text="Re-render", font=FONT_TINY, bg="#1f2937", fg="#9ca3af",
            bd=0, padx=6, cursor="hand2", activebackground="#374151", activeforeground="#d1d5db",
            command=self._on_rerender,
        )
        self._render_btn.pack(side=tk.RIGHT, padx=4, pady=6)

        # Preview canvas
        self._preview_canvas = tk.Canvas(right, bg=BG_PREVIEW, highlightthickness=0)
        self._preview_canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self._preview_canvas.bind("<Configure>", self._on_canvas_resize)
        self._placeholder_id = self._preview_canvas.create_text(
            0, 0,
            text="Scene preview will appear here\nafter generation\n\n"
                 "Tip: Pick an example prompt to get started!",
            fill="#4b5563", font=("Segoe UI", 11), justify=tk.CENTER,
        )

        # ── Keyboard shortcuts ──
        self.bind("<Control-Return>", lambda e: self._on_generate())
        self.bind("<Control-r>", lambda e: self._on_rerender())
        self.bind("<Control-l>", lambda e: self._clear_log())
        self.bind("<Escape>", lambda e: self._on_cancel())

    # ── Provider / Settings ──────────────────────────────────────────

    def _on_provider_change(self, value: str) -> None:
        cfg.LLM_PROVIDER = value
        self._log_msg(f"Switched to {value.upper()} provider", "info")

    def _open_settings(self) -> None:
        """Open settings dialog."""
        win = tk.Toplevel(self)
        win.title("Settings")
        win.geometry("420x440")
        win.resizable(False, False)
        win.configure(bg=BG_LIGHT)
        win.transient(self)
        win.grab_set()

        saved = load_settings()
        entries: dict[str, tk.Variable] = {}

        fields = [
            ("LLM Provider", "llm_provider", "str", ["gemini", "ollama"]),
            ("Gemini Model", "gemini_model", "str", None),
            ("Ollama Model", "ollama_model", "str", None),
            ("Context Window", "ollama_num_ctx", "int", None),
            ("Max Retries", "max_retries", "int", None),
            ("Render Width", "render_width", "int", None),
            ("Render Height", "render_height", "int", None),
            ("Render Quality", "render_quality", "str", ["draft", "standard", "high"]),
        ]

        frame = tk.Frame(win, bg=BG_LIGHT, padx=20, pady=16)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text="Settings", font=FONT_HEADER, bg=BG_LIGHT, fg=FG_BODY).pack(anchor=tk.W, pady=(0, 12))

        for label, key, typ, options in fields:
            row = tk.Frame(frame, bg=BG_LIGHT)
            row.pack(fill=tk.X, pady=3)
            tk.Label(row, text=label, font=FONT_SMALL, bg=BG_LIGHT, fg=FG_BODY, width=16, anchor=tk.W).pack(side=tk.LEFT)

            if options:  # dropdown
                var = tk.StringVar(value=str(saved.get(key, DEFAULTS[key])))
                tk.OptionMenu(row, var, *options).pack(side=tk.LEFT, fill=tk.X, expand=True)
            else:
                var = tk.StringVar(value=str(saved.get(key, DEFAULTS[key])))
                tk.Entry(row, textvariable=var, font=FONT_SMALL, width=24).pack(side=tk.LEFT, fill=tk.X, expand=True)
            entries[key] = var

        def _save() -> None:
            new_settings = {}
            for key, var in entries.items():
                val = var.get()
                if key in ("ollama_num_ctx", "max_retries", "render_width", "render_height"):
                    try:
                        val = int(val)
                    except ValueError:
                        val = DEFAULTS[key]
                new_settings[key] = val
            save_settings(new_settings)
            apply_to_config(new_settings)
            self._provider_var.set(cfg.LLM_PROVIDER)
            self._quality_var.set(cfg.RENDER_QUALITY)
            self._log_msg("Settings saved", "success")
            win.destroy()

        def _reset() -> None:
            for key, var in entries.items():
                var.set(str(DEFAULTS[key]))

        # Cache info
        cache_frame = tk.Frame(frame, bg="#f1f5f9", bd=1, relief=tk.SOLID, padx=8, pady=6)
        cache_frame.pack(fill=tk.X, pady=(10, 0))
        stats = cache_stats()
        cache_info = tk.StringVar(value=f"Code cache: {stats['count']} entries ({stats['size_mb']} MB)")
        tk.Label(cache_frame, textvariable=cache_info, font=FONT_TINY, bg="#f1f5f9", fg=FG_MUTED).pack(side=tk.LEFT)

        def _clear_code_cache() -> None:
            n = clear_cache()
            cache_info.set(f"Code cache: 0 entries (0 MB) — cleared {n}")
            self._log_msg(f"Cache cleared ({n} entries removed)", "info")

        tk.Button(cache_frame, text="Clear Cache", font=FONT_TINY, bg="#e2e8f0", fg=FG_BODY,
                  relief=tk.FLAT, padx=6, pady=1, command=_clear_code_cache).pack(side=tk.RIGHT)

        btn_row = tk.Frame(frame, bg=BG_LIGHT)
        btn_row.pack(fill=tk.X, pady=(12, 0))
        tk.Button(btn_row, text="Save", font=FONT_BODY, bg=ACCENT, fg="white",
                  relief=tk.FLAT, padx=16, pady=4, command=_save).pack(side=tk.LEFT)
        tk.Button(btn_row, text="Reset Defaults", font=FONT_SMALL, bg="#e2e8f0", fg=FG_BODY,
                  relief=tk.FLAT, padx=10, pady=4, command=_reset).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(btn_row, text="Cancel", font=FONT_SMALL, bg="#e2e8f0", fg=FG_BODY,
                  relief=tk.FLAT, padx=10, pady=4, command=win.destroy).pack(side=tk.RIGHT)

    def _open_render_history(self) -> None:
        """Open render history gallery window."""
        entries = load_render_history()
        if not entries:
            self._log_msg("No render history yet. Generate some scenes first!", "info")
            return

        win = tk.Toplevel(self)
        win.title("Render History")
        win.geometry("700x500")
        win.configure(bg=BG_LIGHT)
        win.transient(self)

        tk.Label(win, text="Render History", font=FONT_HEADER, bg=BG_LIGHT, fg=FG_BODY).pack(padx=16, pady=(12, 8))

        # Scrollable frame
        canvas = tk.Canvas(win, bg=BG_LIGHT, highlightthickness=0)
        scrollbar = tk.Scrollbar(win, orient=tk.VERTICAL, command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=BG_LIGHT)

        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=4)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Store PhotoImage refs to prevent GC
        win._thumb_refs = []

        for entry in reversed(entries):  # newest first
            row = tk.Frame(scroll_frame, bg="#f1f5f9", bd=1, relief=tk.SOLID, padx=8, pady=6)
            row.pack(fill=tk.X, padx=8, pady=3)

            # Thumbnail
            try:
                from PIL import Image, ImageTk as ITk
                img = Image.open(entry.thumbnail_path)
                img.thumbnail((100, 75), Image.LANCZOS)
                photo = ITk.PhotoImage(img)
                win._thumb_refs.append(photo)
                tk.Label(row, image=photo, bg="#f1f5f9").pack(side=tk.LEFT, padx=(0, 10))
            except Exception:
                tk.Label(row, text="[no thumb]", font=FONT_TINY, bg="#f1f5f9", fg=FG_MUTED).pack(side=tk.LEFT, padx=(0, 10))

            # Info
            info_frame = tk.Frame(row, bg="#f1f5f9")
            info_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
            tk.Label(info_frame, text=entry.short_prompt, font=FONT_SMALL, bg="#f1f5f9", fg=FG_BODY,
                     anchor=tk.W, wraplength=400).pack(anchor=tk.W)
            tk.Label(info_frame, text=entry.time_str, font=FONT_TINY, bg="#f1f5f9", fg=FG_MUTED,
                     anchor=tk.W).pack(anchor=tk.W)

            # Load prompt button
            prompt_text = entry.prompt
            tk.Button(row, text="Use Prompt", font=FONT_TINY, bg=ACCENT, fg="white",
                      relief=tk.FLAT, padx=6, pady=2, cursor="hand2",
                      command=lambda p=prompt_text: (self._insert_example(p), win.destroy())
                      ).pack(side=tk.RIGHT, padx=4)

    # ── Prompt helpers ───────────────────────────────────────────────

    def _insert_example(self, text: str) -> None:
        self._prompt.delete("1.0", tk.END)
        self._prompt.insert("1.0", text)

    def _show_tips(self) -> None:
        win = tk.Toplevel(self)
        win.title("Prompt Tips")
        win.geometry("400x280")
        win.resizable(False, False)
        win.configure(bg=BG_LIGHT)
        win.transient(self)
        tips = (
            "Tips for better results:\n\n"
            "\u2022 Be specific about materials: 'wooden table' > 'table'\n"
            "\u2022 Mention colors: 'red metallic sphere on a white pedestal'\n"
            "\u2022 Describe spatial relations: 'a lamp on top of the desk'\n"
            "\u2022 Include size hints: 'a small plant' or 'a tall bookshelf'\n"
            "\u2022 One scene per prompt works best\n"
            "\u2022 Use 'Modify' mode to add to an existing scene\n\n"
            "Shortcuts:\n"
            "  Ctrl+Enter  Generate\n"
            "  Ctrl+R      Re-render\n"
            "  Ctrl+L      Clear log\n"
            "  Escape      Cancel generation"
        )
        tk.Label(win, text=tips, font=FONT_BODY, bg=BG_LIGHT, fg=FG_BODY,
                 justify=tk.LEFT, anchor=tk.NW, padx=20, pady=16).pack(fill=tk.BOTH, expand=True)

    def _history_prev(self) -> None:
        if self._history and self._history_idx > 0:
            self._history_idx -= 1
            self._prompt.delete("1.0", tk.END)
            self._prompt.insert("1.0", self._history[self._history_idx])

    def _history_next(self) -> None:
        if self._history_idx < len(self._history) - 1:
            self._history_idx += 1
            self._prompt.delete("1.0", tk.END)
            self._prompt.insert("1.0", self._history[self._history_idx])
        elif self._history_idx == len(self._history) - 1:
            self._history_idx = len(self._history)
            self._prompt.delete("1.0", tk.END)

    # ── Connection check ─────────────────────────────────────────────

    def _check_blender_connection(self) -> None:
        def _check() -> None:
            ok = ping_blender()
            self._blender_ok = ok
            self._update_connection_ui(ok)
            # Re-check every 30 seconds
            self.after(30000, self._check_blender_connection)
        threading.Thread(target=_check, daemon=True).start()

    def _update_connection_ui(self, connected: bool) -> None:
        """Update the connection indicator label (thread-safe)."""
        color = "#22c55e" if connected else "#ef4444"
        text = "\u25cf Blender Connected" if connected else "\u25cf Blender Disconnected"
        self.after(0, lambda: (self._conn_var.set(text), self._conn_label.configure(fg=color)))

    # ── Generation ───────────────────────────────────────────────────

    def _on_enter(self, event: tk.Event) -> str:
        if not (event.state & 0x1):  # Shift not held
            self._on_generate()
            return "break"
        return ""

    def _on_generate(self) -> None:
        if self._generating:
            return
        prompt = self._prompt.get("1.0", tk.END).strip()
        if not prompt:
            return
        self._generating = True
        self._cancel_event.clear()
        self._current_prompt = prompt
        self._gen_btn.configure(text="Cancel", bg=STEP_FAIL, command=self._on_cancel)
        self._render_btn.configure(state=tk.DISABLED)
        self._reset_progress()
        self._set_status("Starting...")
        self.title("BlenderMCP — Generating...")
        threading.Thread(target=self._run_pipeline, args=(prompt,), daemon=True).start()

    def _on_cancel(self) -> None:
        if self._generating:
            self._cancel_event.set()
            self._log_msg("Cancelling...", "info")

    def _on_rerender(self) -> None:
        self._render_btn.configure(state=tk.DISABLED)
        self._set_status("Rendering...")
        threading.Thread(target=self._do_render, daemon=True).start()

    def _run_pipeline(self, prompt: str) -> None:
        """Full pipeline: LLM -> safety -> execute -> validate -> scene setup -> render."""
        try:
            # Get scene context if in modify mode
            scene_context = ""
            if self._mode_var.get() == "modify":
                self._log_msg("Fetching current scene state...", "step")
                info = get_scene_info()
                if info.ok and info.stdout:
                    scene_context = info.stdout
                    self._log_msg(f"  Scene context: {len(scene_context)} chars", "info")

            # Step 0.5: Enrich prompt (PubChem, etc.)
            enriched_prompt, enrich_log = enrich_prompt(prompt)
            if enrich_log:
                self._log_msg(f"Prompt enriched: {enrich_log}", "success")
                prompt = enriched_prompt

            # Step 1: Generate
            code = self._step_generate(prompt, scene_context)
            if code is None or self._cancelled():
                return

            # Step 2+3: Execute (safety is inside generate)
            ok = self._step_execute(code, prompt, scene_context)
            if not ok or self._cancelled():
                return

            # Step 4: Scene setup
            # Always run scene setup — even in modify mode, camera may be missing
            self._step_scene_setup()

            if self._cancelled():
                return

            # Step 5: Render
            self._step_render_preview()

            self._set_status("Done!")
            self.after(0, lambda: self.title("BlenderMCP — Scene Ready"))
            self._log_msg("Scene complete!", "success")

            # Pipeline succeeded → Blender is definitely connected
            self._blender_ok = True
            self._update_connection_ui(True)

            # Save to history
            self._history = save_prompt(prompt, self._history)
            self._history_idx = len(self._history)

        except Exception as e:
            self._log_error(str(e))
            self._set_status("Error")
            self.after(0, lambda: self.title("BlenderMCP — Error"))
        finally:
            self._generating = False
            self.after(0, self._restore_generate_btn)

    def _cancelled(self) -> bool:
        if self._cancel_event.is_set():
            self._log_msg("Generation cancelled.", "info")
            self._set_status("Cancelled")
            self.after(0, lambda: self.title("BlenderMCP — Cancelled"))
            return True
        return False

    def _restore_generate_btn(self) -> None:
        self._gen_btn.configure(text="Generate Scene", bg=ACCENT, command=self._on_generate)
        self._render_btn.configure(state=tk.NORMAL)

    # ── Pipeline steps ───────────────────────────────────────────────

    def _step_generate(self, prompt: str, scene_context: str = "") -> str | None:
        feedback = ""
        for attempt in range(1 + cfg.MAX_RETRIES):
            if self._cancel_event.is_set():
                return None

            label = f" (attempt {attempt + 1})" if attempt > 0 else ""
            self._set_pipeline_step(0, "active")
            self._set_status(f"Generating code...{label}")
            self._log_msg(f"Generating bpy code{label}...", "step")

            try:
                code, was_cached = generate_bpy_code(prompt, feedback=feedback, scene_context=scene_context)
            except Exception as e:
                self._log_error(str(e))
                self._set_pipeline_step(0, "fail")
                self._set_status("LLM error")
                return None

            if was_cached:
                self._log_msg("Using cached code (saved API call)", "success")
            self._log_msg(f"Generated {len(code.splitlines())} lines", "info")
            self._set_pipeline_step(0, "done")

            # Safety check
            self._set_pipeline_step(1, "active")
            result = validate_code(code)
            if result.ok:
                self._log_msg("Safety check: PASSED", "success")
                self._set_pipeline_step(1, "done")
                return code

            self._log_msg(f"Safety: FAILED ({len(result.violations)} violations)", "error")
            for v in result.violations:
                self._log_msg(f"  - {v}", "error")
            self._set_pipeline_step(1, "fail")

            feedback = (
                "Your previous code had safety violations:\n"
                + "\n".join(f"- {v}" for v in result.violations)
                + "\n\nFix these. Only use allowed imports: bpy, bmesh, math, mathutils, random, colorsys."
                + "\nOutput the complete fixed script."
            )

        self._log_msg("All attempts failed safety checks.", "error")
        self._set_status("Safety check failed")
        return None

    def _step_execute(self, code: str, prompt: str, scene_context: str = "") -> bool:
        current_code = code
        for attempt in range(1 + cfg.MAX_RETRIES):
            if self._cancel_event.is_set():
                return False

            label = f" (attempt {attempt + 1})" if attempt > 0 else ""
            self._set_pipeline_step(2, "active")
            self._set_status(f"Running in Blender...{label}")
            self._log_msg(f"Executing in Blender{label}...", "step")

            result = execute_code(current_code)

            if result.stdout:
                for line in result.stdout.splitlines():
                    self._log_msg(f"  {line}", "info")

            if result.ok:
                self._log_msg("Execution: OK", "success")
                self._set_pipeline_step(2, "done")

                # Quick validation
                self._validate_scene_quick()
                return True

            self._log_error(result.stderr)
            self._set_pipeline_step(2, "fail")

            # Retry with error feedback
            feedback = (
                f"Your code produced an error in Blender:\n{result.stderr}\n\n"
                "Fix the error and regenerate the complete script."
            )
            self._log_msg("Regenerating with error feedback...", "info")

            try:
                current_code, _ = generate_bpy_code(prompt, feedback=feedback, scene_context=scene_context)
            except Exception as e:
                self._log_error(str(e))
                break

            safety = validate_code(current_code)
            if not safety.ok:
                self._log_msg(f"Retry failed safety: {safety.violations}", "error")
                break

        self._log_msg("All execution attempts failed.", "error")
        self._set_status("Execution failed")
        return False

    def _validate_scene_quick(self) -> None:
        """Quick scene validation — non-blocking, non-critical."""
        info = get_scene_info()
        if not info.ok or not info.stdout:
            return
        scene_text = info.stdout
        if "MESH" in scene_text or "mesh" in scene_text.lower():
            import re
            mesh_count = scene_text.upper().count("MESH")
            self._log_msg(f"  Scene: {mesh_count} mesh objects", "info")

    def _step_scene_setup(self) -> None:
        self._set_pipeline_step(3, "active")
        renderer = self._renderer_var.get()
        quality = self._quality_var.get()
        self._set_status(f"Setting up camera and lighting ({renderer}, {quality})...")
        self._log_msg(f"Adding camera, lights, ground ({renderer.upper()}, {quality})...", "step")

        cam_code = generate_camera_lighting_code(renderer=renderer, quality=quality)
        result = execute_code(cam_code)

        if result.ok:
            self._log_msg("Camera and lighting: OK", "success")
            self._set_pipeline_step(3, "done")
        else:
            self._log_msg(f"Scene setup warning: {result.stderr}", "error")
            self._set_pipeline_step(3, "fail")

    def _step_render_preview(self) -> None:
        self._set_pipeline_step(4, "active")
        self._set_status("Rendering preview...")
        self._log_msg("Rendering preview...", "step")
        self.after(0, self._render_status.set, "Rendering...")

        saved = load_settings()
        w = saved.get("render_width", 960)
        h = saved.get("render_height", 540)

        result = render_preview(self._preview_path, width=w, height=h)

        if result.ok and os.path.exists(self._preview_path):
            self._log_msg(f"Render complete! ({w}x{h})", "success")
            self._set_pipeline_step(4, "done")
            self.after(0, self._render_status.set, f"{w} x {h}")
            self.after(0, self._load_and_display_preview)
            # Auto-save to render history
            entry = save_render(self._preview_path, self._current_prompt)
            if entry:
                self._log_msg(f"Saved to history", "info")
        else:
            self._log_error(result.stderr or "Render failed")
            self._set_pipeline_step(4, "fail")
            self.after(0, self._render_status.set, "Render failed")

    def _do_render(self) -> None:
        try:
            self._step_render_preview()
            self._set_status("Done")
        except Exception as e:
            self._log_error(str(e))
        finally:
            self.after(0, lambda: self._render_btn.configure(state=tk.NORMAL))

    # ── Preview ──────────────────────────────────────────────────────

    def _on_canvas_resize(self, event: tk.Event) -> None:
        cx, cy = event.width // 2, event.height // 2
        self._preview_canvas.coords(self._placeholder_id, cx, cy)
        if self._preview_image:
            self._display_preview_image()

    def _load_and_display_preview(self) -> None:
        try:
            img = Image.open(self._preview_path)
            self._preview_source = img
            self._display_preview_image()
        except Exception as e:
            self._log_msg(f"Could not load preview: {e}", "error")

    def _display_preview_image(self) -> None:
        if not hasattr(self, '_preview_source'):
            return
        canvas_w = self._preview_canvas.winfo_width()
        canvas_h = self._preview_canvas.winfo_height()
        if canvas_w < 10 or canvas_h < 10:
            return

        img = self._preview_source
        img_w, img_h = img.size
        scale = min(canvas_w / img_w, canvas_h / img_h)
        new_w = max(1, int(img_w * scale))
        new_h = max(1, int(img_h * scale))

        resized = img.resize((new_w, new_h), Image.LANCZOS)
        self._preview_image = ImageTk.PhotoImage(resized)

        self._preview_canvas.delete("all")
        cx, cy = canvas_w // 2, canvas_h // 2
        self._preview_canvas.create_image(cx, cy, image=self._preview_image, anchor=tk.CENTER)

    def _save_image(self) -> None:
        if not os.path.exists(self._preview_path):
            self._log_msg("No render to save. Generate a scene first.", "error")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png"), ("JPEG Image", "*.jpg"), ("All Files", "*.*")],
            title="Save Render",
        )
        if path:
            shutil.copy2(self._preview_path, path)
            # Save prompt as sidecar
            txt_path = os.path.splitext(path)[0] + "_prompt.txt"
            try:
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(self._current_prompt)
            except Exception:
                pass
            self._log_msg(f"Saved to: {path}", "success")

    # ── Progress indicator ───────────────────────────────────────────

    def _reset_progress(self) -> None:
        for lbl in self._step_labels:
            self.after(0, lambda l=lbl: l.configure(fg=STEP_PENDING, bg="#e2e8f0"))

    def _set_pipeline_step(self, index: int, state: str) -> None:
        colors = {"active": STEP_ACTIVE, "done": STEP_DONE, "fail": STEP_FAIL}
        fg = colors.get(state, STEP_PENDING)
        bg = "#e2e8f0" if state == "active" else "#e2e8f0"
        self.after(0, lambda: self._step_labels[index].configure(fg=fg))

    # ── Logging ──────────────────────────────────────────────────────

    def _log_msg(self, msg: str, level: str = "info") -> None:
        self.after(0, self._append_log, msg, level)

    def _log_error(self, raw: str) -> None:
        """Log with friendly message if available, raw details below."""
        friendly = get_friendly_error(raw)
        if friendly:
            self._log_msg(f"{friendly.title}: {friendly.message}", "error")
            self._log_msg(f"  \u2192 {friendly.suggestion}", "info")
        else:
            self._log_msg(f"Error: {raw}", "error")

    def _append_log(self, msg: str, level: str = "info") -> None:
        self._log.configure(state=tk.NORMAL)
        tag = level if level in ("error", "success", "step") else "info"
        self._log.insert(tk.END, f"> {msg}\n", tag)
        self._log.see(tk.END)
        self._log.configure(state=tk.DISABLED)

    def _set_status(self, msg: str) -> None:
        self.after(0, self._status_var.set, msg)

    def _clear_log(self) -> None:
        self._log.configure(state=tk.NORMAL)
        self._log.delete("1.0", tk.END)
        self._log.configure(state=tk.DISABLED)
        self._status_var.set("Ready")
        self._reset_progress()

    def _copy_log(self) -> None:
        self.clipboard_clear()
        text = self._log.get("1.0", tk.END).strip()
        if text:
            self.clipboard_append(text)
            self._set_status("Log copied to clipboard")


def main() -> None:
    app = BlenderMCPApp()
    app.mainloop()


if __name__ == "__main__":
    main()
