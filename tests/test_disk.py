"""Tests for disk analysis: biggest items and duplicate detection."""

from __future__ import annotations

from sifty.commands import disk


def test_biggest_orders_by_size(tmp_path):
    (tmp_path / "small.txt").write_text("a" * 10)
    (tmp_path / "big.txt").write_text("a" * 1000)
    folder = tmp_path / "folder"
    folder.mkdir()
    (folder / "f.bin").write_text("a" * 500)

    result = disk.biggest(tmp_path, top=3)
    names = [p.name for p, _ in result]
    assert names[0] == "big.txt"  # 1000
    assert names[1] == "folder"  # 500
    assert names[2] == "small.txt"  # 10


def test_find_duplicates_groups_identical_content(tmp_path):
    (tmp_path / "x1.txt").write_text("identical content here")
    (tmp_path / "x2.txt").write_text("identical content here")
    (tmp_path / "unique.txt").write_text("totally different content")

    groups = disk.find_duplicates(tmp_path, min_size=1)
    assert len(groups) == 1
    (paths,) = groups.values()
    assert {p.name for p in paths} == {"x1.txt", "x2.txt"}


def test_find_duplicates_respects_min_size(tmp_path):
    (tmp_path / "a.txt").write_text("hi")
    (tmp_path / "b.txt").write_text("hi")
    assert disk.find_duplicates(tmp_path, min_size=100) == {}
