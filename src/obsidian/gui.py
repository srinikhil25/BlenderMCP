"""Desktop GUI for Obsidian MCP — AI-powered note generation."""

from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext
from pathlib import Path

import src.config as cfg
from src.obsidian import config as obs_cfg
from src.obsidian.llm import generate_note
from src.obsidian.vault import (
    get_vault_path, list_notes, list_note_titles, read_note, write_note,
    extract_title_from_markdown, slugify, search_notes,
)
from src.obsidian.examples import EXAMPLES
from src.error_messages import get_friendly_error

# ── Colours ──────────────────────────────────────────────────────────
BG_DARK = "#1e1b2e"
BG_MID = "#2d2640"
BG_LIGHT = "#f8f7fc"
BG_LOG = "#0f0d1a"
FG_LOG = "#e2e0f0"
ACCENT = "#7c3aed"
ACCENT_HOVER = "#6d28d9"
FG_DARK = "#f1f0f9"
FG_BODY = "#1e1b2e"
FG_MUTED = "#6b6580"
BG_PREVIEW = "#1a1726"

STEP_DONE = "#22c55e"
STEP_ACTIVE = ACCENT
STEP_FAIL = "#ef4444"
STEP_PENDING = "#4b4560"

FONT_BODY = ("Segoe UI", 11)
FONT_MONO = ("Consolas", 10)
FONT_HEADER = ("Segoe UI", 14, "bold")
FONT_STATUS = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 9)
FONT_TINY = ("Segoe UI", 8)

PIPELINE_STEPS = ["Generate", "Process", "Save"]


class ObsidianMCPApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("ObsidianMCP — Text to Knowledge")
        self.geometry("1120x720")
        self.minsize(900, 600)
        self.configure(bg=BG_LIGHT)

        # State
        self._generating = False
        self._cancel_event = threading.Event()
        self._current_prompt = ""
        self._current_note = ""

        # Load settings
        saved = obs_cfg.load_settings()
        obs_cfg.apply_settings(saved)

        self._build_ui()
        self._check_vault()

    def _build_ui(self) -> None:
        # ── Header bar ──
        header = tk.Frame(self, bg=BG_DARK, height=48)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        tk.Label(
            header, text="ObsidianMCP  \u2014  Text to Knowledge", font=FONT_HEADER,
            bg=BG_DARK, fg=FG_DARK,
        ).pack(side=tk.LEFT, padx=16, pady=8)

        # Right side
        right_hdr = tk.Frame(header, bg=BG_DARK)
        right_hdr.pack(side=tk.RIGHT, padx=12, pady=8)

        # Settings gear
        tk.Button(
            right_hdr, text="\u2699", font=("Segoe UI", 14),
            bg=BG_DARK, fg="#9b8fc4", bd=0, cursor="hand2",
            activebackground=BG_DARK, activeforeground=FG_DARK,
            command=self._open_settings,
        ).pack(side=tk.RIGHT, padx=(8, 0))

        # Vault status
        self._vault_var = tk.StringVar(value="\u25cf No vault")
        self._vault_label = tk.Label(
            right_hdr, textvariable=self._vault_var, font=FONT_SMALL,
            bg=BG_DARK, fg="#ef4444",
        )
        self._vault_label.pack(side=tk.RIGHT, padx=(0, 12))

        # ── Body: PanedWindow ──
        paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg="#c4b5d0", sashwidth=5, sashrelief=tk.FLAT)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        # ── Left column: prompt + controls + log ──
        left = tk.Frame(paned, bg=BG_LIGHT)
        paned.add(left, minsize=350, width=480)

        # Prompt label
        prompt_hdr = tk.Frame(left, bg=BG_LIGHT)
        prompt_hdr.pack(fill=tk.X, padx=8, pady=(8, 0))
        tk.Label(prompt_hdr, text="Describe your note:", font=FONT_BODY, bg=BG_LIGHT, fg=FG_BODY).pack(side=tk.LEFT)

        # Prompt text area
        self._prompt = tk.Text(left, height=3, font=FONT_BODY, wrap=tk.WORD, relief=tk.SOLID, bd=1)
        self._prompt.pack(fill=tk.X, padx=8, pady=(4, 6))
        self._prompt.bind("<Return>", self._on_enter)

        # ── Buttons row ──
        btn_frame = tk.Frame(left, bg=BG_LIGHT)
        btn_frame.pack(fill=tk.X, padx=8, pady=(0, 4))

        self._gen_btn = tk.Button(
            btn_frame, text="Generate Note", font=FONT_BODY,
            bg=ACCENT, fg="white", activebackground=ACCENT_HOVER,
            activeforeground="white", relief=tk.FLAT, padx=14, pady=5,
            cursor="hand2", command=self._on_generate,
        )
        self._gen_btn.pack(side=tk.LEFT)

        # Examples dropdown
        examples_btn = tk.Menubutton(
            btn_frame, text="Examples \u25bc", font=FONT_STATUS,
            bg="#8b5cf6", fg="white", activebackground="#7c3aed",
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
        tk.Radiobutton(mode_frame, text="Modify", variable=self._mode_var, value="modify",
                        font=FONT_SMALL, bg=BG_LIGHT, fg=FG_BODY, selectcolor=BG_LIGHT,
                        activebackground=BG_LIGHT).pack(side=tk.LEFT)

        # Template selector
        self._template_var = tk.StringVar(value="standard")
        tmpl_frame = tk.Frame(btn_frame, bg=BG_LIGHT)
        tmpl_frame.pack(side=tk.LEFT, padx=(8, 0))
        tk.Label(tmpl_frame, text="Style:", font=FONT_TINY, bg=BG_LIGHT, fg=FG_MUTED).pack(side=tk.LEFT)
        tmpl_menu = tk.OptionMenu(tmpl_frame, self._template_var,
                                   "standard", "cornell", "zettelkasten", "meeting", "research")
        tmpl_menu.configure(font=FONT_TINY, bg="#e8e4f0", fg=FG_BODY,
                            highlightthickness=0, relief=tk.FLAT)
        tmpl_menu["menu"].configure(font=FONT_TINY)
        tmpl_menu.pack(side=tk.LEFT)

        # Right-side buttons
        tk.Button(btn_frame, text="Copy Log", font=FONT_TINY, bg="#e8e4f0", fg=FG_BODY,
                  relief=tk.FLAT, padx=6, pady=3, cursor="hand2",
                  command=self._copy_log).pack(side=tk.RIGHT, padx=(4, 0))
        tk.Button(btn_frame, text="Clear", font=FONT_TINY, bg="#e8e4f0", fg=FG_BODY,
                  relief=tk.FLAT, padx=6, pady=3, cursor="hand2",
                  command=self._clear_log).pack(side=tk.RIGHT)

        # ── Pipeline progress ──
        self._step_labels: list[tk.Label] = []
        prog_frame = tk.Frame(left, bg=BG_LIGHT)
        prog_frame.pack(fill=tk.X, padx=8, pady=(0, 6))

        for i, name in enumerate(PIPELINE_STEPS):
            if i > 0:
                tk.Label(prog_frame, text="\u2192", font=FONT_TINY, bg=BG_LIGHT, fg="#9b8fc4").pack(side=tk.LEFT, padx=2)
            lbl = tk.Label(prog_frame, text=name, font=FONT_TINY, bg="#e8e4f0", fg=STEP_PENDING,
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
            left, height=10, font=FONT_MONO, bg=BG_LOG, fg=FG_LOG,
            insertbackground=FG_LOG, relief=tk.SOLID, bd=1, state=tk.DISABLED, wrap=tk.WORD,
        )
        self._log.pack(fill=tk.BOTH, expand=True, padx=8, pady=(2, 8))

        self._log.tag_configure("error", foreground="#ef4444")
        self._log.tag_configure("success", foreground="#22c55e")
        self._log.tag_configure("step", foreground=ACCENT, font=("Consolas", 10, "bold"))
        self._log.tag_configure("info", foreground=FG_LOG)

        # ── Right column: note preview ──
        right = tk.Frame(paned, bg=BG_PREVIEW, bd=1, relief=tk.SOLID)
        paned.add(right, minsize=350)

        # Preview header
        prev_hdr = tk.Frame(right, bg="#1f1a2e")
        prev_hdr.pack(fill=tk.X)
        tk.Label(prev_hdr, text="Note Preview", font=FONT_BODY, bg="#1f1a2e", fg="#c4b5d0").pack(side=tk.LEFT, padx=10, pady=6)

        self._note_status = tk.StringVar(value="No note yet")
        tk.Label(prev_hdr, textvariable=self._note_status, font=FONT_TINY, bg="#1f1a2e", fg="#6b6580").pack(side=tk.LEFT, padx=4)

        # Copy note + Save buttons
        tk.Button(prev_hdr, text="Save to Vault", font=FONT_TINY, bg="#1f1a2e", fg="#9b8fc4",
                  bd=0, padx=6, cursor="hand2", activebackground="#2d2640", activeforeground="#c4b5d0",
                  command=self._save_to_vault).pack(side=tk.RIGHT, padx=(0, 10), pady=6)
        tk.Button(prev_hdr, text="Copy Note", font=FONT_TINY, bg="#1f1a2e", fg="#9b8fc4",
                  bd=0, padx=6, cursor="hand2", activebackground="#2d2640", activeforeground="#c4b5d0",
                  command=self._copy_note).pack(side=tk.RIGHT, padx=4, pady=6)

        # Note preview text
        self._preview = scrolledtext.ScrolledText(
            right, font=("Consolas", 11), bg=BG_PREVIEW, fg="#e2e0f0",
            insertbackground="#e2e0f0", relief=tk.FLAT, state=tk.DISABLED, wrap=tk.WORD,
        )
        self._preview.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # Markdown syntax highlighting tags
        self._preview.tag_configure("heading", foreground="#c084fc", font=("Consolas", 12, "bold"))
        self._preview.tag_configure("link", foreground="#38bdf8")
        self._preview.tag_configure("tag", foreground="#22c55e")
        self._preview.tag_configure("bold", foreground="#f1f0f9", font=("Consolas", 11, "bold"))
        self._preview.tag_configure("code", foreground="#fbbf24", background="#2d2640")
        self._preview.tag_configure("quote", foreground="#a78bfa", font=("Consolas", 11, "italic"))

        # ── Keyboard shortcuts ──
        self.bind("<Control-Return>", lambda e: self._on_generate())
        self.bind("<Control-l>", lambda e: self._clear_log())
        self.bind("<Escape>", lambda e: self._on_cancel())

    # ── Vault check ──────────────────────────────────────────────────

    def _check_vault(self) -> None:
        vault = get_vault_path()
        if vault:
            count = len(list_notes())
            self._vault_var.set(f"\u25cf {vault.name} ({count} notes)")
            self._vault_label.configure(fg="#22c55e")
        else:
            self._vault_var.set("\u25cf No vault — set in Settings")
            self._vault_label.configure(fg="#ef4444")

    # ── Settings ─────────────────────────────────────────────────────

    def _open_settings(self) -> None:
        win = tk.Toplevel(self)
        win.title("Obsidian Settings")
        win.geometry("480x320")
        win.resizable(False, False)
        win.configure(bg=BG_LIGHT)
        win.transient(self)
        win.grab_set()

        saved = obs_cfg.load_settings()
        entries: dict[str, tk.Variable] = {}

        frame = tk.Frame(win, bg=BG_LIGHT, padx=20, pady=16)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(frame, text="Obsidian Settings", font=FONT_HEADER, bg=BG_LIGHT, fg=FG_BODY).pack(anchor=tk.W, pady=(0, 12))

        # Vault path with browse button
        vault_row = tk.Frame(frame, bg=BG_LIGHT)
        vault_row.pack(fill=tk.X, pady=3)
        tk.Label(vault_row, text="Vault Path", font=FONT_SMALL, bg=BG_LIGHT, fg=FG_BODY, width=14, anchor=tk.W).pack(side=tk.LEFT)
        vault_var = tk.StringVar(value=saved.get("vault_path", ""))
        vault_entry = tk.Entry(vault_row, textvariable=vault_var, font=FONT_SMALL, width=28)
        vault_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        entries["vault_path"] = vault_var

        def _browse():
            d = filedialog.askdirectory(title="Select Obsidian Vault Folder")
            if d:
                vault_var.set(d)

        tk.Button(vault_row, text="Browse", font=FONT_TINY, bg="#e8e4f0", fg=FG_BODY,
                  relief=tk.FLAT, padx=6, command=_browse).pack(side=tk.LEFT, padx=(4, 0))

        # Other fields
        fields = [
            ("Note Template", "template", ["standard", "cornell", "zettelkasten", "meeting", "research"]),
        ]

        for label, key, options in fields:
            row = tk.Frame(frame, bg=BG_LIGHT)
            row.pack(fill=tk.X, pady=3)
            tk.Label(row, text=label, font=FONT_SMALL, bg=BG_LIGHT, fg=FG_BODY, width=14, anchor=tk.W).pack(side=tk.LEFT)
            var = tk.StringVar(value=str(saved.get(key, obs_cfg.DEFAULTS[key])))
            tk.OptionMenu(row, var, *options).pack(side=tk.LEFT, fill=tk.X, expand=True)
            entries[key] = var

        # Checkboxes
        checks = [
            ("Auto wiki-links", "auto_link"),
            ("Auto tags", "auto_tags"),
            ("YAML frontmatter", "frontmatter"),
        ]
        check_frame = tk.Frame(frame, bg=BG_LIGHT)
        check_frame.pack(fill=tk.X, pady=(8, 0))
        for label, key in checks:
            var = tk.BooleanVar(value=saved.get(key, obs_cfg.DEFAULTS[key]))
            tk.Checkbutton(check_frame, text=label, variable=var, font=FONT_SMALL,
                           bg=BG_LIGHT, fg=FG_BODY, selectcolor=BG_LIGHT,
                           activebackground=BG_LIGHT).pack(side=tk.LEFT, padx=(0, 12))
            entries[key] = var

        def _save():
            new_settings = {}
            for key, var in entries.items():
                val = var.get()
                new_settings[key] = val
            obs_cfg.save_settings(new_settings)
            obs_cfg.apply_settings(new_settings)
            self._check_vault()
            self._log_msg("Settings saved", "success")
            win.destroy()

        btn_row = tk.Frame(frame, bg=BG_LIGHT)
        btn_row.pack(fill=tk.X, pady=(16, 0))
        tk.Button(btn_row, text="Save", font=FONT_BODY, bg=ACCENT, fg="white",
                  relief=tk.FLAT, padx=16, pady=4, command=_save).pack(side=tk.LEFT)
        tk.Button(btn_row, text="Cancel", font=FONT_SMALL, bg="#e8e4f0", fg=FG_BODY,
                  relief=tk.FLAT, padx=10, pady=4, command=win.destroy).pack(side=tk.RIGHT)

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
        self.title("ObsidianMCP \u2014 Generating...")
        threading.Thread(target=self._run_pipeline, args=(prompt,), daemon=True).start()

    def _on_cancel(self) -> None:
        if self._generating:
            self._cancel_event.set()
            self._log_msg("Cancelling...", "info")

    def _run_pipeline(self, prompt: str) -> None:
        try:
            # Step 1: Generate
            self._set_pipeline_step(0, "active")
            self._set_status("Generating note...")
            self._log_msg("Generating note...", "step")

            template = self._template_var.get()
            existing = ""

            # In modify mode, get current preview content
            if self._mode_var.get() == "modify" and self._current_note:
                existing = self._current_note
                self._log_msg(f"  Modify mode: {len(existing)} chars existing", "info")

            # Get vault context for wiki-link suggestions
            vault_context = ""
            vault = get_vault_path()
            if vault:
                titles = list_note_titles()[:50]  # top 50 for context
                if titles:
                    vault_context = ", ".join(titles)

            try:
                note, was_cached = generate_note(
                    prompt, template=template,
                    existing_content=existing,
                    vault_context=vault_context,
                )
            except Exception as e:
                self._log_error(str(e))
                self._set_pipeline_step(0, "fail")
                self._set_status("Generation failed")
                return

            if was_cached:
                self._log_msg("Using cached note (saved API call)", "success")
            lines = len(note.splitlines())
            self._log_msg(f"Generated {lines} lines", "info")
            self._set_pipeline_step(0, "done")

            if self._cancel_event.is_set():
                self._log_msg("Cancelled.", "info")
                return

            # Step 2: Process (extract metadata)
            self._set_pipeline_step(1, "active")
            self._set_status("Processing note...")
            self._log_msg("Processing...", "step")

            title = extract_title_from_markdown(note)
            self._log_msg(f"  Title: {title}", "info")

            # Count wiki-links and tags
            import re
            links = re.findall(r'\[\[(.+?)\]\]', note)
            tags = re.findall(r'#([\w-]+)', note)
            if links:
                self._log_msg(f"  Wiki-links: {len(links)} ({', '.join(links[:5])})", "info")
            if tags:
                self._log_msg(f"  Tags: {len(tags)} ({', '.join(tags[:5])})", "info")

            self._set_pipeline_step(1, "done")
            self._current_note = note

            # Step 3: Display (and optionally auto-save)
            self._set_pipeline_step(2, "active")
            self._set_status("Displaying note...")
            self.after(0, lambda: self._display_note(note))
            self._set_pipeline_step(2, "done")

            self._set_status("Done!")
            self.after(0, lambda: self.title(f"ObsidianMCP \u2014 {title}"))
            self._log_msg("Note ready!", "success")

        except Exception as e:
            self._log_error(str(e))
            self._set_status("Error")
        finally:
            self._generating = False
            self.after(0, self._restore_generate_btn)

    def _restore_generate_btn(self) -> None:
        self._gen_btn.configure(text="Generate Note", bg=ACCENT, command=self._on_generate)

    # ── Note display ─────────────────────────────────────────────────

    def _display_note(self, content: str) -> None:
        self._preview.configure(state=tk.NORMAL)
        self._preview.delete("1.0", tk.END)
        self._preview.insert("1.0", content)

        # Basic syntax highlighting
        self._highlight_markdown()

        self._preview.configure(state=tk.DISABLED)
        self._note_status.set(f"{len(content)} chars, {len(content.splitlines())} lines")

    def _highlight_markdown(self) -> None:
        """Apply basic markdown syntax highlighting to the preview."""
        content = self._preview.get("1.0", tk.END)

        for i, line in enumerate(content.splitlines(), 1):
            line_start = f"{i}.0"
            line_end = f"{i}.end"

            if line.startswith("#"):
                self._preview.tag_add("heading", line_start, line_end)
            elif line.startswith(">"):
                self._preview.tag_add("quote", line_start, line_end)

        # Highlight [[wiki-links]]
        import re
        for match in re.finditer(r'\[\[.+?\]\]', content):
            start_idx = f"1.0+{match.start()}c"
            end_idx = f"1.0+{match.end()}c"
            self._preview.tag_add("link", start_idx, end_idx)

        # Highlight #tags
        for match in re.finditer(r'#[\w-]+', content):
            start_idx = f"1.0+{match.start()}c"
            end_idx = f"1.0+{match.end()}c"
            self._preview.tag_add("tag", start_idx, end_idx)

    # ── Vault operations ─────────────────────────────────────────────

    def _save_to_vault(self) -> None:
        if not self._current_note:
            self._log_msg("No note to save. Generate one first.", "error")
            return

        vault = get_vault_path()
        if not vault:
            self._log_msg("No vault configured. Set it in Settings.", "error")
            self._open_settings()
            return

        title = extract_title_from_markdown(self._current_note)
        filename = slugify(title) + ".md"

        # Ask user for filename/location
        path = filedialog.asksaveasfilename(
            initialdir=str(vault),
            initialfile=filename,
            defaultextension=".md",
            filetypes=[("Markdown", "*.md"), ("All Files", "*.*")],
            title="Save Note to Vault",
        )

        if path:
            try:
                # Make path relative to vault if inside it
                full_path = Path(path)
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(self._current_note, encoding="utf-8")
                self._log_msg(f"Saved: {full_path.name}", "success")
                self._check_vault()  # refresh note count
            except Exception as e:
                self._log_msg(f"Save failed: {e}", "error")

    def _copy_note(self) -> None:
        if not self._current_note:
            self._log_msg("No note to copy.", "error")
            return
        self.clipboard_clear()
        self.clipboard_append(self._current_note)
        self._set_status("Note copied to clipboard")

    # ── Progress & Logging ───────────────────────────────────────────

    def _reset_progress(self) -> None:
        for lbl in self._step_labels:
            self.after(0, lambda l=lbl: l.configure(fg=STEP_PENDING, bg="#e8e4f0"))

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
    app = ObsidianMCPApp()
    app.mainloop()


if __name__ == "__main__":
    main()
