"""Tests for git worktree cleanup (git + trash mocked)."""

from __future__ import annotations

from pathlib import Path

from sifty.core import safety, vcs
from sifty.core.vcs import OrphanWorktree


def _orphans(tmp_path: Path, names: list[str]) -> list[OrphanWorktree]:
    out = []
    for name in names:
        wt = tmp_path / name
        wt.mkdir()
        (wt / "f.txt").write_bytes(b"x" * 10)
        out.append(OrphanWorktree(wt, "abc123", "prunable by git"))
    return out


def test_prune_worktrees_trashes_all_orphans(tmp_path, monkeypatch):
    orphans = _orphans(tmp_path, ["wt-a", "wt-b"])
    trashed = []
    monkeypatch.setattr(vcs, "find_orphan_worktrees", lambda root: orphans)
    monkeypatch.setattr(vcs, "_run_git", lambda args, cwd: (True, ""))
    monkeypatch.setattr(safety, "send_to_trash", lambda p: trashed.append(p))
    monkeypatch.setattr(safety, "audit", lambda msg: None)

    result = vcs.prune_worktrees(tmp_path, dry_run=False)
    assert result.items == 2
    assert sorted(p.name for p in trashed) == ["wt-a", "wt-b"]


def test_prune_worktrees_honors_only_selection(tmp_path, monkeypatch):
    """``only`` restricts pruning to the selected worktree paths."""
    orphans = _orphans(tmp_path, ["wt-a", "wt-b"])
    trashed = []
    monkeypatch.setattr(vcs, "find_orphan_worktrees", lambda root: orphans)
    monkeypatch.setattr(vcs, "_run_git", lambda args, cwd: (True, ""))
    monkeypatch.setattr(safety, "send_to_trash", lambda p: trashed.append(p))
    monkeypatch.setattr(safety, "audit", lambda msg: None)

    result = vcs.prune_worktrees(tmp_path, dry_run=False, only=[orphans[0].path])
    assert result.items == 1
    assert [p.name for p in trashed] == ["wt-a"]
    assert orphans[1].path.exists()  # deselected worktree untouched


def test_prune_worktrees_dry_run_touches_nothing(tmp_path, monkeypatch):
    orphans = _orphans(tmp_path, ["wt-a"])
    git_calls = []
    monkeypatch.setattr(vcs, "find_orphan_worktrees", lambda root: orphans)
    monkeypatch.setattr(vcs, "_run_git", lambda args, cwd: (git_calls.append(args), "")[0] or (True, ""))
    monkeypatch.setattr(safety, "send_to_trash", lambda p: (_ for _ in ()).throw(AssertionError("trashed in dry-run")))

    result = vcs.prune_worktrees(tmp_path, dry_run=True)
    assert result.items == 1 and result.trashed == []
    assert orphans[0].path.exists()
    assert git_calls == []  # no `git worktree prune` in dry-run
