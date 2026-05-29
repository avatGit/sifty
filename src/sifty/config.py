"""Configuration loading and the per-user app data directory.

Config lives at ``%APPDATA%\\sifty\\config.toml``. Anything not set there
falls back to :data:`DEFAULTS`. The config holds the AI model name, optional
extra protected paths, and feature preferences — never anything secret.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

APP_NAME = "sifty"

DEFAULTS: dict[str, Any] = {
    "ai": {
        # Ollama HTTP endpoint and the local model to use.
        "host": "http://localhost:11434",
        "model": "qwen2.5:3b",
        "timeout_seconds": 60,
    },
    "safety": {
        # User-supplied extra paths that must never be touched, on top of the
        # built-in system denylist in safety.py.
        "extra_protected_paths": [],
    },
    "junk": {
        # Whether to offer leftover installers in Downloads as junk (off by
        # default — those are often wanted).
        "include_downloads_installers": False,
    },
}


def app_data_dir() -> Path:
    """Return (and create) the per-user app data directory."""
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return app_data_dir() / "config.toml"


def audit_log_path() -> Path:
    return app_data_dir() / "audit.log"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``override`` onto a copy of ``base``."""
    result = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


@dataclass
class Config:
    data: dict[str, Any] = field(default_factory=lambda: _deep_merge(DEFAULTS, {}))

    def section(self, name: str) -> dict[str, Any]:
        return self.data.get(name, {})


def load_config(path: Path | None = None) -> Config:
    """Load config from disk, merged over defaults. Missing file → defaults."""
    target = path or config_path()
    if target.exists():
        with target.open("rb") as fh:
            user_data = tomllib.load(fh)
        return Config(data=_deep_merge(DEFAULTS, user_data))
    return Config()
