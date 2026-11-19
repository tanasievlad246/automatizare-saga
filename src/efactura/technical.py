"""The technical side of the journal, for whoever looks into how the program works.

Two kinds of records, each filed under the operation (the journal's trace) it happened in:

    http  Every exchange the program's HTTP client has with ANAF (the login, the message list,
          the downloads) and with OpenRouter (Jev): the method, the address, the code that came
          back, how long it took, the headers, and the bodies when they are text.

    log   The program's own debug records, with the file, the line and the function that wrote
          them. Records from "information" up are journal lines already (journal.JournalHandler).

The same rules hold as for the journal, and three more:

    Writing never breaks the work, and nothing here raises into it.

    No secret is ever kept: everything passes through `redact` before it is written.

    What is kept is bounded. A binary body (the ZIP of a download) is never kept, only its type
    and size. A body is cut at BODY_LIMIT characters and not even looked at above TOO_LARGE
    bytes. The whole is kept under TOTAL_BYTES and KEEP_RECORDS records, the oldest going first,
    and nothing older than KEEP_DAYS. It never leaves this computer.
"""

from __future__ import annotations

import itertools
import json
import logging
import sqlite3
import threading
import time
import weakref
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from . import journal, redact
from .errors import NOT_FOUND, EfacturaError, said_by

KEEP_DAYS = 7  # sooner than the journal (30): the bodies take far more room than its lines
KEEP_RECORDS = 20_000
TOTAL_BYTES = 10_000_000  # about 10 MB for the whole technical side
BODY_LIMIT = 32 * 1024  # characters of one body kept
TOO_LARGE = 2_000_000  # bytes of a body above which it is not read at all
TRIM_EVERY = 200  # records written between two checks of the whole size
PAGE = 500  # records read at a time
MOST_AT_ONCE = 2000
WRITE_TIMEOUT = 2  # seconds a record waits for a busy database before it is dropped

_HEAD = ("id", "at", "trace", "kind", "level", "summary", "head")
_SERVICES = {"logincert.anaf.ro": "anaf_login", "openrouter.ai": "jev"}
_BINARY_TYPES = ("zip", "octet-stream", "pdf", "pkcs7", "x-pkcs", "gzip", "x-tar", "x-7z", "msword", "vnd.")
_written = itertools.count(1)
# When each request in flight was sent: httpx knows it only for a body it read from the network.
_sent_at: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_sent_at_lock = threading.Lock()


# --- what is recorded -------------------------------------------------------------------------------


def watch(client: httpx.Client) -> httpx.Client:
    """Record every exchange this client has from now on. Asking twice records once."""
    hooks = client.event_hooks
    sent, answered = list(hooks.get("request", [])), list(hooks.get("response", []))
    if _on_response not in answered:
        client.event_hooks = {**hooks, "request": [*sent, _on_request], "response": [*answered, _on_response]}
    return client


def unanswered(exc: Exception, duration_ms: int | None) -> None:
    """Record a request that got no answer (no connection, a timeout). Called where the
    program catches the failure: a response hook never sees one."""
    try:
        request = exc.request  # every httpx.RequestError knows the request it was about
    except (AttributeError, RuntimeError):
        return
    try:
        _keep_exchange(request, None, f"{type(exc).__name__}: {said_by(exc)}", duration_ms)
    except Exception:  # a record must never break the work
        pass


class TechnicalHandler(logging.Handler):
    """Keeps the program's debug records. Those from information up are journal lines."""

    def __init__(self):
        super().__init__(logging.DEBUG)

    def emit(self, entry: logging.LogRecord) -> None:
        if entry.levelno >= logging.INFO or getattr(entry, "journaled", False):
            return
        try:
            head = {
                "logger": entry.name,
                "where": f"{entry.filename}:{entry.lineno}",
                "function": entry.funcName,
                "has_exception": bool(entry.exc_info),
            }
            body = (
                {"exception": redact.clean(logging.Formatter().formatException(entry.exc_info))}
                if entry.exc_info else {}
            )
            _keep("log", "debug", redact.clean(entry.getMessage()), head, body)
        except Exception:  # a log record must never raise
            pass


def _on_request(request: httpx.Request) -> None:
    with _sent_at_lock:
        _sent_at[request] = time.monotonic()


def _on_response(response: httpx.Response) -> None:
    # The client reads the body right after its hooks; reading it here first changes nothing,
    # and a failure to read it is the call's own failure, so it is not caught.
    response.read()
    try:
        _keep_exchange(response.request, response, None, _elapsed_ms(response.request))
    except Exception:  # a record must never break the call
        pass


def _keep_exchange(request: httpx.Request, response: httpx.Response | None, error: str | None, duration_ms) -> None:
    address = redact.url(str(request.url))
    status = response.status_code if response is not None else None
    sent = _body(request.headers.get("content-type"), _content(request))
    received = _body(response.headers.get("content-type"), response.content) if response is not None else None
    head = {
        "method": request.method,
        "url": address,
        "status": status,
        "duration_ms": duration_ms,
        "service": _service(request.url.host),
        "error": redact.clean(error) if error else None,
        "sent": _brief(sent),
        "received": _brief(received) if received is not None else None,
    }
    body = {
        "request": {"headers": redact.headers(request.headers.multi_items()), "body": sent},
        "response": None if response is None else {
            "headers": redact.headers(response.headers.multi_items()), "body": received,
        },
    }
    level = "error" if status is None or status >= 500 else "warning" if status >= 400 else "info"
    answer = str(status) if status is not None else "no answer"
    took = f" {duration_ms} ms" if duration_ms is not None else ""
    _keep("http", level, f"{request.method} {address} {answer}{took}", head, body)


def _content(request: httpx.Request) -> bytes:
    try:
        return request.content
    except httpx.RequestNotRead:  # a body sent as a stream: not kept
        return b""


def _body(content_type: str | None, data: bytes) -> dict:
    """What is kept of a body: its text with the secrets hidden, or only what it was."""
    kind = (content_type or "").split(";")[0].strip().lower() or None
    size = len(data)
    if not size:
        return {"empty": True}
    if size > TOO_LARGE:
        return {"too_large": True, "type": kind, "bytes": size}
    if _binary(kind, data):
        return {"binary": True, "type": kind, "bytes": size}
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return {"binary": True, "type": kind, "bytes": size}
    shape = _format(kind, text)
    cleaned = {"json": redact.json_text, "form": redact.form}.get(shape, redact.clean)(text)
    kept = {"format": shape, "type": kind, "bytes": size, "text": cleaned[:BODY_LIMIT]}
    if len(cleaned) > BODY_LIMIT:
        kept["cut"] = True
    return kept


def _binary(kind: str | None, data: bytes) -> bool:
    if data.startswith(b"PK\x03\x04") or b"\x00" in data[:4096]:
        return True
    if not kind:
        return False
    main, _, sub = kind.partition("/")
    return main in ("image", "audio", "video", "font") or any(part in sub for part in _BINARY_TYPES)


def _format(kind: str | None, text: str) -> str:
    kind = kind or ""
    if "x-www-form-urlencoded" in kind:
        return "form"
    stripped = text.lstrip()
    if "json" in kind or stripped[:1] in ("{", "["):
        try:
            json.loads(text)
            return "json"
        except ValueError:
            pass
    if "html" not in kind and ("xml" in kind or stripped.startswith("<")):
        return "xml"
    return "text"


def _brief(body: dict) -> dict:
    return {"type": body.get("type"), "bytes": body.get("bytes", 0)}


def _service(host: str) -> str:
    if host in _SERVICES:
        return _SERVICES[host]
    return "anaf" if host == "anaf.ro" or host.endswith(".anaf.ro") else host


def _elapsed_ms(request: httpx.Request) -> int | None:
    """From the moment the request was sent to the moment its whole answer was read."""
    with _sent_at_lock:
        sent = _sent_at.pop(request, None)
    return None if sent is None else round((time.monotonic() - sent) * 1000)


# --- keeping ---------------------------------------------------------------------------------------------


def _keep(kind: str, level: str, summary: str, head: dict, body: dict) -> None:
    database = journal.database()
    if database is None:
        return
    head_text = json.dumps(head, ensure_ascii=False, default=str)
    body_text = json.dumps(body, ensure_ascii=False, default=str)
    size = len(summary.encode()) + len(head_text.encode()) + len(body_text.encode())
    row = (
        datetime.now().astimezone().isoformat(timespec="microseconds"),
        journal.current_trace(), kind, level, summary, head_text, body_text, size,
    )
    try:
        _insert(database, row)
    except (sqlite3.Error, OSError):
        pass


def _insert(database: Path, row: tuple) -> None:
    # A connection of its own, as for a journal line: records come from several threads.
    connection = sqlite3.connect(database, timeout=WRITE_TIMEOUT)
    try:
        with connection:
            connection.execute(
                "INSERT INTO technical (at, trace, kind, level, summary, head, body, size) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                row,
            )
            # The whole size is checked now and then, not only at the quarter-hour
            # housekeeping: one long download can write a great deal in between.
            if next(_written) % TRIM_EVERY == 0:
                _trim(connection)
    finally:
        connection.close()


def _trim(connection: sqlite3.Connection) -> int:
    """Remove the oldest records until the rest fit in TOTAL_BYTES. Returns how many went."""
    gone = connection.execute(
        "DELETE FROM technical WHERE id <= ("
        "SELECT id FROM (SELECT id, SUM(size) OVER (ORDER BY id DESC) AS kept FROM technical) "
        "WHERE kept > ? ORDER BY id DESC LIMIT 1)",
        (TOTAL_BYTES,),
    )
    return gone.rowcount


def prune(db_path: Path, now: datetime) -> int:
    """Remove what is older than KEEP_DAYS, then the oldest beyond KEEP_RECORDS, then the
    oldest beyond TOTAL_BYTES. Returns how many went."""
    connection = sqlite3.connect(db_path, timeout=5)
    try:
        with connection:
            aged = connection.execute(
                "DELETE FROM technical WHERE at < ?", ((now - timedelta(days=KEEP_DAYS)).isoformat(),)
            )
            extra = connection.execute(
                "DELETE FROM technical WHERE id <= (SELECT id FROM technical ORDER BY id DESC LIMIT 1 OFFSET ?)",
                (KEEP_RECORDS,),
            )
            heavy = _trim(connection)
        return aged.rowcount + extra.rowcount + heavy
    finally:
        connection.close()


# --- reading ------------------------------------------------------------------------------------------------


def records(
    db_path: Path, *, trace: str | None = None, before: int | None = None, limit: int = PAGE,
    oldest_first: bool = False,
) -> dict:
    """The records of one operation (or all), newest first, without their bodies."""
    where, values = [], []
    if trace:
        where.append("trace = ?")
        values.append(trace)
    if before is not None:
        where.append("id < ?")
        values.append(before)
    limit = max(1, min(int(limit), MOST_AT_ONCE))
    sql = (
        f"SELECT {', '.join(_HEAD)} FROM technical"
        + (" WHERE " + " AND ".join(where) if where else "")
        + f" ORDER BY id {'ASC' if oldest_first else 'DESC'} LIMIT ?"
    )
    found = _read(db_path, sql, [*values, limit + 1])
    return {"ok": True, "records": [_head_of(row) for row in found[:limit]], "has_more": len(found) > limit}


def record(db_path: Path, record_id: int) -> dict:
    """One record whole: what was sent and what came back, or the exception."""
    found = _read(db_path, f"SELECT {', '.join(_HEAD)}, body FROM technical WHERE id = ?", [record_id])
    if not found:
        raise EfacturaError(NOT_FOUND, f"No technical record with id {record_id}; it may have been cleared.")
    return {**_head_of(found[0][:-1]), "body": json.loads(found[0][-1])}


def counts(db_path: Path, traces) -> dict:
    """For each operation that has technical records: how many requests, how many of them
    went wrong, and how many program records."""
    wanted = sorted({trace for trace in traces if trace})
    found: dict = {}
    for start in range(0, len(wanted), 500):
        chunk = wanted[start : start + 500]
        rows = _read(
            db_path,
            "SELECT trace, SUM(kind = 'http'), SUM(kind = 'http' AND level IN ('warning', 'error')), "
            f"SUM(kind = 'log') FROM technical WHERE trace IN ({', '.join('?' * len(chunk))}) GROUP BY trace",
            chunk,
        )
        found.update({trace: {"http": http, "problems": problems, "log": logs} for trace, http, problems, logs in rows})
    return found


def for_export(db_path: Path, traces) -> list[dict]:
    """The records of these operations, newest first, for the saved journal: one line each."""
    wanted = {trace for trace in traces if trace}
    if not wanted:
        return []
    rows = _read(
        db_path, f"SELECT {', '.join(_HEAD)} FROM technical ORDER BY id DESC LIMIT ?", [KEEP_RECORDS]
    )
    return [_head_of(row) for row in rows if row[2] in wanted]


def _read(db_path: Path, sql: str, values: list) -> list[tuple]:
    connection = sqlite3.connect(db_path, timeout=5)
    try:
        return connection.execute(sql, values).fetchall()
    finally:
        connection.close()


def _head_of(row) -> dict:
    return {**dict(zip(_HEAD[:-1], row[:-1])), **json.loads(row[-1])}
