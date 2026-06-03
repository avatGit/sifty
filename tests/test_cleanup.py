"""Tests for the smart-cleanup engine (sandboxed; trash mocked)."""

from __future__ import annotations

import time
from pathlib import Path

from sifty.core import cleanup, disk, safety


def test_find_large_files_filters_and_sorts(tmp_path):
    (tmp_path / "big.bin").write_bytes(b"x" * 5000)
    (tmp_path / "small.bin").write_bytes(b"x" * 10)
    # recent_days=0 disables the recency filter so just-created test files appear.
    result = cleanup.find_large_files(tmp_path, min_size=1000, top=10, recent_days=0)
    assert [p.name for p, _s in result] == ["big.bin"]


def test_find_large_files_recent_filter(tmp_path):
    """Files modified within recent_days are excluded from suggestions."""
    (tmp_path / "new.bin").write_bytes(b"x" * 5000)
    result = cleanup.find_large_files(tmp_path, min_size=1000, top=10, recent_days=7)
    assert result == []  # recently created file is protected


def test_choose_duplicate_deletions_keeps_one_per_group(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "longer_name.txt"
    a.write_text("same content")
    b.write_text("same content")
    groups = disk.find_duplicates(tmp_path, min_size=1)
    # recent_days=0 disables recency filter; files created now would otherwise be skipped.
    to_delete = cleanup.choose_duplicate_deletions(groups, recent_days=0)
    # Exactly one copy deleted, and it's the longer path (a.txt is kept).
    assert len(to_delete) == 1
    assert to_delete[0].name == "longer_name.txt"


def test_choose_duplicate_deletions_recent_filter(tmp_path):
    """Files modified within recent_days are not suggested for deletion."""
    a = tmp_path / "a.txt"
    b = tmp_path / "longer_name.txt"
    a.write_text("same content")
    b.write_text("same content")
    groups = disk.find_duplicates(tmp_path, min_size=1)
    to_delete = cleanup.choose_duplicate_deletions(groups, recent_days=7)
    assert to_delete == []  # recently created files are protected


def test_find_stale_downloads(tmp_path):
    fresh = tmp_path / "fresh.txt"
    old = tmp_path / "old.zip"
    fresh.write_text("new")
    old.write_bytes(b"x" * 100)
    old_time = time.time() - 365 * 86400
    import os
    os.utime(old, (old_time, old_time))
    stale = cleanup.find_stale_downloads(days=180, downloads=tmp_path)
    assert [p.name for p, _s, _m in stale] == ["old.zip"]


def test_trash_paths_dry_run_and_apply(tmp_path, monkeypatch):
    trashed = []
    monkeypatch.setattr(safety, "send_to_trash", lambda p: trashed.append(p))
    monkeypatch.setattr(safety, "audit", lambda msg: None)
    f1 = tmp_path / "scratch" / "x.bin"
    f1.parent.mkdir()
    f1.write_bytes(b"x" * 50)

    dry = cleanup.trash_paths([f1], dry_run=True)
    assert dry.bytes_freed == 50 and dry.items == 1 and dry.trashed == []
    assert trashed == []  # dry-run trashes nothing

    applied = cleanup.trash_paths([f1], dry_run=False)
    assert applied.items == 1 and applied.trashed == [f1]
    assert trashed == [f1]
