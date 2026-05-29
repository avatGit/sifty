"""Installed-app and startup-program management.

Reads from the Windows registry (Uninstall + Run keys) and the Startup folder,
and shells out to ``winget`` for clean uninstalls. All write actions (disabling
startup entries, uninstalling) are dry-run by default and confirm first.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import typer
from rich.table import Table

from ..console import confirm, console, error, human_size, success, warn

try:  # Windows-only; tests mock the reader functions.
    import winreg
except ImportError:  # pragma: no cover - non-Windows
    winreg = None  # type: ignore[assignment]

app = typer.Typer(help="List, inspect, and remove installed apps and startup items.")

_UNINSTALL_KEYS = [
    ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ("HKLM", r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    ("HKCU", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
]
_RUN_KEYS = [
    ("HKCU", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
    ("HKLM", r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run"),
]


@dataclass
class InstalledApp:
    name: str
    version: str
    publisher: str
    size_bytes: int
    uninstall_string: str
    source: str


@dataclass
class StartupEntry:
    name: str
    command: str
    location: str  # human-readable origin (registry hive or "Startup folder")


def _hive(name: str):
    return winreg.HKEY_LOCAL_MACHINE if name == "HKLM" else winreg.HKEY_CURRENT_USER


def _read_value(key, name: str, default=""):
    try:
        return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return default


def installed_apps() -> list[InstalledApp]:
    """Enumerate installed apps from the registry Uninstall keys."""
    if winreg is None:  # pragma: no cover - non-Windows
        return []
    apps: dict[str, InstalledApp] = {}
    for hive_name, subpath in _UNINSTALL_KEYS:
        try:
            root = winreg.OpenKey(_hive(hive_name), subpath)
        except OSError:
            continue
        with root:
            count = winreg.QueryInfoKey(root)[0]
            for i in range(count):
                try:
                    sub_name = winreg.EnumKey(root, i)
                    with winreg.OpenKey(root, sub_name) as sub:
                        name = _read_value(sub, "DisplayName")
                        if not name or _read_value(sub, "SystemComponent", 0) == 1:
                            continue
                        size_kb = _read_value(sub, "EstimatedSize", 0) or 0
                        apps[name.lower()] = InstalledApp(
                            name=name,
                            version=str(_read_value(sub, "DisplayVersion")),
                            publisher=str(_read_value(sub, "Publisher")),
                            size_bytes=int(size_kb) * 1024,
                            uninstall_string=str(_read_value(sub, "UninstallString")),
                            source=hive_name,
                        )
                except OSError:
                    continue
    return sorted(apps.values(), key=lambda a: a.name.lower())


def startup_entries() -> list[StartupEntry]:
    """Enumerate auto-start programs from Run keys and the Startup folder."""
    entries: list[StartupEntry] = []
    if winreg is not None:
        for hive_name, subpath in _RUN_KEYS:
            try:
                key = winreg.OpenKey(_hive(hive_name), subpath)
            except OSError:
                continue
            with key:
                count = winreg.QueryInfoKey(key)[1]
                for i in range(count):
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                        entries.append(StartupEntry(name, str(value), f"{hive_name} Run"))
                    except OSError:
                        continue

    appdata = os.environ.get("APPDATA")
    if appdata:
        folder = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        if folder.exists():
            for item in folder.iterdir():
                if item.is_file():
                    entries.append(StartupEntry(item.stem, str(item), "Startup folder"))
    return entries


@app.command("list")
def list_cmd(
    sort_by_size: bool = typer.Option(False, "--by-size", help="Sort by disk size (largest first)."),
    limit: int = typer.Option(0, "--limit", "-n", help="Show only the first N apps (0 = all)."),
) -> None:
    """List installed applications."""
    apps = installed_apps()
    if sort_by_size:
        apps = sorted(apps, key=lambda a: a.size_bytes, reverse=True)
    if limit:
        apps = apps[:limit]

    table = Table(title=f"Installed apps ({len(apps)})")
    table.add_column("Name")
    table.add_column("Version", style="dim")
    table.add_column("Publisher", style="dim")
    table.add_column("Size", justify="right")
    for a in apps:
        table.add_row(a.name, a.version, a.publisher, human_size(a.size_bytes) if a.size_bytes else "—")
    console.print(table)


@app.command("startup")
def startup_cmd() -> None:
    """List programs that launch at startup."""
    entries = startup_entries()
    table = Table(title=f"Startup programs ({len(entries)})")
    table.add_column("Name")
    table.add_column("Origin", style="dim")
    table.add_column("Command")
    for e in entries:
        table.add_row(e.name, e.location, e.command)
    console.print(table)


def _winget_available() -> bool:
    try:
        subprocess.run(["winget", "--version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


@app.command("uninstall")
def uninstall_cmd(
    name: str = typer.Argument(..., help="App name (or winget id) to uninstall."),
    apply: bool = typer.Option(False, "--apply", help="Actually run the uninstaller."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    """Uninstall an app via winget (preferred) with a dry-run preview."""
    if not _winget_available():
        error("winget is not available on this system.")
        raise typer.Exit(1)

    if not apply:
        console.print(f"[dim]Dry-run:[/dim] would run [cyan]winget uninstall --name \"{name}\"[/cyan]")
        console.print("[dim]Re-run with --apply to uninstall.[/dim]")
        return

    if not confirm(f"Uninstall '{name}'?", assume_yes=yes):
        warn("Cancelled.")
        return

    result = subprocess.run(
        ["winget", "uninstall", "--name", name, "--silent",
         "--accept-source-agreements"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        success(f"Uninstalled '{name}'.")
    else:
        error(f"winget failed (exit {result.returncode}): {result.stderr.strip() or result.stdout.strip()}")
        raise typer.Exit(result.returncode)
