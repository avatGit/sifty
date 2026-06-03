"""Optimize screen: run non-destructive system cache cleanup operations."""

from __future__ import annotations

import logging

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, SelectionList, Static
from textual.widgets.selection_list import Selection

from ...core import optimize
from ...windows.admin import is_admin
from .base import BaseView

logger = logging.getLogger("sifty.tui")


class OptimizeView(BaseView):
    def compose(self) -> ComposeResult:
        yield Static("System optimize", classes="title")
        yield Static(
            "Non-destructive cache cleanup — each operation is safe and rebuilds "
            "automatically. Admin-only items are greyed out when not elevated (F2).",
            classes="subtle",
        )
        yield SelectionList(id="optimize-list")
        with Horizontal(classes="actions"):
            yield Button("Run selected", id="run", variant="primary")
        yield Static("", id="optimize-log", classes="status")
        yield Static("", id="optimize-status", classes="status")

    def on_mount(self) -> None:
        self._ops: list[optimize.OptimizeOp] = optimize.list_operations()
        self._admin = is_admin()
        self._log_lines: list[str] = []
        sl = self.query_one("#optimize-list", SelectionList)
        for op in self._ops:
            if op.requires_admin and not self._admin:
                label = f"{op.label}  [dim](needs admin — F2)[/dim]"
                sl.add_option(Selection(label, op.key, initial_state=False))
            else:
                label = f"{op.label}  [dim]· {op.reversible}[/dim]"
                sl.add_option(Selection(label, op.key, initial_state=True))
        self._set_status("Select operations and press Run selected.")

    def _set_status(self, msg: str) -> None:
        self.query_one("#optimize-status", Static).update(msg)

    def _append_log(self, msg: str) -> None:
        self._log_lines.append(msg)
        self.query_one("#optimize-log", Static).update("\n".join(self._log_lines))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run":
            keys = set(self.query_one("#optimize-list", SelectionList).selected)
            if not keys:
                self._set_status("Nothing selected.")
                return
            ops = [op for op in self._ops if op.key in keys]
            self._log_lines = []
            self.query_one("#optimize-log", Static).update("")
            self._set_status("Running…")
            self.query_one("#run", Button).disabled = True
            self.run_ops(ops)

    @work(thread=True, exclusive=True, group="optimize-run")
    def run_ops(self, ops: list[optimize.OptimizeOp]) -> None:
        for op in ops:
            self.app.call_from_thread(self._append_log, f"  {op.label}…")
            try:
                ok, msg = optimize.run_op(op, dry_run=False)
                line = f"  [green]✓[/green] {op.label}: {msg}" if ok else f"  [red]✗[/red] {op.label}: {msg}"
            except Exception as exc:
                logger.exception("Optimize op %s failed", op.key)
                line = f"  [red]✗[/red] {op.label}: {exc}"
            self.app.call_from_thread(self._append_log, line)
        self.app.call_from_thread(self._done)

    def _done(self) -> None:
        self.query_one("#run", Button).disabled = False
        self._set_status("Done.")
