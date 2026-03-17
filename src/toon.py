"""
TOON (Token-Oriented Object Notation) encoder for LLM prompts.

Implements the TOON v3.0 spec — a compact, human-readable encoding of JSON
that minimizes tokens sent to LLMs. Combines YAML-style indentation for objects
with CSV-style tabular layout for uniform arrays.

Token savings: ~40-60% fewer tokens than equivalent JSON.

Spec: https://github.com/toon-format/spec/blob/main/SPEC.md
"""

from __future__ import annotations

import math
import re
from datetime import datetime, date
from decimal import Decimal
from typing import Any, Union

# ── Configuration ─────────────────────────────────────────────────────

DEFAULT_INDENT = 2  # spaces per nesting level
DEFAULT_DELIMITER = ","

# Pattern for safe unquoted keys (§7.3)
_SAFE_KEY_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_.]*$')

# Pattern for numeric-looking strings that need quoting (§7.2)
_NUMERIC_RE = re.compile(r'^-?\d+(?:\.\d+)?(?:e[+-]?\d+)?$', re.IGNORECASE)
_LEADING_ZERO_RE = re.compile(r'^0\d+$')

# Reserved words that need quoting when used as string values
_RESERVED_WORDS = frozenset({"true", "false", "null"})


# ── Public API ────────────────────────────────────────────────────────

def encode(data: Any, indent: int = DEFAULT_INDENT, delimiter: str = DEFAULT_DELIMITER) -> str:
    """Encode a Python object to TOON format.

    Args:
        data: Python dict, list, or primitive to encode.
        indent: Spaces per indentation level (default 2).
        delimiter: Field delimiter for arrays (default comma).

    Returns:
        TOON-encoded string.

    Examples:
        >>> encode({"name": "Alice", "age": 30})
        'name: Alice\\nage: 30'

        >>> encode({"users": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]})
        'users[2]{id,name}:\\n  1,Alice\\n  2,Bob'
    """
    ctx = _Context(indent_size=indent, delimiter=delimiter)

    if isinstance(data, dict):
        return _encode_object(data, ctx, depth=0)
    elif isinstance(data, (list, tuple, set, frozenset)):
        data = list(data)
        return _encode_root_array(data, ctx)
    else:
        return _encode_primitive(data, ctx)


def encode_context(label: str, data: Any, **kwargs) -> str:
    """Encode data with a descriptive label — convenience for LLM prompts.

    Example:
        >>> encode_context("vault_notes", [{"title": "ML", "links": 5}, ...])
        '--- vault_notes ---\\ntitles[2]{title,links}:\\n  ML,5\\n  ...'
    """
    header = f"--- {label} ---"
    body = encode(data, **kwargs)
    return f"{header}\n{body}"


# ── Internal types ────────────────────────────────────────────────────

class _Context:
    """Encoding state and configuration."""
    __slots__ = ("indent_size", "delimiter")

    def __init__(self, indent_size: int, delimiter: str):
        self.indent_size = indent_size
        self.delimiter = delimiter

    def indent(self, depth: int) -> str:
        return " " * (self.indent_size * depth)


# ── Primitive encoding (§2, §7) ──────────────────────────────────────

def _normalize_number(value: Union[int, float, Decimal]) -> str:
    """Canonical number format per §2."""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return "null"
        # Negative zero
        if value == 0.0 and math.copysign(1, value) < 0:
            value = 0.0
        # Integer if no fractional part
        if value == int(value) and not math.isinf(value):
            return str(int(value))
        # Strip trailing zeros
        s = f"{value}"
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return s

    if isinstance(value, Decimal):
        if value.is_nan() or value.is_infinite():
            return "null"
        # Normalize
        return str(value.normalize())

    # int
    return str(value)


def _needs_quoting(value: str, delimiter: str) -> bool:
    """Check if a string value needs quoting per §7.2."""
    if not value:  # empty string
        return True
    if value in _RESERVED_WORDS:
        return True
    if _NUMERIC_RE.match(value) or _LEADING_ZERO_RE.match(value):
        return True
    # Contains problematic characters
    if any(c in value for c in (delimiter, '"', '\\', ':', '[', ']', '{', '}')):
        return True
    # Control characters
    if any(c in value for c in ('\n', '\r', '\t')):
        return True
    # Leading/trailing whitespace
    if value != value.strip():
        return True
    # Starts with dash
    if value.startswith("-"):
        return True
    return False


def _escape_string(value: str) -> str:
    """Escape a string for quoting per §7.1."""
    value = value.replace("\\", "\\\\")
    value = value.replace('"', '\\"')
    value = value.replace("\n", "\\n")
    value = value.replace("\r", "\\r")
    value = value.replace("\t", "\\t")
    return value


def _encode_primitive(value: Any, ctx: _Context) -> str:
    """Encode a single primitive value."""
    # Host type normalization (§3)
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, Decimal)):
        return _normalize_number(value)
    if isinstance(value, (datetime, date)):
        return _quote_if_needed(value.isoformat(), ctx.delimiter)
    if isinstance(value, str):
        return _quote_if_needed(value, ctx.delimiter)
    # Fallback
    return _quote_if_needed(str(value), ctx.delimiter)


def _quote_if_needed(value: str, delimiter: str) -> str:
    """Quote and escape a string if needed, otherwise return as-is."""
    if _needs_quoting(value, delimiter):
        return f'"{_escape_string(value)}"'
    return value


def _encode_key(key: str) -> str:
    """Encode an object key per §7.3."""
    if _SAFE_KEY_RE.match(key):
        return key
    return f'"{_escape_string(key)}"'


# ── Object encoding (§8) ─────────────────────────────────────────────

def _encode_object(obj: dict, ctx: _Context, depth: int) -> str:
    """Encode a dict as a TOON object with indentation."""
    if not obj:
        return ""

    lines = []
    prefix = ctx.indent(depth)

    for key, value in obj.items():
        k = _encode_key(str(key))

        if isinstance(value, dict):
            if not value:
                # Empty object — just the key with colon
                lines.append(f"{prefix}{k}:")
            else:
                lines.append(f"{prefix}{k}:")
                lines.append(_encode_object(value, ctx, depth + 1))

        elif isinstance(value, (list, tuple, set, frozenset)):
            arr = list(value)
            arr_str = _encode_array_field(k, arr, ctx, depth)
            lines.append(arr_str)

        else:
            v = _encode_primitive(value, ctx)
            lines.append(f"{prefix}{k}: {v}")

    return "\n".join(lines)


# ── Array encoding (§6, §9) ──────────────────────────────────────────

def _is_uniform_object_array(arr: list) -> bool:
    """Check if array qualifies for tabular format (§9.3).

    All elements must be dicts with identical keys, and all values must be primitives.
    """
    if len(arr) < 1:
        return False
    if not all(isinstance(item, dict) for item in arr):
        return False

    # Check identical key sets
    first_keys = tuple(arr[0].keys())
    if not first_keys:
        return False
    for item in arr[1:]:
        if tuple(item.keys()) != first_keys:
            return False

    # Check all values are primitives (not nested dicts/lists)
    for item in arr:
        for v in item.values():
            if isinstance(v, (dict, list, tuple, set, frozenset)):
                return False

    return True


def _is_primitive_array(arr: list) -> bool:
    """Check if array contains only primitives."""
    return all(
        not isinstance(item, (dict, list, tuple, set, frozenset))
        for item in arr
    )


def _encode_root_array(arr: list, ctx: _Context) -> str:
    """Encode a top-level array."""
    if not arr:
        return "[0]:"

    if _is_primitive_array(arr):
        values = ctx.delimiter.join(_encode_primitive(v, ctx) for v in arr)
        return f"[{len(arr)}]: {values}"

    if _is_uniform_object_array(arr):
        fields = list(arr[0].keys())
        header = f"[{len(arr)}]{{{ctx.delimiter.join(fields)}}}:"
        rows = []
        for item in arr:
            row = ctx.delimiter.join(
                _encode_primitive(item[f], ctx) for f in fields
            )
            rows.append(f"{ctx.indent(1)}{row}")
        return f"{header}\n" + "\n".join(rows)

    # Mixed/nested array — expanded list (§9.4)
    lines = [f"[{len(arr)}]:"]
    for item in arr:
        if isinstance(item, dict):
            lines.append(f"{ctx.indent(1)}- {_encode_object(item, ctx, 2).lstrip()}")
        elif isinstance(item, (list, tuple)):
            inner = _encode_root_array(list(item), ctx)
            lines.append(f"{ctx.indent(1)}- {inner}")
        else:
            lines.append(f"{ctx.indent(1)}- {_encode_primitive(item, ctx)}")
    return "\n".join(lines)


def _encode_array_field(key: str, arr: list, ctx: _Context, depth: int) -> str:
    """Encode an array as a field of a parent object."""
    prefix = ctx.indent(depth)
    delim = ctx.delimiter

    if not arr:
        return f"{prefix}{key}[0]:"

    # Primitive array — inline (§9.1)
    if _is_primitive_array(arr):
        values = delim.join(_encode_primitive(v, ctx) for v in arr)
        return f"{prefix}{key}[{len(arr)}]: {values}"

    # Uniform object array — tabular (§9.3)
    if _is_uniform_object_array(arr):
        fields = list(arr[0].keys())
        field_header = delim.join(fields)
        header = f"{prefix}{key}[{len(arr)}]{{{field_header}}}:"
        rows = []
        row_prefix = ctx.indent(depth + 1)
        for item in arr:
            row = delim.join(
                _encode_primitive(item[f], ctx) for f in fields
            )
            rows.append(f"{row_prefix}{row}")
        return f"{header}\n" + "\n".join(rows)

    # Mixed/nested — expanded list (§9.4)
    lines = [f"{prefix}{key}[{len(arr)}]:"]
    item_prefix = ctx.indent(depth + 1)
    for item in arr:
        if isinstance(item, dict):
            obj_str = _encode_object(item, ctx, depth + 2).lstrip()
            lines.append(f"{item_prefix}- {obj_str}")
        elif isinstance(item, (list, tuple)):
            inner = _encode_root_array(list(item), ctx)
            lines.append(f"{item_prefix}- {inner}")
        else:
            lines.append(f"{item_prefix}- {_encode_primitive(item, ctx)}")
    return "\n".join(lines)


# ── Convenience helpers for LLM context encoding ─────────────────────

def encode_list_inline(items: list[str], label: str = "") -> str:
    """Encode a simple string list in compact TOON format.

    Example:
        >>> encode_list_inline(["ML", "Neural Nets", "AI"], "topics")
        'topics[3]: ML,Neural Nets,AI'
    """
    safe_items = []
    for item in items:
        safe_items.append(_quote_if_needed(item, DEFAULT_DELIMITER))
    values = DEFAULT_DELIMITER.join(safe_items)
    if label:
        return f"{label}[{len(items)}]: {values}"
    return f"[{len(items)}]: {values}"


def encode_key_value(data: dict[str, str]) -> str:
    """Encode a flat key-value dict — simplest TOON form.

    Example:
        >>> encode_key_value({"provider": "gemini", "model": "2.5-flash"})
        'provider: gemini\\nmodel: 2.5-flash'
    """
    lines = []
    for k, v in data.items():
        key = _encode_key(str(k))
        val = _quote_if_needed(str(v), DEFAULT_DELIMITER) if v else '""'
        lines.append(f"{key}: {val}")
    return "\n".join(lines)


def encode_table(rows: list[dict], label: str = "") -> str:
    """Encode a uniform list of dicts as a TOON table.

    Example:
        >>> encode_table([{"name": "ML", "links": 5}, {"name": "AI", "links": 3}], "notes")
        'notes[2]{name,links}:\\n  ML,5\\n  AI,3'
    """
    if not rows:
        return f"{label}[0]:" if label else "[0]:"

    if not _is_uniform_object_array(rows):
        # Fall back to full encode
        return encode({label: rows} if label else rows)

    fields = list(rows[0].keys())
    field_header = ",".join(fields)
    prefix = label if label else ""
    header = f"{prefix}[{len(rows)}]{{{field_header}}}:"

    lines = [header]
    for row in rows:
        values = ",".join(
            _encode_primitive(row[f], _Context(DEFAULT_INDENT, DEFAULT_DELIMITER))
            for f in fields
        )
        lines.append(f"  {values}")

    return "\n".join(lines)
