"""Tests for logging setup and crash capture."""

from __future__ import annotations

import logging
import logging.handlers
import sys

import pytest

from sifty import logsetup


@pytest.fixture
def isolated_logs(monkeypatch, tmp_path):
    """Point the log dir at tmp and reset module/handler state per test."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(logsetup, "_FILE_HANDLER", None)
    logger = logging.getLogger("sifty")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    yield tmp_path
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    logsetup._FILE_HANDLER = None


def test_setup_creates_log_and_writes(isolated_logs):
    path = logsetup.setup_logging()
    assert path.exists()
    assert path.parent.name == "logs"

    logsetup.get_logger("sifty.test").error("hello-marker")
    logsetup._FILE_HANDLER.flush()
    assert "hello-marker" in path.read_text(encoding="utf-8")


def test_setup_is_idempotent(isolated_logs):
    logsetup.setup_logging()
    logsetup.setup_logging()
    logsetup.setup_logging(verbose=True)
    logger = logging.getLogger("sifty")
    file_handlers = [
        h for h in logger.handlers
        if isinstance(h, logging.handlers.RotatingFileHandler)
    ]
    assert len(file_handlers) == 1  # not duplicated


def test_verbose_toggles_console_handler(isolated_logs):
    logsetup.setup_logging(verbose=True)
    logger = logging.getLogger("sifty")
    assert any(getattr(h, "_sifty_console", False) for h in logger.handlers)
    logsetup.setup_logging(verbose=False)
    assert not any(getattr(h, "_sifty_console", False) for h in logger.handlers)


def test_excepthook_logs_unhandled(isolated_logs):
    path = logsetup.setup_logging()
    try:
        raise ValueError("boom-marker")
    except ValueError:
        sys.excepthook(*sys.exc_info())  # our installed hook
    logsetup._FILE_HANDLER.flush()
    contents = path.read_text(encoding="utf-8")
    assert "Unhandled exception" in contents
    assert "boom-marker" in contents
