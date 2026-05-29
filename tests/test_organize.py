"""Tests for file organization planning and applying moves."""

from __future__ import annotations

from sifty.commands import organize


def test_plan_by_type_routes_extensions(tmp_path):
    (tmp_path / "photo.jpg").write_text("x")
    (tmp_path / "notes.pdf").write_text("x")
    (tmp_path / "weird.xyz").write_text("x")

    moves = organize.plan_organization(tmp_path, "type")
    dest = {m.src.name: m.dest.parent.name for m in moves}
    assert dest["photo.jpg"] == "Images"
    assert dest["notes.pdf"] == "Documents"
    assert dest["weird.xyz"] == "Other"


def test_plan_skips_directories(tmp_path):
    (tmp_path / "file.txt").write_text("x")
    (tmp_path / "subdir").mkdir()
    moves = organize.plan_organization(tmp_path, "type")
    assert [m.src.name for m in moves] == ["file.txt"]


def test_apply_moves_creates_folders_and_moves(tmp_path):
    (tmp_path / "a.png").write_text("x")
    moves = organize.plan_organization(tmp_path, "type")
    organize.apply_moves(moves)
    assert (tmp_path / "Images" / "a.png").exists()
    assert not (tmp_path / "a.png").exists()


def test_apply_moves_avoids_clobber(tmp_path):
    (tmp_path / "a.png").write_text("first")
    (tmp_path / "Images").mkdir()
    (tmp_path / "Images" / "a.png").write_text("existing")

    moves = organize.plan_organization(tmp_path, "type")
    organize.apply_moves(moves)
    assert (tmp_path / "Images" / "a.png").read_text() == "existing"
    assert (tmp_path / "Images" / "a (1).png").read_text() == "first"
