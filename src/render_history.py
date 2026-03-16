"""Render history — saves thumbnails and prompts for browsing past generations."""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

_HISTORY_DIR = Path.home() / ".blendermcp" / "renders"
_MAX_RENDERS = 50  # keep last N renders


@dataclass
class RenderEntry:
    timestamp: float
    prompt: str
    image_path: str
    thumbnail_path: str

    @property
    def time_str(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(self.timestamp))

    @property
    def short_prompt(self) -> str:
        return self.prompt[:60] + "..." if len(self.prompt) > 60 else self.prompt


def save_render(image_path: str, prompt: str) -> Optional[RenderEntry]:
    """Save a render image and prompt to history.

    Args:
        image_path: Path to the rendered PNG file.
        prompt: The prompt that generated this scene.

    Returns:
        RenderEntry if saved successfully, None otherwise.
    """
    try:
        _HISTORY_DIR.mkdir(parents=True, exist_ok=True)

        ts = time.time()
        ts_str = time.strftime("%Y%m%d_%H%M%S", time.localtime(ts))

        # Copy full image
        img_dest = _HISTORY_DIR / f"render_{ts_str}.png"
        shutil.copy2(image_path, img_dest)

        # Create thumbnail (128px wide)
        thumb_dest = _HISTORY_DIR / f"thumb_{ts_str}.png"
        try:
            from PIL import Image
            img = Image.open(image_path)
            img.thumbnail((128, 128), Image.LANCZOS)
            img.save(str(thumb_dest))
        except Exception:
            shutil.copy2(image_path, thumb_dest)

        # Save metadata
        entry = RenderEntry(
            timestamp=ts,
            prompt=prompt,
            image_path=str(img_dest),
            thumbnail_path=str(thumb_dest),
        )

        # Update index
        index = _load_index()
        index.append({
            "timestamp": ts,
            "prompt": prompt,
            "image": str(img_dest),
            "thumb": str(thumb_dest),
        })

        # Trim to max
        if len(index) > _MAX_RENDERS:
            for old in index[:-_MAX_RENDERS]:
                _safe_delete(old.get("image", ""))
                _safe_delete(old.get("thumb", ""))
            index = index[-_MAX_RENDERS:]

        _save_index(index)
        return entry

    except Exception:
        return None


def load_history() -> List[RenderEntry]:
    """Load all render history entries."""
    index = _load_index()
    entries = []
    for item in index:
        if Path(item.get("thumb", "")).exists():
            entries.append(RenderEntry(
                timestamp=item.get("timestamp", 0),
                prompt=item.get("prompt", ""),
                image_path=item.get("image", ""),
                thumbnail_path=item.get("thumb", ""),
            ))
    return entries


def _load_index() -> list:
    index_file = _HISTORY_DIR / "index.json"
    try:
        if index_file.exists():
            data = json.loads(index_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def _save_index(index: list) -> None:
    index_file = _HISTORY_DIR / "index.json"
    try:
        _HISTORY_DIR.mkdir(parents=True, exist_ok=True)
        index_file.write_text(
            json.dumps(index, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def _safe_delete(path: str) -> None:
    try:
        p = Path(path)
        if p.exists():
            p.unlink()
    except Exception:
        pass
