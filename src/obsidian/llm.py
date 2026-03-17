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

TOPIC_MAP_PROMPT = """\
You are a knowledge architect. Given a broad topic, generate a topic cluster map
for an Obsidian knowledge base.

OUTPUT FORMAT: Return ONLY a JSON array of objects inside ```json fences.
Each object has: "title" (string), "description" (one sentence), "type" (one of: hub, concept, example, reference).

RULES:
1. First item MUST be the hub note (type: "hub") — the main overview
2. Generate 5-9 subtopic notes that branch from the hub
3. Include a mix of: core concepts, practical examples, and references
4. Titles should be concise (2-5 words) and work as [[wiki-links]]
5. Subtopics should be interconnected — not just linked to the hub
6. Think in terms of an Obsidian graph: create a web, not a star

Example output:
```json
[
  {"title": "Machine Learning", "description": "Overview of ML paradigms and applications", "type": "hub"},
  {"title": "Supervised Learning", "description": "Learning from labeled training data", "type": "concept"},
  {"title": "Neural Networks", "description": "Interconnected layers of artificial neurons", "type": "concept"},
  {"title": "Gradient Descent", "description": "Optimization algorithm for training models", "type": "concept"},
  {"title": "Image Classification", "description": "Practical example using CNNs", "type": "example"},
  {"title": "Overfitting", "description": "When models memorize rather than generalize", "type": "concept"},
  {"title": "ML Glossary", "description": "Key terms and definitions", "type": "reference"}
]
```
"""

CLUSTER_NOTE_PROMPT = """\
You are generating ONE note in a topic cluster for an Obsidian knowledge base.

CLUSTER CONTEXT:
- Hub topic: {hub_title}
- All notes in this cluster: {all_titles}
- This note's role: {note_type}

IMPORTANT:
1. Generate the note for: "{note_title}" — {note_description}
2. Use [[wiki-links]] to link to OTHER notes in this cluster (use exact titles from the list above)
3. Also link to concepts OUTSIDE this cluster that could be future notes
4. The "See Also" section MUST reference at least 2-3 other cluster notes
5. Keep content focused and atomic — this is ONE piece of a larger knowledge web
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
        # TOON table format passed by caller — rich metadata in compact form
        parts.append(f"Existing notes in vault (use for [[wiki-links]]):\n{vault_context}")
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


def _generate_gemini(user_msg: str, system_override: str = "", raw: bool = False) -> str:
    """Generate via Gemini API."""
    from google import genai

    api_key = cfg.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "Gemini API key not set. Set GEMINI_API_KEY in .env or environment."
        )

    client = genai.Client(api_key=api_key)
    system = system_override or SYSTEM_PROMPT

    result_container: list = []
    error_container: list = []

    def _call() -> None:
        try:
            response = client.models.generate_content(
                model=cfg.GEMINI_MODEL,
                contents=user_msg,
                config=genai.types.GenerateContentConfig(
                    system_instruction=system,
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

    if raw:
        return result_container[0]
    return _extract_markdown(result_container[0])


def _generate_ollama(user_msg: str, system_override: str = "", raw: bool = False) -> str:
    """Generate via local Ollama."""
    import ollama

    system = system_override or SYSTEM_PROMPT
    messages = [
        {"role": "system", "content": system},
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

    if raw:
        return result_container[0]
    return _extract_markdown(result_container[0])


def generate_topic_map(topic: str) -> list[dict]:
    """Generate a topic cluster map (list of subtopics) for a broad topic.

    Returns:
        List of dicts with keys: title, description, type.
    """
    import json as _json

    user_msg = f"Generate a topic cluster map for: {topic}"

    if cfg.LLM_PROVIDER == "gemini":
        result = _generate_gemini(user_msg, system_override=TOPIC_MAP_PROMPT, raw=True)
    else:
        result = _generate_ollama(user_msg, system_override=TOPIC_MAP_PROMPT, raw=True)

    # Extract JSON from the response
    result = re.sub(r"<think>.*?</think>", "", result, flags=re.DOTALL)
    json_match = re.search(r"```json\s*\n(.*?)```", result, re.DOTALL)
    if json_match:
        raw = json_match.group(1).strip()
    else:
        # Try to find a raw JSON array
        arr_match = re.search(r'\[.*\]', result, re.DOTALL)
        if arr_match:
            raw = arr_match.group(0)
        else:
            raise RuntimeError("LLM did not return a valid topic map. Try again.")

    try:
        topics = _json.loads(raw)
    except _json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse topic map JSON: {e}")

    if not isinstance(topics, list) or len(topics) < 2:
        raise RuntimeError("Topic map must contain at least 2 entries.")

    # Validate structure
    for t in topics:
        if "title" not in t:
            raise RuntimeError(f"Topic entry missing 'title': {t}")
        t.setdefault("description", "")
        t.setdefault("type", "concept")

    return topics


def generate_cluster_note(
    note_title: str,
    note_description: str,
    note_type: str,
    hub_title: str,
    all_titles: list[str],
    template: str = "standard",
    vault_context: str = "",
) -> str:
    """Generate a single note within a topic cluster.

    Args:
        note_title: Title of this specific note.
        note_description: One-sentence description.
        note_type: Role in cluster (hub, concept, example, reference).
        hub_title: The main hub topic title.
        all_titles: All note titles in the cluster.
        template: Note template style.
        vault_context: Existing vault note titles.

    Returns:
        Generated markdown string.
    """
    cluster_context = CLUSTER_NOTE_PROMPT.format(
        hub_title=hub_title,
        all_titles=", ".join(f"[[{t}]]" for t in all_titles),
        note_type=note_type,
        note_title=note_title,
        note_description=note_description,
    )

    parts = [cluster_context]
    if vault_context:
        # TOON table format passed by caller
        parts.append(f"Existing notes in vault (also link to these if relevant):\n{vault_context}")
    parts.append(f"Template style: {template}")
    parts.append(f"Generate the complete note for: {note_title}")

    user_msg = "\n\n".join(parts)

    if cfg.LLM_PROVIDER == "gemini":
        result = _generate_gemini(user_msg)
    else:
        result = _generate_ollama(user_msg)

    return result


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
