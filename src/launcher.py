"""Launcher homepage — choose between Blender, Obsidian, Krita, or Pencil tools."""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

# ── Colours (shared with tool GUIs) ──────────────────────────────────
BG_DARK = "#0f172a"
BG_CARD = "#1e293b"
BG_CARD_HOVER = "#334155"
FG_TITLE = "#f1f5f9"
FG_BODY = "#94a3b8"
FG_ACCENT = "#38bdf8"
ACCENT_BLENDER = "#ea7600"
ACCENT_OBSIDIAN = "#7c3aed"
ACCENT_KRITA = "#2dd4bf"
ACCENT_PENCIL = "#6366f1"


# ── Tool definitions ─────────────────────────────────────────────────
TOOLS = [
    {
        "id": "blender",
        "name": "Blender",
        "icon": "\U0001f3a8",  # artist palette
        "accent": ACCENT_BLENDER,
        "tagline": "Text to 3D",
        "description": (
            "Generate photorealistic 3D scenes from text prompts.\n"
            "Cycles ray-tracing, PBR materials, chemistry molecules."
        ),
        "status": "Ready",
        "launch": "_launch_blender",
    },
    {
        "id": "obsidian",
        "name": "Obsidian",
        "icon": "\U0001f4dd",  # memo
        "accent": ACCENT_OBSIDIAN,
        "tagline": "Text to Knowledge",
        "description": (
            "Generate and organize notes, link ideas,\n"
            "build knowledge graphs from text prompts."
        ),
        "status": "Ready",
        "launch": "_launch_obsidian",
    },
    {
        "id": "krita",
        "name": "Krita",
        "icon": "\U0001f58c\ufe0f",  # paintbrush
        "accent": ACCENT_KRITA,
        "tagline": "Text to 2D Art",
        "description": (
            "Generate digital paintings, illustrations,\n"
            "and concept art with AI image generation."
        ),
        "status": "Ready",
        "launch": "_launch_krita",
    },
    {
        "id": "pencil",
        "name": "Pencil",
        "icon": "\u270f\ufe0f",  # pencil
        "accent": ACCENT_PENCIL,
        "tagline": "Text to UI Design",
        "description": (
            "Generate responsive UI designs, landing pages,\n"
            "dashboards, and components as production code."
        ),
        "status": "Ready",
        "launch": "_launch_pencil",
    },
]


class LauncherApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Creative MCP Suite")
        self.geometry("1120x520")
        self.minsize(1000, 450)
        self.configure(bg=BG_DARK)
        self._build_ui()

    def _build_ui(self) -> None:
        # ── Header ──
        header = tk.Frame(self, bg=BG_DARK)
        header.pack(fill=tk.X, padx=40, pady=(32, 0))

        tk.Label(
            header, text="Creative MCP Suite",
            font=("Segoe UI", 22, "bold"), bg=BG_DARK, fg=FG_TITLE,
        ).pack(side=tk.LEFT)

        tk.Label(
            header, text="AI-powered creative tools via MCP",
            font=("Segoe UI", 11), bg=BG_DARK, fg=FG_BODY,
        ).pack(side=tk.LEFT, padx=(16, 0), pady=(6, 0))

        # ── Subtitle ──
        tk.Label(
            self, text="Choose a tool to get started:",
            font=("Segoe UI", 12), bg=BG_DARK, fg=FG_BODY,
        ).pack(anchor=tk.W, padx=40, pady=(12, 16))

        # ── Cards container ──
        cards_frame = tk.Frame(self, bg=BG_DARK)
        cards_frame.pack(fill=tk.BOTH, expand=True, padx=32, pady=(0, 32))

        # Make columns expand equally
        for i in range(len(TOOLS)):
            cards_frame.columnconfigure(i, weight=1, uniform="card")
        cards_frame.rowconfigure(0, weight=1)

        for i, tool in enumerate(TOOLS):
            self._build_card(cards_frame, tool, i)

        # ── Footer ──
        footer = tk.Frame(self, bg=BG_DARK)
        footer.pack(fill=tk.X, padx=40, pady=(0, 16))

        tk.Label(
            footer, text="Powered by Gemini AI + MCP Protocol",
            font=("Segoe UI", 9), bg=BG_DARK, fg="#475569",
        ).pack(side=tk.LEFT)

        tk.Label(
            footer, text="v1.0",
            font=("Segoe UI", 9), bg=BG_DARK, fg="#475569",
        ).pack(side=tk.RIGHT)

    def _build_card(self, parent: tk.Frame, tool: dict, col: int) -> None:
        accent = tool["accent"]
        is_ready = tool["status"] == "Ready"

        # Card frame
        card = tk.Frame(
            parent, bg=BG_CARD, bd=0,
            highlightbackground=accent, highlightthickness=2,
            padx=20, pady=20,
        )
        card.grid(row=0, column=col, sticky="nsew", padx=8, pady=4)

        # Icon + Name row
        icon_row = tk.Frame(card, bg=BG_CARD)
        icon_row.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            icon_row, text=tool["icon"], font=("Segoe UI", 28),
            bg=BG_CARD, fg=accent,
        ).pack(side=tk.LEFT)

        name_col = tk.Frame(icon_row, bg=BG_CARD)
        name_col.pack(side=tk.LEFT, padx=(12, 0))

        tk.Label(
            name_col, text=tool["name"], font=("Segoe UI", 16, "bold"),
            bg=BG_CARD, fg=FG_TITLE, anchor=tk.W,
        ).pack(anchor=tk.W)

        tk.Label(
            name_col, text=tool["tagline"], font=("Segoe UI", 10),
            bg=BG_CARD, fg=accent, anchor=tk.W,
        ).pack(anchor=tk.W)

        # Description
        tk.Label(
            card, text=tool["description"],
            font=("Segoe UI", 10), bg=BG_CARD, fg=FG_BODY,
            justify=tk.LEFT, anchor=tk.NW, wraplength=200,
        ).pack(fill=tk.X, pady=(4, 12))

        # Spacer to push button to bottom
        tk.Frame(card, bg=BG_CARD).pack(fill=tk.BOTH, expand=True)

        # Status badge
        status_color = "#22c55e" if is_ready else "#f59e0b"
        status_frame = tk.Frame(card, bg=BG_CARD)
        status_frame.pack(fill=tk.X, pady=(0, 10))
        tk.Label(
            status_frame, text=f"\u25cf {tool['status']}",
            font=("Segoe UI", 9), bg=BG_CARD, fg=status_color,
        ).pack(side=tk.LEFT)

        # Launch button
        btn_bg = accent if is_ready else "#475569"
        btn_fg = "white"
        btn_text = f"Launch {tool['name']}" if is_ready else "Coming Soon"
        btn_state = tk.NORMAL if is_ready else tk.DISABLED

        btn = tk.Button(
            card, text=btn_text, font=("Segoe UI", 11, "bold"),
            bg=btn_bg, fg=btn_fg, activebackground=btn_bg,
            activeforeground=btn_fg, relief=tk.FLAT,
            padx=16, pady=8, cursor="hand2" if is_ready else "arrow",
            state=btn_state,
            command=getattr(self, tool["launch"], lambda: None),
        )
        btn.pack(fill=tk.X)

        # Hover effects (only for ready tools)
        if is_ready:
            def _on_enter(e, c=card, a=accent):
                c.configure(bg=BG_CARD_HOVER, highlightthickness=3)
                for w in c.winfo_children():
                    try:
                        w.configure(bg=BG_CARD_HOVER)
                        for ww in w.winfo_children():
                            try:
                                ww.configure(bg=BG_CARD_HOVER)
                            except Exception:
                                pass
                    except Exception:
                        pass

            def _on_leave(e, c=card, a=accent):
                c.configure(bg=BG_CARD, highlightthickness=2)
                for w in c.winfo_children():
                    try:
                        w.configure(bg=BG_CARD)
                        for ww in w.winfo_children():
                            try:
                                ww.configure(bg=BG_CARD)
                            except Exception:
                                pass
                    except Exception:
                        pass

            card.bind("<Enter>", _on_enter)
            card.bind("<Leave>", _on_leave)

    # ── Launch handlers ──────────────────────────────────────────────

    def _launch_blender(self) -> None:
        """Launch the Blender MCP tool."""
        self.withdraw()  # hide launcher
        from src.gui import BlenderMCPApp
        app = BlenderMCPApp()
        app.protocol("WM_DELETE_WINDOW", lambda: self._on_tool_close(app))
        app.mainloop()

    def _launch_obsidian(self) -> None:
        """Launch the Obsidian MCP tool."""
        self.withdraw()
        from src.obsidian.gui import ObsidianMCPApp
        app = ObsidianMCPApp()
        app.protocol("WM_DELETE_WINDOW", lambda: self._on_tool_close(app))
        app.mainloop()

    def _launch_krita(self) -> None:
        """Launch the Krita MCP tool."""
        self.withdraw()
        from src.krita.gui import KritaMCPApp
        app = KritaMCPApp()
        app.protocol("WM_DELETE_WINDOW", lambda: self._on_tool_close(app))
        app.mainloop()

    def _launch_pencil(self) -> None:
        """Launch the Pencil MCP tool."""
        self.withdraw()
        from src.pencil.gui import PencilMCPApp
        app = PencilMCPApp()
        app.protocol("WM_DELETE_WINDOW", lambda: self._on_tool_close(app))
        app.mainloop()

    def _on_tool_close(self, tool_window: tk.Tk) -> None:
        """When a tool window closes, show the launcher again."""
        tool_window.destroy()
        self.deiconify()  # show launcher


def main() -> None:
    app = LauncherApp()
    app.mainloop()


if __name__ == "__main__":
    main()
