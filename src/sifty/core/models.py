"""Shared domain dataclasses.

Centralised so the engine, CLI, TUI, and AI agent all speak the same types. Each
core module re-exports the ones it owns for ergonomic imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class JunkCategory:
    key: str
    label: str
    description: str
    roots: list[Path] = field(default_factory=list)
    requires_admin: bool = False


@dataclass
class CategoryScan:
    category: JunkCategory
    size: int
    file_count: int
    existing_roots: list[Path]


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
    location: str          # human-readable origin (registry hive or "Startup folder")
    enabled: bool = True
    kind: str = "run"      # "hkcu-run" | "hklm-run" | "folder"


@dataclass
class Upgrade:
    name: str
    id: str
    current: str
    available: str


@dataclass
class Move:
    src: Path
    dest: Path


@dataclass
class CleanResult:
    bytes_freed: int
    items: int
    skipped: list[str]
    trashed: list[Path]  # original paths sent to the Recycle Bin (apply only)


@dataclass
class Profile:
    name: str
    categories: list[str]  # junk category keys this profile cleans


@dataclass
class ServiceInfo:
    name: str
    label: str
    description: str
    start_type: str   # "auto" | "manual" | "disabled" | "absent"
    present: bool


@dataclass
class Run:
    id: int
    ts: str           # ISO timestamp (UTC)
    action: str       # e.g. "junk"
    detail: str       # e.g. category keys
    bytes_freed: int
    items: int
    success: bool
    restorable: int   # count of trashed items not yet restored
