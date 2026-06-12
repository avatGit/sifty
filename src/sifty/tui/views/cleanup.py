"""Cleanup screen: find duplicates / large files / stale downloads and trash them."""

from __future__ import annotations

import logging
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Input, Static

from ...console import human_size
from ...core import cleanup, disk, history
from ...core.vcs import find_orphan_worktrees, prune_worktrees
from .. import state
from ..modals import ConfirmModal
from ..screens.path_picker import PathPicker
from ..widgets import Panel
from .base import BaseView

logger = logging.getLogger("sifty.tui")

_MARK = "✓"
_UNMARK = " "


class CleanupView(BaseView):
    BINDINGS = [("space", "toggle_mark", "Mark")]

    def compose(self) -> ComposeResult:
        yield Static("Smart cleanup", classes="title")
        yield Static(
            "Pick a mode, scan, then mark rows (click / Space) and Clean selected. "
            "Duplicates pre-mark the redundant copies (one kept per group). "
            "Worktrees needs a git repo root.",
            classes="subtle",
        )
        yield Input(value=str(Path.home()), id="cleanup-path", placeholder="Folder (for duplicates / large files / worktrees)")
        with Horizontal(classes="actions"):
            yield Button("Browse…", id="browse")
            yield Button("Duplicates", id="mode-duplicates", variant="primary")
            yield Button("Large files", id="mode-large")
            yield Button("Stale downloads", id="mode-stale")
            yield Button("Worktrees", id="mode-worktrees")
        yield Panel(DataTable(id="cleanup-table"), title="Results", id="cleanup-panel")
        with Horizontal(classes="actions", id="cleanup-actions"):
            yield Button("Select all", id="select-all")
            yield Button("Deselect all", id="deselect-all")
            yield Button("Clean selected", id="clean", variant="warning")
        yield Static("Pick a mode to scan.", id="cleanup-status", classes="status")

    def on_mount(self) -> None:
        self._mode: str | None = None
        self._rows: list[tuple[Path, int]] = []
        self._marked: set[str] = set()
        table = self.query_one("#cleanup-table", DataTable)
        table.cursor_type = "row"
        self._cols = table.add_columns("", "Size", "Path")
        # Results panel + action buttons stay hidden until a scan finds something.
        self.query_one("#cleanup-panel").display = False
        self.query_one("#cleanup-actions").display = False

    def _path(self) -> Path:
        return Path(self.query_one("#cleanup-path", Input).value or str(Path.home())).expanduser()

    def _status(self, msg: str) -> None:
        self.query_one("#cleanup-status", Static).update(msg)

    # --------------------------------------------------------------- scanning
    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "browse":
            self._browse()
        elif bid.startswith("mode-"):
            self._mode = bid.removeprefix("mode-")
            self._status(f"Scanning ({self._mode})…")
            self.query_one("#cleanup-panel").display = True
            self.query_one("#cleanup-actions").display = False  # nothing to act on yet
            self.query_one("#cleanup-table", DataTable).loading = True
            self.scan()
        elif bid == "select-all":
            self._marked = {str(p) for p, _s in self._rows}
            self._rebuild_table()
        elif bid == "deselect-all":
            self._marked.clear()
            self._rebuild_table()
        elif bid == "clean":
            self._clean_flow()

    @work
    async def _browse(self) -> None:
        # Worker context required for push_screen_wait.
        drives = [v.mountpoint for v in disk.volumes()]
        picked = await self.app.push_screen_wait(
            PathPicker(self._path(), state.recent_paths(), drives=drives)
        )
        if picked is None:
            return
        self.query_one("#cleanup-path", Input).value = str(picked)
        state.add_recent_path(str(picked))

    @work(thread=True, exclusive=True)
    def scan(self) -> None:
        mode = self._mode
        try:
            if mode == "duplicates":
                groups = disk.find_duplicates(self._path(), 1024)
                rows = [(p, disk._entry_size(p)) for p in cleanup.choose_duplicate_deletions(groups, recent_days=7)]
                premark = True
            elif mode == "large":
                rows = cleanup.find_large_files(self._path(), recent_days=7)
                premark = False
            elif mode == "worktrees":
                orphans = find_orphan_worktrees(self._path())
                rows = [(o.path, disk._entry_size(o.path)) for o in orphans]
                premark = True
            else:  # stale
                rows = [(p, s) for p, s, _m in cleanup.find_stale_downloads()]
                premark = False
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Cleanup scan failed (%s)", mode)
            self.app.call_from_thread(self._scan_failed, exc)
            return
        self.app.call_from_thread(self._populate, rows, premark)

    def _scan_failed(self, exc: Exception) -> None:
        self.query_one("#cleanup-table", DataTable).loading = False
        self.query_one("#cleanup-panel").display = False
        self.query_one("#cleanup-actions").display = False
        self._status(f"Failed: {exc}")

    def _populate(self, rows: list[tuple[Path, int]], premark: bool) -> None:
        self._rows = rows
        self._marked = {str(p) for p, _s in rows} if premark else set()
        self.query_one("#cleanup-table", DataTable).loading = False
        if not rows:
            self.query_one("#cleanup-panel").display = False
            self.query_one("#cleanup-actions").display = False
            self._status(f"Nothing found ({self._mode}).")
            return
        self.query_one("#cleanup-panel").display = True
        self.query_one("#cleanup-actions").display = True
        self._rebuild_table()

    def _rebuild_table(self) -> None:
        table = self.query_one("#cleanup-table", DataTable)
        table.clear()
        for path, size in self._rows:
            mark = _MARK if str(path) in self._marked else _UNMARK
            table.add_row(mark, human_size(size), str(path), key=str(path))
        marked_bytes = sum(s for p, s in self._rows if str(p) in self._marked)
        self._status(
            f"{len(self._rows)} items · {len(self._marked)} marked "
            f"({human_size(marked_bytes)})" if self._rows else "Nothing found."
        )

    # ------------------------------------------------------------- selection
    def _toggle_mark(self, key: str) -> None:
        table = self.query_one("#cleanup-table", DataTable)
        if key in self._marked:
            self._marked.discard(key)
            table.update_cell(key, self._cols[0], _UNMARK)
        else:
            self._marked.add(key)
            table.update_cell(key, self._cols[0], _MARK)
        marked_bytes = sum(s for p, s in self._rows if str(p) in self._marked)
        self._status(f"{len(self._rows)} items · {len(self._marked)} marked ({human_size(marked_bytes)})")

    def action_toggle_mark(self) -> None:
        table = self.query_one("#cleanup-table", DataTable)
        if table.row_count and table.cursor_row is not None and 0 <= table.cursor_row < len(self._rows):
            self._toggle_mark(str(self._rows[table.cursor_row][0]))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key is not None and event.row_key.value is not None:
            self._toggle_mark(event.row_key.value)

    # ----------------------------------------------------------------- clean
    @work
    async def _clean_flow(self) -> None:
        if not self._marked:
            self._status("Nothing marked.")
            return
        paths = [Path(k) for k in self._marked]
        marked_bytes = sum(s for p, s in self._rows if str(p) in self._marked)
        ok = await self.app.push_screen_wait(
            ConfirmModal(
                f"Move {len(paths)} item(s) ({human_size(marked_bytes)}) to the Recycle Bin?",
                confirm_label="Clean",
            )
        )
        if ok:
            self._status("Cleaning…")
            self.do_clean(paths)

    @work(thread=True, exclusive=True)
    def do_clean(self, paths: list[Path]) -> None:
        if self._mode == "worktrees":
            result = prune_worktrees(self._path(), dry_run=False, only=paths)
        else:
            result = cleanup.trash_paths(paths, dry_run=False)
        history.record_clean(
            f"cleanup-{self._mode}", str(self._path()),
            result.bytes_freed, result.items, result.trashed,
        )
        self.app.call_from_thread(self._after_clean, result.bytes_freed, result.items, len(result.skipped))

    def _after_clean(self, freed: int, items: int, skipped: int) -> None:
        self.app.notify(
            f"Sent {items} item(s) ({human_size(freed)}) to the Recycle Bin"
            + (f" · {skipped} skipped" if skipped else ""),
            title="Cleanup",
        )
        self.scan()  # refresh current mode
