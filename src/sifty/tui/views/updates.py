"""Updates screen: list winget upgrades and apply selected/all."""

from __future__ import annotations

import logging

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Static

from ...commands import updates as updates_mod
from ..modals import ConfirmModal
from .base import BaseView

logger = logging.getLogger("sifty.tui")


class UpdatesView(BaseView):
    def compose(self) -> ComposeResult:
        yield Static("Updates", classes="title")
        yield Static("Available application updates via winget.", classes="subtle")
        yield DataTable(id="updates-table")
        with Horizontal(classes="actions"):
            yield Button("Check", id="check")
            yield Button("Apply selected", id="apply-one", variant="primary")
            yield Button("Apply all", id="apply-all", variant="warning")
        yield Static("", id="updates-status", classes="status")

    def on_mount(self) -> None:
        self._ups: list = []
        table = self.query_one("#updates-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Name", "Id", "Current", "Available")
        if self.workers_enabled():
            self.check()

    @work(thread=True, exclusive=True)
    def check(self) -> None:
        try:
            ups = updates_mod.list_upgrades()
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Update check failed")
            self.app.call_from_thread(self._status, f"Failed: {exc}")
            return
        self.app.call_from_thread(self._populate, ups)

    def _populate(self, ups) -> None:
        self._ups = ups
        table = self.query_one("#updates-table", DataTable)
        table.clear()
        for u in ups:
            table.add_row(u.name, u.id, u.current, u.available)
        self._status(f"{len(ups)} updates available" if ups else "Everything is up to date.")

    def _status(self, msg: str) -> None:
        self.query_one("#updates-status", Static).update(msg)

    def _selected(self):
        table = self.query_one("#updates-table", DataTable)
        if table.row_count == 0:
            return None
        idx = table.cursor_row
        if idx is not None and 0 <= idx < len(self._ups):
            return self._ups[idx]
        return None

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "check":
            self._status("Checking…")
            self.check()
        elif bid == "apply-one":
            u = self._selected()
            if not u:
                self._status("No update selected.")
                return
            ok = await self.app.push_screen_wait(
                ConfirmModal(f"Upgrade {u.name} ({u.current} → {u.available})?",
                             confirm_label="Upgrade")
            )
            if ok:
                self._status(f"Upgrading {u.name}…")
                self.apply(u.id)
        elif bid == "apply-all":
            if not self._ups:
                self._status("Nothing to upgrade.")
                return
            ok = await self.app.push_screen_wait(
                ConfirmModal(f"Upgrade all {len(self._ups)} apps now?",
                             confirm_label="Upgrade all")
            )
            if ok:
                self._status("Upgrading all…")
                self.apply(None)

    @work(thread=True, exclusive=True)
    def apply(self, upgrade_id) -> None:
        code = updates_mod.apply_upgrades(upgrade_id)
        self.app.call_from_thread(self._after_apply, code)

    def _after_apply(self, code: int) -> None:
        self.app.notify(
            "Updates applied." if code == 0 else f"winget exited with code {code}.",
            severity="information" if code == 0 else "error",
            title="Updates",
        )
        self.check()
