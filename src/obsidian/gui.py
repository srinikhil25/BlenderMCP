"""Desktop GUI for Obsidian MCP — AI-powered note generation."""

from __future__ import annotations

import os
import re
import threading
import tkinter as tk
from tkinter import filedialog, scrolledtext, ttk
from pathlib import Path

import src.config as cfg
from src.obsidian import config as obs_cfg
from src.obsidian.llm import generate_note, generate_topic_map, generate_cluster_note
from src.obsidian.vault import (
    get_vault_path, list_notes, list_note_titles, read_note, write_note,
    extract_title_from_markdown, slugify, search_notes,
)
from src.obsidian.graph import GraphCanvas
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
CLUSTER_STEPS = ["Map", "Generate", "Link", "Save"]


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
        self._cluster_notes: list[dict] = []  # [{title, content, type}]
        self._cluster_index = 0  # currently viewed note in cluster

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
        tk.Radiobutton(mode_frame, text="Cluster", variable=self._mode_var, value="cluster",
                        font=FONT_SMALL, bg=BG_LIGHT, fg="#7c3aed", selectcolor=BG_LIGHT,
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

        # ── Right column: tabbed Notebook ──
        right = tk.Frame(paned, bg=BG_PREVIEW, bd=1, relief=tk.SOLID)
        paned.add(right, minsize=350)

        # Style the notebook tabs (dark theme)
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Dark.TNotebook", background=BG_PREVIEW, borderwidth=0)
        style.configure("Dark.TNotebook.Tab",
                        background="#2d2640", foreground="#c4b5d0",
                        padding=[12, 4], font=("Segoe UI", 9))
        style.map("Dark.TNotebook.Tab",
                  background=[("selected", "#7c3aed")],
                  foreground=[("selected", "white")])

        self._notebook = ttk.Notebook(right, style="Dark.TNotebook")
        self._notebook.pack(fill=tk.BOTH, expand=True)

        # ── Tab 1: Note Preview ──
        preview_tab = tk.Frame(self._notebook, bg=BG_PREVIEW)
        self._notebook.add(preview_tab, text="  Preview  ")

        # Preview header
        prev_hdr = tk.Frame(preview_tab, bg="#1f1a2e")
        prev_hdr.pack(fill=tk.X)

        self._note_status = tk.StringVar(value="No note yet")
        tk.Label(prev_hdr, textvariable=self._note_status, font=FONT_TINY, bg="#1f1a2e", fg="#6b6580").pack(side=tk.LEFT, padx=10, pady=6)

        # Copy note + Save buttons
        self._save_btn = tk.Button(prev_hdr, text="Save to Vault", font=FONT_TINY, bg="#1f1a2e", fg="#9b8fc4",
                  bd=0, padx=6, cursor="hand2", activebackground="#2d2640", activeforeground="#c4b5d0",
                  command=self._save_to_vault)
        self._save_btn.pack(side=tk.RIGHT, padx=(0, 10), pady=6)
        tk.Button(prev_hdr, text="Copy Note", font=FONT_TINY, bg="#1f1a2e", fg="#9b8fc4",
                  bd=0, padx=6, cursor="hand2", activebackground="#2d2640", activeforeground="#c4b5d0",
                  command=self._copy_note).pack(side=tk.RIGHT, padx=4, pady=6)

        # Cluster navigation bar (hidden by default)
        self._cluster_nav = tk.Frame(preview_tab, bg="#251f38")
        # NOT packed yet — shown only in cluster mode

        self._cluster_prev_btn = tk.Button(
            self._cluster_nav, text="\u25c0 Prev", font=FONT_TINY, bg="#251f38", fg="#9b8fc4",
            bd=0, padx=8, cursor="hand2", activebackground="#2d2640",
            command=lambda: self._navigate_cluster(-1),
        )
        self._cluster_prev_btn.pack(side=tk.LEFT, padx=6, pady=4)

        self._cluster_title_var = tk.StringVar(value="")
        tk.Label(self._cluster_nav, textvariable=self._cluster_title_var, font=FONT_SMALL,
                 bg="#251f38", fg="#c084fc").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        self._cluster_next_btn = tk.Button(
            self._cluster_nav, text="Next \u25b6", font=FONT_TINY, bg="#251f38", fg="#9b8fc4",
            bd=0, padx=8, cursor="hand2", activebackground="#2d2640",
            command=lambda: self._navigate_cluster(1),
        )
        self._cluster_next_btn.pack(side=tk.RIGHT, padx=(0, 4), pady=4)

        self._cluster_save_all_btn = tk.Button(
            self._cluster_nav, text="Save All to Vault", font=FONT_TINY, bg="#7c3aed", fg="white",
            bd=0, padx=8, pady=2, cursor="hand2", activebackground="#6d28d9",
            command=self._save_cluster_to_vault,
        )
        self._cluster_save_all_btn.pack(side=tk.RIGHT, padx=4, pady=4)

        # Note preview text
        self._preview = scrolledtext.ScrolledText(
            preview_tab, font=("Consolas", 11), bg=BG_PREVIEW, fg="#e2e0f0",
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

        # ── Tab 2: Graph View ──
        graph_tab = tk.Frame(self._notebook, bg=BG_PREVIEW)
        self._notebook.add(graph_tab, text="  Graph  ")

        # Graph toolbar
        graph_toolbar = tk.Frame(graph_tab, bg="#1f1a2e")
        graph_toolbar.pack(fill=tk.X)
        tk.Button(graph_toolbar, text="\u27f3 Refresh", font=FONT_TINY,
                  bg="#1f1a2e", fg="#9b8fc4", bd=0, padx=8, pady=4,
                  cursor="hand2", activebackground="#2d2640",
                  command=self._refresh_graph).pack(side=tk.LEFT, padx=6)
        tk.Button(graph_toolbar, text="\u2302 Fit View", font=FONT_TINY,
                  bg="#1f1a2e", fg="#9b8fc4", bd=0, padx=8, pady=4,
                  cursor="hand2", activebackground="#2d2640",
                  command=self._fit_graph_view).pack(side=tk.LEFT)

        # Graph legend
        legend = tk.Frame(graph_toolbar, bg="#1f1a2e")
        legend.pack(side=tk.RIGHT, padx=8, pady=4)
        for label, color in [("Hub", "#c084fc"), ("Connected", "#38bdf8"),
                             ("Leaf", "#22c55e"), ("Ghost", "#4b4560")]:
            tk.Label(legend, text="\u25cf", font=("Segoe UI", 8), bg="#1f1a2e", fg=color).pack(side=tk.LEFT, padx=(4, 0))
            tk.Label(legend, text=label, font=("Segoe UI", 7), bg="#1f1a2e", fg="#6b6580").pack(side=tk.LEFT, padx=(0, 4))

        # Graph canvas
        self._graph = GraphCanvas(graph_tab, on_node_click=self._on_graph_node_click)
        self._graph.pack(fill=tk.BOTH, expand=True)

        # ── Tab 3: Vault Explorer ──
        explorer_tab = tk.Frame(self._notebook, bg=BG_PREVIEW)
        self._notebook.add(explorer_tab, text="  Explorer  ")
        self._build_explorer(explorer_tab)

        # Auto-refresh graph when tab is selected
        self._notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # ── Keyboard shortcuts ──
        self.bind("<Control-Return>", lambda e: self._on_generate())
        self.bind("<Control-l>", lambda e: self._clear_log())
        self.bind("<Escape>", lambda e: self._on_cancel())
        self.bind("<Control-g>", lambda e: self._switch_to_graph())

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

    # ── Vault Explorer ────────────────────────────────────────────────

    def _build_explorer(self, parent: tk.Frame) -> None:
        """Build the vault explorer tab content."""
        # Search bar
        search_frame = tk.Frame(parent, bg="#1f1a2e")
        search_frame.pack(fill=tk.X)
        tk.Label(search_frame, text="\U0001f50d", font=FONT_SMALL, bg="#1f1a2e", fg="#6b6580").pack(side=tk.LEFT, padx=(8, 4), pady=4)
        self._explorer_search_var = tk.StringVar()
        self._explorer_search = tk.Entry(
            search_frame, textvariable=self._explorer_search_var,
            font=FONT_SMALL, bg="#2d2640", fg="#e2e0f0",
            insertbackground="#e2e0f0", relief=tk.FLAT, bd=0,
        )
        self._explorer_search.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4, pady=4, ipady=2)
        self._explorer_search_var.trace_add("write", lambda *_: self._filter_explorer())

        tk.Button(search_frame, text="\u27f3", font=FONT_TINY,
                  bg="#1f1a2e", fg="#9b8fc4", bd=0, padx=6,
                  cursor="hand2", activebackground="#2d2640",
                  command=self._refresh_explorer).pack(side=tk.RIGHT, padx=4, pady=4)

        # Note list with Treeview
        tree_frame = tk.Frame(parent, bg=BG_PREVIEW)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        style = ttk.Style()
        style.configure("Explorer.Treeview",
                        background="#1a1726", foreground="#e2e0f0",
                        fieldbackground="#1a1726", borderwidth=0,
                        font=("Segoe UI", 9), rowheight=24)
        style.configure("Explorer.Treeview.Heading",
                        background="#2d2640", foreground="#c4b5d0",
                        font=("Segoe UI", 8, "bold"))
        style.map("Explorer.Treeview",
                  background=[("selected", "#7c3aed")],
                  foreground=[("selected", "white")])

        columns = ("links", "tags")
        self._explorer_tree = ttk.Treeview(
            tree_frame, style="Explorer.Treeview",
            columns=columns, show="tree headings", selectmode="browse",
        )
        self._explorer_tree.heading("#0", text="Note", anchor=tk.W)
        self._explorer_tree.heading("links", text="Links", anchor=tk.CENTER)
        self._explorer_tree.heading("tags", text="Tags", anchor=tk.W)
        self._explorer_tree.column("#0", minwidth=150, width=250)
        self._explorer_tree.column("links", minwidth=40, width=50, anchor=tk.CENTER)
        self._explorer_tree.column("tags", minwidth=100, width=150)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._explorer_tree.yview)
        self._explorer_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._explorer_tree.pack(fill=tk.BOTH, expand=True)

        self._explorer_tree.bind("<<TreeviewSelect>>", self._on_explorer_select)
        self._explorer_tree.bind("<Double-1>", self._on_explorer_double_click)

        # Note info bar at bottom
        self._explorer_info_var = tk.StringVar(value="Select a note to preview")
        tk.Label(parent, textvariable=self._explorer_info_var, font=FONT_TINY,
                 bg="#1a1726", fg="#6b6580", anchor=tk.W, padx=8, pady=3).pack(fill=tk.X)

        # Store all notes data for filtering
        self._explorer_notes_data: list[dict] = []

    def _refresh_explorer(self) -> None:
        """Reload the vault explorer note list."""
        vault = get_vault_path()
        if not vault:
            self._explorer_info_var.set("No vault configured — set in Settings")
            return

        self._explorer_tree.delete(*self._explorer_tree.get_children())
        self._explorer_notes_data.clear()

        # Build folder structure
        folders: dict[str, str] = {}  # folder_path -> treeview_id

        for note_path in list_notes():
            full = vault / note_path
            parts = Path(note_path).parts
            title = Path(note_path).stem

            # Read note metadata
            content = ""
            try:
                content = full.read_text(encoding="utf-8")
            except Exception:
                pass

            links = re.findall(r'\[\[(.+?)\]\]', content)
            tags = re.findall(r'#([\w-]+)', content)

            # Create folder nodes
            parent_id = ""
            if len(parts) > 1:
                folder_path = str(Path(*parts[:-1]))
                if folder_path not in folders:
                    # Create nested folders
                    accumulated = ""
                    for folder_part in parts[:-1]:
                        accumulated = f"{accumulated}/{folder_part}" if accumulated else folder_part
                        if accumulated not in folders:
                            parent_folder = folders.get(str(Path(*accumulated.split("/")[:-1])), "") if "/" in accumulated else ""
                            folders[accumulated] = self._explorer_tree.insert(
                                parent_folder, tk.END,
                                text=f"\U0001f4c1 {folder_part}",
                                values=("", ""),
                                open=True,
                            )
                parent_id = folders.get(folder_path, "")

            # Insert note
            item_id = self._explorer_tree.insert(
                parent_id, tk.END,
                text=f"\U0001f4c4 {title}",
                values=(str(len(links)), ", ".join(tags[:3])),
            )

            self._explorer_notes_data.append({
                "path": note_path,
                "title": title,
                "item_id": item_id,
                "link_count": len(links),
                "tags": tags,
            })

        total = len(self._explorer_notes_data)
        self._explorer_info_var.set(f"{total} notes in vault")

    def _filter_explorer(self) -> None:
        """Filter the explorer tree based on search text."""
        query = self._explorer_search_var.get().strip().lower()
        if not query:
            # Show all
            for data in self._explorer_notes_data:
                # Treeview doesn't have show/hide per item easily,
                # so we just re-tag. For simplicity, refresh the list.
                pass
            self._refresh_explorer()
            return

        # Simple approach: rebuild tree with only matching notes
        vault = get_vault_path()
        if not vault:
            return

        self._explorer_tree.delete(*self._explorer_tree.get_children())
        count = 0
        for data in self._explorer_notes_data:
            title_match = query in data["title"].lower()
            tag_match = any(query in t.lower() for t in data["tags"])
            if title_match or tag_match:
                self._explorer_tree.insert(
                    "", tk.END,
                    text=f"\U0001f4c4 {data['title']}",
                    values=(str(data["link_count"]), ", ".join(data["tags"][:3])),
                    tags=(data["path"],),
                )
                count += 1

        self._explorer_info_var.set(f"{count} notes matching '{query}'")

    def _on_explorer_select(self, event: tk.Event) -> None:
        """Load the selected note into the preview."""
        sel = self._explorer_tree.selection()
        if not sel:
            return
        item = sel[0]
        text = self._explorer_tree.item(item, "text")
        if text.startswith("\U0001f4c1"):  # folder, skip
            return

        # Find the note path
        title = text.replace("\U0001f4c4 ", "")
        for data in self._explorer_notes_data:
            if data["title"] == title:
                content = read_note(data["path"])
                if content:
                    self._current_note = content
                    self._notebook.select(0)  # Switch to Preview tab
                    self._display_note(content)
                    self._explorer_info_var.set(f"Viewing: {data['path']}")
                break

    def _on_explorer_double_click(self, event: tk.Event) -> None:
        """Load note into prompt for modification."""
        sel = self._explorer_tree.selection()
        if not sel:
            return
        item = sel[0]
        text = self._explorer_tree.item(item, "text")
        if text.startswith("\U0001f4c1"):
            return

        title = text.replace("\U0001f4c4 ", "")
        for data in self._explorer_notes_data:
            if data["title"] == title:
                content = read_note(data["path"])
                if content:
                    self._current_note = content
                    self._mode_var.set("modify")
                    self._notebook.select(0)
                    self._display_note(content)
                    self._prompt.delete("1.0", tk.END)
                    self._prompt.insert("1.0", f"Enhance the note about {title}")
                    self._log_msg(f"Loaded '{title}' for modification", "info")
                    self._explorer_info_var.set(f"Editing: {data['path']} (double-click loaded)")
                break

    # ── Graph View ────────────────────────────────────────────────────

    def _refresh_graph(self) -> None:
        """Reload the knowledge graph from vault."""
        vault = get_vault_path()
        if not vault:
            self._log_msg("No vault configured for graph view.", "error")
            return

        self._graph.load_vault(vault)
        self._log_msg("Graph refreshed from vault", "info")

    def _fit_graph_view(self) -> None:
        """Reset graph zoom and pan to fit all nodes."""
        self._graph._scale = 1.0
        self._graph._offset_x = 0.0
        self._graph._offset_y = 0.0
        self._graph._render()

    def _on_graph_node_click(self, title: str, path: str) -> None:
        """Handle clicking a node in the graph — load note into preview."""
        if path:  # real note (not ghost)
            content = read_note(path)
            if content:
                self._current_note = content
                self._notebook.select(0)  # Switch to Preview tab
                self._display_note(content)
                self._log_msg(f"Graph: loaded '{title}'", "info")
        else:
            # Ghost node — offer to create it
            self._prompt.delete("1.0", tk.END)
            self._prompt.insert("1.0", f"Create a note about: {title}")
            self._mode_var.set("new")
            self._notebook.select(0)
            self._log_msg(f"Graph: '{title}' is a ghost node (not yet created). Prompt pre-filled.", "info")

    def _switch_to_graph(self) -> None:
        """Switch to graph tab (Ctrl+G shortcut)."""
        self._notebook.select(1)

    def _on_tab_changed(self, event: tk.Event) -> None:
        """Handle notebook tab switches."""
        tab_idx = self._notebook.index(self._notebook.select())
        if tab_idx == 1:  # Graph tab
            # Auto-load graph if vault is set and graph is empty
            vault = get_vault_path()
            if vault and not self._graph._nodes:
                self._refresh_graph()
        elif tab_idx == 2:  # Explorer tab
            vault = get_vault_path()
            if vault and not self._explorer_notes_data:
                self._refresh_explorer()

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

        if self._mode_var.get() == "cluster":
            self.title("ObsidianMCP \u2014 Building Cluster...")
            self._show_cluster_steps()
            threading.Thread(target=self._run_cluster_pipeline, args=(prompt,), daemon=True).start()
        else:
            self.title("ObsidianMCP \u2014 Generating...")
            self._show_single_steps()
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

    # ── Pipeline step labels ─────────────────────────────────────────

    def _show_single_steps(self) -> None:
        """Switch progress bar to single-note pipeline steps."""
        self._rebuild_step_labels(PIPELINE_STEPS)
        self.after(0, lambda: self._cluster_nav.pack_forget())

    def _show_cluster_steps(self) -> None:
        """Switch progress bar to cluster pipeline steps."""
        self._rebuild_step_labels(CLUSTER_STEPS)

    def _rebuild_step_labels(self, steps: list[str]) -> None:
        """Rebuild the step label widgets for a different pipeline."""
        parent = self._step_labels[0].master if self._step_labels else None
        if not parent:
            return
        for child in parent.winfo_children():
            child.destroy()
        self._step_labels.clear()
        for i, name in enumerate(steps):
            if i > 0:
                tk.Label(parent, text="\u2192", font=FONT_TINY, bg=BG_LIGHT, fg="#9b8fc4").pack(side=tk.LEFT, padx=2)
            lbl = tk.Label(parent, text=name, font=FONT_TINY, bg="#e8e4f0", fg=STEP_PENDING,
                           padx=6, pady=1, relief=tk.FLAT)
            lbl.pack(side=tk.LEFT, padx=1)
            self._step_labels.append(lbl)

    # ── Cluster pipeline ─────────────────────────────────────────────

    def _run_cluster_pipeline(self, topic: str) -> None:
        """Generate a full topic cluster: map → notes → display."""
        try:
            # Step 1: Generate topic map
            self._set_pipeline_step(0, "active")
            self._set_status("Mapping subtopics...")
            self._log_msg("Building topic map...", "step")

            try:
                topic_map = generate_topic_map(topic)
            except Exception as e:
                self._log_error(str(e))
                self._set_pipeline_step(0, "fail")
                self._set_status("Mapping failed")
                return

            titles = [t["title"] for t in topic_map]
            hub = topic_map[0]
            self._log_msg(f"Topic map: {len(topic_map)} notes planned", "success")
            for t in topic_map:
                icon = {"hub": "\u2b50", "concept": "\u25cb", "example": "\u25a1", "reference": "\U0001f4d6"}.get(t["type"], "\u25cb")
                self._log_msg(f"  {icon} {t['title']} — {t['description']}", "info")
            self._set_pipeline_step(0, "done")

            if self._cancel_event.is_set():
                self._log_msg("Cancelled.", "info")
                return

            # Step 2: Generate each note
            self._set_pipeline_step(1, "active")
            self._set_status("Generating notes...")
            self._log_msg("Generating cluster notes...", "step")

            template = self._template_var.get()
            vault_context = ""
            vault = get_vault_path()
            if vault:
                existing = list_note_titles()[:50]
                if existing:
                    vault_context = ", ".join(existing)

            cluster_notes: list[dict] = []
            for i, t in enumerate(topic_map):
                if self._cancel_event.is_set():
                    self._log_msg("Cancelled.", "info")
                    return

                self._set_status(f"Generating {i + 1}/{len(topic_map)}: {t['title']}...")
                self._log_msg(f"  [{i + 1}/{len(topic_map)}] {t['title']}...", "info")

                try:
                    content = generate_cluster_note(
                        note_title=t["title"],
                        note_description=t["description"],
                        note_type=t["type"],
                        hub_title=hub["title"],
                        all_titles=titles,
                        template=template,
                        vault_context=vault_context,
                    )
                    cluster_notes.append({
                        "title": t["title"],
                        "content": content,
                        "type": t["type"],
                        "description": t["description"],
                    })
                    lines = len(content.splitlines())
                    self._log_msg(f"    \u2713 {lines} lines", "success")
                except Exception as e:
                    self._log_msg(f"    \u2717 Failed: {e}", "error")
                    # Continue with other notes even if one fails
                    continue

            if not cluster_notes:
                self._log_msg("No notes generated. All failed.", "error")
                self._set_pipeline_step(1, "fail")
                return

            self._log_msg(f"Generated {len(cluster_notes)}/{len(topic_map)} notes", "success")
            self._set_pipeline_step(1, "done")

            # Step 3: Link analysis
            self._set_pipeline_step(2, "active")
            self._set_status("Analyzing links...")
            self._log_msg("Analyzing cross-links...", "step")

            total_links = 0
            internal_links = 0
            for note in cluster_notes:
                links = re.findall(r'\[\[(.+?)\]\]', note["content"])
                total_links += len(links)
                for link in links:
                    if link in titles:
                        internal_links += 1

            self._log_msg(f"  Total wiki-links: {total_links}", "info")
            self._log_msg(f"  Internal cluster links: {internal_links}", "info")
            self._log_msg(f"  External links: {total_links - internal_links}", "info")
            self._set_pipeline_step(2, "done")

            # Step 4: Display
            self._set_pipeline_step(3, "active")
            self._set_status("Displaying cluster...")

            self._cluster_notes = cluster_notes
            self._cluster_index = 0
            self._current_note = cluster_notes[0]["content"]

            # Show cluster nav and display first note
            self.after(0, self._show_cluster_nav)
            self.after(0, lambda: self._display_note(cluster_notes[0]["content"]))

            self._set_pipeline_step(3, "done")
            self._set_status(f"Cluster ready! {len(cluster_notes)} notes")
            self.after(0, lambda: self.title(f"ObsidianMCP \u2014 Cluster: {hub['title']}"))
            self._log_msg(f"Cluster ready! Navigate with \u25c0 \u25b6 buttons.", "success")

            # Auto-load cluster into graph view
            self.after(100, lambda: self._graph.load_cluster(cluster_notes))
            self._log_msg("Graph view updated with cluster topology.", "info")

        except Exception as e:
            self._log_error(str(e))
            self._set_status("Error")
        finally:
            self._generating = False
            self.after(0, self._restore_generate_btn)

    # ── Cluster navigation ───────────────────────────────────────────

    def _show_cluster_nav(self) -> None:
        """Show the cluster navigation bar."""
        self._cluster_nav.pack(fill=tk.X, before=self._preview)
        self._update_cluster_nav()
        # Update save button for cluster
        self._save_btn.configure(text="Save This Note", command=self._save_to_vault)

    def _hide_cluster_nav(self) -> None:
        """Hide the cluster navigation bar."""
        self._cluster_nav.pack_forget()
        self._save_btn.configure(text="Save to Vault", command=self._save_to_vault)

    def _update_cluster_nav(self) -> None:
        """Update the cluster nav label and button states."""
        if not self._cluster_notes:
            return
        idx = self._cluster_index
        total = len(self._cluster_notes)
        note = self._cluster_notes[idx]
        icon = {"hub": "\u2b50", "concept": "\u25cb", "example": "\u25a1", "reference": "\U0001f4d6"}.get(note["type"], "\u25cb")
        self._cluster_title_var.set(f"{icon} [{idx + 1}/{total}] {note['title']}")
        self._cluster_prev_btn.configure(state=tk.NORMAL if idx > 0 else tk.DISABLED)
        self._cluster_next_btn.configure(state=tk.NORMAL if idx < total - 1 else tk.DISABLED)

    def _navigate_cluster(self, direction: int) -> None:
        """Navigate to the previous/next note in the cluster."""
        if not self._cluster_notes:
            return
        new_idx = self._cluster_index + direction
        if 0 <= new_idx < len(self._cluster_notes):
            self._cluster_index = new_idx
            note = self._cluster_notes[new_idx]
            self._current_note = note["content"]
            self._display_note(note["content"])
            self._update_cluster_nav()

    def _save_cluster_to_vault(self) -> None:
        """Save ALL cluster notes to the vault at once."""
        if not self._cluster_notes:
            self._log_msg("No cluster notes to save.", "error")
            return

        vault = get_vault_path()
        if not vault:
            self._log_msg("No vault configured. Set it in Settings.", "error")
            self._open_settings()
            return

        # Ask for a subfolder name
        hub_title = self._cluster_notes[0]["title"]
        folder = slugify(hub_title)

        # Use a dialog to confirm
        confirm = tk.Toplevel(self)
        confirm.title("Save Cluster to Vault")
        confirm.geometry("420x280")
        confirm.resizable(False, False)
        confirm.configure(bg=BG_LIGHT)
        confirm.transient(self)
        confirm.grab_set()

        tk.Label(confirm, text="Save Topic Cluster", font=FONT_HEADER, bg=BG_LIGHT, fg=FG_BODY).pack(padx=16, pady=(16, 8))
        tk.Label(confirm, text=f"{len(self._cluster_notes)} notes will be saved to your vault.",
                 font=FONT_BODY, bg=BG_LIGHT, fg=FG_BODY).pack(padx=16)

        # Folder input
        folder_frame = tk.Frame(confirm, bg=BG_LIGHT)
        folder_frame.pack(fill=tk.X, padx=16, pady=(12, 4))
        tk.Label(folder_frame, text="Subfolder:", font=FONT_SMALL, bg=BG_LIGHT, fg=FG_BODY).pack(side=tk.LEFT)
        folder_var = tk.StringVar(value=folder)
        tk.Entry(folder_frame, textvariable=folder_var, font=FONT_SMALL, width=30).pack(side=tk.LEFT, padx=(8, 0), fill=tk.X, expand=True)

        # Note list preview
        list_frame = tk.Frame(confirm, bg=BG_LIGHT)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)
        listbox = tk.Listbox(list_frame, font=FONT_SMALL, height=6, bg="#f0edf5", fg=FG_BODY, selectmode=tk.NONE)
        listbox.pack(fill=tk.BOTH, expand=True)
        for note in self._cluster_notes:
            icon = {"hub": "\u2b50", "concept": "\u25cb", "example": "\u25a1", "reference": "\U0001f4d6"}.get(note["type"], "\u25cb")
            listbox.insert(tk.END, f"  {icon} {note['title']}.md")

        def _do_save():
            subfolder = folder_var.get().strip()
            saved_count = 0
            for note in self._cluster_notes:
                filename = slugify(note["title"]) + ".md"
                rel_path = f"{subfolder}/{filename}" if subfolder else filename
                try:
                    write_note(rel_path, note["content"], overwrite=False)
                    saved_count += 1
                except Exception as e:
                    self._log_msg(f"Failed to save {note['title']}: {e}", "error")
            self._log_msg(f"Saved {saved_count}/{len(self._cluster_notes)} notes to {subfolder}/", "success")
            self._check_vault()
            confirm.destroy()

        btn_row = tk.Frame(confirm, bg=BG_LIGHT)
        btn_row.pack(fill=tk.X, padx=16, pady=(0, 12))
        tk.Button(btn_row, text="Save All", font=FONT_BODY, bg=ACCENT, fg="white",
                  relief=tk.FLAT, padx=16, pady=4, command=_do_save).pack(side=tk.LEFT)
        tk.Button(btn_row, text="Cancel", font=FONT_SMALL, bg="#e8e4f0", fg=FG_BODY,
                  relief=tk.FLAT, padx=10, pady=4, command=confirm.destroy).pack(side=tk.RIGHT)

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
                self._explorer_notes_data.clear()  # force explorer refresh on next visit
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
