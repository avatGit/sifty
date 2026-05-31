"""Windows toast notifications via the windows-toasts library.

Degrades gracefully: if the library or WinRT isn't available, returns False
instead of raising (callers carry on without a toast).
"""

from __future__ import annotations

import logging

logger = logging.getLogger("sifty.windows")


def toast(title: str, message: str, app_name: str = "Sifty") -> bool:
    """Show a toast with a title + message. Returns True on success."""
    try:
        from windows_toasts import Toast, WindowsToaster

        toaster = WindowsToaster(app_name)
        notification = Toast()
        notification.text_fields = [title, message]
        toaster.show_toast(notification)
        return True
    except Exception:
        logger.exception("toast notification failed")
        return False
