"""Run history + trashed-item ledger, backed by SQLite.

Records each applied clean (what ran, when, how much was freed) so the TUI can
show reports, and stores the original paths of trashed items so an "undo last
clean" can restore them from the Recycle Bin. Lives at
``%APPDATA%\\sifty\\history.db``.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from ..infra.config import app_data_dir
from .models import Run

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    bytes_freed INTEGER NOT NULL DEFAULT 0,
    items INTEGER NOT NULL DEFAULT 0,
    success INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS trashed_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    original_path TEXT NOT NULL,
    restored INTEGER NOT NULL DEFAULT 0
);
"""


def db_path() -> Path:
    return app_data_dir() / "history.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.executescript(_SCHEMA)
    return conn


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def record_clean(
    action: str,
    detail: str,
    bytes_freed: int,
    items: int,
    trashed_paths: list[Path] | None = None,
    *,
    success: bool = True,
) -> int:
    """Record one applied run + its trashed paths. Returns the run id."""
    conn = _connect()
    try:
        cur = conn.execute(
            "INSERT INTO runs (ts, action, detail, bytes_freed, items, success) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (_now(), action, detail, bytes_freed, items, int(success)),
        )
        run_id = cur.lastrowid
        if trashed_paths:
            conn.executemany(
                "INSERT INTO trashed_items (run_id, original_path) VALUES (?, ?)",
                [(run_id, str(p)) for p in trashed_paths],
            )
        conn.commit()
        return int(run_id)
    finally:
        conn.close()


def _row_to_run(row) -> Run:
    return Run(
        id=row[0], ts=row[1], action=row[2], detail=row[3],
        bytes_freed=row[4], items=row[5], success=bool(row[6]), restorable=row[7],
    )


_SELECT = """
SELECT r.id, r.ts, r.action, r.detail, r.bytes_freed, r.items, r.success,
       (SELECT COUNT(*) FROM trashed_items t
        WHERE t.run_id = r.id AND t.restored = 0) AS restorable
FROM runs r
"""


def recent_runs(limit: int = 20) -> list[Run]:
    conn = _connect()
    try:
        rows = conn.execute(_SELECT + " ORDER BY r.id DESC LIMIT ?", (limit,)).fetchall()
        return [_row_to_run(r) for r in rows]
    finally:
        conn.close()


def summary() -> dict:
    conn = _connect()
    try:
        runs, total_bytes, total_items = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(bytes_freed), 0), COALESCE(SUM(items), 0) FROM runs"
        ).fetchone()
        return {"runs": runs, "bytes_freed": total_bytes, "items": total_items}
    finally:
        conn.close()


def last_restorable_run() -> Run | None:
    """The most recent run that still has un-restored trashed items."""
    conn = _connect()
    try:
        row = conn.execute(
            _SELECT + " WHERE restorable > 0 ORDER BY r.id DESC LIMIT 1"
        ).fetchone()
        return _row_to_run(row) if row else None
    finally:
        conn.close()


def items_to_restore(run_id: int) -> list[tuple[int, str]]:
    """(item_id, original_path) for un-restored items of a run."""
    conn = _connect()
    try:
        return [
            (r[0], r[1])
            for r in conn.execute(
                "SELECT id, original_path FROM trashed_items "
                "WHERE run_id = ? AND restored = 0",
                (run_id,),
            ).fetchall()
        ]
    finally:
        conn.close()


def mark_restored(item_ids: list[int]) -> None:
    if not item_ids:
        return
    conn = _connect()
    try:
        conn.executemany(
            "UPDATE trashed_items SET restored = 1 WHERE id = ?",
            [(i,) for i in item_ids],
        )
        conn.commit()
    finally:
        conn.close()
