"""
Desktop UI with tool-first flow.

Run from the project root (with venv active):

    python -m src.ui.desktop

Place PNG icons in assets/icons/ named: blender.png, obsidian.png, krita.png.
If missing, text fallbacks are used.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from src.core.models import ProjectScope, ToolType
from src.core.runner import run_request

# Icons directory: project_root/assets/icons (blender.png, obsidian.png, krita.png)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ICONS_DIR = _PROJECT_ROOT / "assets" / "icons"
ICON_SIZE = (80, 80)  # displayed size for tool cards

# Text fallbacks when PNG is missing
TOOL_ICONS = {
    ToolType.BLENDER: "[ 3D ]",
    ToolType.OBSIDIAN: "[ MD ]",
    ToolType.KRITA: "[ 2D ]",
}
TOOL_DESCRIPTIONS = {
    ToolType.BLENDER: "Procedural 3D structures",
    ToolType.OBSIDIAN: "Knowledge graphs & markdown",
    ToolType.KRITA: "Layered 2D compositions",
}

# Workspace theme
WS = {
    "bg": "#f1f5f9",
    "header_bg": "#1e293b",
    "header_fg": "#f8fafc",
    "accent": "#0d9488",
    "accent_hover": "#0f766e",
    "card_bg": "#ffffff",
    "card_border": "#e2e8f0",
    "card_radius_px": 8,
    "label_fg": "#334155",
    "label_font": ("Segoe UI", 10),
    "title_font": ("Segoe UI", 11, "bold"),
    "output_bg": "#f8fafc",
    "output_font": ("Consolas", 9),
}


class AgentDesktopApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Local Creative Agent")
        self.geometry("820x640")
        self.current_tool: ToolType | None = None

        self._picker_frame: ttk.Frame | None = None
        self._workspace_frame: ttk.Frame | None = None

        self._tool_photos: list[tk.PhotoImage] = []
        self._build_picker()
        self._build_workspace()
        self._show_picker()

    def _load_tool_icon(self, tool: ToolType) -> tk.PhotoImage | None:
        try:
            from PIL import Image, ImageTk
        except ImportError:
            return None
        path = ICONS_DIR / f"{tool.value}.png"
        if not path.is_file():
            return None
        try:
            img = Image.open(path).convert("RGBA")
            img.thumbnail(ICON_SIZE, getattr(Image, "Resampling", Image).LANCZOS)
            photo = ImageTk.PhotoImage(img)
            self._tool_photos.append(photo)
            return photo
        except Exception:
            return None

    def _build_picker(self) -> None:
        self._picker_frame = ttk.Frame(self, padding=20)
        title = ttk.Label(
            self._picker_frame,
            text="Choose a tool to work with",
            font=("Segoe UI", 14, "bold"),
        )
        title.pack(pady=(0, 24))

        cards = ttk.Frame(self._picker_frame)
        cards.pack(expand=True)

        for i, tool in enumerate(ToolType):
            card = self._make_tool_card(cards, tool)
            card.grid(row=0, column=i, padx=20, pady=10, sticky="nsew")
            cards.columnconfigure(i, weight=1)

    def _make_tool_card(self, parent: ttk.Frame, tool: ToolType) -> tk.Frame:
        card = tk.Frame(parent, relief=tk.RAISED, borderwidth=2, padx=24, pady=24)
        card.configure(bg="#f0f0f0")
        card.bind("<Button-1>", lambda e, t=tool: self._on_tool_selected(t))
        card.bind("<Enter>", lambda e, c=card: c.configure(bg="#e0e8f0"))
        card.bind("<Leave>", lambda e, c=card: c.configure(bg="#f0f0f0"))

        photo = self._load_tool_icon(tool)
        icon = tk.Label(card, bg=card.cget("bg"))
        if photo:
            icon.configure(image=photo)
        else:
            icon.configure(text=TOOL_ICONS.get(tool, tool.value), font=("Segoe UI", 24), fg="#333")
        icon.pack(pady=(0, 8))
        icon.bind("<Button-1>", lambda e, t=tool: self._on_tool_selected(t))

        name = tk.Label(
            card, text=tool.value.capitalize(),
            font=("Segoe UI", 12, "bold"), bg=card.cget("bg"), fg="#111",
        )
        name.pack(pady=(0, 4))
        name.bind("<Button-1>", lambda e, t=tool: self._on_tool_selected(t))

        desc = TOOL_DESCRIPTIONS.get(tool, "")
        if desc:
            desc_label = tk.Label(
                card, text=desc, font=("Segoe UI", 9),
                bg=card.cget("bg"), fg="#666",
            )
            desc_label.pack(pady=(0, 0))
            desc_label.bind("<Button-1>", lambda e, t=tool: self._on_tool_selected(t))

        return card

    def _on_tool_selected(self, tool: ToolType) -> None:
        self.current_tool = tool
        self._show_workspace()

    def _show_picker(self) -> None:
        if self._workspace_frame:
            self._workspace_frame.pack_forget()
        if self._picker_frame:
            self._picker_frame.pack(fill=tk.BOTH, expand=True)
        self.current_tool = None

    def _show_workspace(self) -> None:
        if self._picker_frame:
            self._picker_frame.pack_forget()
        if self._workspace_frame:
            self._workspace_frame.pack(fill=tk.BOTH, expand=True)
        self._refresh_workspace_header()

    def _build_workspace(self) -> None:
        ws = tk.Frame(self, bg=WS["bg"], padx=0, pady=0)
        self._workspace_frame = ws

        # Header bar
        header = tk.Frame(ws, bg=WS["header_bg"], height=48)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        self._workspace_title_var = tk.StringVar(value="")
        header_title = tk.Label(
            header, textvariable=self._workspace_title_var,
            font=("Segoe UI", 13, "bold"),
            bg=WS["header_bg"], fg=WS["header_fg"],
        )
        header_title.pack(side=tk.LEFT, padx=(20, 0), pady=12)

        change_btn = tk.Label(
            header, text="  <- Change tool  ",
            font=("Segoe UI", 10),
            bg=WS["header_bg"], fg=WS["header_fg"], cursor="hand2", relief=tk.FLAT,
        )
        change_btn.pack(side=tk.RIGHT, padx=16, pady=10)
        change_btn.bind("<Button-1>", lambda e: self._show_picker())
        change_btn.bind("<Enter>", lambda e: change_btn.configure(fg="#94a3b8"))
        change_btn.bind("<Leave>", lambda e: change_btn.configure(fg=WS["header_fg"]))

        # Content
        content = tk.Frame(ws, bg=WS["bg"], padx=20, pady=16)
        content.pack(fill=tk.BOTH, expand=True)

        # Input card
        input_card = tk.Frame(content, bg=WS["card_bg"], highlightbackground=WS["card_border"], highlightthickness=1)
        input_card.pack(fill=tk.X, pady=(0, 12))

        card_inner = tk.Frame(input_card, bg=WS["card_bg"], padx=16, pady=14)
        card_inner.pack(fill=tk.X)

        tk.Label(card_inner, text="Project", font=WS["title_font"], bg=WS["card_bg"], fg=WS["label_fg"]).pack(anchor="w")
        self.root_var = tk.StringVar(value=str(Path.cwd()))
        ttk.Entry(card_inner, textvariable=self.root_var, width=70).pack(fill=tk.X, pady=(4, 12))

        tk.Label(card_inner, text="Sub-scope (optional)", font=WS["title_font"], bg=WS["card_bg"], fg=WS["label_fg"]).pack(anchor="w")
        self.sub_var = tk.StringVar()
        ttk.Entry(card_inner, textvariable=self.sub_var, width=40).pack(fill=tk.X, pady=(4, 12))

        tk.Label(card_inner, text="Prompt", font=WS["title_font"], bg=WS["card_bg"], fg=WS["label_fg"]).pack(anchor="w")
        self.prompt_text = tk.Text(card_inner, height=5, font=("Segoe UI", 10), wrap=tk.WORD, relief=tk.FLAT, padx=8, pady=8)
        self.prompt_text.pack(fill=tk.X, pady=(4, 0))

        # Run button
        run_frame = tk.Frame(content, bg=WS["accent"], height=44)
        run_frame.pack(fill=tk.X, pady=(0, 12))
        run_frame.pack_propagate(False)
        run_btn = tk.Label(
            run_frame, text="Run Plan -> Build -> Inspect",
            font=("Segoe UI", 11, "bold"), bg=WS["accent"], fg="white", cursor="hand2",
        )
        run_btn.place(relx=0.5, rely=0.5, anchor="center")

        def _run_hover_in(e):
            run_btn.configure(bg=WS["accent_hover"])
            run_frame.configure(bg=WS["accent_hover"])

        def _run_hover_out(e):
            run_btn.configure(bg=WS["accent"])
            run_frame.configure(bg=WS["accent"])

        run_btn.bind("<Button-1>", lambda e: self._on_run_clicked())
        run_btn.bind("<Enter>", _run_hover_in)
        run_btn.bind("<Leave>", _run_hover_out)
        run_frame.bind("<Button-1>", lambda e: self._on_run_clicked())
        run_frame.bind("<Enter>", _run_hover_in)
        run_frame.bind("<Leave>", _run_hover_out)

        # Output card
        out_card = tk.Frame(content, bg=WS["card_bg"], highlightbackground=WS["card_border"], highlightthickness=1)
        out_card.pack(fill=tk.BOTH, expand=True)

        out_header = tk.Frame(out_card, bg=WS["card_bg"])
        out_header.pack(fill=tk.X, padx=16, pady=(10, 4))
        tk.Label(out_header, text="Output", font=WS["title_font"], bg=WS["card_bg"], fg=WS["label_fg"]).pack(side=tk.LEFT)

        self.output_text = tk.Text(
            out_card, height=14, font=WS["output_font"], wrap=tk.WORD,
            relief=tk.FLAT, bg=WS["output_bg"], fg="#334155", padx=12, pady=10,
        )
        self.output_text.pack(fill=tk.BOTH, expand=True, padx=1, pady=(0, 1))

    def _refresh_workspace_header(self) -> None:
        if self.current_tool is not None:
            self._workspace_title_var.set(f"Working with: {self.current_tool.value.capitalize()}")

    def _on_run_clicked(self) -> None:
        if self.current_tool is None:
            self._set_output("No tool selected. Use Change tool to pick one.")
            return

        prompt = self.prompt_text.get("1.0", tk.END).strip()
        root_path = self.root_var.get().strip()
        sub_scope = self.sub_var.get().strip() or None

        if not prompt:
            self._set_output("Please enter a prompt.")
            return

        scope = ProjectScope(tool=self.current_tool, root_path=Path(root_path), sub_scope=sub_scope)

        try:
            result = run_request(prompt, scope)
        except NotImplementedError as e:
            self._set_output(str(e))
            return
        except Exception as e:
            self._set_output(f"Unexpected error: {e!r}")
            return

        self._render_result(result)

    def _set_output(self, text: str) -> None:
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert(tk.END, text)

    def _render_result(self, payload: dict) -> None:
        res = payload.get("result", {})
        lines = []
        lines.append(f"Tool: {payload.get('tool')}")
        scope = payload.get("scope", {})
        lines.append(f"Root path: {scope.get('root_path')}")
        lines.append(f"Sub-scope: {scope.get('sub_scope')}")
        lines.append("")

        # Plan info
        lines.append(f"Plan: {res.get('plan_name')} ({res.get('plan_component_count', '?')} components)")
        lines.append(f"Description: {res.get('plan_description', '')}")
        lines.append("")

        # Verification
        verification = res.get("verification", {})
        lines.append(f"Verification: {'OK' if verification.get('ok') else 'ISSUES'}")
        if not verification.get("ok"):
            lines.append(str(verification.get("notes", "")).strip())
        lines.append("")

        # Execution
        exec_res = res.get("execution", {})
        lines.append(f"Execution: {'OK' if exec_res.get('ok') else 'FAILED'}")
        if exec_res.get("stdout"):
            lines.append("\n--- Blender stdout ---")
            lines.append(exec_res["stdout"])
        if exec_res.get("stderr"):
            lines.append("\n--- Blender stderr ---")
            lines.append(exec_res["stderr"])
        lines.append("")

        # Inspection
        inspection = res.get("inspection", {})
        lines.append(f"Inspection: {'OK' if inspection.get('ok') else 'ISSUES'}")
        lines.append(f"  Expected: {inspection.get('expected', '?')}, Found: {inspection.get('actual', '?')}")
        if inspection.get("missing"):
            lines.append(f"  Missing: {', '.join(inspection['missing'])}")
        lines.append(f"  {inspection.get('notes', '')}")

        self._set_output("\n".join(lines))


def main() -> None:
    app = AgentDesktopApp()
    app.mainloop()


if __name__ == "__main__":
    main()
