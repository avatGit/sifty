"""Home dashboard: volume gauges + an at-a-glance summary of every area."""

from __future__ import annotations

import logging

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.widgets import Button, Static

from ...console import human_size
from ...core import apps as apps_mod
from ...core import disk, history, junk, services, startup, updates
from ...windows import winget
from ...windows.admin import is_admin
from ..widgets import Panel, usage_gauge
from .base import BaseView

logger = logging.getLogger("sifty.tui")

# (key, label) for each at-a-glance stat line, in display order.
_STATS = [
    ("junk", "Junk"),
    ("updates", "Updates"),
    ("apps", "Apps"),
    ("startup", "Startup"),
    ("services", "Services"),
    ("history", "History"),
]


class HomeView(BaseView):
    def compose(self) -> ComposeResult:
        yield Static("Overview", classes="title")
        yield Panel(Static("Reading volumes…", id="vol-body"), title="Volumes")
        yield Panel(Static("", id="stats-body"), title="At a glance")
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
        self._stats: dict[str, str] = {k: "…" for k, _ in _STATS}
        self._render_volumes()  # fast (psutil), no worker needed
        self._stats["updates"] = "checking…"
        self._stats["history"] = self._history_text()  # fast (sqlite)
        self._render_stats()
        if self.workers_enabled():
            self.compute_junk()
            self.compute_apps()
            self.compute_startup()
            self.compute_services()
            self.compute_updates()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "elevate":
            self.app.action_elevate()

    # ----------------------------------------------------------------- render
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
        try:
            self.query_one("#vol-body", Static).update(text)
        except Exception:
            pass

    def _render_stats(self) -> None:
        lines = "\n".join(f"[b]{label:<9}[/b] {self._stats[key]}" for key, label in _STATS)
        try:
            self.query_one("#stats-body", Static).update(lines)
        except Exception:
            pass

    def _set_stat(self, key: str, value: str) -> None:
        self._stats[key] = value
        self._render_stats()

    def _history_text(self) -> str:
        try:
            summ = history.summary()
        except Exception:
            return "no history yet"
        if not summ["runs"]:
            return "nothing cleaned yet"
        return f"reclaimed [b]{human_size(summ['bytes_freed'])}[/b] over {summ['runs']} runs"

    # ----------------------------------------------------------------- workers
    @work(thread=True, exclusive=True, group="home-junk")
    def compute_junk(self) -> None:
        try:
            total = sum(cat.size for cat in junk.scan())
        except Exception:
            logger.exception("Home: junk total scan failed")
            return
        self.app.call_from_thread(self._set_stat, "junk", f"[b]{human_size(total)}[/b] reclaimable")

    @work(thread=True, exclusive=True, group="home-apps")
    def compute_apps(self) -> None:
        try:
            installed = apps_mod.installed_apps()
        except Exception:
            logger.exception("Home: apps summary failed")
            return
        if installed:
            largest = max(installed, key=lambda a: a.size_bytes)
            value = f"[b]{len(installed)}[/b] installed · largest {largest.name} ({human_size(largest.size_bytes)})"
        else:
            value = "none found"
        self.app.call_from_thread(self._set_stat, "apps", value)

    @work(thread=True, exclusive=True, group="home-startup")
    def compute_startup(self) -> None:
        try:
            entries = startup.list_entries()
        except Exception:
            logger.exception("Home: startup summary failed")
            return
        enabled = sum(1 for e in entries if e.enabled)
        self.app.call_from_thread(self._set_stat, "startup", f"[b]{len(entries)}[/b] programs · {enabled} enabled")

    @work(thread=True, exclusive=True, group="home-services")
    def compute_services(self) -> None:
        try:
            items = services.list_services()
        except Exception:
            logger.exception("Home: services summary failed")
            return
        present = sum(1 for s in items if s.present)
        disabled = sum(1 for s in items if s.start_type == "disabled")
        self.app.call_from_thread(self._set_stat, "services", f"[b]{present}[/b] optional · {disabled} disabled")

    @work(thread=True, exclusive=True, group="home-updates")
    def compute_updates(self) -> None:
        try:
            if not winget.available():
                value = "winget unavailable"
            else:
                ups = updates.list_upgrades()
                value = f"[b]{len(ups)}[/b] available" if ups else "up to date"
        except Exception:
            logger.exception("Home: updates summary failed")
            return
        self.app.call_from_thread(self._set_stat, "updates", value)
