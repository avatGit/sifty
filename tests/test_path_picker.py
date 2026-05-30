"""Tests for the path-picker modal and the recents store."""

from __future__ import annotations

from pathlib import Path

from textual.widgets import Input

from sifty.tui import state
from sifty.tui.app import SiftyApp
from sifty.tui.screens.path_picker import PathPicker


def test_recent_paths_dedup_and_cap(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    for i in range(12):
        state.add_recent_path(f"C:/dir{i}")
    state.add_recent_path("C:/dir0")  # re-adding moves it to front, no dupe
    recents = state.recent_paths()
    assert recents[0] == "C:/dir0"
    assert len(recents) == 10  # capped
    assert recents.count("C:/dir0") == 1


async def test_path_picker_ok_returns_typed_path(tmp_path):
    result = {}
    async with SiftyApp(start_workers=False).run_test(size=(120, 40)) as pilot:
        async def grab():
            result["path"] = await pilot.app.push_screen_wait(PathPicker(tmp_path, []))

        pilot.app.run_worker(grab())
        await pilot.pause()
        assert isinstance(pilot.app.screen, PathPicker)

        pilot.app.screen.query_one("#picker-path", Input).value = str(tmp_path / "sub")
        await pilot.pause()
        await pilot.click("#ok")
        await pilot.pause()

    assert result["path"] == (tmp_path / "sub")


async def test_path_picker_cancel_returns_none(tmp_path):
    result = {}
    async with SiftyApp(start_workers=False).run_test() as pilot:
        async def grab():
            result["path"] = await pilot.app.push_screen_wait(PathPicker(tmp_path, []))

        pilot.app.run_worker(grab())
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

    assert result["path"] is None
