"""Moving an installed copy to the newest release, keeping its settings and its data.

An installed copy is the folder the installer cloned: a Git repository standing on a
release tag, with config.toml and the data folder beside the code. Git never lists those
two, so changing release leaves them alone, with one catch that is checked here: Git
overwrites an ignored file without a word if a release ever came to contain it.

Everything this module needs is imported at the top. Halfway through an update the files
on disk belong to the new release, and a late import would mix the two.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from . import __version__, backup, background, journal
from .config import Config
from .errors import BUSY, UPDATE_ERROR, EfacturaError
from .service import _FileLock
from .store import Store

PROJECT = Path(__file__).resolve().parents[2]  # the cloned repository this program runs from
CHECK_EVERY = timedelta(hours=12)  # how long "is there a newer release?" is remembered
BACKUPS_KEPT = 3
LATEST = "update_latest"  # in the settings table
CHECKED_AT = "update_checked_at"
RECORD = "last-update.json"  # in the data folder: how the last update ended, for the page
UPDATE_OUTPUT = "update.log"

# Seconds a step may take before it counts as failed.
LOOK_TIMEOUT = 30
FETCH_TIMEOUT = 300
SYNC_TIMEOUT = 900


def status(cfg: Config, check: bool = False, project: Path | None = None, now: datetime | None = None) -> dict:
    """Which release is installed and whether a newer one exists.

    An installed copy asks the remote when `check` is set or the last answer is older than
    CHECK_EVERY; otherwise the remembered answer is given, so opening the page does not wait
    on GitHub. A copy that cannot be updated asks only when `check` is set.
    """
    project, now = project or PROJECT, now or datetime.now().astimezone()
    why_not = _why_not_updatable(project)
    is_clone = (project / ".git").exists()
    installed = _installed_release(project)
    store = Store(cfg.db_path)
    try:
        latest, checked_at, check_error = store.get_setting(LATEST), store.get_setting(CHECKED_AT), None
        stale = checked_at is None or now - datetime.fromisoformat(checked_at) >= CHECK_EVERY
        # A development copy looks too, so the page can name the newest release; it just never
        # updates. It looks only when asked: on a development copy or the demo, the first page
        # load would otherwise wait on `git ls-remote`, up to LOOK_TIMEOUT with no network.
        if is_clone and (check or (stale and why_not is None)):
            try:
                latest = latest_release(project) or ""
                store.set_setting(LATEST, latest)
            except EfacturaError as exc:
                check_error = exc.message
            # Remembered even when it failed: an offline PC must not wait on every page.
            checked_at = now.isoformat()
            store.set_setting(CHECKED_AT, checked_at)
    finally:
        store.close()
    return {
        "ok": True,
        "version": installed or __version__,
        "installed_release": installed,
        "latest_release": latest or None,
        "update_available": why_not is None and bool(latest) and latest != installed,
        "can_update": why_not is None,
        "why_not": why_not,
        # For the page to decide on without reading the English sentence above.
        "why_not_kind": None if why_not is None else ("development" if is_clone else "not_a_clone"),
        "checked_at": checked_at,
        "check_error": check_error,
        "last_update": _last_record(cfg),
    }


def update(cfg: Config, project: Path | None = None, now: datetime | None = None) -> dict:
    """Move this installed copy to the newest release.

    The running program is stopped first and started again afterwards. If the new release
    cannot be put in place, the folder goes back to the release it had.
    """
    project, now = project or PROJECT, now or datetime.now().astimezone()
    why_not = _why_not_updatable(project)
    if why_not:
        raise EfacturaError(UPDATE_ERROR, why_not)
    with _only_one_update(cfg), backup.no_restore_running(cfg):
        installed = _installed_release(project)
        aimed_at = {"release": None}  # known once the remote has answered
        try:
            result = _move_to_latest(cfg, project, now, installed, aimed_at)
        except Exception as exc:
            # However early it failed, and whatever it was, the page that started it is waiting to be told.
            failure = _said(exc)
            _write_record(cfg, {
                "at": now.isoformat(), "ok": False, "from": installed, "to": aimed_at["release"], "error": failure,
            })
            journal.record("update", "update.failed", f"The update failed: {failure}", level="error",
                           installed=installed, release=aimed_at["release"], error=failure)
            if isinstance(exc, EfacturaError):
                raise
            raise EfacturaError(UPDATE_ERROR, f"The update failed. {failure}") from None
        _write_record(cfg, {
            "at": now.isoformat(), "ok": True, "from": installed, "to": aimed_at["release"], "error": None,
        })
        if result["updated"]:
            journal.record("update", "update.finished", f"Updated from {installed} to {aimed_at['release']}.",
                           installed=installed, release=aimed_at["release"], restarted=result["restarted"])
            if result["not_started"]:
                # The update itself is done; saying it failed would be untrue and send the person to repeat it.
                journal.record("update", "update.not_restarted",
                               f"After the update the program did not start again: {result['not_started']}",
                               level="warning", error=result["not_started"])
        return result


def _move_to_latest(cfg: Config, project: Path, now: datetime, installed: str | None, aimed_at: dict) -> dict:
    latest = latest_release(project)
    if not latest:
        raise EfacturaError(UPDATE_ERROR, "The repository has no release to update to.")
    aimed_at["release"] = latest
    _remember(cfg, latest, now)
    if latest == installed:
        return {"ok": True, "updated": False, "version": installed}

    # Everything that can fail without touching the program comes first.
    _git(project, "fetch", "--tags", "--prune", "origin", what="Fetching the release", timeout=FETCH_TIMEOUT)
    _refuse_a_release_that_replaces_local_files(project, latest, cfg)
    previous = _git(project, "rev-parse", "HEAD", what="Reading the installed release")
    # Taken before the program is stopped: stopping it does not stop a download under way, which
    # would go on writing while its code is replaced. A download running refuses the update now;
    # one that would start meanwhile waits until the new release is in place.
    with backup.held_or_busy(cfg.lock_path, "Invoices are being downloaded. Wait for that to finish, then update."):
        was_running = background.stop(cfg)["stopped"]

        failure, copy = None, None
        try:
            copy = back_up_database(cfg, installed or previous[:7], now)
            try:
                _switch_to(project, latest)
                sync_dependencies(project)
            except Exception:
                _go_back(project, previous)
                raise
        except Exception as exc:  # whatever it was, the program is started again below
            failure = _said(exc)
    restarted, not_started = False, None
    if was_running:
        try:
            restarted = background.start(cfg, cfg.path)["ok"]
        except Exception as exc:
            not_started = _said(exc)
    if failure:
        raise EfacturaError(
            UPDATE_ERROR,
            f"The update to {latest} failed and the program was put back to {installed}. {failure}"
            + (f" The program did not start again: {not_started}" if not_started else ""),
        )
    return {
        "ok": True,
        "updated": True,
        "from": installed,
        "to": latest,
        "backup": str(copy) if copy else None,
        "restarted": restarted,
        "not_started": not_started,
    }


def start_in_background(cfg: Config) -> dict:
    """What the page's button does: run `efactura update` as a process of its own. The
    program cannot replace its own files while it runs, and the update has to stop it."""
    why_not = _why_not_updatable(PROJECT)
    if why_not:
        raise EfacturaError(UPDATE_ERROR, why_not)
    # Said here, to the person, rather than found out by the process the button starts.
    with backup.held_or_busy(cfg.lock_path, "Invoices are being downloaded. Wait for that to finish, then update."):
        pass
    background.spawn_command(cfg.path, cfg.data_dir / UPDATE_OUTPUT, "update")
    return {"ok": True, "started": True}


def latest_release(project: Path) -> str | None:
    """The highest version among the remote's tags; None when it has none."""
    tags = _git(
        project, "ls-remote", "--tags", "--refs", "--sort=-v:refname", "origin",
        what="Reading the releases", timeout=LOOK_TIMEOUT,
    )
    first = tags.splitlines()[0] if tags else ""
    return first.split("refs/tags/", 1)[1] if "refs/tags/" in first else None


def back_up_database(cfg: Config, label: str, now: datetime) -> Path | None:
    """Copy the database before a new release gets to open it; keep the last few copies."""
    if not cfg.db_path.exists():
        return None
    folder = cfg.data_dir / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    safe_label = "".join(ch if ch.isalnum() or ch in ".-" else "-" for ch in label)
    copy = folder / f"efactura-{safe_label}-{now:%Y%m%d-%H%M%S}.db"
    backup.copy_database(cfg.db_path, copy)
    copies = sorted(folder.glob("efactura-*.db"), key=lambda path: (path.stat().st_mtime_ns, path.name))
    for old in copies[:-BACKUPS_KEPT]:
        old.unlink()
    return copy


def sync_dependencies(project: Path) -> None:
    """Install exactly what the release now in the folder was tested with."""
    uv = _find("uv", Path.home() / ".local" / "bin" / "uv.exe", Path.home() / ".local" / "bin" / "uv")
    _run(
        [uv, "sync", "--frozen", "--no-dev", "--project", str(project)],
        what="Installing the dependencies", timeout=SYNC_TIMEOUT,
    )


# --- the steps ---------------------------------------------------------------------------------


def _why_not_updatable(project: Path) -> str | None:
    """None for a copy the installer made; otherwise the reason this one is left alone."""
    if not (project / ".git").exists():
        return "This folder was not made by the installer, so there is nothing to update it from."
    branch = _git_quietly(project, "symbolic-ref", "--quiet", "--short", "HEAD")
    if branch:
        return f"This folder is a development copy on the branch {branch}; update it with Git."
    return None


def _installed_release(project: Path) -> str | None:
    """The release tag the folder stands on; None when it stands on none."""
    if not (project / ".git").exists():
        return None
    return _git_quietly(project, "describe", "--tags", "--exact-match", "HEAD")


def _refuse_a_release_that_replaces_local_files(project: Path, release: str, cfg: Config) -> None:
    local = [
        path.relative_to(project).as_posix()
        for path in (cfg.path, cfg.data_dir)
        if path is not None and path.is_relative_to(project)
    ]
    if not local:
        return
    inside = _git(project, "ls-tree", "-r", "--name-only", release, "--", *local, what=f"Inspecting {release}")
    if inside:
        raise EfacturaError(
            UPDATE_ERROR,
            f"Release {release} contains files where this PC keeps its settings and data "
            f"({', '.join(inside.splitlines()[:5])}). Installing it would replace them, so it was not installed.",
        )


def _switch_to(project: Path, revision: str) -> None:
    _git(
        project, "-c", "advice.detachedHead=false", "checkout", "--detach", revision,
        what=f"Switching to {revision}", timeout=FETCH_TIMEOUT,
    )


def _go_back(project: Path, previous: str) -> None:
    """Best effort: the release that worked, with its own dependencies."""
    try:
        _switch_to(project, previous)
        sync_dependencies(project)
    except Exception:
        pass  # the failure that brought us here is the one to report


def _only_one_update(cfg: Config) -> _FileLock:
    class _Lock(_FileLock):
        def __enter__(self):
            try:
                return super().__enter__()
            except EfacturaError:
                raise EfacturaError(BUSY, "An update is already running.") from None

    return _Lock(cfg.data_dir / "update.lock")


def _remember(cfg: Config, latest: str, now: datetime) -> None:
    store = Store(cfg.db_path)
    try:
        store.set_setting(LATEST, latest)
        store.set_setting(CHECKED_AT, now.isoformat())
    finally:
        store.close()


def _write_record(cfg: Config, record: dict) -> None:
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    (cfg.data_dir / RECORD).write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")


def _last_record(cfg: Config) -> dict | None:
    try:
        record = json.loads((cfg.data_dir / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


# --- running Git and uv ------------------------------------------------------------------------


def _git(project: Path, *arguments: str, what: str, timeout: int = LOOK_TIMEOUT) -> str:
    git = _find("git", Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git" / "cmd" / "git.exe")
    return _run([git, "-C", str(project), *arguments], what=what, timeout=timeout)


def _git_quietly(project: Path, *arguments: str) -> str | None:
    """Git's answer, or None when it has none to give (not a tag, not a branch)."""
    try:
        return _git(project, *arguments, what="Asking Git") or None
    except EfacturaError:
        return None


def _find(name: str, *usual_places: Path) -> str:
    found = shutil.which(name) or next((str(place) for place in usual_places if place.exists()), None)
    if not found:
        raise EfacturaError(UPDATE_ERROR, f"{name} was not found on this computer; the installer puts it there.")
    return found


def _run(command: list[str], what: str, timeout: int) -> str:
    """Run a program without a window and without questions; its output, or what went wrong."""
    try:
        done = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", errors="replace",
            stdin=subprocess.DEVNULL, timeout=timeout,
            # A prompt for a password would wait forever where nobody can see it.
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        raise EfacturaError(UPDATE_ERROR, f"{what} took longer than {timeout} seconds.") from None
    except OSError as exc:
        raise EfacturaError(UPDATE_ERROR, f"{what} could not be started: {exc}") from None
    if done.returncode != 0:
        said = (done.stderr or done.stdout).strip().splitlines()
        raise EfacturaError(UPDATE_ERROR, f"{what} failed: {' '.join(said[-3:]) or f'exit code {done.returncode}'}")
    return done.stdout.strip()


def _said(exc: Exception) -> str:
    return exc.message if isinstance(exc, EfacturaError) else f"{type(exc).__name__}: {exc}"
