"""The journal: what the program did, line by line, and which lines belong together.

Every part of the program writes here with `record`. Lines written during one operation
(one request from the page, one terminal command, one background job) share a trace, so
the page can show the whole story of a download or a click, in order.

Two rules hold everywhere:

    Writing a line never breaks the work. If the journal cannot be written, the download
    or the click carries on.

    Keys never get in. Callers do not pass them, and anything named like one is hidden
    here as well, in case a caller forgets.
"""

from __future__ import annotations

import json
import logging
import secrets
import sqlite3
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator

LEVELS = ("detail", "info", "warning", "error")  # detail: the page hides it until asked
KEEP_DAYS = 30
KEEP_LINES = 50_000
PAGE = 200  # lines read at a time
MOST_AT_ONCE = 1000
WRITE_TIMEOUT = 2  # seconds a line waits for a busy database before it is dropped

# Part of a name that marks a value as one to keep out, whatever it holds.
_NEVER_WRITTEN = ("key", "secret", "token", "password", "pin", "authorization")
_LOG_LEVELS = {"detail": logging.DEBUG, "info": logging.INFO, "warning": logging.WARNING, "error": logging.ERROR}
_COLUMNS = ("id", "at", "level", "area", "event", "message", "data", "trace", "duration_ms")

_database: Path | None = None  # where lines are written; None until the program says
_trace: ContextVar[str | None] = ContextVar("journal_trace", default=None)
_file_log = logging.getLogger("efactura.journal")


def configure(db_path: Path | None) -> None:
    """Say which database the journal lives in. The table itself is made by the Store."""
    global _database
    _database = Path(db_path) if db_path else None


@contextmanager
def trace(fresh: bool = False) -> Iterator[str]:
    """Everything recorded inside belongs to one operation. A step inside an operation
    that is already being traced joins it instead of starting its own.

    `fresh` starts a new operation whatever is going on around it. The running program
    needs that: its server is started inside the trace of the `serve` command, and each
    request and each round of housekeeping is a story of its own, not part of that one."""
    current = _trace.get()
    if current is not None and not fresh:
        yield current
        return
    started = _trace.set(secrets.token_hex(6))
    try:
        yield _trace.get()
    finally:
        _trace.reset(started)


def record(
    area: str,
    event: str | None,
    message: str,
    level: str = "info",
    duration_ms: int | None = None,
    now: datetime | None = None,
    **data,
) -> None:
    """Write one line. `event` is a stable code the page knows how to say in Romanian;
    `message` is the same thing in English, for whoever debugs."""
    safe = {
        name: "[hidden]" if any(part in name.lower() for part in _NEVER_WRITTEN) else value
        for name, value in data.items()
        if value is not None
    }
    _write(area, event, message, level, duration_ms, now, safe)
    # The text log gets the line too. `journaled` keeps the handler below from writing it twice.
    _file_log.log(_LOG_LEVELS.get(level, logging.INFO), "%s %s %s", event, message, safe or "", extra={"journaled": True})


class JournalHandler(logging.Handler):
    """Puts the program's ordinary log lines in the journal as well."""

    def emit(self, entry: logging.LogRecord) -> None:
        if getattr(entry, "journaled", False):
            return
        level = "error" if entry.levelno >= logging.ERROR else "warning" if entry.levelno >= logging.WARNING else "info"
        data = {}
        if entry.exc_info:
            data["traceback"] = logging.Formatter().formatException(entry.exc_info)
        try:
            _write("program", None, entry.getMessage(), level, None, None, data)
        except Exception:  # a log line must never raise
            pass


def events(
    db_path: Path,
    *,
    details: bool = False,
    problems_only: bool = False,
    area: str | None = None,
    text: str | None = None,
    since: str | None = None,
    trace: str | None = None,
    before: int | None = None,
    limit: int = PAGE,
    oldest_first: bool = False,
    everything: bool = False,
) -> dict:
    """Lines of the journal, the newest first. A trace shows its whole operation, details
    included; otherwise details are left out unless asked for. `everything` is for saving
    the journal to a file: every line that fits, however many."""
    where, values = [], []
    if problems_only:
        where.append("level IN ('warning', 'error')")
    elif not details and trace is None:
        where.append("level != 'detail'")
    for column, value in (("area", area), ("trace", trace)):
        if value:
            where.append(f"{column} = ?")
            values.append(value)
    if since:
        where.append("at >= ?")
        values.append(since)
    if before is not None:
        where.append("id < ?")
        values.append(before)
    if text:
        like = "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        where.append("(message LIKE ? ESCAPE '\\' OR data LIKE ? ESCAPE '\\')")
        values += [like, like]
    limit = KEEP_LINES if everything else max(1, min(int(limit), MOST_AT_ONCE))
    sql = (
        f"SELECT {', '.join(_COLUMNS)} FROM events"
        + (" WHERE " + " AND ".join(where) if where else "")
        + f" ORDER BY id {'ASC' if oldest_first else 'DESC'} LIMIT ?"
    )
    connection = sqlite3.connect(db_path, timeout=5)
    try:
        found = connection.execute(sql, [*values, limit + 1]).fetchall()
    finally:
        connection.close()
    lines = [{**dict(zip(_COLUMNS, row)), "data": json.loads(row[6])} for row in found[:limit]]
    return {"ok": True, "events": lines, "has_more": len(found) > limit}


def as_text(lines: list[dict]) -> str:
    """The lines as a text file, to send to whoever helps."""
    return "\n".join(
        f"{line['at']}  {line['level'].upper():<8} {line['area']:<8} {line['message']}"
        + ("  " + " ".join(f"{name}={value}" for name, value in line["data"].items()) if line["data"] else "")
        for line in lines
    )


def prune(db_path: Path, now: datetime) -> int:
    """Remove what is older than KEEP_DAYS, then the oldest beyond KEEP_LINES. Returns how many went."""
    connection = sqlite3.connect(db_path, timeout=5)
    try:
        with connection:
            aged = connection.execute("DELETE FROM events WHERE at < ?", ((now - timedelta(days=KEEP_DAYS)).isoformat(),))
            extra = connection.execute(
                "DELETE FROM events WHERE id <= (SELECT id FROM events ORDER BY id DESC LIMIT 1 OFFSET ?)", (KEEP_LINES,)
            )
        return aged.rowcount + extra.rowcount
    finally:
        connection.close()


def _write(area, event, message, level, duration_ms, now, data) -> None:
    if _database is None:
        return
    try:
        # A connection of its own, opened and closed for the line: lines come from several
        # threads, and one that cannot be written (database busy, table missing) is dropped.
        connection = sqlite3.connect(_database, timeout=WRITE_TIMEOUT)
        try:
            with connection:
                connection.execute(
                    "INSERT INTO events (at, level, area, event, message, data, trace, duration_ms) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        (now or datetime.now().astimezone()).isoformat(), level if level in LEVELS else "info",
                        area, event, message, json.dumps(data, ensure_ascii=False, default=str),
                        _trace.get(), duration_ms,
                    ),
                )
        finally:
            connection.close()
    except (sqlite3.Error, OSError):
        pass
