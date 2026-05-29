"""Shared Rich console and small formatting/prompt helpers."""

from __future__ import annotations

import sys

import typer
from rich.console import Console

# Windows consoles often default to a legacy code page (cp1252) that can't
# encode glyphs like → or ✓. Force UTF-8 with a replace fallback so output can
# never crash on encoding, regardless of where it's piped.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

console = Console()
err_console = Console(stderr=True)


def human_size(num_bytes: float) -> str:
    """Format a byte count as a human-readable string (e.g. ``1.5 GB``)."""
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(value) < 1024.0:
            return f"{value:,.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024.0
    return f"{value:,.1f} EB"


def confirm(message: str, *, assume_yes: bool = False) -> bool:
    """Ask the user to confirm an action unless ``assume_yes`` is set."""
    if assume_yes:
        return True
    return typer.confirm(message)


def warn(message: str) -> None:
    err_console.print(f"[yellow]![/yellow] {message}")


def error(message: str) -> None:
    err_console.print(f"[red]✗[/red] {message}")


def success(message: str) -> None:
    console.print(f"[green]✓[/green] {message}")
