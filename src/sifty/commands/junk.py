"""Junk scanning and cleanup.

Each junk *category* points at one or more directories whose top-level entries
are safe to send to the Recycle Bin. The directory itself is registered as an
allowed subtree so :func:`sifty.safety.trash` permits its contents even when
the directory sits inside a protected root (e.g. ``C:\\Windows\\Temp``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import typer
from rich.table import Table

from ..config import load_config
from ..console import confirm, console, human_size, success, warn
from ..safety import ProtectedPathError, trash


@dataclass
class JunkCategory:
    key: str
    label: str
    description: str
    roots: list[Path] = field(default_factory=list)
    requires_admin: bool = False


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value) if value else None


def _local_appdata() -> Path | None:
    return _env_path("LOCALAPPDATA")


def junk_categories(config=None) -> list[JunkCategory]:
    """Build the list of junk categories from the environment + config."""
    config = config or load_config()
    cats: list[JunkCategory] = []

    user_temp = _env_path("TEMP") or _env_path("TMP")
    if user_temp:
        cats.append(
            JunkCategory(
                "user-temp", "User temp files",
                "Per-user temporary files (%TEMP%).", [user_temp],
            )
        )

    win_temp = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "Temp"
    cats.append(
        JunkCategory(
            "windows-temp", "Windows temp files",
            "System-wide temp files (C:\\Windows\\Temp).", [win_temp],
            requires_admin=True,
        )
    )

    local = _local_appdata()
    if local:
        thumb = local / "Microsoft" / "Windows" / "Explorer"
        cats.append(
            JunkCategory(
                "thumbnail-cache", "Thumbnail & icon cache",
                "Explorer thumbnail/icon cache (rebuilt automatically).", [thumb],
            )
        )
        chrome = local / "Google" / "Chrome" / "User Data" / "Default" / "Cache"
        edge = local / "Microsoft" / "Edge" / "User Data" / "Default" / "Cache"
        cats.append(
            JunkCategory(
                "browser-cache", "Browser caches",
                "Chrome/Edge on-disk caches.", [chrome, edge],
            )
        )

    wu = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "SoftwareDistribution" / "Download"
    cats.append(
        JunkCategory(
            "windows-update-cache", "Windows Update cache",
            "Downloaded update packages (re-downloaded if needed).", [wu],
            requires_admin=True,
        )
    )

    if config.section("junk").get("include_downloads_installers"):
        downloads = Path.home() / "Downloads"
        cats.append(
            JunkCategory(
                "downloads-installers", "Leftover installers",
                "Installer files (.exe/.msi) in Downloads.", [downloads],
            )
        )

    return cats


def _dir_size(path: Path) -> tuple[int, int]:
    """Return (total_bytes, file_count) for everything under ``path``."""
    total = 0
    count = 0
    for root, _dirs, files in os.walk(path, onerror=lambda _e: None):
        for name in files:
            fp = Path(root) / name
            try:
                total += fp.stat(follow_symlinks=False).st_size
                count += 1
            except OSError:
                continue
    return total, count


@dataclass
class CategoryScan:
    category: JunkCategory
    size: int
    file_count: int
    existing_roots: list[Path]


def scan(config=None, only: set[str] | None = None) -> list[CategoryScan]:
    """Measure each junk category. ``only`` filters by category key."""
    results: list[CategoryScan] = []
    for cat in junk_categories(config):
        if only and cat.key not in only:
            continue
        total = 0
        files = 0
        present: list[Path] = []
        for root in cat.roots:
            if root.exists():
                present.append(root)
                size, count = _dir_size(root)
                total += size
                files += count
        results.append(CategoryScan(cat, total, files, present))
    return results


def _downloads_installer_filter(path: Path) -> bool:
    return path.suffix.lower() in {".exe", ".msi"}


def clean(
    config=None,
    only: set[str] | None = None,
    *,
    dry_run: bool = True,
) -> tuple[int, int, list[str]]:
    """Trash the contents of selected junk categories.

    Returns ``(bytes_freed, items_removed, skipped_messages)``.
    """
    config = config or load_config()
    extra_protected = config.section("safety").get("extra_protected_paths", [])
    bytes_freed = 0
    items = 0
    skipped: list[str] = []

    for cat_scan in scan(config, only):
        cat = cat_scan.category
        for root in cat_scan.existing_roots:
            try:
                entries = list(root.iterdir())
            except OSError as exc:
                # e.g. C:\Windows\Temp without Administrator rights.
                skipped.append(f"{root}: {exc}")
                continue
            for entry in entries:
                if cat.key == "downloads-installers" and not (
                    entry.is_file() and _downloads_installer_filter(entry)
                ):
                    continue
                try:
                    if entry.is_dir():
                        size, _ = _dir_size(entry)
                    else:
                        size = entry.stat(follow_symlinks=False).st_size
                    trash(
                        entry,
                        allow_subtrees=[root],
                        extra_protected=extra_protected,
                        dry_run=dry_run,
                    )
                    bytes_freed += size
                    items += 1
                except ProtectedPathError as exc:
                    skipped.append(str(exc))
                except OSError as exc:
                    skipped.append(f"{entry}: {exc}")

    return bytes_freed, items, skipped


# --------------------------------------------------------------------------- #
# Typer command group
# --------------------------------------------------------------------------- #

app = typer.Typer(help="Scan and clean junk files (temp, caches, update cache).")


@app.command("scan")
def scan_cmd(
    category: list[str] = typer.Option(None, "--category", "-c", help="Limit to category key(s)."),
) -> None:
    """Show how much junk each category holds, without deleting anything."""
    only = set(category) if category else None
    results = scan(only=only)

    table = Table(title="Junk scan")
    table.add_column("Category")
    table.add_column("Key", style="dim")
    table.add_column("Files", justify="right")
    table.add_column("Size", justify="right")
    total = 0
    for r in results:
        total += r.size
        admin = " [yellow](admin)[/yellow]" if r.category.requires_admin else ""
        table.add_row(r.category.label + admin, r.category.key, f"{r.file_count:,}", human_size(r.size))
    table.add_section()
    table.add_row("[bold]Total reclaimable[/bold]", "", "", f"[bold]{human_size(total)}[/bold]")
    console.print(table)
    console.print("\nRun [cyan]sifty junk clean[/cyan] to preview removal (dry-run by default).")


@app.command("clean")
def clean_cmd(
    category: list[str] = typer.Option(None, "--category", "-c", help="Limit to category key(s)."),
    apply: bool = typer.Option(False, "--apply", help="Actually move items to the Recycle Bin."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    """Move junk to the Recycle Bin. Dry-run unless --apply is given."""
    only = set(category) if category else None

    # Always preview first.
    preview_bytes, preview_items, _ = clean(only=only, dry_run=True)
    if preview_items == 0:
        success("Nothing to clean — you're already tidy.")
        return

    console.print(
        f"Found [bold]{preview_items:,}[/bold] items totalling "
        f"[bold]{human_size(preview_bytes)}[/bold]."
    )
    if not apply:
        console.print("[dim]Dry-run — nothing was deleted. Re-run with --apply to remove.[/dim]")
        return

    if not confirm(f"Move {preview_items:,} items ({human_size(preview_bytes)}) to the Recycle Bin?", assume_yes=yes):
        warn("Cancelled.")
        return

    freed, items, skipped = clean(only=only, dry_run=False)
    success(f"Sent {items:,} items ({human_size(freed)}) to the Recycle Bin.")
    if skipped:
        warn(f"{len(skipped)} item(s) skipped (in use or protected).")
