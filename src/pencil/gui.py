"""Desktop GUI for PencilMCP — AI-powered UI/UX design generation."""

from __future__ import annotations

import os
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog, scrolledtext, ttk
from pathlib import Path

import src.config as cfg
from src.pencil import config as pencil_cfg
from src.pencil.llm import (
    generate_ui_code, save_to_history, list_history,
    clear_cache, cache_stats,
)
from src.pencil.examples import EXAMPLES
from src.error_messages import get_friendly_error

# ── Colours (indigo theme) ───────────────────────────────────────────
BG_DARK = "#0f172a"
BG_MID = "#1e293b"
BG_LIGHT = "#f1f5f9"
BG_LOG = "#0c1222"
FG_LOG = "#cbd5e1"
ACCENT = "#6366f1"
ACCENT_HOVER = "#4f46e5"
FG_DARK = "#f1f5f9"
FG_BODY = "#0f172a"
FG_MUTED = "#64748b"
BG_CODE = "#1e1e2e"

STEP_DONE = "#22c55e"
STEP_ACTIVE = ACCENT
STEP_FAIL = "#ef4444"
STEP_PENDING = "#475569"

FONT_BODY = ("Segoe UI", 11)
FONT_MONO = ("Consolas", 10)
FONT_CODE = ("Cascadia Code", 11)
FONT_HEADER = ("Segoe UI", 14, "bold")
FONT_STATUS = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 9)
FONT_TINY = ("Segoe UI", 8)

PIPELINE_STEPS = ["Prepare", "Generate", "Preview"]


class PencilMCPApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PencilMCP — Text to UI Design")
        self.geometry("1250x750")
        self.minsize(1050, 600)
        self.configure(bg=BG_LIGHT)

        # State
        self._generating = False
        self._cancel_event = threading.Event()
        self._current_prompt = ""
        self._current_code = ""
        self._current_path: Path | None = None

        # Load settings
        saved = pencil_cfg.load_settings()
        pencil_cfg.apply_settings(saved)

        self._build_ui()

    def _build_ui(self) -> None:
        # ── Header bar ──
        header = tk.Frame(self, bg=BG_DARK, height=48)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        tk.Label(
            header, text="PencilMCP  \u2014  Text to UI Design", font=FONT_HEADER,
            bg=BG_DARK, fg=FG_DARK,
        ).pack(side=tk.LEFT, padx=16, pady=8)

        right_hdr = tk.Frame(header, bg=BG_DARK)
        right_hdr.pack(side=tk.RIGHT, padx=12, pady=8)

        tk.Button(
            right_hdr, text="\u2699", font=("Segoe UI", 14),
            bg=BG_DARK, fg="#818cf8", bd=0, cursor="hand2",
            activebackground=BG_DARK, activeforeground=FG_DARK,
            command=self._open_settings,
        ).pack(side=tk.RIGHT, padx=(8, 0))

        tk.Button(
            right_hdr, text="\U0001f5c2 History", font=FONT_SMALL,
            bg=BG_DARK, fg="#818cf8", bd=0, cursor="hand2",
            activebackground=BG_DARK, activeforeground=FG_DARK,
            command=self._open_history,
        ).pack(side=tk.RIGHT, padx=(0, 8))

        self._framework_label = tk.StringVar(value=f"\u25cf {pencil_cfg.DEFAULT_FRAMEWORK}")
        tk.Label(
            right_hdr, textvariable=self._framework_label, font=FONT_TINY,
            bg=BG_DARK, fg="#22c55e",
        ).pack(side=tk.RIGHT, padx=(0, 12))

        # ── Body: PanedWindow ──
        paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg="#6366f1",
                               sashwidth=5, sashrelief=tk.FLAT)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        # ── Left column: prompt + controls + log ──
        left = tk.Frame(paned, bg=BG_LIGHT)
        paned.add(left, minsize=320, width=400)

        # Prompt
        prompt_hdr = tk.Frame(left, bg=BG_LIGHT)
        prompt_hdr.pack(fill=tk.X, padx=8, pady=(8, 0))
        tk.Label(prompt_hdr, text="Describe your UI design:", font=FONT_BODY,
                 bg=BG_LIGHT, fg=FG_BODY).pack(side=tk.LEFT)

        self._prompt = tk.Text(left, height=3, font=FONT_BODY, wrap=tk.WORD,
                               relief=tk.SOLID, bd=1)
        self._prompt.pack(fill=tk.X, padx=8, pady=(4, 6))
        self._prompt.bind("<Return>", self._on_enter)

        # ── Row 1: Generate + Examples + Mode ──
        btn_frame = tk.Frame(left, bg=BG_LIGHT)
        btn_frame.pack(fill=tk.X, padx=8, pady=(0, 4))

        self._gen_btn = tk.Button(
            btn_frame, text="Generate Design", font=FONT_BODY,
            bg=ACCENT, fg="white", activebackground=ACCENT_HOVER,
            activeforeground="white", relief=tk.FLAT, padx=14, pady=5,
            cursor="hand2", command=self._on_generate,
        )
        self._gen_btn.pack(side=tk.LEFT)

        # Examples
        examples_btn = tk.Menubutton(
            btn_frame, text="Examples \u25bc", font=FONT_STATUS,
            bg="#4f46e5", fg="white", activebackground="#4338ca",
            activeforeground="white", relief=tk.FLAT, padx=10, pady=5,
            cursor="hand2",
        )
        examples_btn.pack(side=tk.LEFT, padx=(6, 0))
        examples_menu = tk.Menu(examples_btn, tearoff=False, font=FONT_SMALL)
        for category, prompts in EXAMPLES.items():
            sub = tk.Menu(examples_menu, tearoff=False, font=FONT_SMALL)
            for p in prompts:
                display = p[:80] + "..." if len(p) > 80 else p
                sub.add_command(label=display, command=lambda txt=p: self._insert_example(txt))
            examples_menu.add_cascade(label=category, menu=sub)
        examples_btn.configure(menu=examples_menu)

        # Mode
        self._mode_var = tk.StringVar(value="new")
        mode_frame = tk.Frame(btn_frame, bg=BG_LIGHT)
        mode_frame.pack(side=tk.LEFT, padx=(12, 0))
        tk.Radiobutton(mode_frame, text="New", variable=self._mode_var, value="new",
                        font=FONT_SMALL, bg=BG_LIGHT, fg=FG_BODY, selectcolor=BG_LIGHT,
                        activebackground=BG_LIGHT).pack(side=tk.LEFT)
        tk.Radiobutton(mode_frame, text="Modify", variable=self._mode_var, value="modify",
                        font=FONT_SMALL, bg=BG_LIGHT, fg=FG_BODY, selectcolor=BG_LIGHT,
                        activebackground=BG_LIGHT).pack(side=tk.LEFT)

        # Log buttons
        tk.Button(btn_frame, text="Copy Log", font=FONT_TINY, bg="#e0e7ff", fg=FG_BODY,
                  relief=tk.FLAT, padx=6, pady=3, cursor="hand2",
                  command=self._copy_log).pack(side=tk.RIGHT, padx=(4, 0))
        tk.Button(btn_frame, text="Clear", font=FONT_TINY, bg="#e0e7ff", fg=FG_BODY,
                  relief=tk.FLAT, padx=6, pady=3, cursor="hand2",
                  command=self._clear_log).pack(side=tk.RIGHT)

        # ── Row 2: Design type + Framework + Theme ──
        ctrl2 = tk.Frame(left, bg=BG_LIGHT)
        ctrl2.pack(fill=tk.X, padx=8, pady=(0, 4))

        # Design type
        tk.Label(ctrl2, text="Type:", font=FONT_TINY, bg=BG_LIGHT, fg=FG_MUTED).pack(side=tk.LEFT)
        self._type_var = tk.StringVar(value="full_page")
        type_menu = tk.OptionMenu(ctrl2, self._type_var,
                                   *list(pencil_cfg.DESIGN_TYPES.keys()))
        type_menu.configure(font=FONT_TINY, bg="#e0e7ff", fg=FG_BODY,
                           highlightthickness=0, relief=tk.FLAT)
        type_menu["menu"].configure(font=FONT_TINY)
        type_menu.pack(side=tk.LEFT, padx=(2, 6))

        # Framework
        tk.Label(ctrl2, text="Framework:", font=FONT_TINY, bg=BG_LIGHT, fg=FG_MUTED).pack(side=tk.LEFT)
        self._framework_var = tk.StringVar(value=pencil_cfg.DEFAULT_FRAMEWORK)
        fw_menu = tk.OptionMenu(ctrl2, self._framework_var,
                                 *list(pencil_cfg.FRAMEWORKS.keys()))
        fw_menu.configure(font=FONT_TINY, bg="#e0e7ff", fg=FG_BODY,
                         highlightthickness=0, relief=tk.FLAT)
        fw_menu["menu"].configure(font=FONT_TINY)
        fw_menu.pack(side=tk.LEFT, padx=(2, 6))

        # Color theme
        tk.Label(ctrl2, text="Theme:", font=FONT_TINY, bg=BG_LIGHT, fg=FG_MUTED).pack(side=tk.LEFT)
        self._theme_var = tk.StringVar(value="clean_light")
        theme_menu = tk.OptionMenu(ctrl2, self._theme_var,
                                    *list(pencil_cfg.COLOR_THEMES.keys()))
        theme_menu.configure(font=FONT_TINY, bg="#e0e7ff", fg=FG_BODY,
                            highlightthickness=0, relief=tk.FLAT)
        theme_menu["menu"].configure(font=FONT_TINY)
        theme_menu.pack(side=tk.LEFT, padx=(2, 0))

        # ── Pipeline progress ──
        self._step_labels: list[tk.Label] = []
        prog_frame = tk.Frame(left, bg=BG_LIGHT)
        prog_frame.pack(fill=tk.X, padx=8, pady=(0, 6))

        for i, name in enumerate(PIPELINE_STEPS):
            if i > 0:
                tk.Label(prog_frame, text="\u2192", font=FONT_TINY, bg=BG_LIGHT,
                         fg="#818cf8").pack(side=tk.LEFT, padx=2)
            lbl = tk.Label(prog_frame, text=name, font=FONT_TINY, bg="#e0e7ff",
                           fg=STEP_PENDING, padx=6, pady=1, relief=tk.FLAT)
            lbl.pack(side=tk.LEFT, padx=1)
            self._step_labels.append(lbl)

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

        # ── Right column: Code editor ──
        right = tk.Frame(paned, bg=BG_CODE, bd=1, relief=tk.SOLID)
        paned.add(right, minsize=450)

        # Code header
        code_hdr = tk.Frame(right, bg="#181825")
        code_hdr.pack(fill=tk.X)
        tk.Label(code_hdr, text="Generated Code", font=FONT_BODY,
                 bg="#181825", fg="#a5b4fc").pack(side=tk.LEFT, padx=10, pady=6)

        self._code_status = tk.StringVar(value="No code yet")
        tk.Label(code_hdr, textvariable=self._code_status, font=FONT_TINY,
                 bg="#181825", fg="#475569").pack(side=tk.LEFT, padx=4)

        # Action buttons
        tk.Button(code_hdr, text="\U0001f310 Preview in Browser", font=FONT_TINY,
                  bg="#4f46e5", fg="white", bd=0, padx=8, pady=2, cursor="hand2",
                  activebackground="#4338ca",
                  command=self._preview_in_browser).pack(side=tk.RIGHT, padx=(0, 10), pady=6)
        tk.Button(code_hdr, text="Save As...", font=FONT_TINY, bg="#181825", fg="#818cf8",
                  bd=0, padx=6, cursor="hand2", activebackground=BG_MID,
                  command=self._save_code_as).pack(side=tk.RIGHT, padx=4, pady=6)
        tk.Button(code_hdr, text="Copy Code", font=FONT_TINY, bg="#181825", fg="#818cf8",
                  bd=0, padx=6, cursor="hand2", activebackground=BG_MID,
                  command=self._copy_code).pack(side=tk.RIGHT, padx=4, pady=6)

        # Code text area with syntax highlighting
        self._code_editor = scrolledtext.ScrolledText(
            right, font=FONT_CODE, bg=BG_CODE, fg="#cdd6f4",
            insertbackground="#cdd6f4", relief=tk.FLAT, state=tk.DISABLED,
            wrap=tk.NONE, undo=True,
        )
        self._code_editor.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # Syntax highlighting tags
        self._code_editor.tag_configure("tag", foreground="#89b4fa")        # HTML tags
        self._code_editor.tag_configure("attr", foreground="#a6e3a1")       # attributes
        self._code_editor.tag_configure("string", foreground="#f9e2af")     # strings
        self._code_editor.tag_configure("comment", foreground="#6c7086")    # comments
        self._code_editor.tag_configure("keyword", foreground="#cba6f7")    # CSS keywords
        self._code_editor.tag_configure("selector", foreground="#f38ba8")   # CSS selectors
        self._code_editor.tag_configure("value", foreground="#fab387")      # values

        # ── Keyboard shortcuts ──
        self.bind("<Control-Return>", lambda e: self._on_generate())
        self.bind("<Control-l>", lambda e: self._clear_log())
        self.bind("<Escape>", lambda e: self._on_cancel())
        self.bind("<Control-b>", lambda e: self._preview_in_browser())
        self.bind("<Control-s>", lambda e: self._save_code_as())

    # ── Generation ───────────────────────────────────────────────────

    def _insert_example(self, text: str) -> None:
        self._prompt.delete("1.0", tk.END)
        self._prompt.insert("1.0", text)

    def _on_enter(self, event: tk.Event) -> str:
        if not (event.state & 0x1):
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
        self.title("PencilMCP \u2014 Generating...")

        mode = self._mode_var.get()
        threading.Thread(target=self._run_pipeline, args=(prompt, mode), daemon=True).start()

    def _on_cancel(self) -> None:
        if self._generating:
            self._cancel_event.set()
            self._log_msg("Cancelling...", "info")

    def _run_pipeline(self, prompt: str, mode: str) -> None:
        try:
            framework = self._framework_var.get()
            design_type = self._type_var.get()
            color_theme = self._theme_var.get()
            fw_name = pencil_cfg.FRAMEWORKS.get(framework, {}).get("name", framework)
            dt_name = pencil_cfg.DESIGN_TYPES.get(design_type, {}).get("name", design_type)
            ct_name = pencil_cfg.COLOR_THEMES.get(color_theme, {}).get("name", color_theme)

            # Step 1: Prepare
            self._set_pipeline_step(0, "active")
            self._set_status("Preparing...")
            self._log_msg("Preparing design generation...", "step")
            self._log_msg(f"  Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}", "info")
            self._log_msg(f"  Type: {dt_name}  |  Framework: {fw_name}  |  Theme: {ct_name}", "info")

            existing = ""
            if mode == "modify" and self._current_code:
                existing = self._current_code
                self._log_msg(f"  Modify mode: {len(existing)} chars existing code", "info")

            self._set_pipeline_step(0, "done")

            if self._cancel_event.is_set():
                self._log_msg("Cancelled.", "info")
                return

            # Step 2: Generate
            self._set_pipeline_step(1, "active")
            self._set_status("Generating UI code...")
            self._log_msg("Calling Gemini...", "step")

            try:
                code, was_cached = generate_ui_code(
                    description=prompt,
                    design_type=design_type,
                    framework=framework,
                    color_theme=color_theme,
                    existing_code=existing,
                )
            except Exception as e:
                self._log_error(str(e))
                self._set_pipeline_step(1, "fail")
                self._set_status("Generation failed")
                return

            if was_cached:
                self._log_msg("Using cached code (saved API call)", "success")
            lines = len(code.splitlines())
            self._log_msg(f"Generated {lines} lines of code", "info")
            self._set_pipeline_step(1, "done")

            if self._cancel_event.is_set():
                self._log_msg("Cancelled.", "info")
                return

            # Step 3: Preview
            self._set_pipeline_step(2, "active")
            self._set_status("Saving & previewing...")
            self._log_msg("Processing output...", "step")

            self._current_code = code

            # Save to history
            try:
                path = save_to_history(code, prompt, design_type, framework, color_theme)
                self._current_path = path
                self._log_msg(f"Saved: {path.name}", "success")
            except Exception as e:
                self._log_msg(f"History save failed: {e}", "info")

            # Display code
            self.after(0, lambda: self._display_code(code))
            self._set_pipeline_step(2, "done")

            # Auto-preview
            if pencil_cfg.AUTO_PREVIEW and framework in ("html_css", "html_bootstrap"):
                self.after(500, self._preview_in_browser)
                self._log_msg("Auto-previewing in browser...", "info")

            self._set_status("Done!")
            safe_title = prompt[:50] + ("..." if len(prompt) > 50 else "")
            self.after(0, lambda: self.title(f"PencilMCP \u2014 {safe_title}"))
            self._log_msg("Design ready!", "success")

        except Exception as e:
            self._log_error(str(e))
            self._set_status("Error")
        finally:
            self._generating = False
            self.after(0, self._restore_generate_btn)

    def _restore_generate_btn(self) -> None:
        self._gen_btn.configure(text="Generate Design", bg=ACCENT, command=self._on_generate)

    # ── Code Display ──────────────────────────────────────────────────

    def _display_code(self, code: str) -> None:
        """Display generated code with syntax highlighting."""
        self._code_editor.configure(state=tk.NORMAL)
        self._code_editor.delete("1.0", tk.END)
        self._code_editor.insert("1.0", code)

        self._highlight_syntax(code)

        self._code_editor.configure(state=tk.DISABLED)
        lines = len(code.splitlines())
        chars = len(code)
        self._code_status.set(f"{lines} lines  |  {chars} chars")

    def _highlight_syntax(self, code: str) -> None:
        """Basic syntax highlighting for HTML/CSS/JSX."""
        import re

        content = self._code_editor.get("1.0", tk.END)

        # HTML tags: <tag>, </tag>, <tag/>
        for match in re.finditer(r'</?[\w-]+', content):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self._code_editor.tag_add("tag", start, end)

        # Closing >
        for match in re.finditer(r'/?>',  content):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self._code_editor.tag_add("tag", start, end)

        # Strings: "..." and '...'
        for match in re.finditer(r'"[^"]*"|\'[^\']*\'', content):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self._code_editor.tag_add("string", start, end)

        # HTML comments: <!-- ... -->
        for match in re.finditer(r'<!--.*?-->', content, re.DOTALL):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self._code_editor.tag_add("comment", start, end)

        # CSS comments: /* ... */
        for match in re.finditer(r'/\*.*?\*/', content, re.DOTALL):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self._code_editor.tag_add("comment", start, end)

        # CSS properties (word followed by :)
        for match in re.finditer(r'[\w-]+(?=\s*:)', content):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self._code_editor.tag_add("keyword", start, end)

        # HTML attributes (word followed by =)
        for match in re.finditer(r'[\w-]+(?==)', content):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self._code_editor.tag_add("attr", start, end)

    # ── Preview & Save ────────────────────────────────────────────────

    def _preview_in_browser(self) -> None:
        """Save current code to temp file and open in browser."""
        if not self._current_code:
            self._log_msg("No code to preview. Generate a design first.", "error")
            return

        framework = self._framework_var.get()

        if framework in ("html_css", "html_bootstrap"):
            # Direct HTML preview
            preview_path = pencil_cfg.OUTPUT_DIR / "_preview.html"
            preview_path.write_text(self._current_code, encoding="utf-8")
            webbrowser.open(preview_path.as_uri())
            self._log_msg(f"Preview opened: {preview_path}", "info")
        elif framework == "react_tailwind":
            # Wrap in HTML with Tailwind CDN + React CDN for preview
            wrapped = self._wrap_react_for_preview(self._current_code)
            preview_path = pencil_cfg.OUTPUT_DIR / "_preview.html"
            preview_path.write_text(wrapped, encoding="utf-8")
            webbrowser.open(preview_path.as_uri())
            self._log_msg("React preview opened (with CDN wrappers)", "info")
        else:
            # For Vue/Svelte, just open the code file
            if self._current_path and self._current_path.exists():
                os.startfile(str(self._current_path))
            else:
                self._log_msg(f"Direct preview not available for {framework}. Use Save As.", "info")

    def _wrap_react_for_preview(self, jsx_code: str) -> str:
        """Wrap a React component in a standalone HTML for browser preview."""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PencilMCP Preview</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
    <script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
    <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
</head>
<body>
    <div id="root"></div>
    <script type="text/babel">
{jsx_code}

// Auto-render
const rootEl = document.getElementById('root');
const root = ReactDOM.createRoot(rootEl);
// Try to find the default export
const Component = typeof App !== 'undefined' ? App :
                  typeof Default !== 'undefined' ? Default :
                  () => React.createElement('div', null, 'Component rendered');
root.render(React.createElement(Component));
    </script>
</body>
</html>"""

    def _save_code_as(self) -> None:
        if not self._current_code:
            self._log_msg("No code to save.", "error")
            return

        framework = self._framework_var.get()
        ext = pencil_cfg.FRAMEWORKS.get(framework, {}).get("extension", ".html")
        safe = "".join(
            c if c.isalnum() or c in " -_" else ""
            for c in self._current_prompt
        )[:40].strip().replace(" ", "_") or "design"

        path = filedialog.asksaveasfilename(
            initialdir=str(pencil_cfg.OUTPUT_DIR),
            initialfile=f"{safe}{ext}",
            defaultextension=ext,
            filetypes=[
                ("HTML", "*.html"), ("JSX", "*.jsx"),
                ("Vue", "*.vue"), ("Svelte", "*.svelte"),
                ("All Files", "*.*"),
            ],
            title="Save Design Code",
        )

        if path:
            try:
                Path(path).write_text(self._current_code, encoding="utf-8")
                self._log_msg(f"Saved: {path}", "success")
            except Exception as e:
                self._log_msg(f"Save failed: {e}", "error")

    def _copy_code(self) -> None:
        if not self._current_code:
            self._log_msg("No code to copy.", "error")
            return
        self.clipboard_clear()
        self.clipboard_append(self._current_code)
        self._set_status("Code copied to clipboard")

    def _open_output_folder(self) -> None:
        if pencil_cfg.OUTPUT_DIR.exists():
            os.startfile(str(pencil_cfg.OUTPUT_DIR))

    # ── History Dialog ────────────────────────────────────────────────

    def _open_history(self) -> None:
        win = tk.Toplevel(self)
        win.title("Design History")
        win.geometry("700x500")
        win.configure(bg=BG_LIGHT)
        win.transient(self)

        tk.Label(win, text="Design History", font=FONT_HEADER,
                 bg=BG_LIGHT, fg=FG_BODY).pack(padx=16, pady=(16, 8))

        frame = tk.Frame(win, bg=BG_LIGHT)
        frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)

        columns = ("prompt", "type", "framework", "time")
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        tree.heading("prompt", text="Prompt", anchor=tk.W)
        tree.heading("type", text="Type", anchor=tk.W)
        tree.heading("framework", text="Framework", anchor=tk.W)
        tree.heading("time", text="Time", anchor=tk.W)
        tree.column("prompt", width=280)
        tree.column("type", width=100)
        tree.column("framework", width=100)
        tree.column("time", width=120)

        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        tree.pack(fill=tk.BOTH, expand=True)

        history = list_history()
        history_map: dict[str, dict] = {}
        for item in history:
            iid = tree.insert("", tk.END, values=(
                item["prompt"][:60],
                item.get("design_type", ""),
                item.get("framework", ""),
                item.get("timestamp", ""),
            ))
            history_map[iid] = item

        btn_row = tk.Frame(win, bg=BG_LIGHT)
        btn_row.pack(fill=tk.X, padx=16, pady=(0, 16))

        def _load():
            sel = tree.selection()
            if not sel:
                return
            item = history_map.get(sel[0])
            if item and item["path"].exists():
                code = item["path"].read_text(encoding="utf-8")
                self._current_code = code
                self._current_path = item["path"]
                self._current_prompt = item["prompt"]
                self._display_code(code)
                self._log_msg(f"Loaded: {item['filename']}", "info")
                win.destroy()

        tk.Button(btn_row, text="Load Selected", font=FONT_BODY, bg=ACCENT, fg="white",
                  relief=tk.FLAT, padx=16, pady=4, command=_load).pack(side=tk.LEFT)
        tk.Button(btn_row, text="Open Folder", font=FONT_SMALL, bg="#e0e7ff", fg=FG_BODY,
                  relief=tk.FLAT, padx=10, pady=4,
                  command=self._open_output_folder).pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(btn_row, text=f"{len(history)} designs", font=FONT_TINY,
                 bg=BG_LIGHT, fg=FG_MUTED).pack(side=tk.RIGHT)

    # ── Settings ─────────────────────────────────────────────────────

    def _open_settings(self) -> None:
        win = tk.Toplevel(self)
        win.title("Pencil Settings")
        win.geometry("480x360")
        win.resizable(False, False)
        win.configure(bg=BG_LIGHT)
        win.transient(self)
        win.grab_set()

        saved = pencil_cfg.load_settings()
        entries: dict[str, tk.Variable] = {}

        frame = tk.Frame(win, bg=BG_LIGHT, padx=20, pady=16)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text="PencilMCP Settings", font=FONT_HEADER,
                 bg=BG_LIGHT, fg=FG_BODY).pack(anchor=tk.W, pady=(0, 12))

        # Output dir
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

        tk.Button(out_row, text="Browse", font=FONT_TINY, bg="#e0e7ff", fg=FG_BODY,
                  relief=tk.FLAT, padx=6, command=_browse).pack(side=tk.LEFT, padx=(4, 0))

        # Dropdowns
        dropdowns = [
            ("Default Framework", "default_framework", list(pencil_cfg.FRAMEWORKS.keys())),
        ]
        for label, key, options in dropdowns:
            row = tk.Frame(frame, bg=BG_LIGHT)
            row.pack(fill=tk.X, pady=3)
            tk.Label(row, text=label, font=FONT_SMALL, bg=BG_LIGHT, fg=FG_BODY,
                     width=14, anchor=tk.W).pack(side=tk.LEFT)
            var = tk.StringVar(value=str(saved.get(key, pencil_cfg.DEFAULTS[key])))
            tk.OptionMenu(row, var, *options).pack(side=tk.LEFT, fill=tk.X, expand=True)
            entries[key] = var

        # Checkboxes
        checks = [
            ("Auto-preview in browser", "auto_preview"),
            ("Auto-save to history", "auto_save"),
        ]
        check_frame = tk.Frame(frame, bg=BG_LIGHT)
        check_frame.pack(fill=tk.X, pady=(8, 0))
        for label, key in checks:
            var = tk.BooleanVar(value=saved.get(key, pencil_cfg.DEFAULTS[key]))
            tk.Checkbutton(check_frame, text=label, variable=var, font=FONT_SMALL,
                           bg=BG_LIGHT, fg=FG_BODY, selectcolor=BG_LIGHT,
                           activebackground=BG_LIGHT).pack(side=tk.LEFT, padx=(0, 12))
            entries[key] = var

        # Cache
        stats = cache_stats()
        tk.Label(frame, text=f"Cache: {stats['entries']} items, {stats['total_kb']} KB",
                 font=FONT_TINY, bg=BG_LIGHT, fg=FG_MUTED).pack(anchor=tk.W, pady=(12, 0))

        def _clear():
            n = clear_cache()
            self._log_msg(f"Cleared {n} cached designs", "info")
            win.destroy()
            self._open_settings()

        tk.Button(frame, text="Clear Cache", font=FONT_TINY, bg="#fecaca", fg="#991b1b",
                  relief=tk.FLAT, padx=6, command=_clear).pack(anchor=tk.W, pady=(4, 0))

        def _save():
            new = {}
            for key, var in entries.items():
                new[key] = var.get()
            pencil_cfg.save_settings(new)
            pencil_cfg.apply_settings(new)
            self._framework_label.set(f"\u25cf {pencil_cfg.DEFAULT_FRAMEWORK}")
            self._log_msg("Settings saved", "success")
            win.destroy()

        btn_row = tk.Frame(frame, bg=BG_LIGHT)
        btn_row.pack(fill=tk.X, pady=(16, 0))
        tk.Button(btn_row, text="Save", font=FONT_BODY, bg=ACCENT, fg="white",
                  relief=tk.FLAT, padx=16, pady=4, command=_save).pack(side=tk.LEFT)
        tk.Button(btn_row, text="Cancel", font=FONT_SMALL, bg="#e0e7ff", fg=FG_BODY,
                  relief=tk.FLAT, padx=10, pady=4, command=win.destroy).pack(side=tk.RIGHT)

    # ── Progress & Logging ───────────────────────────────────────────

    def _reset_progress(self) -> None:
        for lbl in self._step_labels:
            self.after(0, lambda l=lbl: l.configure(fg=STEP_PENDING, bg="#e0e7ff"))

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
    app = PencilMCPApp()
    app.mainloop()


if __name__ == "__main__":
    main()
