"""Small JSON persistence for TUI state (recent paths, favorites)."""

from __future__ import annotations

import json

from ..infra.config import app_data_dir

_MAX_RECENTS = 10


def _state_file():
    return app_data_dir() / "ui_state.json"


def _load() -> dict:
    path = _state_file()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
    return {}


def _save(data: dict) -> None:
    try:
        _state_file().write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def recent_paths() -> list[str]:
    data = _load()
    return list(data.get("recent_paths", []))


def add_recent_path(path: str) -> None:
    """Record a path as most-recent (de-duplicated, capped)."""
    data = _load()
    recents = [p for p in data.get("recent_paths", []) if p != path]
    recents.insert(0, path)
    data["recent_paths"] = recents[:_MAX_RECENTS]
    _save(data)
