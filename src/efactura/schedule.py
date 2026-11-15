"""When the program downloads invoices by itself: the rules, kept apart from anything that runs.

The person picks days of the week and times of day. Nothing here contacts ANAF, starts a
thread or touches the page: every function takes the clock as an argument, so the rules can
be tested by moving it by hand.

Every moment is the PC's own clock, without a time zone, to the second
(`YYYY-MM-DDTHH:MM:SS`). Day 0 is Monday.

A moment of the schedule is a "slot". At most one run is due per slot: the latest slot that
has come, when no record says it was already run. A slot that passed while the PC was off is
made up once, and only the latest of several is. A run that could not reach ANAF, or whose
record never got its end, is tried again a quarter of an hour later, up to four attempts in
all; the next slot drops whatever attempts the one before was still owed. A slot that was
already past when the schedule was saved never runs.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Callable

from . import journal
from .config import Config
from .errors import INTERNAL_ERROR, INVALID_INPUT, EfacturaError
from .store import Store

log = logging.getLogger(__name__)

SETTING = "auto_sync"  # in the settings table: when to download by itself
LAST_RUN = "auto_sync_last_run"  # how the last automatic download went
RETRY_AFTER = timedelta(minutes=15)
MAX_ATTEMPTS = 4
MAX_TIMES = 4
CUT_OFF = ("running", "interrupted")  # a record whose run never wrote its end

_TIME = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


@dataclass(frozen=True)
class Schedule:
    enabled: bool = False
    days: tuple[int, ...] = (0, 1, 2, 3, 4)  # 0 is Monday
    times: tuple[str, ...] = ("08:00",)
    saved_at: str | None = None  # the PC's clock, to the second


def _refuse(message: str) -> EfacturaError:
    return EfacturaError(INVALID_INPUT, message)


def checked(enabled, days, times) -> Schedule:
    """A schedule with its days and times sorted, or invalid_input saying which rule it broke."""
    if not isinstance(enabled, bool):
        raise _refuse("The schedule must be either on or off.")
    if not isinstance(days, (list, tuple)):
        raise _refuse("The days must be a list.")
    if any(not isinstance(day, int) or isinstance(day, bool) or not 0 <= day <= 6 for day in days):
        raise _refuse("Each day must be a number from 0 (Monday) to 6 (Sunday).")
    if len(set(days)) != len(days):
        raise _refuse("A day may be listed only once.")
    if enabled and not days:
        raise _refuse("A schedule that is on needs at least one day.")
    if not isinstance(times, (list, tuple)):
        raise _refuse("The times must be a list.")
    if not 1 <= len(times) <= MAX_TIMES:
        raise _refuse(f"There must be between 1 and {MAX_TIMES} times.")
    if any(not isinstance(time, str) or not _TIME.fullmatch(time) for time in times):
        raise _refuse("Each time must be written HH:MM, from 00:00 to 23:59.")
    if len(set(times)) != len(times):
        raise _refuse("A time may be listed only once.")
    return Schedule(enabled, tuple(sorted(days)), tuple(sorted(times)), None)


def read(store: Store) -> Schedule:
    """The stored schedule; Schedule() (off) when nothing readable is stored."""
    try:
        stored = json.loads(store.get_setting(SETTING) or "")
        saved_at = stored.get("saved_at")
        if saved_at is not None and datetime.fromisoformat(saved_at).tzinfo is not None:
            return Schedule()  # the clock is kept without a zone; one with a zone cannot be compared
        return replace(checked(stored["enabled"], stored["days"], stored["times"]), saved_at=saved_at)
    except (ValueError, TypeError, KeyError, AttributeError, EfacturaError):
        return Schedule()


def save(store: Store, schedule: Schedule, clock: datetime) -> Schedule:
    """Store the schedule stamped with the clock, so a slot already past is never made up."""
    saved = replace(schedule, saved_at=clock.isoformat(timespec="seconds"))
    store.set_setting(
        SETTING,
        json.dumps(
            {"enabled": saved.enabled, "days": list(saved.days), "times": list(saved.times), "saved_at": saved.saved_at}
        ),
    )
    return saved


def last_run(store: Store) -> dict | None:
    """The record of the last automatic download; None when nothing readable is stored."""
    try:
        record = json.loads(store.get_setting(LAST_RUN) or "")
    except ValueError:
        return None
    if not isinstance(record, dict):
        return None
    for field in ("slot", "started_at", "finished_at"):
        text = record.get(field)
        if text is not None and ((moment := _moment(text)) is None or moment.tzinfo is not None):
            return None  # the clock is kept without a zone; a moment with one cannot be compared
    return record


def record_run(store: Store, record: dict) -> None:
    store.set_setting(LAST_RUN, json.dumps(record))


def local_clock(now: datetime | None = None) -> datetime:
    """The PC's own clock: no time zone, no fraction of a second."""
    return (now or datetime.now()).astimezone().replace(tzinfo=None, microsecond=0)


def _slots_on(schedule: Schedule, day: datetime) -> list[datetime]:
    if day.weekday() not in schedule.days:
        return []
    return [
        day.replace(hour=int(time[:2]), minute=int(time[3:]), second=0, microsecond=0) for time in schedule.times
    ]


def latest_slot(schedule: Schedule, clock: datetime) -> datetime | None:
    """The last slot not after the clock, looking back a week. Ignores `enabled`."""
    found = [
        slot
        for back in range(8)
        for slot in _slots_on(schedule, clock - timedelta(days=back))
        if slot <= clock
    ]
    return max(found, default=None)


def next_slot(schedule: Schedule, clock: datetime) -> datetime | None:
    """The first slot after the clock, looking ahead a week. Ignores `enabled`."""
    found = [
        slot
        for ahead in range(8)
        for slot in _slots_on(schedule, clock + timedelta(days=ahead))
        if slot > clock
    ]
    return min(found, default=None)


def _moment(text) -> datetime | None:
    try:
        return datetime.fromisoformat(text)
    except (ValueError, TypeError):
        return None


def _after_saving(schedule: Schedule, moment: datetime | None) -> bool:
    """Whether a moment may count: it is after the schedule was last saved (a save starts afresh)."""
    saved_at = _moment(schedule.saved_at)
    return moment is not None and (saved_at is None or moment > saved_at)


def retry_at(schedule: Schedule, last: dict | None, clock: datetime) -> datetime | None:
    """When the latest slot is tried again, or None when it is not owed another attempt."""
    if not schedule.enabled or last is None:
        return None
    slot = latest_slot(schedule, clock)
    if slot is None or not _after_saving(schedule, slot) or _moment(last.get("slot")) != slot:
        return None
    if last.get("status") != "unreachable" and last.get("status") not in CUT_OFF:
        return None
    attempt = last.get("attempt")
    if not isinstance(attempt, int) or attempt >= MAX_ATTEMPTS:
        return None
    began = _moment(last.get("finished_at")) or _moment(last.get("started_at"))
    return None if began is None else began + RETRY_AFTER


def due(schedule: Schedule, last: dict | None, clock: datetime) -> tuple[datetime, int] | None:
    """The slot to run now and which attempt it is, or None when nothing is due."""
    if not schedule.enabled:
        return None
    slot = latest_slot(schedule, clock)
    if slot is None:
        return None
    if not _after_saving(schedule, slot):
        return None
    done = _moment(last.get("slot")) if last else None
    if done is None or done < slot:
        return slot, 1
    if done > slot:
        return None
    again = retry_at(schedule, last, clock)
    if again is None or again > clock:
        return None
    return slot, last["attempt"] + 1


# --- running it ------------------------------------------------------------------------------

_lock = threading.Lock()
_running: dict | None = None  # the run in progress in this program: started_at, done, total
_AUTO_LEVELS = {"ok": "info", "partial": "warning", "failed": "error", "unreachable": "error"}


def _text(moment: datetime | None) -> str | None:
    return None if moment is None else moment.isoformat(timespec="seconds")


def _in_progress() -> dict | None:
    with _lock:
        return None if _running is None else dict(_running)


def _progress(done: int, total: int) -> None:
    with _lock:
        if _running is not None:
            _running["done"], _running["total"] = done, total


def _write_record(cfg: Config, record: dict) -> None:
    store = Store(cfg.db_path)
    try:
        record_run(store, record)
    finally:
        store.close()


def status(cfg: Config, now: datetime | None = None) -> dict:
    """What the page shows: the schedule, the next moment, the run in progress, the last run."""
    clock = local_clock(now)
    store = Store(cfg.db_path)
    try:
        current, last = read(store), last_run(store)
        on, off = store.client_switch_counts()
    finally:
        store.close()
    running = _in_progress()
    if last is not None:
        if last.get("status") == "running" and running is None:
            # The record was read before the memory: a run may have ended in between. The
            # memory is cleared after the final write, so a second read is conclusive.
            store = Store(cfg.db_path)
            try:
                again = last_run(store)
            finally:
                store.close()
            if again is not None and again.get("status") == "running":
                last = {**again, "status": "interrupted"}  # its program ended before it wrote its end
            elif again is not None:
                last = again
        retry = None if running is not None else retry_at(current, last, clock)
        last = {**last, "retry_at": _text(retry)}
    return {
        "ok": True,
        "enabled": current.enabled,
        "days": list(current.days),
        "times": list(current.times),
        "next_at": _text(next_slot(current, clock)) if current.enabled else None,
        "running": running,
        "last_run": last,
        "clients_on": on,
        "clients_off": off,
    }


def run_if_due(
    cfg: Config, now: datetime | None = None, make_service: Callable[[Config], "Service"] | None = None
) -> dict | None:
    """Download for every client that is on when the schedule says a moment has come.
    Answers the record of the run it made, or None. Never raises: nobody is watching."""
    global _running
    try:
        clock = local_clock(now)
        store = Store(cfg.db_path)
        try:
            found = due(read(store), last_run(store), clock)
        finally:
            store.close()
        if found is None:
            return None
        with _lock:
            if _running is not None:
                return None
            _running = {"started_at": _text(clock), "done": 0, "total": 0}
        try:
            with journal.trace(fresh=True) as trace:
                return _run(cfg, now, make_service, clock, found, trace)
        finally:
            with _lock:
                _running = None
    except Exception:
        log.exception("The automatic download could not be run")
        return None


def _run(cfg, now, make_service, clock, found, trace) -> dict:
    from .service import Service  # service.py imports this module

    slot, attempt = found
    record = {
        "slot": _text(slot), "attempt": attempt, "started_at": _text(clock), "finished_at": None,
        "status": "running", "clients": 0, "failed_clients": 0, "new": 0, "review": 0,
        "error": None, "trace": trace,
    }
    journal.configure(cfg.db_path)
    _write_record(cfg, record)
    journal.record(
        "sync", "sync.auto_started", f"Automatic download started for {record['slot']} (attempt {attempt}).",
        slot=record["slot"], attempt=attempt,
    )
    began = time.monotonic()
    service = None
    try:
        service = (make_service or Service)(cfg)
        answer = service.sync_all(progress=_progress)
    except Exception as exc:
        log.exception("The automatic download failed")
        answer = {"status": "failed", "error": {"code": INTERNAL_ERROR, "message": repr(exc)}}
    finally:
        if service is not None:
            try:
                service.close()
            except Exception:
                log.exception("The service could not be closed after the automatic download")
    error = answer.get("error")
    if error is None and answer.get("stopped_by"):
        error = next(
            (r["error"] for r in reversed(answer["results"]) if not r["ok"] and r["error"]["code"] == answer["stopped_by"]),
            {"code": answer["stopped_by"], "message": answer["stopped_by"]},
        )
    if error is None and answer["status"] in ("failed", "unreachable"):
        error = next((r["error"] for r in answer.get("results", []) if not r["ok"] and r.get("error")), None)
    record.update(
        finished_at=_text(local_clock(now)), status=answer["status"],
        clients=answer.get("clients", 0), failed_clients=answer.get("failed_clients", 0),
        new=answer.get("new", 0), review=answer.get("review", 0), error=error,
    )
    try:
        _write_record(cfg, record)
    except Exception as exc:
        journal.record(
            "sync", "sync.record_unsaved",
            f"The automatic download ended as {record['status']}, but its record could not be saved: {exc!r}.",
            level="error", slot=record["slot"], attempt=attempt, status=record["status"],
        )
    journal.record(
        "sync", "sync.auto_finished",
        f"Automatic download for {record['slot']} ended as {record['status']}.",
        level=_AUTO_LEVELS.get(record["status"], "error"),
        slot=record["slot"], attempt=attempt, status=record["status"], clients=record["clients"],
        failed_clients=record["failed_clients"], new=record["new"], review=record["review"],
        error=error["code"] if error else None, duration_ms=round((time.monotonic() - began) * 1000),
    )
    return record
