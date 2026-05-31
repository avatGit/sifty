"""Tool registry for the AI agent.

Each tool has a name, Ollama-compatible JSON-schema descriptor, a risk tag
(``"read"`` | ``"low"`` | ``"high"``), and a handler.

Risk levels:
  - ``read``  — no side effects, always runs automatically.
  - ``low``   — reversible or low-impact (e.g. toggle startup entry).
  - ``high``  — destructive or hard to reverse (delete files, uninstall app, apply update).

The autonomy level in config decides which risk tiers need a confirm prompt:
  - ``ask``           — confirm ``low`` and ``high``.
  - ``low_risk_auto`` — auto-run ``low``, confirm ``high``.
  - ``full_auto``     — auto-run all (still routes through safety.trash).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from ..console import human_size


# ---------------------------------------------------------------------------
# Tool dataclass
# ---------------------------------------------------------------------------

@dataclass
class Tool:
    name: str
    description: str
    parameters: dict          # JSON Schema for the function's arguments
    risk: str                 # "read" | "low" | "high"
    handler: Callable[[dict], str]

    def to_ollama(self) -> dict:
        """Return the Ollama tool-descriptor for this tool."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


# ---------------------------------------------------------------------------
# Handlers (call core functions; return human-readable result strings)
# ---------------------------------------------------------------------------

def _handler_scan_junk(_args: dict) -> str:
    from ..core import junk
    cats = junk.scan()
    if not cats:
        return "No junk found."
    lines = [f"Junk scan — {sum(c.size for c in cats) / 1024**3:.2f} GB reclaimable:"]
    for c in cats:
        if c.size > 0:
            lines.append(f"  {c.category.key}: {c.category.label} — {human_size(c.size)} ({c.file_count} files)")
    return "\n".join(lines)


def _handler_analyze_disk(args: dict) -> str:
    from ..core import disk
    path = args.get("path", "")
    try:
        items = disk.biggest(path, 20)
    except (OSError, ValueError) as exc:
        return f"Error: {exc}"
    if not items:
        return f"No files found in {path}."
    lines = [f"Largest items in {path}:"]
    for entry, size in items:
        lines.append(f"  {entry.name} — {human_size(size)}")
    return "\n".join(lines)


def _handler_find_duplicates(args: dict) -> str:
    from ..core import disk
    path = args.get("path", "")
    try:
        groups = disk.find_duplicates(path)
    except (OSError, ValueError) as exc:
        return f"Error: {exc}"
    if not groups:
        return f"No duplicates found in {path}."
    wasted = sum(g[0].stat().st_size * (len(g) - 1) for g in groups if g)
    lines = [f"Found {len(groups)} duplicate group(s), ~{human_size(wasted)} wasted:"]
    for g in groups[:5]:
        lines.append(f"  {len(g)} copies of '{g[0].name}'")
    if len(groups) > 5:
        lines.append(f"  … and {len(groups) - 5} more group(s)")
    return "\n".join(lines)


def _handler_list_apps(_args: dict) -> str:
    from ..core.apps import installed_apps
    apps = installed_apps()
    if not apps:
        return "No apps found."
    lines = [f"Installed apps ({len(apps)}):"]
    for a in sorted(apps, key=lambda x: x.size_bytes, reverse=True)[:20]:
        size = human_size(a.size_bytes) if a.size_bytes else "?"
        lines.append(f"  {a.name} ({a.version}) — {size}")
    if len(apps) > 20:
        lines.append(f"  … and {len(apps) - 20} more")
    return "\n".join(lines)


def _handler_clean_junk(args: dict) -> str:
    from ..core import junk
    categories = args.get("categories") or []
    only = set(categories) if categories else None
    result = junk.clean(only=only, dry_run=False)
    return (
        f"Cleaned: {result.items} items ({human_size(result.bytes_freed)}) moved to the Recycle Bin."
        if result.items else "Nothing was cleaned."
    )


def _handler_uninstall_app(args: dict) -> str:
    from ..core.apps import uninstall_app
    name = args.get("name", "")
    ok, message = uninstall_app(name)
    return f"Uninstall {'succeeded' if ok else 'failed'}: {message}"


def _handler_toggle_startup(args: dict) -> str:
    from ..core import startup
    name = args.get("name", "")
    enable = bool(args.get("enable", True))
    verb = "enable" if enable else "disable"
    entries = [e for e in startup.startup_entries() if e.name == name]
    if not entries:
        return f"No startup entry named '{name}' found."
    entry = entries[0]
    try:
        if enable:
            startup.enable(entry)
        else:
            startup.disable(entry)
        return f"Startup entry '{name}' {verb}d."
    except Exception as exc:
        return f"Failed to {verb} '{name}': {exc}"


def _handler_apply_updates(args: dict) -> str:
    from ..core.updates import apply_upgrades
    pkg_id = args.get("id", "")
    ok, message = apply_upgrades([pkg_id])
    return f"Update {'succeeded' if ok else 'failed'}: {message}"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

TOOLS: list[Tool] = [
    Tool(
        name="scan_junk",
        description="Scan for junk files (temp files, cache, old logs) and return a breakdown by category with sizes.",
        parameters={"type": "object", "properties": {}, "required": []},
        risk="read",
        handler=_handler_scan_junk,
    ),
    Tool(
        name="analyze_disk",
        description="List the largest files and folders in a given directory path.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute directory path to analyze, e.g. C:\\Users\\User\\Downloads"}
            },
            "required": ["path"],
        },
        risk="read",
        handler=_handler_analyze_disk,
    ),
    Tool(
        name="find_duplicates",
        description="Find duplicate files inside a given directory path.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path to scan for duplicates"}
            },
            "required": ["path"],
        },
        risk="read",
        handler=_handler_find_duplicates,
    ),
    Tool(
        name="list_apps",
        description="List installed applications sorted by size.",
        parameters={"type": "object", "properties": {}, "required": []},
        risk="read",
        handler=_handler_list_apps,
    ),
    Tool(
        name="clean_junk",
        description="Remove junk files from specific categories by moving them to the Recycle Bin.",
        parameters={
            "type": "object",
            "properties": {
                "categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Junk category keys to clean, e.g. ['user-temp', 'browser-cache']. Use scan_junk first to see available keys.",
                }
            },
            "required": ["categories"],
        },
        risk="high",
        handler=_handler_clean_junk,
    ),
    Tool(
        name="uninstall_app",
        description="Uninstall an application by its display name (uses winget).",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Application display name or winget package ID"}
            },
            "required": ["name"],
        },
        risk="high",
        handler=_handler_uninstall_app,
    ),
    Tool(
        name="toggle_startup",
        description="Enable or disable a Windows startup entry.",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Startup entry name"},
                "enable": {"type": "boolean", "description": "True to enable, False to disable"},
            },
            "required": ["name", "enable"],
        },
        risk="low",
        handler=_handler_toggle_startup,
    ),
    Tool(
        name="apply_updates",
        description="Apply a pending software update by its winget package ID.",
        parameters={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "winget package ID, e.g. 'Microsoft.PowerToys'"}
            },
            "required": ["id"],
        },
        risk="high",
        handler=_handler_apply_updates,
    ),
]

_TOOL_MAP: dict[str, Tool] = {t.name: t for t in TOOLS}


def get(name: str) -> Tool | None:
    """Look up a tool by name."""
    return _TOOL_MAP.get(name)


def ollama_schemas() -> list[dict]:
    """Return all tools formatted for Ollama's ``tools`` field."""
    return [t.to_ollama() for t in TOOLS]
