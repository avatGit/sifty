"""Startup screen: list startup programs; click a row to enable/disable it."""

from __future__ import annotations

import logging

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Static

from ...core import startup
from .base import BaseView

logger = logging.getLogger("sifty.tui")


class StartupView(BaseView):
    def compose(self) -> ComposeResult:
        yield Static("Startup programs", classes="title")
        yield Static(
            "Click a row to enable/disable it (reversible). HKLM entries need "
            "administrator rights — press F2 to elevate.",
            classes="subtle",
        )
        yield DataTable(id="startup-table")
        with Horizontal(classes="actions"):
            yield Button("Refresh", id="refresh")
        yield Static("", id="startup-status", classes="status")

    def on_mount(self) -> None:
        self._entries: list = []
        table = self.query_one("#startup-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Name", "State", "Origin", "Command")
        if self.workers_enabled():
            self.load()

    @work(thread=True, exclusive=True)
    def load(self) -> None:
        try:
            entries = startup.list_entries()
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Startup enumeration failed")
            self.app.call_from_thread(self._status, f"Failed: {exc}")
            return
        self.app.call_from_thread(self._populate, entries)

    def _populate(self, entries) -> None:
        self._entries = entries
        table = self.query_one("#startup-table", DataTable)
        table.clear()
        for i, e in enumerate(entries):
            state = "[green]enabled[/green]" if e.enabled else "[yellow]disabled[/yellow]"
            table.add_row(e.name, state, e.location, e.command, key=str(i))
        enabled = sum(1 for e in entries if e.enabled)
        self._status(f"{len(entries)} entries · {enabled} enabled")

    def _status(self, msg: str) -> None:
        self.query_one("#startup-status", Static).update(msg)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh":
            self.load()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key is None or event.row_key.value is None:
            return
        idx = int(event.row_key.value)
        if 0 <= idx < len(self._entries):
            self.toggle(idx)

    @work(thread=True, exclusive=True)
    def toggle(self, idx: int) -> None:
        entry = self._entries[idx]
        want_enabled = not entry.enabled
        ok = startup.enable(entry) if want_enabled else startup.disable(entry)
        self.app.call_from_thread(self._after_toggle, entry.name, want_enabled, ok)

    def _after_toggle(self, name: str, want_enabled: bool, ok: bool) -> None:
        if ok:
            self.app.notify(
                f"{'Enabled' if want_enabled else 'Disabled'} '{name}'.", title="Startup"
            )
            self.load()
        else:
            self.app.notify(
                f"Couldn't change '{name}' — HKLM entries need admin (F2).",
                severity="warning", title="Startup",
            )
