"""Tests for the optimize engine (subprocess and admin calls mocked)."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from sifty.core import optimize


def test_list_operations_returns_all():
    ops = optimize.list_operations()
    keys = {op.key for op in ops}
    assert {"dns-flush", "thumbnail-cache", "prefetch", "update-cache", "dism-cleanup", "compact-vhd"} == keys


def test_run_op_dry_run_never_calls_subprocess():
    ops = optimize.list_operations()
    for op in ops:
        with patch("subprocess.run") as mock_run:
            ok, msg = optimize.run_op(op, dry_run=True)
            assert ok
            assert "dry-run" in msg
            mock_run.assert_not_called()


def test_dns_flush_calls_ipconfig(monkeypatch):
    monkeypatch.setattr(
        "sifty.core.optimize._run_subprocess",
        lambda cmd, op, **kw: (True, "Successfully flushed") if "ipconfig" in cmd else (False, "wrong cmd"),
    )
    op = next(o for o in optimize.list_operations() if o.key == "dns-flush")
    ok, msg = optimize.run_op(op, dry_run=False)
    assert ok


def test_dism_not_called_directly_via_subprocess_without_admin(monkeypatch):
    called_cmds = []
    def fake_run(cmd, op, **kw):
        called_cmds.append(cmd)
        return True, "ok"
    monkeypatch.setattr("sifty.core.optimize._run_subprocess", fake_run)
    op = next(o for o in optimize.list_operations() if o.key == "dism-cleanup")
    optimize.run_op(op, dry_run=False)
    assert any("DISM" in str(c) for c in called_cmds)


def test_prefetch_requires_admin_flag():
    op = next(o for o in optimize.list_operations() if o.key == "prefetch")
    assert op.requires_admin


def test_dns_flush_does_not_require_admin():
    op = next(o for o in optimize.list_operations() if o.key == "dns-flush")
    assert not op.requires_admin


def test_run_subprocess_handles_missing_command():
    op = optimize.list_operations()[0]
    with patch("subprocess.run", side_effect=FileNotFoundError("not found")):
        ok, msg = optimize._run_subprocess(["nonexistent_cmd"], op)
    assert not ok
    assert "not found" in msg.lower() or "command" in msg.lower()
