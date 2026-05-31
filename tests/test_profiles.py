"""Tests for cleanup profiles (store + CLI), using a temp APPDATA."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from sifty.cli.app import app
from sifty.core import profiles
from sifty.core.models import Profile

runner = CliRunner()


@pytest.fixture
def temp_appdata(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return tmp_path


def test_profile_crud_round_trip(temp_appdata):
    assert profiles.list_profiles() == []
    profiles.save(Profile("weekly", ["user-temp", "browser-cache"]))
    got = profiles.get("weekly")
    assert got is not None and got.categories == ["user-temp", "browser-cache"]
    assert [p.name for p in profiles.list_profiles()] == ["weekly"]
    assert profiles.remove("weekly") is True
    assert profiles.get("weekly") is None
    assert profiles.remove("weekly") is False  # already gone


def test_profile_add_validates_categories(temp_appdata):
    bad = runner.invoke(app, ["profile", "add", "x", "-c", "not-a-real-category"])
    assert bad.exit_code == 1

    ok = runner.invoke(app, ["profile", "add", "sys", "-c", "windows-temp"])
    assert ok.exit_code == 0
    assert profiles.get("sys").categories == ["windows-temp"]


def test_clean_unknown_profile_errors(temp_appdata):
    result = runner.invoke(app, ["clean", "--profile", "does-not-exist"])
    assert result.exit_code == 1
