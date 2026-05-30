"""Apps screen: list installed apps and uninstall the selected one."""

from __future__ import annotations

import logging

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Static

from ...commands import apps as apps_mod
from ...console import human_size
from ..modals import ConfirmModal
from .base import BaseView

logger = logging.getLogger("sifty.tui")


class AppsView(BaseView):
    def compose(self) -> ComposeResult:
        yield Static("Installed apps", classes="title")
        yield Static("Highlight a row, then Uninstall. Sorted by size.", classes="subtle")
        yield DataTable(id="apps-table")
        with Horizontal(classes="actions"):
            yield Button("Refresh", id="refresh")
            yield Button("Uninstall selected", id="uninstall", variant="warning")
        yield Static("", id="apps-status", classes="status")

    def on_mount(self) -> None:
        self._apps: list = []
        table = self.query_one("#apps-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Name", "Version", "Publisher", "Size")
        if self.workers_enabled():
            self.load()

    @work(thread=True, exclusive=True)
    def load(self) -> None:
        try:
            apps = sorted(apps_mod.installed_apps(), key=lambda a: a.size_bytes, reverse=True)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Apps enumeration failed")
            self.app.call_from_thread(self._status, f"Failed: {exc}")
            return
        self.app.call_from_thread(self._populate, apps)

    def _populate(self, apps) -> None:
        self._apps = apps
        table = self.query_one("#apps-table", DataTable)
        table.clear()
        for a in apps:
            table.add_row(
                a.name,
                a.version or "—",
                a.publisher or "—",
                human_size(a.size_bytes) if a.size_bytes else "—",
            )
        self._status(f"{len(apps)} apps installed")

    def _status(self, msg: str) -> None:
        self.query_one("#apps-status", Static).update(msg)

    def _selected_app(self):
        table = self.query_one("#apps-table", DataTable)
        if table.row_count == 0:
            return None
        idx = table.cursor_row
        if idx is not None and 0 <= idx < len(self._apps):
            return self._apps[idx]
        return None

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh":
            self._status("Refreshing…")
            self.load()
        elif event.button.id == "uninstall":
            app_obj = self._selected_app()
            if not app_obj:
                self._status("No app selected.")
                return
            ok = await self.app.push_screen_wait(
                ConfirmModal(
                    f"Uninstall '{app_obj.name}'?\nThis runs winget and may open the "
                    f"app's own uninstaller.",
                    confirm_label="Uninstall",
                )
            )
            if ok:
                self._status(f"Uninstalling {app_obj.name}…")
                self.do_uninstall(app_obj.name)

    @work(thread=True, exclusive=True)
    def do_uninstall(self, name: str) -> None:
        ok, msg = apps_mod.uninstall_app(name)
        self.app.call_from_thread(self._after_uninstall, ok, msg)

    def _after_uninstall(self, ok: bool, msg: str) -> None:
        self.app.notify(msg, severity="information" if ok else "error", title="Uninstall")
        if ok:
            self.load()
