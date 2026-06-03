"""Junk scanning and cleanup (engine).

Each junk *category* points at one or more directories whose top-level entries
are safe to send to the Recycle Bin. The directory itself is registered as an
allowed subtree so :func:`sifty.core.safety.trash` permits its contents even when
the directory sits inside a protected root (e.g. ``C:\\Windows\\Temp``).
"""

from __future__ import annotations

import os
from pathlib import Path

from ..infra.config import load_config
from .models import CategoryScan, CleanResult, JunkCategory
from .safety import ProtectedPathError, trash

__all__ = ["JunkCategory", "CategoryScan", "CleanResult", "junk_categories", "scan", "clean"]


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
    extra_protected: list[str] | None = None,
) -> CleanResult:
    """Trash the contents of selected junk categories.

    Returns a :class:`CleanResult`. ``trashed`` holds the original paths sent to
    the Recycle Bin (empty on a dry-run) — used to record an undoable session.
    ``extra_protected`` extends the built-in denylist for this call only.
    """
    config = config or load_config()
    cfg_protected = config.section("safety").get("extra_protected_paths", [])
    extra_protected = list(cfg_protected) + list(extra_protected or [])
    bytes_freed = 0
    items = 0
    skipped: list[str] = []
    trashed: list[Path] = []

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
                        extra_protected=extra_protected,  # merged above
                        dry_run=dry_run,
                    )
                    bytes_freed += size
                    items += 1
                    if not dry_run:
                        trashed.append(entry)
                except ProtectedPathError as exc:
                    skipped.append(str(exc))
                except OSError as exc:
                    skipped.append(f"{entry}: {exc}")

    return CleanResult(bytes_freed, items, skipped, trashed)
