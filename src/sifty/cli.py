"""Sifty command-line entry point."""

from __future__ import annotations

import ctypes

import typer

from . import __version__
from .commands import ai_group, apps, disk, junk, organize, updates
from .console import console

app = typer.Typer(
    name="sifty",
    help="Sifty — AI-assisted Windows maintenance: junk, disk, apps, updates, files.",
    no_args_is_help=True,
    add_completion=False,
)

app.add_typer(junk.app, name="junk")
app.add_typer(disk.app, name="disk")
app.add_typer(apps.app, name="apps")
app.add_typer(updates.app, name="update")
app.add_typer(organize.app, name="organize")
app.add_typer(ai_group.app, name="ai")


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
    except Exception:
        return False


@app.command("version")
def version_cmd() -> None:
    """Show the Sifty version."""
    console.print(f"Sifty {__version__}")


@app.command("doctor")
def doctor_cmd() -> None:
    """Report environment readiness (admin rights, winget, Ollama)."""
    from .commands.updates import _winget_available
    from .ai.client import OllamaClient

    admin = _is_admin()
    console.print(f"Administrator: {'[green]yes[/green]' if admin else '[yellow]no[/yellow] (some junk/uninstall actions need it)'}")
    console.print(f"winget: {'[green]available[/green]' if _winget_available() else '[red]missing[/red]'}")
    client = OllamaClient.from_config()
    console.print(f"Ollama ({client.model}): {'[green]reachable[/green]' if client.is_available() else '[yellow]not running[/yellow]'}")


if __name__ == "__main__":
    app()
