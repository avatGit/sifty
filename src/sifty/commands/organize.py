"""File organization: sort a directory's files into subfolders by type or date.

Moves are reversible (files go into subfolders, not the Recycle Bin), but the
command is still dry-run by default and previews every move before acting.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import typer
from rich.table import Table

from ..console import confirm, console, success, warn

app = typer.Typer(help="Organize files in a folder by type or date.")

# Extension → destination subfolder.
TYPE_FOLDERS: dict[str, str] = {}
for folder, exts in {
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".svg", ".tiff"],
    "Documents": [".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".xls", ".xlsx", ".ppt", ".pptx", ".csv", ".md"],
    "Videos": [".mp4", ".mkv", ".mov", ".avi", ".wmv", ".flv", ".webm"],
    "Audio": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"],
    "Archives": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"],
    "Installers": [".exe", ".msi", ".msix", ".appx"],
    "Code": [".py", ".js", ".ts", ".java", ".c", ".cpp", ".cs", ".go", ".rs", ".rb", ".sh", ".json", ".xml", ".html", ".css"],
}.items():
    for _ext in exts:
        TYPE_FOLDERS[_ext] = folder


@dataclass
class Move:
    src: Path
    dest: Path


def _dest_folder_by_type(file: Path) -> str:
    return TYPE_FOLDERS.get(file.suffix.lower(), "Other")


def _dest_folder_by_date(file: Path) -> str:
    try:
        mtime = file.stat().st_mtime
    except OSError:
        return "Unknown-date"
    return datetime.fromtimestamp(mtime).strftime("%Y-%m")


def plan_organization(path: Path, scheme: str = "type") -> list[Move]:
    """Build the list of (src → dest) moves for top-level files in ``path``."""
    chooser = _dest_folder_by_date if scheme == "date" else _dest_folder_by_type
    moves: list[Move] = []
    for entry in path.iterdir():
        if not entry.is_file():
            continue  # only loose files at the top level are organized
        folder = chooser(entry)
        dest_dir = path / folder
        if entry.parent == dest_dir:
            continue  # already in place
        moves.append(Move(entry, dest_dir / entry.name))
    return moves


def _unique_dest(dest: Path) -> Path:
    """Avoid clobbering an existing file by suffixing ``(n)``."""
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    n = 1
    while True:
        candidate = dest.with_name(f"{stem} ({n}){suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def apply_moves(moves: list[Move]) -> int:
    """Execute the planned moves, creating destination folders as needed."""
    done = 0
    for move in moves:
        move.dest.parent.mkdir(parents=True, exist_ok=True)
        final = _unique_dest(move.dest)
        shutil.move(str(move.src), str(final))
        done += 1
    return done


@app.command("preview")
def preview_cmd(
    path: Path = typer.Argument(..., help="Folder to organize."),
    scheme: str = typer.Option("type", "--by", help="'type' or 'date'."),
) -> None:
    """Preview how files would be reorganized (no changes made)."""
    _run(path, scheme, apply=False, yes=False)


@app.command("apply")
def apply_cmd(
    path: Path = typer.Argument(..., help="Folder to organize."),
    scheme: str = typer.Option("type", "--by", help="'type' or 'date'."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    """Reorganize files into subfolders by type or date."""
    _run(path, scheme, apply=True, yes=yes)


def _run(path: Path, scheme: str, *, apply: bool, yes: bool) -> None:
    path = path.expanduser()
    if not path.is_dir():
        warn(f"Not a directory: {path}")
        raise typer.Exit(1)
    if scheme not in {"type", "date"}:
        warn("--by must be 'type' or 'date'.")
        raise typer.Exit(1)

    moves = plan_organization(path, scheme)
    if not moves:
        success("Nothing to organize — all files are already sorted.")
        return

    table = Table(title=f"Organize '{path}' by {scheme} ({len(moves)} files)")
    table.add_column("File")
    table.add_column("→ Folder", style="cyan")
    for m in moves[:50]:
        table.add_row(m.src.name, m.dest.parent.name)
    console.print(table)
    if len(moves) > 50:
        console.print(f"[dim]…and {len(moves) - 50} more.[/dim]")

    if not apply:
        console.print("[dim]Dry-run — nothing moved. Re-run with 'organize apply' to perform.[/dim]")
        return

    if not confirm(f"Move {len(moves)} files into subfolders?", assume_yes=yes):
        warn("Cancelled.")
        return

    done = apply_moves(moves)
    success(f"Organized {done} files.")
