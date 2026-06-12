"""Content views — one per sidebar section.

The sidebar now lists eight top-level sections; the "free up space" and
"installed software" screens are consolidated into the tabbed ``CleanView`` and
``AppsSystemView`` groups (see ``group.py``). The individual sub-views still
exist and stay reachable via ``SUBVIEW_ROUTES`` (deep-linking into a tab).
"""

from __future__ import annotations

from .ai import AIView
from .apps import AppsView
from .cleanup import CleanupView
from .disk import DiskView
from .group import (
    AppsSystemView,
    CleanView,
    SUBVIEW_LABELS,
    SUBVIEW_ROUTES,
    TabGroupView,
)
from .home import HomeView
from .junk import JunkView
from .monitor import MonitorView
from .optimize import OptimizeView
from .purge import PurgeView
from .reports import ReportsView
from .services import ServicesView
from .startup import StartupView
from .updates import UpdatesView

# Maps a sidebar nav key to its view class (the eight top-level sections).
VIEWS = {
    "home": HomeView,
    "clean": CleanView,
    "disk": DiskView,
    "apps": AppsSystemView,
    "updates": UpdatesView,
    "monitor": MonitorView,
    "reports": ReportsView,
    "ai": AIView,
}

__all__ = [
    "VIEWS",
    "SUBVIEW_ROUTES",
    "SUBVIEW_LABELS",
    "TabGroupView",
    "CleanView",
    "AppsSystemView",
    "HomeView",
    "JunkView",
    "DiskView",
    "CleanupView",
    "AppsView",
    "StartupView",
    "ServicesView",
    "UpdatesView",
    "ReportsView",
    "AIView",
    "MonitorView",
    "PurgeView",
    "OptimizeView",
]
