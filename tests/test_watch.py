"""Tests for the low-disk watch (disk + toast mocked)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from sifty.cli.app import app
from sifty.core import disk, watch
from sifty.core.models import VolumeUsage
from sifty.windows import notify

runner = CliRunner()
_GB = 1024 ** 3


@pytest.fixture
def temp_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return tmp_path


def test_threshold_default_and_override(temp_appdata):
    assert watch.threshold_gb() == 5
    assert watch.threshold_gb(20) == 20


def test_low_space_filters(monkeypatch):
    vols = [
        VolumeUsage("C", "C:\\", "NTFS", 100 * _GB, 98 * _GB, 2 * _GB),  # 2 GB free
        VolumeUsage("E", "E:\\", "NTFS", 100 * _GB, 50 * _GB, 50 * _GB),  # 50 GB free
    ]
    monkeypatch.setattr(disk, "volumes", lambda: vols)
    low = watch.low_space(5)
    assert [v.mountpoint for v in low] == ["C:\\"]


def test_watch_check_toasts_when_low(temp_appdata, monkeypatch):
    monkeypatch.setattr(
        watch, "low_space",
        lambda override=None: [VolumeUsage("C", "C:\\", "NTFS", 100 * _GB, 98 * _GB, 2 * _GB)],
    )
    sent = {}
    monkeypatch.setattr(notify, "toast", lambda title, msg, **k: sent.update(title=title) or True)
    result = runner.invoke(app, ["watch", "check", "--threshold", "5"])
    assert result.exit_code == 0
    assert sent.get("title") == "Low disk space"


def test_watch_check_quiet_when_ok(temp_appdata, monkeypatch):
    monkeypatch.setattr(watch, "low_space", lambda override=None: [])
    sent = []
    monkeypatch.setattr(notify, "toast", lambda *a, **k: sent.append(1) or True)
    result = runner.invoke(app, ["watch", "check"])
    assert result.exit_code == 0
    assert sent == []  # no toast when nothing is low
