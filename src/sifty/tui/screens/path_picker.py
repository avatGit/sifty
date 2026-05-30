"""A modal folder picker: switch drives, browse a tree, or type/autocomplete."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.suggester import SuggestFromList
from textual.widgets import Button, DirectoryTree, Input, Static


class PathPicker(ModalScreen[Path | None]):
    """Pick a folder. ``await app.push_screen_wait(...)`` returns Path or None."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(
        self,
        start: Path,
        recents: list[str] | None = None,
        drives: list[str] | None = None,
    ) -> None:
        super().__init__()
        self._start = Path(start).expanduser()
        self._recents = recents or []
        self._drives = drives or []

    def compose(self) -> ComposeResult:
        root = self._start.anchor or str(self._start)
        with Vertical(id="picker-box"):
            yield Static("Choose a folder to analyze", classes="title")
            if self._drives:
                with Horizontal(id="picker-drives"):
                    for i, drive in enumerate(self._drives):
                        yield Button(drive, id=f"drive-{i}", classes="drive-btn")
            yield Input(
                value=str(self._start),
                id="picker-path",
                placeholder="Type or paste a path…",
                suggester=SuggestFromList(self._recents, case_sensitive=False),
            )
            yield DirectoryTree(root, id="picker-tree")
            with Horizontal(id="picker-buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Analyze", id="ok", variant="primary")

    def _set_root(self, root: str) -> None:
        tree = self.query_one("#picker-tree", DirectoryTree)
        tree.path = root
        tree.reload()
        self.query_one("#picker-path", Input).value = root

    def on_directory_tree_directory_selected(
        self, event: DirectoryTree.DirectorySelected
    ) -> None:
        self.query_one("#picker-path", Input).value = str(event.path)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if "drive-btn" in event.button.classes:
            idx = int(event.button.id.removeprefix("drive-"))
            self._set_root(self._drives[idx])
            return
        if event.button.id == "ok":
            value = self.query_one("#picker-path", Input).value.strip()
            self.dismiss(Path(value).expanduser() if value else None)
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)
