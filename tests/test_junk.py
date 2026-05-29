"""Tests for junk scanning and cleaning against a sandbox temp dir."""

from __future__ import annotations

from pathlib import Path

import pytest

from sifty import safety
from sifty.commands import junk
from sifty.config import Config


@pytest.fixture
def sandbox_temp(monkeypatch, tmp_path):
    """Point %TEMP% at a sandbox and populate it with junk."""
    temp = tmp_path / "temp"
    temp.mkdir()
    (temp / "a.tmp").write_text("x" * 100)
    (temp / "b.log").write_text("y" * 200)
    sub = temp / "cache"
    sub.mkdir()
    (sub / "c.dat").write_text("z" * 300)

    monkeypatch.setenv("TEMP", str(temp))
    monkeypatch.setenv("TMP", str(temp))
    # Keep other categories out of the way by pointing them at empty dirs.
    monkeypatch.setenv("SystemRoot", str(tmp_path / "win"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    return temp


def test_scan_reports_user_temp_size(sandbox_temp):
    results = junk.scan(only={"user-temp"})
    user_temp = next(r for r in results if r.category.key == "user-temp")
    assert user_temp.size == 600  # 100 + 200 + 300
    assert user_temp.file_count == 3


def test_clean_dry_run_does_not_delete(monkeypatch, sandbox_temp):
    monkeypatch.setattr(safety, "send2trash", lambda p: pytest.fail("must not delete in dry-run"))
    freed, items, skipped = junk.clean(only={"user-temp"}, dry_run=True)
    assert freed == 600
    assert items == 3  # three top-level entries: a.tmp, b.log, cache/
    assert sandbox_temp.exists()


def test_clean_apply_trashes_entries(monkeypatch, sandbox_temp):
    trashed = []
    monkeypatch.setattr(safety, "send2trash", lambda p: trashed.append(p))
    monkeypatch.setattr(safety, "audit", lambda msg: None)
    freed, items, skipped = junk.clean(only={"user-temp"}, dry_run=False)
    assert items == 3
    assert len(trashed) == 3
    assert not skipped


def test_downloads_installers_gated_by_config(monkeypatch, tmp_path):
    cfg_off = Config()
    keys_off = {c.key for c in junk.junk_categories(cfg_off)}
    assert "downloads-installers" not in keys_off

    cfg_on = Config(data={**Config().data})
    cfg_on.data["junk"] = {"include_downloads_installers": True}
    keys_on = {c.key for c in junk.junk_categories(cfg_on)}
    assert "downloads-installers" in keys_on
