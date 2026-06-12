"""Tests for the startup manager (registry primitives + folder moves mocked)."""

from __future__ import annotations

from sifty.core import startup
from sifty.windows import registry


class FakeRegistry:
    """In-memory stand-in for the Run-key registry primitives."""

    def __init__(self):
        # {(hive, subkey): {name: value}}
        self.store: dict[tuple[str, str], dict[str, str]] = {}

    def list_run_values(self, hive, subkey=registry.RUN_SUBKEY):
        return list(self.store.get((hive, subkey), {}).items())

    def write_run_value(self, hive, subkey, name, value):
        self.store.setdefault((hive, subkey), {})[name] = value

    def delete_run_value(self, hive, subkey, name):
        self.store.get((hive, subkey), {}).pop(name, None)


def _install_fake(monkeypatch, tmp_path):
    fake = FakeRegistry()
    monkeypatch.setattr(registry, "list_run_values", fake.list_run_values)
    monkeypatch.setattr(registry, "write_run_value", fake.write_run_value)
    monkeypatch.setattr(registry, "delete_run_value", fake.delete_run_value)
    # Keep folder scanning out of the way (no real Startup folder in tests).
    monkeypatch.setattr(startup, "_startup_folder", lambda: None)
    monkeypatch.setenv("APPDATA", str(tmp_path))  # _disabled_folder under tmp
    return fake


def test_list_entries_marks_enabled(monkeypatch, tmp_path):
    fake = _install_fake(monkeypatch, tmp_path)
    fake.store[("HKCU", registry.RUN_SUBKEY)] = {"Spotify": "C:\\spotify.exe"}
    entries = [e for e in startup.list_entries() if e.kind == "hkcu-run"]
    assert len(entries) == 1
    assert entries[0].name == "Spotify" and entries[0].enabled is True


def test_disable_then_enable_round_trip(monkeypatch, tmp_path):
    fake = _install_fake(monkeypatch, tmp_path)
    fake.store[("HKCU", registry.RUN_SUBKEY)] = {"Spotify": "C:\\spotify.exe"}

    entry = next(e for e in startup.list_entries() if e.name == "Spotify")
    assert startup.disable(entry) is True
    # Now it's gone from Run and present (disabled) in the backup.
    names = {(e.name, e.enabled) for e in startup.list_entries()}
    assert ("Spotify", False) in names
    assert ("Spotify", True) not in names

    disabled = next(e for e in startup.list_entries() if e.name == "Spotify")
    assert startup.enable(disabled) is True
    names = {(e.name, e.enabled) for e in startup.list_entries()}
    assert ("Spotify", True) in names
    assert ("Spotify", False) not in names


def test_set_enabled_by_name(monkeypatch, tmp_path):
    fake = _install_fake(monkeypatch, tmp_path)
    fake.store[("HKCU", registry.RUN_SUBKEY)] = {"Teams": "C:\\teams.exe"}
    assert startup.set_enabled("Teams", False) is True
    assert startup.set_enabled("Teams", False) is False  # already disabled → no-op
    assert startup.set_enabled("Teams", True) is True
