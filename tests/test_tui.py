"""Headless smoke tests for the TUI, via Textual's Pilot harness.

`start_workers=False` keeps the slow real-system workers from firing; we then
call each view's `_populate`/render method directly with fake data to verify the
widgets and Textual API usage without touching the OS.
"""

from __future__ import annotations

from pathlib import Path

from textual.widgets import DataTable, Input, SelectionList, Static, Tree

from sifty.core.apps import InstalledApp
from sifty.core.junk import CategoryScan, JunkCategory
from sifty.core.updates import Upgrade
from sifty.tui.app import SECTIONS, SiftyApp
from sifty.tui.commands import SiftyCommands, _entries
from sifty.tui.modals import ConfirmModal
from sifty.tui.views import AppsView, DiskView, HomeView, JunkView, UpdatesView, VIEWS


def _make_app() -> SiftyApp:
    return SiftyApp(start_workers=False)


def test_command_palette_entries_cover_sections_and_admin():
    class _Dummy:
        async def show(self, key):
            ...

        def action_elevate(self):
            ...

    entries = _entries(_Dummy())
    titles = [t for t, _h, _c in entries]
    assert "Go to Home" in titles
    assert "Restart as administrator" in titles
    assert len(entries) == len(SECTIONS) + 1


async def test_command_palette_registered():
    async with _make_app().run_test() as pilot:
        assert SiftyCommands in type(pilot.app).COMMANDS


async def test_app_boots_with_full_sidebar():
    async with _make_app().run_test() as pilot:
        sidebar = pilot.app.query_one("#sidebar")
        assert len(sidebar.children) == len(SECTIONS)


async def test_home_renders_volume_gauges():
    async with _make_app().run_test() as pilot:
        pilot.app.query_one(HomeView)
        body = pilot.app.query_one("#vol-body", Static)
        assert "free" in str(body.render())  # at least one volume rendered


async def test_navigation_mounts_each_view():
    async with _make_app().run_test() as pilot:
        for key, view_cls in VIEWS.items():
            await pilot.app.show(key)
            await pilot.pause()
            assert pilot.app.query_one(view_cls)


async def test_junk_view_populates_selection_list():
    cats = [
        CategoryScan(JunkCategory("user-temp", "User temp", "", []), 600, 3, []),
        CategoryScan(JunkCategory("browser-cache", "Browser cache", "", []), 0, 0, []),
    ]
    async with _make_app().run_test() as pilot:
        await pilot.app.show("junk")
        await pilot.pause()
        view = pilot.app.query_one(JunkView)
        view._populate(cats)
        sl = pilot.app.query_one("#junk-list", SelectionList)
        assert sl.option_count == 2


async def test_apps_view_populates_table():
    apps = [
        InstalledApp("App A", "1.0", "Pub", 1024, "", "HKCU"),
        InstalledApp("App B", "2.0", "Pub", 2048, "", "HKLM"),
    ]
    async with _make_app().run_test() as pilot:
        await pilot.app.show("apps")
        await pilot.pause()
        view = pilot.app.query_one(AppsView)
        view._populate(apps)
        table = pilot.app.query_one("#apps-table", DataTable)
        assert table.row_count == 2
        assert view._selected_app() is not None  # cursor on a row


async def test_apps_filter_narrows_and_marking_selects():
    apps = [
        InstalledApp("Alpha", "1", "Pub", 10, "", "HKCU"),
        InstalledApp("Beta", "1", "Pub", 20, "", "HKCU"),
    ]
    async with _make_app().run_test() as pilot:
        await pilot.app.show("apps")
        await pilot.pause()
        view = pilot.app.query_one(AppsView)
        view._populate(apps)
        await pilot.pause()
        table = pilot.app.query_one("#apps-table", DataTable)
        assert table.row_count == 2

        # Fuzzy filter narrows the table.
        pilot.app.query_one("#apps-filter", Input).value = "alph"
        await pilot.pause()
        assert table.row_count == 1

        # Marking the highlighted row drives the bulk action target.
        view.action_toggle_mark()
        await pilot.pause()
        assert {a.name for a in view._apps_for_action()} == {"Alpha"}


async def test_apps_row_click_toggles_mark():
    apps = [
        InstalledApp("Alpha", "1", "Pub", 10, "", "HKCU"),
        InstalledApp("Beta", "1", "Pub", 20, "", "HKCU"),
    ]
    async with _make_app().run_test() as pilot:
        await pilot.app.show("apps")
        await pilot.pause()
        view = pilot.app.query_one(AppsView)
        view._populate(apps)
        await pilot.pause()
        view._toggle_mark("Alpha")
        view._toggle_mark("Beta")
        view._toggle_mark("Alpha")  # toggling off
        assert {a.name for a in view._apps_for_action()} == {"Beta"}


async def test_disk_view_has_browse_button():
    async with _make_app().run_test() as pilot:
        await pilot.app.show("disk")
        await pilot.pause()
        from textual.widgets import Button
        assert pilot.app.query_one("#browse", Button) is not None


async def test_updates_view_populates_table():
    ups = [Upgrade("Firefox", "Mozilla.Firefox", "120.0", "121.0")]
    async with _make_app().run_test() as pilot:
        await pilot.app.show("updates")
        await pilot.pause()
        view = pilot.app.query_one(UpdatesView)
        view._populate(ups)
        table = pilot.app.query_one("#updates-table", DataTable)
        assert table.row_count == 1


async def test_junk_clean_opens_confirm_in_worker():
    # Regression: push_screen_wait must run in a worker. Before the fix this
    # path raised WorkerError instead of opening the confirm dialog.
    cats = [CategoryScan(JunkCategory("user-temp", "User temp", "", []), 600, 3, [])]
    async with _make_app().run_test() as pilot:
        await pilot.app.show("junk")
        await pilot.pause()
        view = pilot.app.query_one(JunkView)
        view._populate(cats)  # the size>0 category is selected by default
        await pilot.pause()

        view._clean()  # launches the worker that awaits push_screen_wait
        await pilot.pause()
        await pilot.pause()

        assert isinstance(pilot.app.screen, ConfirmModal)  # dialog opened, no crash
        await pilot.press("escape")  # cancel
        await pilot.pause()
        assert not isinstance(pilot.app.screen, ConfirmModal)


async def test_disk_view_shows_biggest_items():
    async with _make_app().run_test() as pilot:
        await pilot.app.show("disk")
        await pilot.pause()
        view = pilot.app.query_one(DiskView)
        view._show_biggest(Path("C:/demo"), [(Path("big.bin"), 5000), (Path("small.txt"), 10)])
        tree = pilot.app.query_one("#biggest-tree", Tree)
        assert len(tree.root.children) == 2
