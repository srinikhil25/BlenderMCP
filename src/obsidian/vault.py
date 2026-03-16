"""Obsidian vault operations — read, write, search notes."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from src.obsidian import config as obs_cfg


def get_vault_path() -> Path | None:
    """Return the configured vault path, or None if not set."""
    if not obs_cfg.VAULT_PATH:
        return None
    p = Path(obs_cfg.VAULT_PATH)
    return p if p.is_dir() else None


def list_notes(folder: str = "") -> List[str]:
    """List all .md files in the vault (or a subfolder). Returns relative paths."""
    vault = get_vault_path()
    if not vault:
        return []
    search_dir = vault / folder if folder else vault
    if not search_dir.is_dir():
        return []
    notes = []
    for f in sorted(search_dir.rglob("*.md")):
        rel = f.relative_to(vault)
        # Skip hidden folders (.obsidian, .trash)
        if any(part.startswith(".") for part in rel.parts):
            continue
        notes.append(str(rel))
    return notes


def list_note_titles(folder: str = "") -> List[str]:
    """List note titles (filenames without .md) for wiki-link suggestions."""
    return [Path(n).stem for n in list_notes(folder)]


def read_note(path: str) -> str | None:
    """Read a note's content by its relative path (e.g., 'folder/note.md')."""
    vault = get_vault_path()
    if not vault:
        return None
    full = vault / path
    if not full.exists() or not full.is_file():
        return None
    try:
        return full.read_text(encoding="utf-8")
    except Exception:
        return None


def write_note(path: str, content: str, overwrite: bool = False) -> Path:
    """Write a note to the vault.

    Args:
        path: Relative path (e.g., 'AI/machine-learning.md').
        content: Markdown content.
        overwrite: If False and file exists, append a number.

    Returns:
        The actual path written to.
    """
    vault = get_vault_path()
    if not vault:
        raise RuntimeError("Obsidian vault path not set. Configure it in Settings.")

    full = vault / path
    full.parent.mkdir(parents=True, exist_ok=True)

    # Avoid overwriting unless explicitly asked
    if not overwrite and full.exists():
        stem = full.stem
        suffix = full.suffix
        parent = full.parent
        i = 1
        while full.exists():
            full = parent / f"{stem}_{i}{suffix}"
            i += 1

    full.write_text(content, encoding="utf-8")
    return full


def search_notes(query: str, max_results: int = 20) -> List[dict]:
    """Search notes by content or title. Returns [{path, title, snippet}]."""
    vault = get_vault_path()
    if not vault:
        return []

    query_lower = query.lower()
    results = []

    for note_path in list_notes():
        full = vault / note_path
        try:
            content = full.read_text(encoding="utf-8")
        except Exception:
            continue

        title = Path(note_path).stem
        title_match = query_lower in title.lower()
        content_match = query_lower in content.lower()

        if title_match or content_match:
            # Extract a snippet around the match
            snippet = ""
            if content_match:
                idx = content.lower().find(query_lower)
                start = max(0, idx - 50)
                end = min(len(content), idx + len(query) + 50)
                snippet = content[start:end].replace("\n", " ").strip()
                if start > 0:
                    snippet = "..." + snippet
                if end < len(content):
                    snippet = snippet + "..."

            results.append({
                "path": note_path,
                "title": title,
                "snippet": snippet or title,
                "title_match": title_match,
            })

        if len(results) >= max_results:
            break

    # Title matches first
    results.sort(key=lambda r: (not r["title_match"], r["title"]))
    return results


def extract_title_from_markdown(content: str) -> str:
    """Extract a note title from markdown content (first H1 or frontmatter title)."""
    # Check frontmatter
    fm_match = re.search(r'^---\s*\n.*?title:\s*["\']?(.+?)["\']?\s*\n.*?---', content, re.DOTALL)
    if fm_match:
        return fm_match.group(1).strip()

    # Check first H1
    h1_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    if h1_match:
        return h1_match.group(1).strip()

    # First non-empty line
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith("---"):
            return line[:60]

    return "Untitled"


def slugify(title: str) -> str:
    """Convert a title to a safe filename slug."""
    # Replace spaces and special chars
    slug = re.sub(r'[^\w\s-]', '', title.lower())
    slug = re.sub(r'[\s_]+', '-', slug).strip('-')
    return slug or "untitled"
