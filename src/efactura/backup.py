"""Copies of the database in a folder the person chose, putting one back, and starting again
from zero.

A copy is made when asked for and by itself every 24 hours. At most 25 are kept: when a
new one arrives, the oldest goes. Only files this program made are ever deleted, known by
their names.

Each copy is one zip holding the whole database. It is made with SQLite's own copy, so it
is complete while the program runs, checked before it is kept, and written under a
temporary name first, so a half-written file is never taken for a backup.

Starting from zero ("Șterge toate datele") makes a copy first, reads it back from the folder
and checks it whole; only then is anything deleted, and only the rows (store.WIPED): the
settings, the journal and every file on disk stay.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from . import background, journal
from .config import Config
from . import store as stored
from .errors import BACKUP_ERROR, BUSY, INVALID_INPUT, SNAPSHOT_TOO_NEW, EfacturaError
from .service import _FileLock
from .store import SCHEMA_VERSION, Store

MAX_SNAPSHOTS = 25
EVERY = timedelta(hours=24)
KINDS = ("auto", "manual", "before-restore", "before-wipe")
INSIDE = "efactura.db"  # the database's name inside each zip

FOLDER = "backup_folder"  # in the settings table
LAST_FAILURE = "backup_last_failure"
RESTORE_RECORD = "last-restore.json"  # in the data folder: how the last restore ended, for the page
RESTORE_OUTPUT = "restore.log"
RESTORE_LOCK = "restore.lock"  # held by a restore and by a wipe

# How long a file that Windows says is in use is tried again. A program that was just
# stopped lets go of its files a moment after it stops answering.
FILE_ATTEMPTS = 20
FILE_RETRY_DELAY = 0.25
HALF_WRITTEN_AFTER = timedelta(hours=1)  # a .partial older than this was left by a crash

_STAMP = "%Y%m%d-%H%M%S"
_KIND = "|".join(re.escape(kind) for kind in KINDS)
_NAME = re.compile(rf"autosaga-(\d{{8}}-\d{{6}})-({_KIND})\.zip")  # matched whole
_HALF_WRITTEN = re.compile(rf"autosaga-(\d{{8}}-\d{{6}})-(?:{_KIND})\.zip\.partial")
_SQLITE_HEADER = b"SQLite format 3\x00"

log = logging.getLogger(__name__)


# --- the folder ---------------------------------------------------------------------------------


def set_folder(cfg: Config, folder: str) -> dict:
    """Choose where the copies go. The folder is made if it is not there."""
    chosen = Path(str(folder or "").strip())
    if not str(folder or "").strip() or not chosen.is_absolute():
        raise EfacturaError(INVALID_INPUT, "Give the whole path of a folder, such as E:\\Copii AutoSaga.")
    try:
        chosen.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise EfacturaError(INVALID_INPUT, f"That folder cannot be used: {exc}") from None
    _setting(cfg, FOLDER, str(chosen))
    journal.record("backup", "backup.folder_set", f"Backups now go to {chosen}.", folder=str(chosen))
    return status(cfg)


def status(cfg: Config, now: datetime | None = None) -> dict:
    """Everything the backups screen shows."""
    now = now or datetime.now().astimezone()
    folder, failure = _settings(cfg, FOLDER, LAST_FAILURE)
    kept = snapshots(Path(folder)) if folder else []
    clock = now.replace(tzinfo=None)  # snapshots are named by the PC's own clock
    last = _newest_made_by(kept, clock)
    if last:
        next_due = datetime.fromisoformat(last) + EVERY
    else:
        next_due = clock if folder else None
    return {
        "ok": True,
        "folder": folder,
        "folder_found": bool(folder) and Path(folder).is_dir(),
        "snapshots": kept,
        "count": len(kept),
        "max": MAX_SNAPSHOTS,
        "last_at": last,
        "next_due_at": next_due.isoformat(timespec="seconds") if next_due else None,
        "due_now": next_due is not None and next_due <= clock,  # the next look of the background job makes one
        "last_failure": json.loads(failure) if failure else None,
        "last_restore": _last_restore(cfg),
    }


def snapshots(folder: Path) -> list[dict]:
    """The copies in the folder, the newest first. Other files there are not listed."""
    found = []
    for path in (folder.iterdir() if folder.is_dir() else ()):
        named = _NAME.fullmatch(path.name)
        taken = _stamp_of(named.group(1)) if named else None
        if taken and path.is_file():  # a name with no real date in it (renamed by hand) is not one of ours
            found.append({"name": path.name, "at": taken.isoformat(), "kind": named.group(2), "size": path.stat().st_size})
    return sorted(found, key=lambda each: each["name"], reverse=True)


def _stamp_of(written: str) -> datetime | None:
    try:
        return datetime.strptime(written, _STAMP)
    except ValueError:
        return None


def _newest_made_by(kept: list[dict], clock: datetime) -> str | None:
    """When the newest copy was made, leaving out any named later than now. Those were made
    while the PC's clock was ahead; counting from them would stop the daily copy until
    that date came round."""
    return next((each["at"] for each in kept if datetime.fromisoformat(each["at"]) <= clock), None)


# --- making a copy ------------------------------------------------------------------------------


def snapshot(cfg: Config, kind: str = "manual", now: datetime | None = None, never_remove: str | None = None) -> dict:
    """Make one copy now, then keep the newest MAX_SNAPSHOTS."""
    now = now or datetime.now().astimezone()
    try:
        made = _make(cfg, kind, now)
    except EfacturaError as exc:
        _setting(cfg, LAST_FAILURE, json.dumps({"at": now.isoformat(), "error": exc.message}))
        (folder,) = _settings(cfg, FOLDER)
        journal.record("backup", "backup.failed", f"The backup failed: {exc.message}", level="error",
                       kind=kind, folder=folder, folder_found=bool(folder) and Path(folder).is_dir(), error=exc.message)
        raise
    size = made.stat().st_size
    _setting(cfg, LAST_FAILURE, "")
    removed = _keep_the_newest(made.parent, now, {made.name, never_remove})
    journal.record("backup", "backup.made", f"Backup {made.name} made.", kind=kind, name=made.name, size=size)
    if removed:
        journal.record("backup", "backup.removed_old", f"{len(removed)} old backup(s) removed.", removed=len(removed))
    return {"ok": True, "name": made.name, "kind": kind, "size": size, "removed": removed}


def run_if_due(cfg: Config, now: datetime | None = None) -> dict | None:
    """What the background job calls: a copy if 24 hours have passed since the last good
    one, whoever made it. Never raises; a failure is kept for the screen to show."""
    now = now or datetime.now().astimezone()
    try:
        (folder,) = _settings(cfg, FOLDER)
        if not folder:
            return None
        clock = now.replace(tzinfo=None)
        last = _newest_made_by(snapshots(Path(folder)), clock)
        if last and clock - datetime.fromisoformat(last) < EVERY:
            return None
        return snapshot(cfg, "auto", now)
    except EfacturaError:
        return None  # snapshot() has recorded why
    except Exception:  # nobody is watching where this runs: say what happened and carry on
        log.exception("The daily backup could not be made")
        return None


def _make(cfg: Config, kind: str, now: datetime) -> Path:
    (folder,) = _settings(cfg, FOLDER)
    if not folder:
        raise EfacturaError(BACKUP_ERROR, "Choose a folder for the backups first.")
    target = Path(folder)
    if not target.is_dir():
        raise EfacturaError(BACKUP_ERROR, f"The backup folder was not found: {target}")
    if kind not in KINDS:
        raise EfacturaError(INVALID_INPUT, f"kind must be one of: {', '.join(KINDS)}.")
    final = target / f"autosaga-{now.strftime(_STAMP)}-{kind}.zip"
    partial = final.with_name(final.name + ".partial")
    try:
        _clear_half_written(target, now)
        # ignore_cleanup_errors: a scanner still reading the scratch copy must not undo a good backup.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as scratch:
            copy = Path(scratch) / INSIDE
            copy_database(cfg.db_path, copy)
            if not _is_sound(copy):
                raise EfacturaError(BACKUP_ERROR, "The copy of the database did not pass SQLite's check; it was not kept.")
            with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.write(copy, INSIDE)
        with zipfile.ZipFile(partial) as archive:
            if archive.testzip() is not None:
                raise EfacturaError(BACKUP_ERROR, "The backup file could not be read back; it was not kept.")
        os.rename(partial, final)  # only now does it count as a backup
    except (OSError, sqlite3.Error, zipfile.BadZipFile) as exc:
        raise EfacturaError(BACKUP_ERROR, f"The backup could not be written to {target}: {exc}") from None
    finally:
        _remove(partial)
    return final


def _clear_half_written(folder: Path, now: datetime) -> None:
    """Remove what a copy that never finished left behind (the PC was switched off). One
    being written this minute by another process is left alone."""
    clock = now.replace(tzinfo=None)
    for path in folder.iterdir():
        named = _HALF_WRITTEN.fullmatch(path.name)
        begun = _stamp_of(named.group(1)) if named else None
        if begun and clock - begun > HALF_WRITTEN_AFTER:
            _remove(path)


def _remove(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass  # in use by another program; it is not worth failing over


def copy_database(source: Path, target: Path) -> None:
    """SQLite's own copy: complete even while the program is writing."""
    reading, writing = sqlite3.connect(source), sqlite3.connect(target)
    try:
        with writing:
            reading.backup(writing)
    finally:
        reading.close()
        writing.close()


def _is_sound(database: Path) -> bool:
    connection = sqlite3.connect(database)
    try:
        has_messages = connection.execute("SELECT 1 FROM sqlite_master WHERE name = 'messages'").fetchone()
        return bool(has_messages) and connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    except sqlite3.Error:
        return False
    finally:
        connection.close()


def _keep_the_newest(folder: Path, now: datetime, never_remove: set) -> list[str]:
    """Delete the oldest copies beyond MAX_SNAPSHOTS and say which went.

    Copies named later than now (made while the clock was ahead) count as the oldest: going
    by their names alone, a copy made today would be the first to go."""
    clock = now.replace(tzinfo=None)
    newest_first = sorted(
        snapshots(folder), key=lambda each: (datetime.fromisoformat(each["at"]) <= clock, each["name"]), reverse=True
    )
    removed = []
    for old in newest_first[MAX_SNAPSHOTS:]:
        if old["name"] in never_remove:
            continue
        try:
            (folder / old["name"]).unlink(missing_ok=True)
        except OSError:
            continue  # open in another program: the copy that was made is made, this one goes next time
        removed.append(old["name"])
    return removed


# --- putting a copy back ------------------------------------------------------------------------


def restore(cfg: Config, name: str, now: datetime | None = None) -> dict:
    """Replace the database with a snapshot.

    `name` is a file in the backup folder. From the terminal it may also be the whole path of
    a snapshot, which works even when the database can no longer be read (and with it, where
    the backup folder is).

    The program is stopped first and started again afterwards. What was there is kept: as a
    copy in the backup folder or, when no sound copy can be made (the folder is gone, the
    database is damaged), as the file itself, beside the new one. If the snapshot cannot be
    put in place, the database that was there is left untouched.
    """
    now, name = now or datetime.now().astimezone(), str(name)
    with _one_at_a_time(cfg), _no_update_running(cfg):
        try:
            done = _replace_with(cfg, name, now)
        except Exception as exc:
            # However early it failed, the page that started it is waiting to be told. Nothing
            # raises once the database has been replaced, so "left as it was" is always true.
            failure, short = _said(exc), Path(name).name
            _write_restore_record(cfg, {"at": now.isoformat(), "ok": False, "name": short, "error": failure})
            journal.record("backup", "restore.failed", f"Restoring {short} failed: {failure}", level="error", name=short, error=failure)
            raise EfacturaError(BACKUP_ERROR, f"The restore failed and the database was left as it was. {failure}") from None
        short = done["name"]
        _write_restore_record(cfg, {"at": now.isoformat(), "ok": True, "name": short, "error": None})
        if done["kept_aside"]:
            journal.record(
                "backup", "restore.kept_aside",
                f"No copy of the old database could be made in the backup folder ({done['kept_aside']}); "
                f"the file itself was kept as {done['kept_as']}.",
                level="warning", kept_as=done["kept_as"], error=done["kept_aside"],
            )
        journal.record("backup", "restore.finished", f"The database was restored from {short}.", name=short, kept_as=done["kept_as"])
        if done["not_started"]:
            # The restore itself is done; saying it failed would send the person to do it again.
            journal.record("backup", "restore.not_restarted", f"After the restore the program did not start again: {done['not_started']}",
                           level="warning", error=done["not_started"])
        return {"ok": True, "restored": short, "kept_as": done["kept_as"], "restarted": done["restarted"]}


def _replace_with(cfg: Config, name: str, now: datetime) -> dict:
    """The restore itself. Raises when the database was not replaced, and only then."""
    folder, readable = _known_folder(cfg)
    chosen = _chosen(name, folder, readable)
    staged = cfg.db_path.with_name(cfg.db_path.name + ".restoring")
    failure = kept_as = kept_aside = not_started = None
    restarted = False
    # ignore_cleanup_errors: a scanner still reading the scratch copy must not fail a finished restore.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as scratch:
        try:
            # Everything that can be refused is refused before the program is touched.
            try:
                with zipfile.ZipFile(chosen) as archive:
                    opened = Path(archive.extract(INSIDE, scratch))
            except (OSError, KeyError, zipfile.BadZipFile) as exc:
                raise EfacturaError(BACKUP_ERROR, f"{chosen.name} could not be opened: {exc}") from None
            if not _is_sound(opened):
                raise EfacturaError(BACKUP_ERROR, f"{chosen.name} does not hold a database this program can use.")
            _refuse_if_newer(chosen.name, _version_of(opened))
            # Backups go on to the same folder, whatever the snapshot remembered.
            _stage(opened, staged, folder if readable else str(chosen.parent))
            _bring_up_to_date(staged)

            with _no_download_running(cfg):
                was_running = background.stop(cfg)["stopped"]
                try:
                    kept_as, kept_aside = _keep_what_is_there(cfg, now, chosen.name)
                    try:
                        _swap(cfg, staged)
                    except Exception:
                        if kept_aside:
                            _bring_back(cfg, kept_as)
                        raise
                except Exception as exc:
                    failure = _said(exc)
                # Started again whatever happened in between: it was running before.
                if was_running:
                    try:
                        restarted = background.start(cfg, cfg.path)["ok"]
                    except Exception as exc:
                        not_started = _said(exc)
        finally:
            for leftover in ("", "-wal", "-shm"):
                _remove(staged.with_name(staged.name + leftover))
    if failure:
        raise EfacturaError(BACKUP_ERROR, failure + (f" The program did not start again: {not_started}" if not_started else ""))
    return {"name": chosen.name, "kept_as": kept_as, "kept_aside": kept_aside, "restarted": restarted, "not_started": not_started}


def start_restore_in_background(cfg: Config, name: str) -> dict:
    """What the page's button does: the restore has to stop the program, so it runs as a
    process of its own and leaves a record the page reads when the program is back. What can
    be refused at once is refused here, so the person is told on the spot."""
    chosen = _snapshot_named(cfg, name)
    _refuse_if_newer(chosen.name, _version_inside(chosen))
    with _no_download_running(cfg):  # said here, to the person, not found out by the other process
        pass
    background.spawn_command(cfg.path, cfg.data_dir / RESTORE_OUTPUT, "restore", name)
    return {"ok": True, "started": True}


def _known_folder(cfg: Config) -> tuple[str | None, bool]:
    """The backup folder, and whether the database could be read at all to find it."""
    try:
        return _settings(cfg, FOLDER)[0], True
    except sqlite3.Error:
        return None, False


def _chosen(name: str, folder: str | None, readable: bool) -> Path:
    given = Path(name)
    if given.is_absolute():  # from the terminal only: the page can name nothing but a file in the folder
        if _NAME.fullmatch(given.name) and given.is_file():
            return given
        raise EfacturaError(BACKUP_ERROR, f"{name} is not a backup made by this program.")
    if not readable:
        raise EfacturaError(
            BACKUP_ERROR,
            "The database cannot be read, so the backup folder is not known. Give the whole path of the "
            "backup file instead of its name, such as E:\\Copii AutoSaga\\autosaga-20261114-090000-auto.zip.",
        )
    # The name is matched whole, so it cannot point out of the folder or at another file.
    if not folder or not _NAME.fullmatch(name) or not (Path(folder) / name).is_file():
        raise EfacturaError(BACKUP_ERROR, f"There is no backup named {name!r} in the backup folder.")
    return Path(folder) / name


def _snapshot_named(cfg: Config, name: str) -> Path:
    (folder,) = _settings(cfg, FOLDER)
    if Path(str(name)).is_absolute():
        raise EfacturaError(BACKUP_ERROR, f"There is no backup named {name!r} in the backup folder.")
    return _chosen(str(name), folder, True)


def _stage(snapshot_database: Path, staged: Path, folder: str | None) -> None:
    """The snapshot as the database it is about to become, next to the one in use."""
    try:
        copy_database(snapshot_database, staged)
        connection = sqlite3.connect(staged)
        try:
            with connection:
                if folder:
                    connection.execute(
                        "INSERT INTO settings (key, value) VALUES (?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (FOLDER, folder),
                    )
                # A failure noted when the snapshot was made is long over.
                connection.execute("DELETE FROM settings WHERE key = ?", (LAST_FAILURE,))
        finally:
            connection.close()
    except (OSError, sqlite3.Error) as exc:
        raise EfacturaError(BACKUP_ERROR, f"The snapshot could not be made ready: {exc}") from None


def _version_of(database: Path) -> int:
    connection = sqlite3.connect(database)
    try:
        return connection.execute("PRAGMA user_version").fetchone()[0]
    finally:
        connection.close()


def _version_inside(snapshot_zip: Path) -> int | None:
    """The database version a copy carries (SQLite's user_version, bytes 60 to 63 of the
    file), read from the start of the file inside the zip, without unpacking it all. None
    when it cannot be read so: the restore itself then says what is wrong with the copy."""
    try:
        with zipfile.ZipFile(snapshot_zip) as archive, archive.open(INSIDE) as inside:
            header = inside.read(100)
    except (OSError, KeyError, zipfile.BadZipFile, RuntimeError):
        return None
    if len(header) < 100 or not header.startswith(_SQLITE_HEADER):
        return None
    return int.from_bytes(header[60:64], "big")


def _refuse_if_newer(name: str, version: int | None) -> None:
    """A newer version may have changed what the tables mean; this one would bring the copy
    "up to date" downwards and lose what it does not know."""
    if version is not None and version > SCHEMA_VERSION:
        raise EfacturaError(
            SNAPSHOT_TOO_NEW,
            f"{name} was made by a newer version of the program (database version {version}; "
            f"this one reads up to {SCHEMA_VERSION}). Update the program, then restore it.",
        )


def _bring_up_to_date(staged: Path) -> None:
    """A copy made by an earlier version gets the columns and tables added since, as the
    program would add them on starting, but here, while the database in use is untouched:
    one that cannot be brought up to date is refused instead of stopping the program."""
    try:
        Store(staged).close()
        connection = sqlite3.connect(staged)
        try:
            connection.execute("PRAGMA journal_mode=DELETE")  # all of it in the one file that is moved
        finally:
            connection.close()
    except Exception as exc:
        raise EfacturaError(BACKUP_ERROR, f"The snapshot could not be brought up to date: {_said(exc)}") from None


def _keep_what_is_there(cfg: Config, now: datetime, never_remove: str) -> tuple[str | None, str | None]:
    """Keep the database that is about to be replaced. Returns the name it was kept under
    and, when it had to be the file itself, why no copy could be made."""
    try:
        return snapshot(cfg, "before-restore", now, never_remove=never_remove)["name"], None
    except Exception as exc:
        why = _said(exc)
    aside = cfg.db_path.with_name(f"{cfg.db_path.name}.replaced-{now.strftime(_STAMP)}")
    moved = []
    try:
        for suffix in ("", "-wal", "-shm"):
            old = cfg.db_path.with_name(cfg.db_path.name + suffix)
            if old.exists():
                _retrying(os.replace, old, aside.with_name(aside.name + suffix))
                moved.append(suffix)
    except OSError as exc:
        _bring_back(cfg, aside.name, moved)
        raise EfacturaError(BACKUP_ERROR, f"The database that is there could not be kept ({why}), nor moved aside: {exc}") from None
    return (aside.name if moved else None), why


def _bring_back(cfg: Config, aside_name: str, suffixes=("", "-wal", "-shm")) -> None:
    """Undo _keep_what_is_there's move, as far as it goes."""
    for suffix in suffixes:
        aside = cfg.db_path.with_name(aside_name + suffix)
        try:
            if aside.exists():
                os.replace(aside, cfg.db_path.with_name(cfg.db_path.name + suffix))
        except OSError:
            log.error("%s could not be put back; the database that was replaced is in that file.", aside)


def _swap(cfg: Config, staged: Path) -> None:
    try:
        # What SQLite had not yet folded into the old file would be applied to the new one.
        for leftover in ("-wal", "-shm"):
            _retrying(cfg.db_path.with_name(cfg.db_path.name + leftover).unlink, missing_ok=True)
        _retrying(os.replace, staged, cfg.db_path)
    except OSError as exc:
        raise EfacturaError(BACKUP_ERROR, f"The snapshot could not be put in place: {exc}") from None


def _retrying(action, *args, **kwargs):
    """Windows refuses to touch a file another program has open. Tried again for a few seconds."""
    for attempt in range(FILE_ATTEMPTS):
        try:
            return action(*args, **kwargs)
        except PermissionError:
            if attempt == FILE_ATTEMPTS - 1:
                raise
            background.pause(FILE_RETRY_DELAY)


def _said(exc: Exception) -> str:
    return exc.message if isinstance(exc, EfacturaError) else f"{type(exc).__name__}: {exc}"


def _one_at_a_time(cfg: Config) -> _FileLock:
    """One restore or one wipe at a time: both replace what the database holds."""
    return held_or_busy(cfg.data_dir / RESTORE_LOCK, "A restore or a wipe of the data is already running.")


def no_restore_running(cfg: Config) -> _FileLock:
    """For the update, which stops and starts the program too."""
    return held_or_busy(cfg.data_dir / RESTORE_LOCK, "A restore or a wipe of the data is running. Wait for it to finish.")


def _no_update_running(cfg: Config) -> _FileLock:
    return held_or_busy(cfg.data_dir / "update.lock", "An update is running. Wait for it to finish, then restore.")


def _no_download_running(cfg: Config) -> _FileLock:
    """Held across the swap: a download writes to the database for minutes, and stopping
    the program does not stop one that is under way."""
    return held_or_busy(cfg.lock_path, "Invoices are being downloaded or classified. Wait for that to finish, then restore.")


def held_or_busy(path: Path, busy: str) -> _FileLock:
    class _Lock(_FileLock):
        def __enter__(self):
            try:
                return super().__enter__()
            except EfacturaError:
                raise EfacturaError(BUSY, busy) from None

    return _Lock(path)


# --- starting again from zero ---------------------------------------------------------------------


def wipe(cfg: Config, now: datetime | None = None) -> dict:
    """Delete every client, invoice, account and rule (store.WIPED), after a copy of it all.

    The copy is made in the backup folder, read back from there and checked whole; if any of
    that fails, nothing is deleted. The settings, the keys typed on screen, the journal, the
    connection to ANAF, config.toml and every file on disk stay. The example accounts and
    rules come back, as on the first day.

    It runs inside the program, which goes on running: the database file stays where it is,
    so there is nothing for Windows to refuse, and the next request already reads the empty
    database. Refused while a download, a classification, a restore, an update or a write of
    the files for SAGA is under way.
    """
    now = now or datetime.now().astimezone()
    try:
        with (
            _one_at_a_time(cfg),
            held_or_busy(cfg.data_dir / "update.lock", "An update is running. Wait for it to finish, then try again."),
            held_or_busy(cfg.lock_path, "Invoices are being downloaded or classified. Wait for that to finish, then try again."),
            held_or_busy(cfg.saga_lock_path, "The files for SAGA are being written. Wait a moment, then try again."),
        ):
            kept = snapshot(cfg, "before-wipe", now)["name"]
            (folder,) = _settings(cfg, FOLDER)
            expected = check_snapshot(Path(folder) / kept)
            store = Store(cfg.db_path)
            try:
                deleted = store.wipe(expected)
            finally:
                store.close()
    except Exception as exc:
        failure = _said(exc)
        busy = isinstance(exc, EfacturaError) and exc.code == BUSY
        journal.record("backup", "wipe.failed", f"The data was not deleted: {failure}",
                       level="warning" if busy else "error", error=failure)
        if busy:
            raise
        raise EfacturaError(BACKUP_ERROR, f"Nothing was deleted. {failure}") from None
    _compact(cfg)
    journal.record(
        "backup", "wipe.finished",
        f"Every client, invoice, account and rule was deleted. The copy made just before is {kept}.",
        kept_as=kept, deleted=deleted,
    )
    # When the copy was made, as the list of copies gives it: the PC's own clock, read from its name.
    kept_at = _stamp_of(_NAME.fullmatch(kept).group(1)).isoformat()
    return {"ok": True, "kept_as": kept, "kept_at": kept_at, "deleted": deleted}


def check_snapshot(path: Path) -> dict[str, int]:
    """Open a copy in the folder as a restore would, and check all of it: SQLite's full check,
    every table this program has, and how many rows each table a wipe empties holds."""
    expected_tables = set(stored.WIPED) | set(stored.KEPT_BY_WIPE)
    try:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as scratch:
            with zipfile.ZipFile(path) as archive:
                inside = Path(archive.extract(INSIDE, scratch))
            connection = sqlite3.connect(inside)
            try:
                verdict = connection.execute("PRAGMA integrity_check").fetchone()[0]
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
                missing = sorted(expected_tables - tables)
                rows = {} if (missing or verdict != "ok") else {
                    table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in stored.WIPED
                }
            finally:
                connection.close()
    except (OSError, KeyError, RuntimeError, zipfile.BadZipFile, sqlite3.Error) as exc:
        raise EfacturaError(BACKUP_ERROR, f"The copy {path.name} could not be read back: {exc}") from None
    if verdict != "ok":
        raise EfacturaError(BACKUP_ERROR, f"The copy {path.name} did not pass SQLite's check: {verdict}")
    if missing:
        raise EfacturaError(BACKUP_ERROR, f"The copy {path.name} lacks tables: {', '.join(missing)}.")
    return rows


def _compact(cfg: Config) -> None:
    """Give back the room the deleted rows took. Left as they are, the freed pages would still
    hold the old invoices, in the file and in every copy made from it later. It is not worth
    failing over: what was asked for is done."""
    connection = sqlite3.connect(cfg.db_path, timeout=5)
    try:
        connection.execute("VACUUM")
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.Error as exc:
        journal.record("backup", None, f"The database could not be compacted after the wipe: {exc}", level="detail")
    finally:
        connection.close()


# --- small things kept between runs --------------------------------------------------------------


def _settings(cfg: Config, *keys: str) -> list[str | None]:
    store = Store(cfg.db_path)
    try:
        return [store.get_setting(key) for key in keys]
    finally:
        store.close()


def _setting(cfg: Config, key: str, value: str) -> None:
    store = Store(cfg.db_path)
    try:
        if value:
            store.set_setting(key, value)
        else:
            store.delete_setting(key)
    finally:
        store.close()


def _write_restore_record(cfg: Config, record: dict) -> None:
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    (cfg.data_dir / RESTORE_RECORD).write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")


def _last_restore(cfg: Config) -> dict | None:
    try:
        record = json.loads((cfg.data_dir / RESTORE_RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None
