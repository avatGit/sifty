"""Application logging and crash capture.

Diagnostics go to a rotating log under ``%APPDATA%\\sifty\\logs\\sifty.log``.
This is separate from the *audit* log (:func:`sifty.safety.audit`), which records
what was deleted; this log records activity, warnings, and crashes so problems can
be diagnosed after the fact.

Unhandled exceptions on the main thread and in worker threads are logged with full
tracebacks (Textual runs blocking work in threads, so the thread hook matters).
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import threading
from pathlib import Path

from .config import app_data_dir

_FILE_HANDLER: logging.Handler | None = None
_CONSOLE_MARK = "_sifty_console"
_ROOT_NAME = "sifty"


def log_dir() -> Path:
    path = app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_file() -> Path:
    return log_dir() / "sifty.log"


def get_logger(name: str = _ROOT_NAME) -> logging.Logger:
    return logging.getLogger(name)


def setup_logging(verbose: bool = False) -> Path:
    """Configure the ``sifty`` logger. Idempotent; re-call to toggle verbose.

    Returns the path to the log file.
    """
    global _FILE_HANDLER
    logger = logging.getLogger(_ROOT_NAME)
    logger.setLevel(logging.DEBUG)
    path = log_file()

    if _FILE_HANDLER is None:
        handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=1_000_000, backupCount=5, encoding="utf-8"
        )
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
        )
        logger.addHandler(handler)
        _FILE_HANDLER = handler
        _install_excepthooks(logger)

    _configure_console(logger, verbose)
    return path


def _configure_console(logger: logging.Logger, verbose: bool) -> None:
    for handler in list(logger.handlers):
        if getattr(handler, _CONSOLE_MARK, False):
            logger.removeHandler(handler)
    if verbose:
        console = logging.StreamHandler(sys.stderr)
        console.setLevel(logging.DEBUG)
        console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        setattr(console, _CONSOLE_MARK, True)
        logger.addHandler(console)


def _install_excepthooks(logger: logging.Logger) -> None:
    previous = sys.excepthook

    def main_hook(exc_type, exc_value, tb):
        if not issubclass(exc_type, KeyboardInterrupt):
            logger.critical("Unhandled exception", exc_info=(exc_type, exc_value, tb))
        previous(exc_type, exc_value, tb)

    sys.excepthook = main_hook

    def thread_hook(args: threading.ExceptHookArgs):
        if issubclass(args.exc_type, SystemExit):
            return
        logger.critical(
            "Unhandled exception in thread %s",
            args.thread.name if args.thread else "?",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = thread_hook
