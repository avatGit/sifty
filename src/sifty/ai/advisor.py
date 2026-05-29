"""AI advisory prompts.

The advisor only ever receives *metadata* — names, sizes, paths, extensions,
counts — never file contents. It explains and recommends; it never deletes.
The calling command does the acting, with the usual dry-run/confirm safeguards.
"""

from __future__ import annotations

from .client import OllamaClient, OllamaUnavailable

_SYSTEM = (
    "You are a careful Windows maintenance assistant embedded in a CLI tool. "
    "You are given only file/app metadata, never file contents. Be concise, "
    "practical, and cautious: when unsure whether something is safe to remove, "
    "say so. Never recommend deleting anything under C:\\Windows, Program Files, "
    "or a user's personal documents."
)


def _safe(client: OllamaClient, user_prompt: str) -> str | None:
    """Run a prompt, returning None if the AI is unavailable."""
    if not client.is_available():
        return None
    try:
        return client.chat(_SYSTEM, user_prompt)
    except OllamaUnavailable:
        return None


def explain_item(client: OllamaClient, name: str, path: str, size_human: str) -> str | None:
    """Explain what an item is and whether it's safe to remove."""
    return _safe(
        client,
        f"What is this Windows item, and is it generally safe to delete?\n"
        f"Name: {name}\nPath: {path}\nSize: {size_human}\n"
        f"Answer in 2-3 sentences.",
    )


def summarize_disk(client: OllamaClient, items: list[tuple[str, str]], question: str) -> str | None:
    """Answer a natural-language question about the biggest disk items."""
    listing = "\n".join(f"- {name}: {size}" for name, size in items)
    return _safe(
        client,
        f"Here are the largest items in a directory:\n{listing}\n\n"
        f"User question: {question}\n"
        f"Give a brief, practical answer and flag anything risky to delete.",
    )


def suggest_organization(client: OllamaClient, sample_names: list[str]) -> str | None:
    """Propose a folder scheme for a messy directory from sample filenames."""
    listing = "\n".join(f"- {n}" for n in sample_names[:40])
    return _safe(
        client,
        f"These are sample filenames from a cluttered folder:\n{listing}\n\n"
        f"Suggest a simple folder structure to organize them. Be concise.",
    )
