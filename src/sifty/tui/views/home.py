"""Home dashboard: volume gauges + reclaimable-junk total."""

from __future__ import annotations

import logging

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.widgets import Button, Label, Static

from ...admin import is_admin
from ...commands import disk, junk
from ...console import human_size
from ..widgets import Panel, usage_gauge
from .base import BaseView

logger = logging.getLogger("sifty.tui")


class HomeView(BaseView):
    def compose(self) -> ComposeResult:
        yield Static("Overview", classes="title")
        yield Panel(Static("Reading volumes…", id="vol-body"), title="Volumes")
        yield Panel(Label("Reclaimable junk: …", id="junk-total"), title="Junk")
        if not is_admin():
            with Panel(title="Administrator"):
                yield Static(
                    "[yellow]●[/yellow] Running as a standard user. Some tasks "
                    "(Windows Temp, Update cache, some uninstalls) need elevation.",
                    classes="subtle",
                )
                yield Button("Restart as administrator", id="elevate", variant="primary")
        else:
            yield Panel(
                Static("[green]●[/green] Running as administrator — all tasks available."),
                title="Administrator",
            )

    def on_mount(self) -> None:
        self._render_volumes()  # fast (psutil), no worker needed
        if self.workers_enabled():
            self.compute_junk_total()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "elevate":
            self.app.action_elevate()

    def _render_volumes(self) -> None:
        text = Text()
        for i, v in enumerate(disk.volumes()):
            if i:
                text.append("\n\n")
            text.append(
                f"{v.mountpoint}   {human_size(v.used)} / {human_size(v.total)}"
                f"   ({human_size(v.free)} free)\n",
                style="bold",
            )
            text.append(usage_gauge(v.percent))
        self.query_one("#vol-body", Static).update(text)

    @work(thread=True, exclusive=True)
    def compute_junk_total(self) -> None:
        try:
            total = sum(cat.size for cat in junk.scan())
        except Exception:
            logger.exception("Home: junk total scan failed")
            return
        self.app.call_from_thread(self._set_junk_total, total)

    def _set_junk_total(self, total: int) -> None:
        try:
            self.query_one("#junk-total", Label).update(
                f"Reclaimable junk: [b]{human_size(total)}[/b]  "
                f"[dim](open the Junk screen to clean)[/dim]"
            )
        except Exception:
            pass
