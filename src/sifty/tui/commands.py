"""Command-palette provider: fuzzy-search and run any Sifty action.

Registered in ``SiftyApp.COMMANDS`` so the built-in palette (Ctrl+P) can jump to
any screen or run a global action.
"""

from __future__ import annotations

from functools import partial

from textual.command import DiscoveryHit, Hit, Hits, Provider


def _entries(app):
    """(title, help, callback) for every palette command."""
    from .app import SECTIONS  # lazy import avoids an app<->commands cycle
    from .views import SUBVIEW_LABELS

    items: list[tuple[str, str, object]] = []
    for key, label in SECTIONS:
        items.append((f"Go to {label}", f"Open the {label} screen", partial(app.show, key)))
    # The consolidated groups hide some screens behind tabs; keep them directly
    # reachable by deep-linking into the right tab.
    for key, label in SUBVIEW_LABELS.items():
        items.append((f"Go to {label}", f"Open the {label} screen", partial(app.show, key)))
    items.append(
        ("Restart as administrator", "Relaunch Sifty elevated (UAC)", app.action_elevate)
    )
    return items


class SiftyCommands(Provider):
    """Sifty's screens and global actions, surfaced in the command palette."""

    async def discover(self) -> Hits:
        for title, help_text, callback in _entries(self.app):
            yield DiscoveryHit(title, callback, help=help_text)

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        for title, help_text, callback in _entries(self.app):
            score = matcher.match(title)
            if score > 0:
                yield Hit(score, matcher.highlight(title), callback, help=help_text)
