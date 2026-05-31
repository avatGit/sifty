"""Cleanup profiles: named presets of junk categories, stored as JSON.

A profile is just a name + a list of junk category keys, so it can be cleaned in
one step (``sifty clean --profile X``) or on a schedule. Lives at
``%APPDATA%\\sifty\\profiles.json``.
"""

from __future__ import annotations

import json

from ..infra.config import app_data_dir
from .models import Profile

__all__ = ["list_profiles", "get", "save", "remove"]


def _file():
    return app_data_dir() / "profiles.json"


def _load_raw() -> dict:
    path = _file()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
    return {}


def _write_raw(data: dict) -> None:
    try:
        _file().write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def list_profiles() -> list[Profile]:
    data = _load_raw()
    return [
        Profile(name, list(spec.get("categories", [])))
        for name, spec in sorted(data.items())
    ]


def get(name: str) -> Profile | None:
    spec = _load_raw().get(name)
    if spec is None:
        return None
    return Profile(name, list(spec.get("categories", [])))


def save(profile: Profile) -> None:
    data = _load_raw()
    data[profile.name] = {"categories": list(profile.categories)}
    _write_raw(data)


def remove(name: str) -> bool:
    data = _load_raw()
    if name not in data:
        return False
    del data[name]
    _write_raw(data)
    return True
