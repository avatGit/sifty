"""Disk and volume analysis: usage per volume, biggest items, duplicates."""

from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import psutil
import typer
from rich.table import Table
from rich.tree import Tree

from ..console import console, human_size, warn

app = typer.Typer(help="Analyze disks: volume usage, biggest items, duplicates.")


@dataclass
class VolumeUsage:
    device: str
    mountpoint: str
    fstype: str
    total: int
    used: int
    free: int

    @property
    def percent(self) -> float:
        return (self.used / self.total * 100) if self.total else 0.0


def volumes() -> list[VolumeUsage]:
    """Return usage for every fixed volume."""
    results: list[VolumeUsage] = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        results.append(
            VolumeUsage(part.device, part.mountpoint, part.fstype, usage.total, usage.used, usage.free)
        )
    return results


@app.command("volumes")
def volumes_cmd() -> None:
    """Show used/free/total for each volume."""
    table = Table(title="Volumes")
    table.add_column("Drive")
    table.add_column("FS", style="dim")
    table.add_column("Used", justify="right")
    table.add_column("Free", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("Used %", justify="right")
    for v in volumes():
        color = "red" if v.percent >= 90 else "yellow" if v.percent >= 75 else "green"
        table.add_row(
            v.mountpoint, v.fstype, human_size(v.used), human_size(v.free),
            human_size(v.total), f"[{color}]{v.percent:.0f}%[/{color}]",
        )
    console.print(table)


def _entry_size(path: Path) -> int:
    if path.is_file():
        try:
            return path.stat(follow_symlinks=False).st_size
        except OSError:
            return 0
    total = 0
    for root, _dirs, files in os.walk(path, onerror=lambda _e: None):
        for name in files:
            try:
                total += (Path(root) / name).stat(follow_symlinks=False).st_size
            except OSError:
                continue
    return total


def biggest(path: Path, top: int = 15) -> list[tuple[Path, int]]:
    """Return the largest immediate children of ``path`` by total size."""
    items: list[tuple[Path, int]] = []
    try:
        for entry in path.iterdir():
            items.append((entry, _entry_size(entry)))
    except OSError as exc:
        warn(f"Cannot read {path}: {exc}")
        return []
    items.sort(key=lambda t: t[1], reverse=True)
    return items[:top]


@app.command("analyze")
def analyze_cmd(
    path: Path = typer.Argument(Path.home(), help="Directory to analyze."),
    top: int = typer.Option(15, "--top", "-n", help="How many of the biggest items to show."),
) -> None:
    """Show the biggest folders/files directly under a path."""
    path = path.expanduser()
    if not path.exists():
        warn(f"Path does not exist: {path}")
        raise typer.Exit(1)

    with console.status(f"Scanning {path}…"):
        items = biggest(path, top)

    tree = Tree(f"[bold]{path}[/bold]")
    for entry, size in items:
        icon = "📁" if entry.is_dir() else "📄"
        tree.add(f"{icon} {entry.name}  [cyan]{human_size(size)}[/cyan]")
    console.print(tree)


def find_duplicates(path: Path, min_size: int = 1) -> dict[str, list[Path]]:
    """Find duplicate files under ``path`` by size, then content hash."""
    by_size: dict[int, list[Path]] = defaultdict(list)
    for root, _dirs, files in os.walk(path, onerror=lambda _e: None):
        for name in files:
            fp = Path(root) / name
            try:
                size = fp.stat(follow_symlinks=False).st_size
            except OSError:
                continue
            if size >= min_size:
                by_size[size].append(fp)

    dupes: dict[str, list[Path]] = defaultdict(list)
    for size, paths in by_size.items():
        if len(paths) < 2:
            continue  # unique size → cannot be a duplicate
        for fp in paths:
            digest = _hash_file(fp)
            if digest:
                dupes[digest].append(fp)
    return {d: ps for d, ps in dupes.items() if len(ps) > 1}


def _hash_file(path: Path, chunk: int = 1 << 20) -> str | None:
    h = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            while block := fh.read(chunk):
                h.update(block)
    except OSError:
        return None
    return h.hexdigest()


@app.command("duplicates")
def duplicates_cmd(
    path: Path = typer.Argument(..., help="Directory to scan for duplicates."),
    min_size: int = typer.Option(1024, "--min-size", help="Ignore files smaller than this (bytes)."),
) -> None:
    """Find duplicate files and report how much space they waste."""
    path = path.expanduser()
    if not path.exists():
        warn(f"Path does not exist: {path}")
        raise typer.Exit(1)

    with console.status(f"Hashing files under {path}…"):
        groups = find_duplicates(path, min_size)

    if not groups:
        console.print("No duplicates found.")
        return

    reclaimable = 0
    table = Table(title="Duplicate files")
    table.add_column("Copies", justify="right")
    table.add_column("Each", justify="right")
    table.add_column("Wasted", justify="right")
    table.add_column("Example path")
    for paths in sorted(groups.values(), key=lambda ps: _entry_size(ps[0]) * (len(ps) - 1), reverse=True):
        each = _entry_size(paths[0])
        wasted = each * (len(paths) - 1)
        reclaimable += wasted
        table.add_row(str(len(paths)), human_size(each), human_size(wasted), str(paths[0]))
    console.print(table)
    console.print(f"\n[bold]Reclaimable by de-duplicating: {human_size(reclaimable)}[/bold]")
