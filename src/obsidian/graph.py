"""Knowledge graph visualization for Obsidian vault.

Builds a node-edge graph from [[wiki-links]] and renders it on a tkinter Canvas
using a force-directed (spring) layout algorithm.
"""

from __future__ import annotations

import math
import random
import re
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple


# ── Graph data model ─────────────────────────────────────────────────

@dataclass
class GraphNode:
    """A single note in the knowledge graph."""
    title: str
    path: str  # relative path in vault
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    link_count: int = 0
    is_ghost: bool = False  # linked but doesn't exist as a file
    tags: list[str] = field(default_factory=list)
    canvas_id: int = 0  # tkinter canvas item id
    label_id: int = 0


@dataclass
class GraphEdge:
    """A directed link between two notes."""
    source: str  # title
    target: str  # title
    canvas_id: int = 0


def build_graph(vault_path: Path) -> Tuple[Dict[str, GraphNode], List[GraphEdge]]:
    """Scan an Obsidian vault and build a graph of notes and links.

    Returns:
        Tuple of (nodes_dict, edges_list).
    """
    nodes: Dict[str, GraphNode] = {}
    edges: List[GraphEdge] = []
    seen_edges: Set[Tuple[str, str]] = set()

    # First pass: collect all real notes
    for md_file in sorted(vault_path.rglob("*.md")):
        rel = md_file.relative_to(vault_path)
        # Skip hidden folders
        if any(part.startswith(".") for part in rel.parts):
            continue

        title = md_file.stem
        content = ""
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        # Extract tags from frontmatter and content
        tags = re.findall(r'#([\w-]+)', content)

        nodes[title] = GraphNode(
            title=title,
            path=str(rel),
            tags=list(set(tags)),
        )

    # Second pass: extract [[wiki-links]] and build edges
    for md_file in sorted(vault_path.rglob("*.md")):
        rel = md_file.relative_to(vault_path)
        if any(part.startswith(".") for part in rel.parts):
            continue

        title = md_file.stem
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception:
            continue

        # Find all [[links]] — handle [[link|alias]] format too
        links = re.findall(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', content)

        for link_title in links:
            link_title = link_title.strip()
            if not link_title or link_title == title:
                continue

            # Create ghost node if target doesn't exist
            if link_title not in nodes:
                nodes[link_title] = GraphNode(
                    title=link_title,
                    path="",
                    is_ghost=True,
                )

            # Add edge (avoid duplicates)
            edge_key = (title, link_title)
            if edge_key not in seen_edges:
                seen_edges.add(edge_key)
                edges.append(GraphEdge(source=title, target=link_title))

    # Count links per node
    for edge in edges:
        if edge.source in nodes:
            nodes[edge.source].link_count += 1
        if edge.target in nodes:
            nodes[edge.target].link_count += 1

    return nodes, edges


# ── Force-directed layout ────────────────────────────────────────────

def layout_force_directed(
    nodes: Dict[str, GraphNode],
    edges: List[GraphEdge],
    width: float = 800,
    height: float = 600,
    iterations: int = 150,
    seed: int = 42,
) -> None:
    """Apply force-directed layout to position nodes.

    Modifies node.x and node.y in-place.
    """
    if not nodes:
        return

    rng = random.Random(seed)
    node_list = list(nodes.values())
    n = len(node_list)

    # Initial random positions
    cx, cy = width / 2, height / 2
    for node in node_list:
        node.x = cx + rng.uniform(-width * 0.35, width * 0.35)
        node.y = cy + rng.uniform(-height * 0.35, height * 0.35)

    # Build adjacency for faster lookup
    adj: Dict[str, Set[str]] = {node.title: set() for node in node_list}
    for edge in edges:
        if edge.source in adj and edge.target in adj:
            adj[edge.source].add(edge.target)
            adj[edge.target].add(edge.source)

    # Simulation parameters
    k = math.sqrt((width * height) / max(n, 1)) * 0.8  # ideal spring length
    temp = width * 0.1  # initial temperature (max displacement)
    min_temp = 1.0

    for iteration in range(iterations):
        # Cool down temperature
        t = max(min_temp, temp * (1.0 - iteration / iterations))

        # Calculate repulsive forces (all pairs)
        for i, a in enumerate(node_list):
            a.vx = 0.0
            a.vy = 0.0
            for j, b in enumerate(node_list):
                if i == j:
                    continue
                dx = a.x - b.x
                dy = a.y - b.y
                dist = max(math.sqrt(dx * dx + dy * dy), 1.0)
                # Coulomb repulsion
                force = (k * k) / dist
                a.vx += (dx / dist) * force
                a.vy += (dy / dist) * force

        # Calculate attractive forces (edges only)
        for edge in edges:
            a = nodes.get(edge.source)
            b = nodes.get(edge.target)
            if not a or not b:
                continue
            dx = a.x - b.x
            dy = a.y - b.y
            dist = max(math.sqrt(dx * dx + dy * dy), 1.0)
            # Hooke's spring attraction
            force = (dist * dist) / k
            fx = (dx / dist) * force
            fy = (dy / dist) * force
            a.vx -= fx
            a.vy -= fy
            b.vx += fx
            b.vy += fy

        # Gravity: pull all nodes toward center
        for node in node_list:
            dx = cx - node.x
            dy = cy - node.y
            dist = max(math.sqrt(dx * dx + dy * dy), 1.0)
            node.vx += dx * 0.01
            node.vy += dy * 0.01

        # Apply velocities with temperature limiting
        for node in node_list:
            speed = math.sqrt(node.vx * node.vx + node.vy * node.vy)
            if speed > t:
                node.vx = (node.vx / speed) * t
                node.vy = (node.vy / speed) * t
            node.x += node.vx
            node.y += node.vy

            # Keep within bounds (soft boundary)
            margin = 40
            node.x = max(margin, min(width - margin, node.x))
            node.y = max(margin, min(height - margin, node.y))


# ── Graph Canvas Widget ──────────────────────────────────────────────

# Colour palette
BG_GRAPH = "#0f0d1a"
EDGE_COLOR = "#2d2640"
EDGE_HIGHLIGHT = "#7c3aed"
NODE_COLORS = {
    "hub": "#c084fc",       # purple — many links
    "connected": "#38bdf8", # blue — some links
    "leaf": "#22c55e",      # green — few links
    "ghost": "#4b4560",     # gray — doesn't exist yet
    "selected": "#f59e0b",  # amber — currently selected
}
LABEL_COLOR = "#e2e0f0"
LABEL_GHOST = "#6b6580"


class GraphCanvas(tk.Frame):
    """Interactive knowledge graph canvas with zoom, pan, and click-to-select."""

    def __init__(
        self,
        parent: tk.Widget,
        on_node_click: Optional[Callable[[str, str], None]] = None,
        **kwargs,
    ):
        """
        Args:
            parent: Parent tkinter widget.
            on_node_click: Callback(title, path) when a node is clicked.
        """
        super().__init__(parent, bg=BG_GRAPH, **kwargs)
        self._on_node_click = on_node_click
        self._nodes: Dict[str, GraphNode] = {}
        self._edges: List[GraphEdge] = []
        self._selected_title: str = ""

        # Transform state (pan + zoom)
        self._scale = 1.0
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._drag_start: Optional[Tuple[int, int]] = None

        # Build canvas
        self._canvas = tk.Canvas(
            self, bg=BG_GRAPH, highlightthickness=0, cursor="fleur",
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)

        # Stats bar
        self._stats_var = tk.StringVar(value="No vault loaded")
        self._stats_label = tk.Label(
            self, textvariable=self._stats_var,
            font=("Segoe UI", 8), bg="#1a1726", fg="#6b6580",
            anchor=tk.W, padx=8, pady=2,
        )
        self._stats_label.pack(fill=tk.X, side=tk.BOTTOM)

        # Bind events
        self._canvas.bind("<ButtonPress-1>", self._on_click)
        self._canvas.bind("<ButtonPress-3>", self._on_pan_start)
        self._canvas.bind("<B3-Motion>", self._on_pan_move)
        self._canvas.bind("<ButtonRelease-3>", self._on_pan_end)
        self._canvas.bind("<MouseWheel>", self._on_zoom)
        self._canvas.bind("<Configure>", self._on_resize)

        # Tooltip
        self._tooltip = tk.Label(
            self._canvas, text="", font=("Segoe UI", 8),
            bg="#2d2640", fg="#e2e0f0", padx=6, pady=2,
            relief=tk.SOLID, bd=1,
        )
        self._tooltip_id: Optional[int] = None
        self._canvas.bind("<Motion>", self._on_mouse_move)

    def load_vault(self, vault_path: Path) -> None:
        """Load graph data from an Obsidian vault and render it."""
        self._nodes, self._edges = build_graph(vault_path)

        if not self._nodes:
            self._stats_var.set("Empty vault — no notes found")
            return

        # Run layout
        w = max(self._canvas.winfo_width(), 800)
        h = max(self._canvas.winfo_height(), 600)
        layout_force_directed(self._nodes, self._edges, width=w, height=h)

        # Reset view
        self._scale = 1.0
        self._offset_x = 0.0
        self._offset_y = 0.0

        self._render()

        # Stats
        ghost_count = sum(1 for n in self._nodes.values() if n.is_ghost)
        real_count = len(self._nodes) - ghost_count
        self._stats_var.set(
            f"{real_count} notes  |  {ghost_count} ghost nodes  |  "
            f"{len(self._edges)} links  |  Scroll to zoom, right-drag to pan"
        )

    def load_cluster(self, cluster_notes: list[dict]) -> None:
        """Build and display a graph from in-memory cluster notes (not yet saved)."""
        self._nodes = {}
        self._edges = []
        seen_edges: set[tuple[str, str]] = set()

        # Build nodes from cluster
        for note in cluster_notes:
            title = note["title"]
            self._nodes[title] = GraphNode(
                title=title,
                path="",
                tags=[],
            )

        # Extract links
        for note in cluster_notes:
            title = note["title"]
            links = re.findall(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', note["content"])
            for link_title in links:
                link_title = link_title.strip()
                if not link_title or link_title == title:
                    continue
                if link_title not in self._nodes:
                    self._nodes[link_title] = GraphNode(
                        title=link_title, path="", is_ghost=True,
                    )
                edge_key = (title, link_title)
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    self._edges.append(GraphEdge(source=title, target=link_title))

        # Count links
        for edge in self._edges:
            if edge.source in self._nodes:
                self._nodes[edge.source].link_count += 1
            if edge.target in self._nodes:
                self._nodes[edge.target].link_count += 1

        if not self._nodes:
            return

        w = max(self._canvas.winfo_width(), 800)
        h = max(self._canvas.winfo_height(), 600)
        layout_force_directed(self._nodes, self._edges, width=w, height=h)
        self._scale = 1.0
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._render()

        ghost_count = sum(1 for n in self._nodes.values() if n.is_ghost)
        cluster_count = len(self._nodes) - ghost_count
        self._stats_var.set(
            f"{cluster_count} cluster notes  |  {ghost_count} external links  |  "
            f"{len(self._edges)} edges"
        )

    def select_node(self, title: str) -> None:
        """Highlight a specific node as selected."""
        old = self._selected_title
        self._selected_title = title
        # Re-colour old and new nodes
        if old and old in self._nodes:
            self._recolor_node(self._nodes[old])
        if title in self._nodes:
            self._recolor_node(self._nodes[title])

    def _render(self) -> None:
        """Clear canvas and draw all edges + nodes."""
        self._canvas.delete("all")

        # Draw edges first (under nodes)
        for edge in self._edges:
            src = self._nodes.get(edge.source)
            tgt = self._nodes.get(edge.target)
            if not src or not tgt:
                continue
            x1, y1 = self._world_to_screen(src.x, src.y)
            x2, y2 = self._world_to_screen(tgt.x, tgt.y)
            edge.canvas_id = self._canvas.create_line(
                x1, y1, x2, y2,
                fill=EDGE_COLOR, width=1, smooth=True,
            )

        # Draw nodes
        for node in self._nodes.values():
            self._draw_node(node)

    def _draw_node(self, node: GraphNode) -> None:
        """Draw a single node (circle + label) on the canvas."""
        sx, sy = self._world_to_screen(node.x, node.y)

        # Node radius based on link count
        base_r = 4
        r = base_r + min(node.link_count, 20) * 0.8
        r *= self._scale

        # Colour
        color = self._get_node_color(node)

        node.canvas_id = self._canvas.create_oval(
            sx - r, sy - r, sx + r, sy + r,
            fill=color, outline=color, width=1,
            tags=("node", f"n_{node.title}"),
        )

        # Label (only show if zoomed in enough or node is important)
        show_label = (
            self._scale > 0.5
            or node.link_count >= 3
            or node.title == self._selected_title
        )
        if show_label:
            label_color = LABEL_GHOST if node.is_ghost else LABEL_COLOR
            font_size = max(7, int(9 * self._scale))
            node.label_id = self._canvas.create_text(
                sx, sy + r + 8,
                text=node.title,
                fill=label_color,
                font=("Segoe UI", font_size),
                anchor=tk.N,
                tags=("label", f"l_{node.title}"),
            )

    def _get_node_color(self, node: GraphNode) -> str:
        """Determine node colour based on its properties."""
        if node.title == self._selected_title:
            return NODE_COLORS["selected"]
        if node.is_ghost:
            return NODE_COLORS["ghost"]
        if node.link_count >= 6:
            return NODE_COLORS["hub"]
        if node.link_count >= 2:
            return NODE_COLORS["connected"]
        return NODE_COLORS["leaf"]

    def _recolor_node(self, node: GraphNode) -> None:
        """Update just the colour of an existing node on canvas."""
        color = self._get_node_color(node)
        if node.canvas_id:
            self._canvas.itemconfigure(node.canvas_id, fill=color, outline=color)

    # ── Coordinate transforms ─────────────────────────────────────

    def _world_to_screen(self, wx: float, wy: float) -> Tuple[float, float]:
        sx = (wx + self._offset_x) * self._scale
        sy = (wy + self._offset_y) * self._scale
        return sx, sy

    def _screen_to_world(self, sx: float, sy: float) -> Tuple[float, float]:
        wx = sx / self._scale - self._offset_x
        wy = sy / self._scale - self._offset_y
        return wx, wy

    # ── Event handlers ────────────────────────────────────────────

    def _on_click(self, event: tk.Event) -> None:
        """Handle left click — select a node."""
        # Find closest node
        wx, wy = self._screen_to_world(event.x, event.y)
        closest: Optional[GraphNode] = None
        min_dist = float("inf")

        for node in self._nodes.values():
            dx = node.x - wx
            dy = node.y - wy
            dist = math.sqrt(dx * dx + dy * dy)
            click_radius = (4 + min(node.link_count, 20) * 0.8) * 2  # generous hit area
            if dist < click_radius and dist < min_dist:
                min_dist = dist
                closest = node

        if closest:
            self.select_node(closest.title)
            # Highlight connected edges
            self._highlight_edges(closest.title)
            if self._on_node_click:
                self._on_node_click(closest.title, closest.path)

    def _highlight_edges(self, title: str) -> None:
        """Highlight edges connected to the selected node."""
        for edge in self._edges:
            connected = (edge.source == title or edge.target == title)
            color = EDGE_HIGHLIGHT if connected else EDGE_COLOR
            width = 2 if connected else 1
            if edge.canvas_id:
                self._canvas.itemconfigure(edge.canvas_id, fill=color, width=width)
                if connected:
                    self._canvas.tag_raise(edge.canvas_id)

        # Raise all nodes above edges
        self._canvas.tag_raise("node")
        self._canvas.tag_raise("label")

    def _on_pan_start(self, event: tk.Event) -> None:
        self._drag_start = (event.x, event.y)

    def _on_pan_move(self, event: tk.Event) -> None:
        if self._drag_start:
            dx = event.x - self._drag_start[0]
            dy = event.y - self._drag_start[1]
            self._offset_x += dx / self._scale
            self._offset_y += dy / self._scale
            self._drag_start = (event.x, event.y)
            self._render()

    def _on_pan_end(self, event: tk.Event) -> None:
        self._drag_start = None

    def _on_zoom(self, event: tk.Event) -> None:
        """Zoom in/out with mouse wheel."""
        factor = 1.15 if event.delta > 0 else 1.0 / 1.15
        new_scale = self._scale * factor
        # Clamp zoom level
        new_scale = max(0.15, min(5.0, new_scale))

        # Zoom toward cursor position
        wx, wy = self._screen_to_world(event.x, event.y)
        self._scale = new_scale
        # Adjust offset so the world point under cursor stays there
        self._offset_x = event.x / self._scale - wx
        self._offset_y = event.y / self._scale - wy

        self._render()

    def _on_resize(self, event: tk.Event) -> None:
        """Re-render on window resize."""
        if self._nodes:
            self._render()

    def _on_mouse_move(self, event: tk.Event) -> None:
        """Show tooltip on node hover."""
        wx, wy = self._screen_to_world(event.x, event.y)
        hovered: Optional[GraphNode] = None

        for node in self._nodes.values():
            dx = node.x - wx
            dy = node.y - wy
            dist = math.sqrt(dx * dx + dy * dy)
            hit_r = (4 + min(node.link_count, 20) * 0.8) * 1.5
            if dist < hit_r:
                hovered = node
                break

        if hovered:
            status = "ghost (not created yet)" if hovered.is_ghost else hovered.path
            links_txt = f"{hovered.link_count} links"
            tags_txt = f"  tags: {', '.join(hovered.tags[:5])}" if hovered.tags else ""
            self._tooltip.configure(text=f"{hovered.title}\n{status}  |  {links_txt}{tags_txt}")
            self._tooltip.place(x=event.x + 12, y=event.y + 12)
        else:
            self._tooltip.place_forget()
