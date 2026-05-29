"""Application updates via winget.

winget has no stable machine-readable output, so we parse its fixed-column
table. The parser is isolated and unit-tested so the fragile bit is covered.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

import typer
from rich.table import Table

from ..console import confirm, console, error, success, warn

app = typer.Typer(help="Check and apply application updates (winget).")


@dataclass
class Upgrade:
    name: str
    id: str
    current: str
    available: str


def _winget_available() -> bool:
    try:
        subprocess.run(["winget", "--version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def parse_upgrade_table(output: str) -> list[Upgrade]:
    """Parse the column layout of ``winget upgrade`` into structured rows.

    winget aligns columns by character offset under a ``Name  Id  Version
    Available  Source`` header, with a dashed separator line beneath it.
    """
    lines = output.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        if "Name" in line and "Id" in line and "Available" in line:
            header_idx = i
            break
    if header_idx is None:
        return []

    header = lines[header_idx]
    # Column start offsets from the header labels.
    cols = {
        "name": header.index("Name"),
        "id": header.index("Id"),
        "version": header.index("Version"),
        "available": header.index("Available"),
    }
    # "Source" may or may not be present; bound "available" by it if so.
    src = header.find("Source")
    avail_end = src if src != -1 else len(header) + 200

    def slice_at(line: str, start: int, end: int) -> str:
        return line[start:end].strip()

    upgrades: list[Upgrade] = []
    for line in lines[header_idx + 1:]:
        if not line.strip() or set(line.strip()) <= {"-"}:
            continue
        if len(line) <= cols["id"]:
            continue
        name = slice_at(line, cols["name"], cols["id"])
        ident = slice_at(line, cols["id"], cols["version"])
        current = slice_at(line, cols["version"], cols["available"])
        available = slice_at(line, cols["available"], avail_end)
        if name and ident:
            upgrades.append(Upgrade(name, ident, current, available))
    return upgrades


def list_upgrades() -> list[Upgrade]:
    result = subprocess.run(
        ["winget", "upgrade", "--include-unknown",
         "--accept-source-agreements"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return parse_upgrade_table(result.stdout)


@app.command("check")
def check_cmd() -> None:
    """List applications that have updates available."""
    if not _winget_available():
        error("winget is not available on this system.")
        raise typer.Exit(1)

    with console.status("Checking for updates…"):
        upgrades = list_upgrades()

    if not upgrades:
        success("Everything is up to date.")
        return

    table = Table(title=f"Available updates ({len(upgrades)})")
    table.add_column("Name")
    table.add_column("Id", style="dim")
    table.add_column("Current", justify="right")
    table.add_column("Available", justify="right", style="green")
    for u in upgrades:
        table.add_row(u.name, u.id, u.current, u.available)
    console.print(table)
    console.print("\nRun [cyan]sifty update apply[/cyan] to install (use --id for a single app).")


@app.command("apply")
def apply_cmd(
    id: str = typer.Option(None, "--id", help="Upgrade only this winget id (default: all)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    """Apply updates via winget."""
    if not _winget_available():
        error("winget is not available on this system.")
        raise typer.Exit(1)

    target = id or "all"
    if not confirm(f"Upgrade {target} now?", assume_yes=yes):
        warn("Cancelled.")
        return

    cmd = ["winget", "upgrade", "--silent",
           "--accept-source-agreements", "--accept-package-agreements"]
    cmd += ["--id", id] if id else ["--all"]

    console.print("[dim]Running winget…[/dim]")
    result = subprocess.run(cmd)
    if result.returncode == 0:
        success("Updates applied.")
    else:
        error(f"winget exited with code {result.returncode}.")
        raise typer.Exit(result.returncode)
