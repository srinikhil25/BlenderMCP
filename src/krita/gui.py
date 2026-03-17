"""Desktop GUI for KritaMCP — AI-powered 2D art generation."""

from __future__ import annotations

import io
import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk
from pathlib import Path
from typing import Optional

import src.config as cfg
from src.krita import config as krita_cfg
from src.krita.llm import (
    generate_image, edit_image, save_to_history, list_history,
    clear_cache, cache_stats,
)
from src.krita.examples import EXAMPLES
from src.error_messages import get_friendly_error

# ── Colours (teal theme) ─────────────────────────────────────────────
BG_DARK = "#0f1e1e"
BG_MID = "#1a2e2e"
BG_LIGHT = "#f0fdfa"
BG_LOG = "#0a1414"
FG_LOG = "#d0f0e8"
ACCENT = "#14b8a6"
ACCENT_HOVER = "#0d9488"
FG_DARK = "#f0fdfa"
FG_BODY = "#0f1e1e"
FG_MUTED = "#4b7a6e"
BG_CANVAS = "#111a1a"

STEP_DONE = "#22c55e"
STEP_ACTIVE = ACCENT
STEP_FAIL = "#ef4444"
STEP_PENDING = "#3b6060"

FONT_BODY = ("Segoe UI", 11)
FONT_MONO = ("Consolas", 10)
FONT_HEADER = ("Segoe UI", 14, "bold")
FONT_STATUS = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 9)
FONT_TINY = ("Segoe UI", 8)

PIPELINE_STEPS = ["Prepare", "Generate", "Save"]


class KritaMCPApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("KritaMCP — Text to 2D Art")
        self.geometry("1200x750")
        self.minsize(1000, 600)
        self.configure(bg=BG_LIGHT)

        # State
        self._generating = False
        self._cancel_event = threading.Event()
        self._current_prompt = ""
        self._current_image_data: Optional[bytes] = None
        self._current_image_path: Optional[Path] = None
        self._tk_image: Optional[tk.PhotoImage] = None

        # Load settings
        saved = krita_cfg.load_settings()
        krita_cfg.apply_settings(saved)

        self._build_ui()

    def _build_ui(self) -> None:
        # ── Header bar ──
        header = tk.Frame(self, bg=BG_DARK, height=48)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        tk.Label(
            header, text="KritaMCP  \u2014  Text to 2D Art", font=FONT_HEADER,
            bg=BG_DARK, fg=FG_DARK,
        ).pack(side=tk.LEFT, padx=16, pady=8)

        # Right side header
        right_hdr = tk.Frame(header, bg=BG_DARK)
        right_hdr.pack(side=tk.RIGHT, padx=12, pady=8)

        tk.Button(
            right_hdr, text="\u2699", font=("Segoe UI", 14),
            bg=BG_DARK, fg="#5e9e8e", bd=0, cursor="hand2",
            activebackground=BG_DARK, activeforeground=FG_DARK,
            command=self._open_settings,
        ).pack(side=tk.RIGHT, padx=(8, 0))

        tk.Button(
            right_hdr, text="\U0001f5c2 History", font=FONT_SMALL,
            bg=BG_DARK, fg="#5e9e8e", bd=0, cursor="hand2",
            activebackground=BG_DARK, activeforeground=FG_DARK,
            command=self._open_history,
        ).pack(side=tk.RIGHT, padx=(0, 8))

        # Model status
        self._model_var = tk.StringVar(value=f"\u25cf {krita_cfg.IMAGE_MODEL}")
        tk.Label(
            right_hdr, textvariable=self._model_var, font=FONT_TINY,
            bg=BG_DARK, fg="#22c55e",
        ).pack(side=tk.RIGHT, padx=(0, 12))

        # ── Body: PanedWindow ──
        paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg="#4b7a6e",
                               sashwidth=5, sashrelief=tk.FLAT)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        # ── Left column: prompt + controls + log ──
        left = tk.Frame(paned, bg=BG_LIGHT)
        paned.add(left, minsize=320, width=420)

        # Prompt label
        prompt_hdr = tk.Frame(left, bg=BG_LIGHT)
        prompt_hdr.pack(fill=tk.X, padx=8, pady=(8, 0))
        tk.Label(prompt_hdr, text="Describe your image:", font=FONT_BODY,
                 bg=BG_LIGHT, fg=FG_BODY).pack(side=tk.LEFT)

        # Prompt text area
        self._prompt = tk.Text(left, height=3, font=FONT_BODY, wrap=tk.WORD,
                               relief=tk.SOLID, bd=1)
        self._prompt.pack(fill=tk.X, padx=8, pady=(4, 6))
        self._prompt.bind("<Return>", self._on_enter)

        # ── Controls row 1: Generate + Examples ──
        btn_frame = tk.Frame(left, bg=BG_LIGHT)
        btn_frame.pack(fill=tk.X, padx=8, pady=(0, 4))

        self._gen_btn = tk.Button(
            btn_frame, text="Generate Image", font=FONT_BODY,
            bg=ACCENT, fg="white", activebackground=ACCENT_HOVER,
            activeforeground="white", relief=tk.FLAT, padx=14, pady=5,
            cursor="hand2", command=self._on_generate,
        )
        self._gen_btn.pack(side=tk.LEFT)

        # Examples dropdown
        examples_btn = tk.Menubutton(
            btn_frame, text="Examples \u25bc", font=FONT_STATUS,
            bg="#0d9488", fg="white", activebackground="#0f766e",
            activeforeground="white", relief=tk.FLAT, padx=10, pady=5,
            cursor="hand2",
        )
        examples_btn.pack(side=tk.LEFT, padx=(6, 0))
        examples_menu = tk.Menu(examples_btn, tearoff=False, font=FONT_SMALL)
        for category, prompts in EXAMPLES.items():
            sub = tk.Menu(examples_menu, tearoff=False, font=FONT_SMALL)
            for p in prompts:
                sub.add_command(label=p, command=lambda txt=p: self._insert_example(txt))
            examples_menu.add_cascade(label=category, menu=sub)
        examples_btn.configure(menu=examples_menu)

        # Mode toggle
        self._mode_var = tk.StringVar(value="new")
        mode_frame = tk.Frame(btn_frame, bg=BG_LIGHT)
        mode_frame.pack(side=tk.LEFT, padx=(12, 0))
        tk.Radiobutton(mode_frame, text="New", variable=self._mode_var, value="new",
                        font=FONT_SMALL, bg=BG_LIGHT, fg=FG_BODY, selectcolor=BG_LIGHT,
                        activebackground=BG_LIGHT).pack(side=tk.LEFT)
        tk.Radiobutton(mode_frame, text="Edit", variable=self._mode_var, value="edit",
                        font=FONT_SMALL, bg=BG_LIGHT, fg=FG_BODY, selectcolor=BG_LIGHT,
                        activebackground=BG_LIGHT).pack(side=tk.LEFT)

        # Right-side buttons
        tk.Button(btn_frame, text="Copy Log", font=FONT_TINY, bg="#d0f0e8", fg=FG_BODY,
                  relief=tk.FLAT, padx=6, pady=3, cursor="hand2",
                  command=self._copy_log).pack(side=tk.RIGHT, padx=(4, 0))
        tk.Button(btn_frame, text="Clear", font=FONT_TINY, bg="#d0f0e8", fg=FG_BODY,
                  relief=tk.FLAT, padx=6, pady=3, cursor="hand2",
                  command=self._clear_log).pack(side=tk.RIGHT)

        # ── Controls row 2: Style + Resolution ──
        ctrl2 = tk.Frame(left, bg=BG_LIGHT)
        ctrl2.pack(fill=tk.X, padx=8, pady=(0, 4))

        # Style selector
        tk.Label(ctrl2, text="Style:", font=FONT_TINY, bg=BG_LIGHT, fg=FG_MUTED).pack(side=tk.LEFT)
        self._style_var = tk.StringVar(value=krita_cfg.DEFAULT_STYLE)
        style_names = list(krita_cfg.STYLE_PRESETS.keys())
        style_menu = tk.OptionMenu(ctrl2, self._style_var, *style_names)
        style_menu.configure(font=FONT_TINY, bg="#d0f0e8", fg=FG_BODY,
                            highlightthickness=0, relief=tk.FLAT)
        style_menu["menu"].configure(font=FONT_TINY)
        style_menu.pack(side=tk.LEFT, padx=(2, 8))

        # Resolution selector
        tk.Label(ctrl2, text="Size:", font=FONT_TINY, bg=BG_LIGHT, fg=FG_MUTED).pack(side=tk.LEFT)
        self._res_var = tk.StringVar(value=krita_cfg.DEFAULT_RESOLUTION)
        res_names = list(krita_cfg.RESOLUTION_PRESETS.keys())
        res_menu = tk.OptionMenu(ctrl2, self._res_var, *res_names)
        res_menu.configure(font=FONT_TINY, bg="#d0f0e8", fg=FG_BODY,
                          highlightthickness=0, relief=tk.FLAT)
        res_menu["menu"].configure(font=FONT_TINY)
        res_menu.pack(side=tk.LEFT, padx=(2, 8))

        # Model selector
        tk.Label(ctrl2, text="Model:", font=FONT_TINY, bg=BG_LIGHT, fg=FG_MUTED).pack(side=tk.LEFT)
        self._model_sel_var = tk.StringVar(value=krita_cfg.IMAGE_MODEL)
        model_names = list(krita_cfg.IMAGE_MODELS.keys())
        model_menu = tk.OptionMenu(ctrl2, self._model_sel_var, *model_names)
        model_menu.configure(font=FONT_TINY, bg="#d0f0e8", fg=FG_BODY,
                            highlightthickness=0, relief=tk.FLAT)
        model_menu["menu"].configure(font=FONT_TINY)
        model_menu.pack(side=tk.LEFT, padx=(2, 0))

        # ── Pipeline progress ──
        self._step_labels: list[tk.Label] = []
        prog_frame = tk.Frame(left, bg=BG_LIGHT)
        prog_frame.pack(fill=tk.X, padx=8, pady=(0, 6))

        for i, name in enumerate(PIPELINE_STEPS):
            if i > 0:
                tk.Label(prog_frame, text="\u2192", font=FONT_TINY, bg=BG_LIGHT,
                         fg="#5e9e8e").pack(side=tk.LEFT, padx=2)
            lbl = tk.Label(prog_frame, text=name, font=FONT_TINY, bg="#d0f0e8",
                           fg=STEP_PENDING, padx=6, pady=1, relief=tk.FLAT)
            lbl.pack(side=tk.LEFT, padx=1)
            self._step_labels.append(lbl)

        # Status text
        self._status_var = tk.StringVar(value="Ready")
        tk.Label(left, textvariable=self._status_var, font=FONT_SMALL, bg=BG_LIGHT,
                 fg=FG_MUTED, anchor=tk.W).pack(fill=tk.X, padx=8)

        # ── Log ──
        tk.Label(left, text="Log:", font=FONT_STATUS, bg=BG_LIGHT,
                 fg=FG_BODY).pack(anchor=tk.W, padx=8, pady=(4, 0))
        self._log = scrolledtext.ScrolledText(
            left, height=10, font=FONT_MONO, bg=BG_LOG, fg=FG_LOG,
            insertbackground=FG_LOG, relief=tk.SOLID, bd=1, state=tk.DISABLED,
            wrap=tk.WORD,
        )
        self._log.pack(fill=tk.BOTH, expand=True, padx=8, pady=(2, 8))

        self._log.tag_configure("error", foreground="#ef4444")
        self._log.tag_configure("success", foreground="#22c55e")
        self._log.tag_configure("step", foreground=ACCENT, font=("Consolas", 10, "bold"))
        self._log.tag_configure("info", foreground=FG_LOG)

        # ── Right column: Image canvas ──
        right = tk.Frame(paned, bg=BG_CANVAS, bd=1, relief=tk.SOLID)
        paned.add(right, minsize=400)

        # Image header
        img_hdr = tk.Frame(right, bg="#142020")
        img_hdr.pack(fill=tk.X)
        tk.Label(img_hdr, text="Generated Image", font=FONT_BODY,
                 bg="#142020", fg="#6db3a0").pack(side=tk.LEFT, padx=10, pady=6)

        self._img_status = tk.StringVar(value="No image yet")
        tk.Label(img_hdr, textvariable=self._img_status, font=FONT_TINY,
                 bg="#142020", fg="#3b6060").pack(side=tk.LEFT, padx=4)

        # Save + Copy buttons
        tk.Button(img_hdr, text="Save As...", font=FONT_TINY, bg="#142020", fg="#5e9e8e",
                  bd=0, padx=6, cursor="hand2", activebackground=BG_MID,
                  activeforeground="#d0f0e8",
                  command=self._save_image_as).pack(side=tk.RIGHT, padx=(0, 10), pady=6)
        tk.Button(img_hdr, text="Open Folder", font=FONT_TINY, bg="#142020", fg="#5e9e8e",
                  bd=0, padx=6, cursor="hand2", activebackground=BG_MID,
                  activeforeground="#d0f0e8",
                  command=self._open_output_folder).pack(side=tk.RIGHT, padx=4, pady=6)

        # Image canvas
        self._canvas = tk.Canvas(right, bg=BG_CANVAS, highlightthickness=0, cursor="crosshair")
        self._canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # Placeholder text
        self._canvas.create_text(
            400, 300, text="Your generated image will appear here\n\n"
            "Type a description and click 'Generate Image'\n"
            "or press Ctrl+Enter",
            font=("Segoe UI", 12), fill="#3b6060", justify=tk.CENTER,
            tags="placeholder",
        )

        # Canvas resize handler
        self._canvas.bind("<Configure>", self._on_canvas_resize)

        # ── Keyboard shortcuts ──
        self.bind("<Control-Return>", lambda e: self._on_generate())
        self.bind("<Control-l>", lambda e: self._clear_log())
        self.bind("<Escape>", lambda e: self._on_cancel())
        self.bind("<Control-s>", lambda e: self._save_image_as())

    # ── Generation ───────────────────────────────────────────────────

    def _insert_example(self, text: str) -> None:
        self._prompt.delete("1.0", tk.END)
        self._prompt.insert("1.0", text)

    def _on_enter(self, event: tk.Event) -> str:
        if not (event.state & 0x1):  # not Shift+Enter
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
        self._reset_progress()
        self._set_status("Starting...")
        self.title("KritaMCP \u2014 Generating...")

        mode = self._mode_var.get()
        threading.Thread(target=self._run_pipeline, args=(prompt, mode), daemon=True).start()

    def _on_cancel(self) -> None:
        if self._generating:
            self._cancel_event.set()
            self._log_msg("Cancelling...", "info")

    def _run_pipeline(self, prompt: str, mode: str) -> None:
        try:
            style = self._style_var.get()
            model = self._model_sel_var.get()
            style_name = krita_cfg.STYLE_PRESETS.get(style, {}).get("name", style)

            # Step 1: Prepare
            self._set_pipeline_step(0, "active")
            self._set_status("Preparing prompt...")
            self._log_msg("Preparing image generation...", "step")
            self._log_msg(f"  Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}", "info")
            self._log_msg(f"  Style: {style_name}", "info")
            self._log_msg(f"  Model: {model}", "info")

            if mode == "edit" and not self._current_image_data:
                self._log_msg("Edit mode requires an existing image. Switching to New.", "error")
                mode = "new"

            self._set_pipeline_step(0, "done")

            if self._cancel_event.is_set():
                self._log_msg("Cancelled.", "info")
                return

            # Step 2: Generate
            self._set_pipeline_step(1, "active")
            self._set_status("Generating image...")
            self._log_msg("Calling Gemini image generation...", "step")

            try:
                if mode == "edit" and self._current_image_data:
                    image_data, mime_type, was_cached = edit_image(
                        original_image=self._current_image_data,
                        edit_prompt=prompt,
                        style=style,
                        model=model,
                    )
                else:
                    image_data, mime_type, was_cached = generate_image(
                        prompt=prompt,
                        style=style,
                        model=model,
                    )
            except Exception as e:
                self._log_error(str(e))
                self._set_pipeline_step(1, "fail")
                self._set_status("Generation failed")
                return

            if was_cached:
                self._log_msg("Using cached image (saved API call)", "success")
            size_kb = len(image_data) / 1024
            self._log_msg(f"Image received: {size_kb:.1f} KB, {mime_type}", "info")
            self._set_pipeline_step(1, "done")

            if self._cancel_event.is_set():
                self._log_msg("Cancelled.", "info")
                return

            # Step 3: Save + Display
            self._set_pipeline_step(2, "active")
            self._set_status("Saving image...")
            self._log_msg("Saving to history...", "step")

            try:
                img_path = save_to_history(image_data, prompt, style, model)
                self._log_msg(f"Saved: {img_path.name}", "success")
            except Exception as e:
                self._log_msg(f"History save failed (non-critical): {e}", "info")
                img_path = None

            self._current_image_data = image_data
            self._current_image_path = img_path
            self._set_pipeline_step(2, "done")

            # Display on canvas
            self.after(0, lambda: self._display_image(image_data))

            self._set_status("Done!")
            safe_title = prompt[:50] + ("..." if len(prompt) > 50 else "")
            self.after(0, lambda: self.title(f"KritaMCP \u2014 {safe_title}"))
            self._log_msg("Image ready!", "success")

        except Exception as e:
            self._log_error(str(e))
            self._set_status("Error")
        finally:
            self._generating = False
            self.after(0, self._restore_generate_btn)

    def _restore_generate_btn(self) -> None:
        self._gen_btn.configure(text="Generate Image", bg=ACCENT, command=self._on_generate)

    # ── Image Display ─────────────────────────────────────────────────

    def _display_image(self, image_data: bytes) -> None:
        """Display image data on the canvas."""
        try:
            from PIL import Image, ImageTk

            # Open image from bytes
            img = Image.open(io.BytesIO(image_data))
            self._pil_image = img  # Keep reference

            # Fit to canvas
            self._fit_image_to_canvas(img)

            # Update status
            self._img_status.set(f"{img.width}×{img.height} px  |  {len(image_data) / 1024:.1f} KB")

        except ImportError:
            # Fallback without PIL — try PhotoImage (only supports PNG/GIF)
            try:
                import base64
                encoded = base64.b64encode(image_data).decode()
                photo = tk.PhotoImage(data=encoded)
                self._tk_image = photo
                self._canvas.delete("all")
                cw = self._canvas.winfo_width()
                ch = self._canvas.winfo_height()
                self._canvas.create_image(cw // 2, ch // 2, image=photo, anchor=tk.CENTER)
                self._img_status.set(f"{photo.width()}×{photo.height()} px")
            except Exception as e:
                self._log_msg(f"Failed to display image: {e}", "error")
        except Exception as e:
            self._log_msg(f"Failed to display image: {e}", "error")

    def _fit_image_to_canvas(self, img) -> None:
        """Scale image to fit canvas while maintaining aspect ratio."""
        from PIL import Image, ImageTk

        cw = max(self._canvas.winfo_width(), 400)
        ch = max(self._canvas.winfo_height(), 400)

        # Calculate scale to fit
        scale = min(cw / img.width, ch / img.height, 1.0)  # don't upscale
        new_w = int(img.width * scale)
        new_h = int(img.height * scale)

        if scale < 1.0:
            resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        else:
            resized = img

        photo = ImageTk.PhotoImage(resized)
        self._tk_image = photo  # Keep reference to prevent GC

        self._canvas.delete("all")
        self._canvas.create_image(cw // 2, ch // 2, image=photo, anchor=tk.CENTER)

    def _on_canvas_resize(self, event: tk.Event) -> None:
        """Re-fit image when canvas is resized."""
        if hasattr(self, "_pil_image") and self._pil_image:
            self.after(100, lambda: self._fit_image_to_canvas(self._pil_image))

    # ── File Operations ───────────────────────────────────────────────

    def _save_image_as(self) -> None:
        """Save current image to a user-chosen location."""
        if not self._current_image_data:
            self._log_msg("No image to save. Generate one first.", "error")
            return

        safe = "".join(
            c if c.isalnum() or c in " -_" else ""
            for c in self._current_prompt
        )[:50].strip().replace(" ", "_") or "image"

        path = filedialog.asksaveasfilename(
            initialdir=str(krita_cfg.OUTPUT_DIR),
            initialfile=f"{safe}.png",
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png"), ("JPEG Image", "*.jpg"), ("All Files", "*.*")],
            title="Save Image",
        )

        if path:
            try:
                full_path = Path(path)
                full_path.parent.mkdir(parents=True, exist_ok=True)

                # If saving as JPEG, convert from PNG
                if full_path.suffix.lower() in (".jpg", ".jpeg"):
                    try:
                        from PIL import Image
                        img = Image.open(io.BytesIO(self._current_image_data))
                        img = img.convert("RGB")  # Remove alpha for JPEG
                        img.save(str(full_path), "JPEG", quality=95)
                    except ImportError:
                        full_path.write_bytes(self._current_image_data)
                else:
                    full_path.write_bytes(self._current_image_data)

                self._log_msg(f"Saved: {full_path}", "success")
            except Exception as e:
                self._log_msg(f"Save failed: {e}", "error")

    def _open_output_folder(self) -> None:
        """Open the output/history folder in file explorer."""
        folder = krita_cfg.HISTORY_DIR
        if folder.exists():
            os.startfile(str(folder))
        else:
            self._log_msg("History folder doesn't exist yet.", "info")

    # ── History Dialog ────────────────────────────────────────────────

    def _open_history(self) -> None:
        """Open a dialog showing generation history."""
        win = tk.Toplevel(self)
        win.title("Image History")
        win.geometry("700x500")
        win.configure(bg=BG_LIGHT)
        win.transient(self)

        tk.Label(win, text="Generation History", font=FONT_HEADER,
                 bg=BG_LIGHT, fg=FG_BODY).pack(padx=16, pady=(16, 8))

        # History list
        frame = tk.Frame(win, bg=BG_LIGHT)
        frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)

        columns = ("prompt", "style", "time", "size")
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        tree.heading("prompt", text="Prompt", anchor=tk.W)
        tree.heading("style", text="Style", anchor=tk.W)
        tree.heading("time", text="Time", anchor=tk.W)
        tree.heading("size", text="Size", anchor=tk.E)
        tree.column("prompt", width=300)
        tree.column("style", width=100)
        tree.column("time", width=120)
        tree.column("size", width=80)

        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        tree.pack(fill=tk.BOTH, expand=True)

        # Populate
        history = list_history()
        history_map: dict[str, dict] = {}
        for item in history:
            iid = tree.insert("", tk.END, values=(
                item["prompt"][:60],
                item.get("style", ""),
                item.get("timestamp", ""),
                f"{item['size_bytes'] / 1024:.0f} KB",
            ))
            history_map[iid] = item

        # Buttons
        btn_row = tk.Frame(win, bg=BG_LIGHT)
        btn_row.pack(fill=tk.X, padx=16, pady=(0, 16))

        def _load_selected():
            sel = tree.selection()
            if not sel:
                return
            item = history_map.get(sel[0])
            if item and item["path"].exists():
                data = item["path"].read_bytes()
                self._current_image_data = data
                self._current_image_path = item["path"]
                self._current_prompt = item["prompt"]
                self._display_image(data)
                self._log_msg(f"Loaded from history: {item['filename']}", "info")
                win.destroy()

        def _delete_selected():
            sel = tree.selection()
            if not sel:
                return
            item = history_map.get(sel[0])
            if item:
                try:
                    item["path"].unlink(missing_ok=True)
                    meta = item["path"].with_suffix(".json")
                    meta.unlink(missing_ok=True)
                    tree.delete(sel[0])
                    self._log_msg(f"Deleted: {item['filename']}", "info")
                except Exception as e:
                    self._log_msg(f"Delete failed: {e}", "error")

        tk.Button(btn_row, text="Load Selected", font=FONT_BODY, bg=ACCENT, fg="white",
                  relief=tk.FLAT, padx=16, pady=4, command=_load_selected).pack(side=tk.LEFT)
        tk.Button(btn_row, text="Delete", font=FONT_SMALL, bg="#ef4444", fg="white",
                  relief=tk.FLAT, padx=10, pady=4, command=_delete_selected).pack(side=tk.LEFT, padx=(8, 0))
        tk.Button(btn_row, text="Open Folder", font=FONT_SMALL, bg="#d0f0e8", fg=FG_BODY,
                  relief=tk.FLAT, padx=10, pady=4,
                  command=self._open_output_folder).pack(side=tk.LEFT, padx=(8, 0))

        tk.Label(btn_row, text=f"{len(history)} images", font=FONT_TINY,
                 bg=BG_LIGHT, fg=FG_MUTED).pack(side=tk.RIGHT)

    # ── Settings ─────────────────────────────────────────────────────

    def _open_settings(self) -> None:
        win = tk.Toplevel(self)
        win.title("Krita Settings")
        win.geometry("480x380")
        win.resizable(False, False)
        win.configure(bg=BG_LIGHT)
        win.transient(self)
        win.grab_set()

        saved = krita_cfg.load_settings()
        entries: dict[str, tk.Variable] = {}

        frame = tk.Frame(win, bg=BG_LIGHT, padx=20, pady=16)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text="KritaMCP Settings", font=FONT_HEADER,
                 bg=BG_LIGHT, fg=FG_BODY).pack(anchor=tk.W, pady=(0, 12))

        # Output directory with browse
        out_row = tk.Frame(frame, bg=BG_LIGHT)
        out_row.pack(fill=tk.X, pady=3)
        tk.Label(out_row, text="Output Dir", font=FONT_SMALL, bg=BG_LIGHT,
                 fg=FG_BODY, width=14, anchor=tk.W).pack(side=tk.LEFT)
        out_var = tk.StringVar(value=saved.get("output_dir", ""))
        tk.Entry(out_row, textvariable=out_var, font=FONT_SMALL, width=28).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        entries["output_dir"] = out_var

        def _browse():
            d = filedialog.askdirectory(title="Select Output Folder")
            if d:
                out_var.set(d)

        tk.Button(out_row, text="Browse", font=FONT_TINY, bg="#d0f0e8", fg=FG_BODY,
                  relief=tk.FLAT, padx=6, command=_browse).pack(side=tk.LEFT, padx=(4, 0))

        # Dropdowns
        dropdowns = [
            ("Default Style", "default_style", list(krita_cfg.STYLE_PRESETS.keys())),
            ("Default Size", "default_resolution", list(krita_cfg.RESOLUTION_PRESETS.keys())),
            ("Image Model", "image_model", list(krita_cfg.IMAGE_MODELS.keys())),
        ]

        for label, key, options in dropdowns:
            row = tk.Frame(frame, bg=BG_LIGHT)
            row.pack(fill=tk.X, pady=3)
            tk.Label(row, text=label, font=FONT_SMALL, bg=BG_LIGHT, fg=FG_BODY,
                     width=14, anchor=tk.W).pack(side=tk.LEFT)
            var = tk.StringVar(value=str(saved.get(key, krita_cfg.DEFAULTS[key])))
            tk.OptionMenu(row, var, *options).pack(side=tk.LEFT, fill=tk.X, expand=True)
            entries[key] = var

        # Checkboxes
        checks = [
            ("Auto-save to history", "auto_save"),
            ("Save prompt metadata", "save_prompt_metadata"),
        ]
        check_frame = tk.Frame(frame, bg=BG_LIGHT)
        check_frame.pack(fill=tk.X, pady=(8, 0))
        for label, key in checks:
            var = tk.BooleanVar(value=saved.get(key, krita_cfg.DEFAULTS[key]))
            tk.Checkbutton(check_frame, text=label, variable=var, font=FONT_SMALL,
                           bg=BG_LIGHT, fg=FG_BODY, selectcolor=BG_LIGHT,
                           activebackground=BG_LIGHT).pack(side=tk.LEFT, padx=(0, 12))
            entries[key] = var

        # Cache stats
        stats = cache_stats()
        tk.Label(frame, text=f"Cache: {stats['entries']} images, {stats['total_mb']} MB",
                 font=FONT_TINY, bg=BG_LIGHT, fg=FG_MUTED).pack(anchor=tk.W, pady=(12, 0))

        def _clear():
            n = clear_cache()
            self._log_msg(f"Cleared {n} cached images", "info")
            win.destroy()
            self._open_settings()  # reopen to refresh stats

        tk.Button(frame, text="Clear Cache", font=FONT_TINY, bg="#fecaca", fg="#991b1b",
                  relief=tk.FLAT, padx=6, command=_clear).pack(anchor=tk.W, pady=(4, 0))

        def _save():
            new_settings = {}
            for key, var in entries.items():
                new_settings[key] = var.get()
            krita_cfg.save_settings(new_settings)
            krita_cfg.apply_settings(new_settings)
            self._model_var.set(f"\u25cf {krita_cfg.IMAGE_MODEL}")
            self._log_msg("Settings saved", "success")
            win.destroy()

        btn_row = tk.Frame(frame, bg=BG_LIGHT)
        btn_row.pack(fill=tk.X, pady=(16, 0))
        tk.Button(btn_row, text="Save", font=FONT_BODY, bg=ACCENT, fg="white",
                  relief=tk.FLAT, padx=16, pady=4, command=_save).pack(side=tk.LEFT)
        tk.Button(btn_row, text="Cancel", font=FONT_SMALL, bg="#d0f0e8", fg=FG_BODY,
                  relief=tk.FLAT, padx=10, pady=4, command=win.destroy).pack(side=tk.RIGHT)

    # ── Progress & Logging ───────────────────────────────────────────

    def _reset_progress(self) -> None:
        for lbl in self._step_labels:
            self.after(0, lambda l=lbl: l.configure(fg=STEP_PENDING, bg="#d0f0e8"))

    def _set_pipeline_step(self, index: int, state: str) -> None:
        colors = {"active": STEP_ACTIVE, "done": STEP_DONE, "fail": STEP_FAIL}
        fg = colors.get(state, STEP_PENDING)
        self.after(0, lambda: self._step_labels[index].configure(fg=fg))

    def _log_msg(self, msg: str, level: str = "info") -> None:
        self.after(0, self._append_log, msg, level)

    def _log_error(self, raw: str) -> None:
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
    app = KritaMCPApp()
    app.mainloop()


if __name__ == "__main__":
    main()
