"""LLM wrapper for Obsidian — generates structured markdown notes."""

from __future__ import annotations

import os
import re
import threading
from typing import Optional

import src.config as cfg

SYSTEM_PROMPT = """\
You are an expert knowledge worker and note-taking specialist.
Generate well-structured Obsidian-compatible Markdown notes.

OUTPUT: Valid Markdown inside ```markdown fences. No explanations outside the fences.

RULES:
1. Use proper heading hierarchy (# > ## > ### etc.)
2. Use [[wiki-links]] for concepts that could be their own notes
3. Use #tags for key themes (lowercase, hyphenated: #machine-learning)
4. Use bullet points and numbered lists for clarity
5. Use > blockquotes for important definitions or quotes
6. Use code blocks with language tags for any code
7. Use **bold** for key terms on first mention
8. Use tables where data is tabular
9. Keep paragraphs short (2-3 sentences max)
10. Include a "## See Also" section at the end with related [[links]]

FRONTMATTER TEMPLATE (always include):
```yaml
---
title: "Note Title"
created: YYYY-MM-DD
tags: [tag1, tag2, tag3]
type: note
---
```

NOTE TYPES:
- "standard": General knowledge note with sections
- "cornell": Cornell method (Questions | Notes | Summary)
- "zettelkasten": Atomic note — ONE idea, with links to related concepts
- "meeting": Meeting notes (Attendees, Agenda, Notes, Action Items)
- "research": Research note (Abstract, Key Findings, Methodology, References)

When asked to generate notes, create rich, interconnected content that
works well in an Obsidian knowledge base. Prefer atomic concepts with
wiki-links over monolithic documents.
"""

MODIFY_PROMPT = """\
The existing note contains:
{note_content}

IMPORTANT: Modify or extend this note based on the user's request.
Keep the existing structure where possible. Add new sections, links, or content.
Output the COMPLETE updated note inside ```markdown fences.
"""


def generate_note(
    prompt: str,
    template: str = "standard",
    existing_content: str = "",
    vault_context: str = "",
    feedback: str = "",
) -> tuple[str, bool]:
    """Generate a markdown note from a prompt.

    Args:
        prompt: User's description of what to generate.
        template: Note template style.
        existing_content: Existing note content (for modify mode).
        vault_context: List of existing note titles for link suggestions.
        feedback: Error feedback from a previous attempt.

    Returns:
        Tuple of (markdown_string, was_cached).
    """
    from src.code_cache import get_cached, save_to_cache

    # Check cache (skip if modifying or retrying)
    cache_key = f"obsidian:{template}:{prompt}"
    if not feedback and not existing_content:
        cached = get_cached(cache_key)
        if cached:
            return cached, True

    # Build user message
    parts = []
    if existing_content:
        parts.append(MODIFY_PROMPT.format(note_content=existing_content))
    if vault_context:
        parts.append(f"Existing notes in vault (use for [[wiki-links]]): {vault_context}")
    parts.append(f"Template style: {template}")
    parts.append(prompt)
    if feedback:
        parts.append(f"\nPrevious attempt had issues:\n{feedback}\nFix and regenerate.")

    user_msg = "\n\n".join(parts)

    if cfg.LLM_PROVIDER == "gemini":
        result = _generate_gemini(user_msg)
    else:
        result = _generate_ollama(user_msg)

    # Save to cache
    if not feedback and not existing_content:
        save_to_cache(cache_key, result)

    return result, False


def _generate_gemini(user_msg: str) -> str:
    """Generate via Gemini API."""
    from google import genai

    api_key = cfg.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "Gemini API key not set. Set GEMINI_API_KEY in .env or environment."
        )

    client = genai.Client(api_key=api_key)

    result_container: list = []
    error_container: list = []

    def _call() -> None:
        try:
            response = client.models.generate_content(
                model=cfg.GEMINI_MODEL,
                contents=user_msg,
                config=genai.types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                ),
            )
            result_container.append(response.text)
        except Exception as e:
            error_container.append(e)

    thread = threading.Thread(target=_call, daemon=True)
    thread.start()
    thread.join(timeout=cfg.LLM_TIMEOUT)

    if thread.is_alive():
        raise RuntimeError(f"Gemini timed out after {cfg.LLM_TIMEOUT}s.")
    if error_container:
        raise error_container[0]
    if not result_container:
        raise RuntimeError("Gemini returned no response.")

    return _extract_markdown(result_container[0])


def _generate_ollama(user_msg: str) -> str:
    """Generate via local Ollama."""
    import ollama

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]

    result_container: list = []
    error_container: list = []

    def _call() -> None:
        try:
            response = ollama.chat(
                model=cfg.OLLAMA_MODEL,
                messages=messages,
                options={"num_ctx": cfg.OLLAMA_NUM_CTX},
            )
            result_container.append(response["message"]["content"])
        except Exception as e:
            error_container.append(e)

    thread = threading.Thread(target=_call, daemon=True)
    thread.start()
    thread.join(timeout=cfg.LLM_TIMEOUT)

    if thread.is_alive():
        raise RuntimeError(f"Ollama timed out after {cfg.LLM_TIMEOUT}s.")
    if error_container:
        raise error_container[0]
    if not result_container:
        raise RuntimeError("Ollama returned no response.")

    return _extract_markdown(result_container[0])


def _extract_markdown(text: str) -> str:
    """Extract markdown content from LLM response."""
    # Remove think tags
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

    # Extract from ```markdown ... ``` fences
    match = re.search(r"```markdown\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Try ```md fences
    match = re.search(r"```md\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Try generic fences
    match = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # No fences — return as-is
    return text.strip()
