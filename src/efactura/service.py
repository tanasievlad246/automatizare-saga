"""One function per command. The terminal commands and the local API both call these,
so they return the same plain dictionaries either way."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from contextlib import nullcontext
from functools import partial
from dataclasses import asdict, dataclass, replace
from decimal import Decimal, InvalidOperation
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

import httpx

from . import __version__, auth, certificate_login, jev, journal, redact, saga, schedule, technical
from .anaf import LIMITING_EVERY_CALL, TYPE_PREFIXES, AnafService, normalize_cui, parse_created_at, type_slug
from .classify import (
    QUESTION,
    JevAnswer,
    decide_by_rules,
    deciding_line,
    fits,
    follows_largest,
    jev_line_request,
    jev_request,
    line_subject,
    read_jev_answer,
    rules_by_line,
    same_question,
    subject_of,
)
from .clients_file import read_client_rows
from .config import MAX_DAYS, Config
from .errors import (
    ANAF_ERROR,
    ANAF_LIMIT_REACHED,
    BUSY,
    CLIENT_OFF,
    SAGA_FILES_CHANGED,
    SAGA_FILES_STALE,
    SAGA_ARCHIVE_ERROR,
    CONFIG_ERROR,
    INTERNAL_ERROR,
    INVALID_CUI,
    INVALID_INPUT,
    JEV_ERROR,
    LOGIN_NEEDED,
    NETWORK_ERROR,
    NOT_CLASSIFIABLE,
    NOT_FOUND,
    EfacturaError,
)
from .invoice import (
    Invoice,
    Line,
    Party,
    decode_xml,
    extract_zip,
    normalise_company_id,
    total_with_vat_of,
    parse_invoice,
    parse_invoice_fields,
)
from .rules import (
    CONDITIONS, DEFAULT_JEV_ISSUED_INSTRUCTIONS, DEFAULT_JEV_ISSUED_LINE_INSTRUCTIONS, DEFAULT_JEV_LINE_INSTRUCTIONS,
    Rule, Rulebook, RuleMatch, Subject, any_of, normalise,
)
from .store import (
    ISSUED as ISSUED_KIND, JEV_INSTRUCTIONS, JEV_ISSUED_INSTRUCTIONS, JEV_ISSUED_LINE_INSTRUCTIONS,
    JEV_LINE_INSTRUCTIONS, KINDS, RECEIVED as RECEIVED_KIND, RULE_TEST, SAGA_FOLDER_OF, Store,
)
from .suggestions import propose, ticked_words, words_of_line

log = logging.getLogger(__name__)

DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

# sync_all: how long and how often a client waits for a download made by hand
BUSY_PAUSE = 5.0
BUSY_TRIES = 12
CERTIFICATE_LOGIN_WAIT = 45.0  # seconds, after the PIN, for a download to let go of the lock
_ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
# Failures that would be the same for every other client: the run stops, and says how it ended.
STOPS_THE_RUN = {
    LOGIN_NEEDED: "failed",
    ANAF_LIMIT_REACHED: "failed",
    CONFIG_ERROR: "failed",
    NETWORK_ERROR: "unreachable",
}

# ANAF rejects an end time ahead of its own clock, so the window ends slightly in the past.
CLOCK_MARGIN = timedelta(minutes=1)
# Keeps the start safely inside ANAF's 60-day limit.
OLDEST_MARGIN = timedelta(minutes=5)
# After this many unreachable downloads in a row, stop instead of timing out on each one.
MAX_NETWORK_FAILURES = 3

_UNSAFE_IN_FILE_NAME = re.compile(r"[^A-Za-z0-9_-]")

# --- classification ---
RECEIVED = TYPE_PREFIXES["primita"]
ISSUED = TYPE_PREFIXES["trimisa"]  # the invoices a client issued itself; these get an account too
PENDING, CLASSIFIED, REVIEW = "pending", "classified", "review"
STATUSES = (PENDING, CLASSIFIED, REVIEW)
# Jev answers below this confidence go to a person. Kept in the database (table settings)
# so it can be changed without touching files; this is the value before anyone sets one.
DEFAULT_MIN_CONFIDENCE = 0.80
MIN_CONFIDENCE = "min_confidence"
COST_GROUPS = ("day", "week", "month", "year")
MAX_LISTED_CALLS = 1000
# Rules are proposed from the decisions of the last RECENT_DAYS days, and tried on the
# invoices given an account in the same days. Older ones no longer say how things are booked.
RECENT_DAYS = 90
MAX_LISTED_SUGGESTIONS = 20
MAX_TRIAL_LINES = 50
MAX_TRIAL_TEXT = 500
MAX_TRIAL_DIGITS = 15  # before the decimal point, in a number of a trial invoice
MAX_TRIAL_DECIMALS = 20
TRIAL_ASKS = ("rules_then_jev", "jev_only")
# A failure that may pass (no connection, rate limit, server error) is tried once more.
JEV_ATTEMPTS = 2
JEV_RETRY_DELAY = 2.0
# An account as SAGA writes it: 628, 6022, or an analytic account such as 371.01.
_ACCOUNT = re.compile(r"^\d{3,}(\.[0-9A-Za-z]+)*$")
MAX_ACCOUNT_LENGTH = 20


# Settings the screen can change. They are kept in the database and win over config.toml.
SAVED_SETTINGS = {  # name in the database -> field of Config
    "saga_dir": "saga_import_dir",
    "openrouter_api_key": "openrouter_api_key",
    "anaf_client_id": "client_id",
    "anaf_client_secret": "client_secret",
}
EDITABLE_SECRETS = ("openrouter_api_key", "anaf_client_id", "anaf_client_secret")
# The setting that says how the invoices waiting for SAGA are put in files: one file per
# client (saga.PER_CLIENT, unless another way is saved) or one per invoice.
SAGA_FILE_PER = "saga_file_per"
# Whether a client's screen also lists the invoices the client issued. Only the page reads it.
SHOW_ISSUED = "show_issued"
# The name of a client's folder inside the folder for SAGA, as the program last had it, kept in
# the setting named store.SAGA_FOLDER_OF and then the CUI. It says which folder to rename when
# the client's name changes, and which one a client taken off the list keeps.
# Bringing a client's files up to date takes a moment; a second writer waits this long for it.
SAGA_LOCK_WAIT = 30.0
# Who confirmed an import in SAGA: a program through the API (the automation), or a person on screen.
SAGA_IMPORT_SOURCES = ("api", "screen")
# Where the files of a confirmed import are kept, inside the data folder.
SAGA_ARCHIVE_DIR = "saga-archive"


class _JevCouldNotDecide(Exception):
    """Jev was reached but gave nothing usable for this one invoice (it refused the
    request, or its answer made no sense). The next invoice may well be fine."""


# Where a decision comes from, as the history of an invoice's account says it.
DOWNLOAD = "download"  # a download, by hand or by itself
AGAIN = "again"  # "Clasifică din nou facturile de verificat"
REDECIDE = "redecide"  # one invoice, or one line, decided again on purpose
PERSON = "person"  # a person chose, or accepted Jev's proposal
SPLIT = "split"  # a person split an invoice with one account into lines


@dataclass(frozen=True)
class _Pass:
    """How one decision is made, and what the history says made it."""

    source: str = DOWNLOAD
    jev_allowed: bool = True
    skip_rules: bool = False  # "Doar cu Jev": the rules are not tried
    line: int | None = None  # only this line of an invoice decided line by line; the others stay
    per_line: bool | None = None  # line by line, or one account; None: as the client is set

    @property
    def again(self) -> bool:
        """Sent back on purpose with classify_again: what is decided stays, and an invoice that
        goes back to a person is only a detail in the journal."""
        return self.source == AGAIN


class Service:
    def __init__(
        self,
        cfg: Config,
        http: httpx.Client | None = None,
        now: Callable[[], datetime] | None = None,
    ):
        self._file_cfg = cfg  # as config.toml gives it
        self.cfg = _with_saved_settings(cfg)
        if http is None and cfg.demo:
            # Chosen here, so no caller can forget it: demo settings never reach the real ANAF
            # or OpenRouter. Imported here because the demo module imports this one.
            from . import demo

            http = demo.client(cfg, now)
        self._http = http or httpx.Client(timeout=httpx.Timeout(60.0))
        # Every exchange with ANAF and OpenRouter goes to the journal's technical side, and no
        # key this program holds is ever written there or in the journal.
        technical.watch(self._http)
        _remember_keys(self.cfg)
        self._now = now or (lambda: datetime.now().astimezone())
        journal.configure(self.cfg.db_path)  # the journal lives in the same database

    def close(self) -> None:
        self._http.close()

    # --- login --------------------------------------------------------------

    def health(self) -> dict:
        return {"ok": True, "service": "efactura", "version": __version__}

    def auth_status(self) -> dict:
        """Reads the saved login only; contacts nothing."""
        tokens = auth.load_tokens(self.cfg.token_file)
        return {
            "ok": True,
            **_login_summary(tokens, self._now()),
            "certificate_login": certificate_login.available(self.cfg),
        }

    def login_start(self) -> dict:
        return {
            "ok": True,
            # The demo has no ANAF page to send the person to: its own address answers instead.
            "authorize_url": "/api/demo/anaf-login" if self.cfg.demo else auth.authorize_url(self.cfg),
            "redirect_uri": self.cfg.redirect_uri,
        }

    def login_finish(self, address: str, wait: float = 0) -> dict:
        """Save the login from the address ANAF ended on. `wait`: how long to wait for a
        download holding the program's lock, rather than refuse at once."""
        code = auth.code_from_redirect(address)
        now = self._now()
        with _FileLock(self.cfg.lock_path, wait=wait):
            tokens = auth.exchange_code(self.cfg, self._http, code, now)
            auth.save_tokens(self.cfg.token_file, tokens)
            journal.record(
                "anaf", "anaf.connected", "Connected to ANAF with the certificate.",
                valid_until=tokens.access_expires_at.isoformat(),
            )
        log.info("Logged in; access valid until %s", tokens.access_expires_at.isoformat())
        return {"ok": True, **_login_summary(tokens, now)}

    def login_with_certificate(self) -> dict:
        """Log in with the certificate Windows holds, with no browser and no pasted address.

        The program's lock is not held while Windows asks, which can take minutes;
        login_finish takes it for the exchange. A second request that comes while Windows is
        being asked waits for that one and gets its answer."""
        if not certificate_login.available(self.cfg):
            raise EfacturaError(INVALID_INPUT, "Logging in with the Windows certificate is not available here.")
        return certificate_login.one_at_a_time(self._certificate_login)

    def _certificate_login(self) -> dict:
        # A download in progress refuses the try now, not after the PIN has been typed.
        with self._lock():
            pass
        address = certificate_login.ask_windows(auth.authorize_url(self.cfg))
        try:
            auth.code_from_redirect(address)
        except EfacturaError as exc:
            if exc.code != INVALID_INPUT:
                raise
            # Nothing the person typed: ANAF ended the login on an address with no code.
            raise EfacturaError(ANAF_ERROR, "ANAF ended the login on an address that holds no code.") from None
        # The PIN has been typed, and the code is good for about a minute: a download that
        # started meanwhile is waited for, not a reason to make the person start again.
        return self.login_finish(address, wait=CERTIFICATE_LOGIN_WAIT)

    # --- ANAF ---------------------------------------------------------------

    def list_remote(self, cui: str, days: int | None = None) -> dict:
        """What ANAF has for the window, each marked new or already saved. Saves nothing."""
        cui = normalize_cui(cui)
        now = self._now()
        store = self._open_store()
        try:
            window_days = _window_days(
                self.cfg.default_days, store.last_clean_run_start(cui), days, now
            )
            anaf_service = self._anaf_service(lock_held=False)
            entries = anaf_service.list_messages(cui, *_window(now, window_days))
            known = store.existing_ids(e["id"] for e in entries)
        finally:
            store.close()
        messages = [
            {
                "id": e["id"],
                "message_type": str(e.get("tip") or ""),
                "anaf_created_at": parse_created_at(e.get("data_creare")),
                "id_solicitare": e.get("id_solicitare"),
                "detalii": e.get("detalii"),
                "is_new": e["id"] not in known,
            }
            for e in entries
        ]
        return {
            "ok": True,
            "cui": cui,
            "window_days": window_days,
            "listed": len(messages),
            "new_count": sum(m["is_new"] for m in messages),
            "messages": messages,
        }

    def sync_all(
        self, progress: Callable[[int, int], None] | None = None, days: int | None = None,
        start: str | None = None, end: str | None = None, cover_gap: bool = False,
    ) -> dict:
        """Download for every client that is switched on, one after another, each for the
        same period (`days`, or `start` and `end`, with `cover_gap`: see `sync`). A first day
        older than ANAF keeps is asked for from the oldest day it keeps.

        One client's failure does not stop the others, except a failure that would be the
        same for all of them (STOPS_THE_RUN). `progress(position, total)` is told before
        each client, and `progress(total, total)` once at the end. Each `sync` takes the
        lock itself; a client that finds it taken waits for a download made by hand.
        """
        store = self._open_store()
        try:
            clients = store.clients_switched_on()
        finally:
            store.close()
        total = len(clients)
        results: list[dict] = []
        stopped_by: str | None = None
        for position, client in enumerate(clients):
            if progress is not None:
                progress(position, total)
            cui, name = client["cui"], client["name"]
            store = self._open_store()
            try:
                still_on = store.client_enabled(cui) is True
            finally:
                store.close()
            if not still_on:
                continue
            try:
                result = self._sync_waiting(
                    cui, days=days, start=self._within_reach(start), end=end, cover_gap=cover_gap, listed_only=True,
                )
            except EfacturaError as exc:
                if exc.code == CLIENT_OFF:
                    continue
                results.append(_failed_client(cui, name, exc.code, exc.message))
                if exc.code in STOPS_THE_RUN:
                    stopped_by = exc.code
                    break
            except Exception as exc:
                log.exception("Download for client %s failed", cui)
                results.append(_failed_client(cui, name, INTERNAL_ERROR, repr(exc)))
            else:
                results.append(
                    {
                        "cui": cui, "name": name, "ok": True,
                        "new_count": result["new_count"], "received_count": result["received_count"],
                        "issued_count": result["issued_count"], "failed_count": result["failed_count"],
                        "review": (result["classification"] or {}).get(REVIEW, 0),
                    }
                )
        if progress is not None:
            progress(total, total)
        done = [r for r in results if r["ok"]]
        failed_clients = len(results) - len(done)
        if stopped_by:
            status = STOPS_THE_RUN[stopped_by]
        elif results and not done:
            status = "failed"  # nobody succeeded: not "not complete", a run that did not work
        elif failed_clients or any(r["failed_count"] for r in done):
            status = "partial"
        else:
            status = "ok"
        return {
            "ok": True,
            "status": status,
            "clients": total,
            "failed_clients": failed_clients,
            "new": sum(r["new_count"] for r in done),
            "received": sum(r["received_count"] for r in done),
            "issued": sum(r["issued_count"] for r in done),
            "review": sum(r["review"] for r in done),
            "stopped_by": stopped_by,
            "results": results,
        }

    def _within_reach(self, start: str | None) -> str | None:
        """The first day to ask for, moved up to the oldest day ANAF keeps. It is worked out for
        each client by the clock of that moment: a run that passes midnight would otherwise
        ask the clients after it for a day that has just become too old."""
        if start is None:
            return None
        oldest = (self._now() - timedelta(days=MAX_DAYS)).date()
        return max(_day(start), oldest).isoformat()

    def _sync_waiting(self, cui: str, **period) -> dict:
        """`sync`, but when another download holds the lock, wait and try again."""
        for attempt in range(1, BUSY_TRIES + 1):
            try:
                return self.sync(cui, **period)
            except EfacturaError as exc:
                if exc.code != BUSY or attempt == BUSY_TRIES:
                    raise
            _pause(BUSY_PAUSE)
        raise AssertionError("unreachable")  # the loop returns or raises

    def sync(
        self,
        cui: str,
        days: int | None = None,
        classify: bool = True,
        start: str | None = None,
        end: str | None = None,
        cover_gap: bool = False,
        listed_only: bool = False,
    ) -> dict:
        """List, skip what is already saved, download and save the rest. Then give the
        received invoices just saved an account and write their SAGA files.

        The period is the last `days` days, or the days from `start` to `end` (dates such
        as 2026-11-03; `end` defaults to today). With neither, it is the default number of
        days, widened to reach back to the last complete run. With cover_gap, `days` is a
        minimum that is widened the same way, so no day since the last run is skipped.

        With classify=False the messages are only saved, and stay outside classification
        for good (for a first run that brings in invoices already booked by hand).

        listed_only: for a run over the client list. The client must still be in it and on
        once the lock is taken: the run may have waited for it while the client was switched
        off, or while every client was deleted ("Șterge toate datele").
        """
        cui = normalize_cui(cui)
        store = self._open_store()
        try:
            switched_off = store.client_enabled(cui) is False
        finally:
            store.close()
        if switched_off:
            raise EfacturaError(
                CLIENT_OFF,
                "This client is switched off. Switch it on in the client list to download its invoices.",
            )
        with self._lock():
            store = self._open_store()
            try:
                if listed_only and store.client_enabled(cui) is not True:
                    raise EfacturaError(CLIENT_OFF, "This client was switched off or removed while its download waited.")
                now = self._now()
                covered_until = store.last_clean_run_start(cui)
                window = _plan_window(
                    self.cfg.default_days, covered_until, days, start, end, now, cover_gap
                )
                run_id = store.start_run(cui, window.days, now.isoformat())
                began, client = time.monotonic(), store.client_name(cui)
                journal.record(
                    "sync", "sync.started", f"Download started for {cui}, {window.days} day(s) back.",
                    cui=cui, client=client, window_days=window.days,
                    start=window.begin.date().isoformat(), end=_last_day(window).isoformat(),
                )
                log.debug(
                    "Window for %s: %s to %s (%s day(s)); everything saved up to %s; reaches back to it: %s",
                    cui, window.begin.isoformat(timespec="minutes"), window.finish.isoformat(timespec="minutes"),
                    window.days, covered_until or "never", window.reaches_back,
                )
                try:
                    result = self._run_sync(store, cui, window, run_id, now, classify)
                except Exception as exc:
                    detail = (
                        f"{exc.code}: {exc.message}" if isinstance(exc, EfacturaError) else repr(exc)
                    )
                    journal.record(
                        "sync", "sync.failed", f"Download for {cui} failed: {detail}", level="error",
                        cui=cui, client=client, error=detail, duration_ms=_since(began),
                        code=exc.code if isinstance(exc, EfacturaError) else INTERNAL_ERROR,
                    )
                    try:
                        store.finish_run(
                            run_id, self._now().isoformat(),
                            listed=0, new=0, failed=0, status="error", error=detail,
                        )
                    except sqlite3.Error as log_failure:
                        # The caller must still get the error that stopped the run.
                        log.error("Could not record failed run %s: %s", run_id, log_failure)
                    raise
                store.finish_run(
                    run_id, self._now().isoformat(),
                    listed=result["listed"], new=result["new_count"], failed=result["failed_count"],
                    status="partial" if result["failed"] else "ok",
                    error=f"{result['failed_count']} message(s) failed" if result["failed"] else None,
                    advances_coverage=not result["failed"] and window.reaches_back,
                )
                result["classification"] = result["saga_folder"] = None
                if classify:
                    try:
                        self._classify_waiting(store, cui, result)
                    except sqlite3.Error:
                        # The messages are saved; what is still waiting is picked up next time.
                        log.exception("Classification for %s stopped", cui)
                        result["classification"] = result["saga_folder"] = None
                decided = result["classification"] or {}
                journal.record(
                    "sync", "sync.finished",
                    f"Download for {cui} finished: {result['listed']} listed, {result['new_count']} new, "
                    f"{result['failed_count']} failed.",
                    level="warning" if result["failed_count"] else "info",
                    cui=cui, client=client, listed=result["listed"], new=result["new_count"],
                    received=result["received_count"], issued=result["issued_count"],
                    failed=result["failed_count"], classified=decided.get(CLASSIFIED), review=decided.get(REVIEW),
                    waiting=decided.get(PENDING), duration_ms=_since(began),
                )
                if result.pop("limited"):
                    # The same for every client after this one: said as the error it is.
                    raise EfacturaError(ANAF_LIMIT_REACHED, LIMITING_EVERY_CALL)
                return result
            finally:
                store.close()

    def _run_sync(
        self, store: Store, cui: str, window: "_Window", run_id: int, now: datetime, classify: bool
    ) -> dict:
        anaf_service = self._anaf_service(lock_held=True)
        entries = anaf_service.list_messages(cui, window.begin, window.finish)
        known = store.existing_ids(e["id"] for e in entries)
        unseen = [e for e in entries if e["id"] not in known]
        folder = self.cfg.invoices_dir / self.cfg.folder_name(now)
        log.debug(
            "%s message(s) listed for %s: %s already saved, %s to download into %s",
            len(entries), cui, len(entries) - len(unseen), len(unseen), folder,
        )

        saved: list[dict] = []
        failed: list[dict] = []
        network_failures, limited = 0, False
        for position, entry in enumerate(unseen):
            try:
                saved.append(
                    self._save_message(store, anaf_service, cui, entry, folder, run_id, now, classify)
                )
                network_failures = 0
                continue
            except EfacturaError as exc:
                if exc.code == LOGIN_NEEDED:
                    raise
                error = exc
            except (OSError, sqlite3.Error) as exc:
                log.exception("Could not save message %s", entry["id"])
                error = EfacturaError(INTERNAL_ERROR, f"Could not save the message: {exc}")
            failed.append(_failure(entry, error))
            journal.record(
                "sync", "sync.message_failed", f"Message {entry['id']} could not be saved: {error.message}",
                level="warning", id=entry["id"], cui=cui, error=error.message, code=error.code,
            )
            log.warning("Message %s failed: %s: %s", entry["id"], error.code, error.message)
            if error.message == LIMITING_EVERY_CALL:
                # ANAF limits every call: the rest are not asked for now. What was saved is still
                # given its account, and the download then ends with this error (`sync`).
                failed.extend(_failure(rest, error) for rest in unseen[position + 1 :])
                limited = True
                break
            network_failures = network_failures + 1 if error.code == NETWORK_ERROR else 0
            if network_failures >= MAX_NETWORK_FAILURES:
                skipped = EfacturaError(
                    NETWORK_ERROR, "Skipped: ANAF was unreachable for the messages before this one."
                )
                failed.extend(_failure(rest, skipped) for rest in unseen[position + 1 :])
                break

        return {
            "limited": limited,
            "ok": True,
            "cui": cui,
            "window_days": window.days,
            "listed": len(entries),
            "new_count": len(saved),
            # Of those: the invoices the client received and the ones it issued; both get an
            # account. Errors and other messages are in neither.
            "received_count": sum(type_slug(m["message_type"]) == "primita" for m in saved),
            "issued_count": sum(type_slug(m["message_type"]) == "trimisa" for m in saved),
            "failed_count": len(failed),
            "folder": str(folder) if saved else None,
            "new": saved,
            "failed": failed,
        }

    def _save_message(
        self, store: Store, anaf_service: AnafService, cui: str, entry: dict,
        folder: Path, run_id: int, now: datetime, classify: bool,
    ) -> dict:
        message_id = entry["id"]
        message_type = str(entry.get("tip") or "")
        archive = anaf_service.download(message_id)
        extracted = extract_zip(archive)
        fields = parse_invoice_fields(extracted.xml)
        log.debug(
            "Message %s (%s) downloaded: a ZIP of %s bytes, an XML of %s; invoice %s of %s from supplier %s",
            message_id, message_type or "no type", len(archive), len(extracted.xml),
            fields["invoice_number"], fields["invoice_issue_date"], fields["supplier_cui"],
        )

        duplicate_of = None
        if fields["invoice_number"] and fields["supplier_cui"]:
            duplicate_of = store.find_same_invoice(
                cui, message_type, fields["supplier_cui"], fields["invoice_number"], fields["invoice_issue_date"]
            )
            if duplicate_of:
                log.warning(
                    "Message %s repeats invoice %s from %s (first saved as message %s)",
                    message_id, fields["invoice_number"], fields["supplier_cui"], duplicate_of,
                )

        safe_id = _UNSAFE_IN_FILE_NAME.sub("_", message_id)
        path = folder / f"{cui}_{type_slug(message_type)}_{safe_id}.xml"
        folder.mkdir(parents=True, exist_ok=True)
        _write_file(path, extracted.xml)
        try:
            store.insert_message(
                {
                    "id": message_id,
                    "cui": cui,
                    "message_type": message_type,
                    "anaf_created_at": parse_created_at(entry.get("data_creare")),
                    "id_solicitare": entry.get("id_solicitare"),
                    "detalii": entry.get("detalii"),
                    **fields,
                    "invoice_xml": decode_xml(extracted.xml),
                    "signature_xml": decode_xml(extracted.signature) if extracted.signature else None,
                    "raw_metadata_json": json.dumps(entry, ensure_ascii=False),
                    "zip_sha256": hashlib.sha256(archive).hexdigest(),
                    "xml_path": path.relative_to(self.cfg.data_dir).as_posix(),
                    "first_seen_at": now.isoformat(),
                    "sync_run_id": run_id,
                    "possible_duplicate_of": duplicate_of,
                    # Only a message saved here, now, ever enters classification.
                    "classification_status": (
                        PENDING
                        if classify and _gets_an_account(message_type)
                        and parse_invoice(extracted.xml) is not None
                        else None
                    ),
                }
            )
        except Exception:
            path.unlink(missing_ok=True)
            raise
        saved = store.get_message(message_id)
        log.debug(
            "Message %s saved to %s; %s", message_id, path.relative_to(self.cfg.data_dir).as_posix(),
            "waits for an account" if saved.get("classification_status") == PENDING else "stays out of classification",
        )
        return self._present(saved)

    # --- the local database ---------------------------------------------------

    def invoices(
        self,
        cui: str | None = None,
        pending: bool = False,
        message_type: str | None = None,
        since: str | None = None,
        classification: str | None = None,
        only_new: bool = False,
    ) -> dict:
        if message_type is not None and message_type not in TYPE_PREFIXES:
            raise EfacturaError(
                INVALID_INPUT, f"type must be one of: {', '.join(TYPE_PREFIXES)}."
            )
        if classification is not None and classification not in STATUSES:
            raise EfacturaError(
                INVALID_INPUT, f"classification must be one of: {', '.join(STATUSES)}."
            )
        _check_date(since)
        store = self._open_store()
        try:
            rows = store.list_messages(
                cui=normalize_cui(cui) if cui else None,
                pending=pending,
                type_prefix=TYPE_PREFIXES[message_type] if message_type else None,
                since=since,
                classification=classification,
                only_new=only_new,
            )
            # One client's list also says how that client's files for SAGA stand, and how
            # many invoices the client issued, which the page does not list unless asked to.
            of_client = {
                "saga": self._saga_state(store, normalize_cui(cui), with_version=message_type != "trimisa"),
                "issued_count": store.issued_count(normalize_cui(cui)),
            } if cui else {}
        finally:
            store.close()
        return {"ok": True, "count": len(rows), "invoices": [self._present(r) for r in rows], **of_client}

    def invoice(self, message_id: str, include_xml: bool = False) -> dict:
        store = self._open_store()
        try:
            row = store.get_message(message_id, include_xml=include_xml)
            # The confirmed import it went to SAGA in, if any: one invoice says it, the lists do not.
            saga_import = store.saga_import_of(message_id) if row else None
        finally:
            store.close()
        if row is None:
            raise EfacturaError(NOT_FOUND, f"No saved message with id: {message_id}")
        return {"ok": True, "invoice": {**self._present(row), "saga_import": saga_import}}

    def mark_uploaded(self, ids: list[str], undo: bool = False) -> dict:
        ids = [str(i) for i in ids]
        if not ids:
            raise EfacturaError(INVALID_INPUT, "Give at least one message id.")
        when = self._now().isoformat()
        store = self._open_store()
        try:
            store.set_uploaded(ids, not undo, when)
            journal.record(
                "accounts", "invoices.unmarked" if undo else "invoices.marked_imported",
                f"{len(ids)} invoice(s) {'no longer marked' if undo else 'marked'} as imported in SAGA.", invoices=len(ids),
            )
            for cui in store.cuis_of(ids):
                self._write_saga_files(store, cui)
        finally:
            store.close()
        return {
            "ok": True,
            "uploaded_to_accounting": not undo,
            "uploaded_at": None if undo else when,
            "updated": ids,
        }

    # --- classification -------------------------------------------------------

    def classify(
        self, message_id: str, force: bool = False, ask: str = "rules_then_jev", line: int | None = None,
        per_line: bool | None = None,
    ) -> dict:
        """Give one saved invoice its account: the rules first, Jev if they cannot decide;
        with `ask` "jev_only", Jev alone. Decided from the start, the lines a person chose
        included, line by line or with one account as `per_line` says (None: as the client is
        set). `line`: that line alone, on an invoice decided line by line.

        Without force this only works on invoices that are waiting or in review. An invoice
        saved outside classification, or one already classified, needs force.
        """
        if ask not in TRIAL_ASKS:
            raise EfacturaError(INVALID_INPUT, f"ask must be one of: {', '.join(TRIAL_ASKS)}.")
        how = _Pass(source=REDECIDE, skip_rules=ask == "jev_only", line=line, per_line=per_line)
        with self._lock():
            store = self._open_store()
            try:
                row, invoice = self._classifiable(store, message_id, force, classified_ok=force)
                if line is not None:
                    if _stored_lines(row) is None:
                        raise EfacturaError(
                            INVALID_INPUT,
                            "This invoice has one account for all its lines. Split it into lines first (split).",
                        )
                    if line not in {item.number for item in invoice.lines}:
                        raise EfacturaError(INVALID_INPUT, f"The invoice has no line {line}.")
                try:
                    self._classify_one(store, message_id, _new_tally(), how)
                finally:
                    self._write_saga_files(store, row["cui"])
                return {"ok": True, "invoice": self._present(store.get_message(message_id))}
            finally:
                store.close()

    def review(self, cui: str | None = None) -> dict:
        """The invoices a person must decide, with what Jev suggested."""
        store = self._open_store()
        try:
            rows = store.list_messages(
                cui=normalize_cui(cui) if cui else None, classification=REVIEW, pending=True
            )
            invoices = [
                {
                    **self._present(row),
                    # Line by line, they are in line_accounts: the last call was about one line only.
                    "jev_probabilities": None if _stored_lines(row) is not None else _probabilities(store, row["id"]),
                }
                for row in rows
            ]
            level = _min_confidence(store)
            accounts, issued_accounts = store.accounts(), store.accounts(ISSUED_KIND)
        finally:
            store.close()
        return {
            "ok": True,
            "count": len(invoices),
            "min_confidence": level,
            "accounts": accounts,
            "issued_accounts": issued_accounts,  # for the invoices a client issued
            "invoices": invoices,
        }

    def set_cont(
        self, message_id: str, cont: str | None = None, accept: bool = False, force: bool = False,
        line: int | None = None,
    ) -> dict:
        """A person's decision: accept Jev's suggestion, or set an account. On an invoice
        decided line by line, `line` names the one line; without it every line gets `cont`,
        or every line left without an account gets what Jev proposed for it."""
        if accept == (cont is not None):
            raise EfacturaError(
                INVALID_INPUT, "Either accept Jev's suggestion or give a cont, one of the two."
            )
        if cont is not None:
            cont = _checked_account(cont)
        with self._lock():
            store = self._open_store()
            try:
                row, invoice = self._classifiable(store, message_id, force, classified_ok=True)
                entries = _stored_lines(row)
                if entries is not None:
                    entries = _aligned(entries, invoice)
                    _choose_on_lines(entries, cont, accept, line)
                    self._record_lines(store, row, invoice, entries, how=_Pass(source=PERSON))
                    self._write_saga_files(store, row["cui"])
                    return {"ok": True, "invoice": self._present(store.get_message(message_id))}
                if line is not None:
                    raise EfacturaError(
                        INVALID_INPUT,
                        "This invoice has one account for all its lines. Split it into lines first (split).",
                    )
                if accept:
                    if not row["suggested_cont"]:
                        raise EfacturaError(
                            INVALID_INPUT, "Jev suggested no account for this invoice; give a cont."
                        )
                    cont, method, reason = (
                        row["suggested_cont"], "jev_accepted", "Jev's suggestion, accepted by a person."
                    )
                else:
                    method, reason = "human", "Set by a person."
                self._finish(store, row, invoice, cont, method, reason, how=_Pass(source=PERSON))
                self._write_saga_files(store, row["cui"])
                return {"ok": True, "invoice": self._present(store.get_message(message_id))}
            finally:
                store.close()

    def split_into_lines(self, message_id: str) -> dict:
        """A person turns an invoice with one account into one decided line by line, whatever
        the client's switch: every line starts with the invoice's account. The largest line
        keeps how it was chosen; a discount, or a line worth nothing, follows the largest line;
        every other line keeps the account as its own (FROM_INVOICE). SAGA's file says the
        same until a line gets another account."""
        with self._lock():
            store = self._open_store()
            try:
                row, invoice = self._classifiable(store, message_id, force=True, classified_ok=True)
                if _stored_lines(row) is not None:
                    raise EfacturaError(INVALID_INPUT, "This invoice is decided line by line already.")
                if len(invoice.lines) < 2:
                    raise EfacturaError(INVALID_INPUT, "This invoice has one line: there is nothing to split.")
                if row["classification_status"] != CLASSIFIED or not row["cont"]:
                    raise EfacturaError(INVALID_INPUT, "This invoice has no account yet. Choose it first, then split it.")
                # The rule and what it found, from the history, when it holds this account.
                last = next((entry for entry in store.decisions(message_id) if entry["line"] is None), None)
                noted = last["said"] if last and last["cont"] == row["cont"] else {}
                largest = deciding_line(invoice).number
                entries = []
                for item in invoice.lines:
                    if item.number == largest:
                        entries.append(_line_entry(
                            item.number, row["cont"], row["classification_method"], row["classification_reason"],
                            rule=noted.get("rule"), match=noted.get("match"), probabilities=noted.get("probabilities"),
                            suggested_cont=row["suggested_cont"], confidence=row["confidence"],
                            confidence_threshold=row["confidence_threshold"],
                            # Jev's answer, as a line Jev was asked about: "Clasifică din nou" keeps it.
                            asked=row["classification_method"] == "jev",
                        ))
                    elif follows_largest(invoice, item):
                        entries.append(_line_entry(
                            item.number, None, FOLLOWS, f"Takes the account of line {largest}, the largest on the invoice.",
                        ))
                    else:
                        entries.append(_line_entry(
                            item.number, row["cont"], FROM_INVOICE,
                            "The account of the whole invoice, kept when a person split it into lines.",
                        ))
                self._record_lines(store, row, invoice, entries, how=_Pass(source=SPLIT))
                self._write_saga_files(store, row["cui"])
                return {"ok": True, "invoice": self._present(store.get_message(message_id))}
            finally:
                store.close()

    def classification_settings(self) -> dict:
        store = self._open_store()
        try:
            return {
                "ok": True,
                "min_confidence": _min_confidence(store),
                "model": self.cfg.jev_model,
                "jev_configured": bool(self.cfg.openrouter_api_key),
                "accounts": store.accounts(),
                "jev_instructions": store.get_setting(JEV_INSTRUCTIONS) or "",
                "jev_line_instructions": store.get_setting(JEV_LINE_INSTRUCTIONS) or DEFAULT_JEV_LINE_INSTRUCTIONS,
                **_issued_questions(store),
            }
        finally:
            store.close()

    def set_jev_issued_instructions(self, text: str) -> dict:
        """The question Jev is asked about a whole invoice the client issued."""
        return self._set_question(JEV_ISSUED_INSTRUCTIONS, text, "settings.jev_issued_question",
                                  "The question put to Jev about an issued invoice was changed.")

    def set_jev_issued_line_instructions(self, text: str) -> dict:
        """The question Jev is asked about one line of an invoice the client issued."""
        return self._set_question(JEV_ISSUED_LINE_INSTRUCTIONS, text, "settings.jev_issued_line_question",
                                  "The question put to Jev about one line of an issued invoice was changed.")

    def _set_question(self, key: str, text: str, event: str, message: str) -> dict:
        text = str(text or "").strip()
        if not text:
            raise EfacturaError(INVALID_INPUT, "The question for Jev cannot be empty.")
        store = self._open_store()
        try:
            store.set_setting(key, text)
            journal.record("settings", event, message)
        finally:
            store.close()
        return self.classification_settings()

    def set_jev_line_instructions(self, text: str) -> dict:
        """The question Jev is asked about one line, for the clients whose invoices are
        decided line by line."""
        text = str(text or "").strip()
        if not text:
            raise EfacturaError(INVALID_INPUT, "The question for Jev cannot be empty.")
        store = self._open_store()
        try:
            store.set_setting(JEV_LINE_INSTRUCTIONS, text)
            journal.record(
                "settings", "settings.jev_line_question", "The question put to Jev about one line was changed."
            )
        finally:
            store.close()
        return self.classification_settings()

    def set_jev_instructions(self, text: str) -> dict:
        """The question Jev is asked about every invoice the rules cannot decide."""
        text = str(text or "").strip()
        if not text:
            raise EfacturaError(INVALID_INPUT, "The question for Jev cannot be empty.")
        store = self._open_store()
        try:
            store.set_setting(JEV_INSTRUCTIONS, text)
            journal.record("settings", "settings.jev_question", "The question put to Jev was changed.")
        finally:
            store.close()
        return self.classification_settings()

    # --- clients ------------------------------------------------------------------

    def clients(self) -> dict:
        """The companies whose invoices are fetched, with how many invoices need attention."""
        store = self._open_store()
        try:
            rows = store.clients()
        finally:
            store.close()
        return {"ok": True, "count": len(rows), "clients": rows}

    def save_client(self, cui: str, name: str) -> dict:
        """Add a client, or rename one that is already in the list."""
        cui, name = normalize_cui(cui), _tidy_name(name)
        if not name:
            raise EfacturaError(INVALID_INPUT, "A client needs a name.")
        store = self._open_store()
        try:
            known_as = store.client_name(cui)
            store.save_client(cui, name, self._now().isoformat())
            journal.record("clients", "client.saved", f"Client {cui} saved.", cui=cui, client=name)
            self._folder_follows_the_name(store, cui, known_as, name)
        finally:
            store.close()
        return self.clients()

    def _folder_follows_the_name(self, store: Store, cui: str, known_as: str | None, name: str) -> None:
        """A client's folder for SAGA carries its name, so it follows a new one at once. A
        client new to the list, with nothing for SAGA on record, has no folder to follow:
        the folder for SAGA, which may be a share that is slow to answer, is left alone."""
        if known_as == name:
            return
        if known_as is not None or store.saga_ledger(cui) or self._folder_names_kept(store, cui):
            self._write_saga_files(store, cui)

    def set_client_enabled(self, cui: str, enabled: bool) -> dict:
        """Switch a client on or off. A client that is off keeps its invoices and is left
        out of every download."""
        cui = normalize_cui(cui)
        store = self._open_store()
        try:
            store.set_client_enabled(cui, enabled)
            journal.record(
                "clients", "client.switched", f"Client {cui} switched {'on' if enabled else 'off'}.",
                cui=cui, client=store.client_name(cui), enabled=enabled,
            )
        finally:
            store.close()
        return self.clients()

    def set_client_per_line(self, cui: str, per_line: bool) -> dict:
        """Whether each line of this client's invoices gets its own account, or the largest
        line decides one account for the whole invoice. It holds for the invoices decided
        from now on; the ones that already have an account keep it."""
        cui = normalize_cui(cui)
        store = self._open_store()
        try:
            if store.set_client_per_line(cui, per_line):
                journal.record(
                    "clients", "client.per_line",
                    f"Client {cui}: " + ("an account for each line." if per_line else "one account for the whole invoice."),
                    cui=cui, client=store.client_name(cui), per_line=per_line,
                )
        finally:
            store.close()
        return self.clients()

    def schedule(self) -> dict:
        """When the program downloads by itself, and how the last run went."""
        return schedule.status(self.cfg, self._now())

    def set_schedule(self, enabled, days, times, period=None) -> dict:
        """Save when the program downloads by itself, and for which period: {"days": 7}, or
        {"start": ..., "end": ...}; left out, the stored period stays. A schedule that makes no
        sense is refused (invalid_input) and the one stored stays."""
        store = self._open_store()
        try:
            clock = schedule.local_clock(self._now())
            if period is None:
                period = schedule.read(store).period.as_dict()
            saved = schedule.save(store, schedule.checked(enabled, days, times, period, clock.date()), clock)
            if saved.enabled:
                names = ", ".join(DAY_NAMES[day] for day in saved.days)
                message = (
                    f"Automatic download switched on: days {names}, at {', '.join(saved.times)}, "
                    f"{saved.period.in_words()}."
                )
            else:
                message = "Automatic download switched off."
            journal.record(
                "settings", "schedule.saved", message,
                enabled=saved.enabled, days=list(saved.days), times=list(saved.times),
                period=saved.period.as_dict(),
            )
        finally:
            store.close()
        return self.schedule()

    def remove_client(self, cui: str) -> dict:
        """Take a client off the list. Its saved invoices stay."""
        store = self._open_store()
        try:
            store.delete_client(normalize_cui(cui))
            journal.record("clients", "client.removed", f"Client {normalize_cui(cui)} taken off the list.", cui=normalize_cui(cui))
        finally:
            store.close()
        return self.clients()

    def import_clients(self, filename: str, content: bytes) -> dict:
        """Add the clients in a CSV or Excel file. Rows that cannot be used are listed
        with the reason as a code, so the screen can explain each in its own words."""
        rows = read_client_rows(filename, content)
        added, updated, rejected, unchanged = [], [], [], 0
        now = self._now().isoformat()
        store = self._open_store()
        try:
            for number, written_name, written_cui in rows:
                name = _tidy_name(written_name)
                problem = _problem_with(name, written_cui)
                if problem:
                    rejected.append({"row": number, "name": name, "cui": written_cui, "code": problem})
                    continue
                cui = normalize_cui(written_cui)
                known_as = store.client_name(cui)
                store.save_client(cui, name, now)
                if known_as is None:
                    added.append({"cui": cui, "name": name})
                elif known_as != name:
                    updated.append({"cui": cui, "name": name})
                else:
                    unchanged += 1
                self._folder_follows_the_name(store, cui, known_as, name)
        finally:
            store.close()
        journal.record(
            "clients", "clients.imported",
            f"Clients imported from {filename}: {len(added)} added, {len(updated)} updated, {len(rejected)} rejected.",
            level="warning" if rejected else "info",
            file=filename, added=len(added), updated=len(updated), rejected=len(rejected),
        )
        return {
            "ok": True, "rows": len(rows), "added": added, "updated": updated,
            "unchanged": unchanged, "rejected": rejected,
        }

    # --- settings and keys changed on screen ----------------------------------

    def app_settings(self) -> dict:
        store = self._open_store()
        try:
            folder, per, issued = self._saga_dir(store), _saga_file_per(store), _show_issued(store)
        finally:
            store.close()
        return {
            "ok": True, "saga_folder": str(folder), "saga_file_per": per, "show_issued": issued,
            "demo": self.cfg.demo,
        }

    def change_settings(
        self, saga_folder: str | None = None, saga_file_per: str | None = None,
        show_issued: bool | None = None,
    ) -> dict:
        """What is changed on the screen, any of it at once; what is left out stays as it
        is. The settings for SAGA are checked first, so a refusal changes nothing."""
        for_saga = saga_folder is not None or saga_file_per is not None
        if not for_saga and show_issued is None:
            raise EfacturaError(INVALID_INPUT, "Give saga_folder, saga_file_per or show_issued.")
        if show_issued is not None and not isinstance(show_issued, bool):
            raise EfacturaError(INVALID_INPUT, "show_issued must be true or false.")
        problems = self.set_saga_output(saga_folder, saga_file_per)["problems"] if for_saga else []
        if show_issued is not None:
            self._set_show_issued(show_issued)
        return {**self.app_settings(), "problems": problems}

    def _set_show_issued(self, shown: bool) -> None:
        store = self._open_store()
        try:
            if shown != _show_issued(store):
                store.set_setting(SHOW_ISSUED, "1" if shown else "0")
                # Since issued invoices have a tab of their own, the setting is kept only for
                # programs that set it; the journal says it changed nothing.
                journal.record(
                    "settings", "settings.show_issued",
                    f"The old setting for showing issued invoices was set to {shown}; it no longer changes anything.",
                    shown=shown, no_effect=True,
                )
        finally:
            store.close()

    def set_saga_output(self, folder: str | None = None, per: str | None = None) -> dict:
        """Change the folder for SAGA, whether it gets one file per client or one per
        invoice, or both. Nothing is saved unless all of it can be; then what is waiting
        for SAGA is written again, in the folder and the way now in force, and the files
        written before are removed. The reply names the clients whose files could not be."""
        if folder is None and per is None:
            raise EfacturaError(INVALID_INPUT, "Give saga_folder, saga_file_per, or both.")
        if per is not None and per not in saga.WAYS:
            raise EfacturaError(INVALID_INPUT, f"saga_file_per must be one of: {', '.join(saga.WAYS)}.")
        path = _checked_folder(folder) if folder is not None else None
        if path is not None:
            self._save_setting("saga_dir", str(path))
        if per is not None:
            store = self._open_store()
            try:
                if per != _saga_file_per(store):
                    store.set_setting(SAGA_FILE_PER, per)
                    journal.record(
                        "settings", "settings.saga_file_per",
                        f"The folder for SAGA now gets one file per {per}.", per=per,
                    )
            finally:
                store.close()
        written = self.write_saga_files()
        return {**self.app_settings(), "problems": written["problems"]}

    def write_saga_files(self, cui: str | None = None) -> dict:
        """Bring the files for SAGA up to date, for one client or for all of them. The
        program does this by itself at every change; this is for its start, for a change of
        folder or of way, and for trying again after a file could not be written."""
        store = self._open_store()
        try:
            if cui:
                clients = [normalize_cui(cui)]
            else:
                with_files = set(store.clients_with_saga_files())
                # Also the clients in the list that have no file: a folder of theirs named as an
                # earlier version named it is given its name of now. Not while the folder for
                # SAGA is away: each of them would wait for it, to find nothing to do.
                listed = {client["cui"] for client in store.clients()} if self._saga_dir(store).is_dir() else set()
                clients = sorted(with_files | listed)
            problems = []
            for client in clients:
                self._write_saga_files(store, client)
                problem = store.saga_problem(client)
                if problem:
                    problems.append({"cui": client, **problem})
        finally:
            store.close()
        return {"ok": True, "clients": len(clients), "problems": problems}

    # --- the import in SAGA, confirmed, and its archive ----------------------------------

    def saga_files(self, cui: str | None = None) -> dict:
        """What waits for SAGA, for one client or for every client that has a file: the
        files with their paths and invoices, whether they are up to date, and their version,
        a fingerprint of the files as they are on disk. A program that imports them into SAGA
        sends the version back with confirm_saga_import."""
        store = self._open_store()
        try:
            if cui:
                return {"ok": True, **self._saga_waiting(store, self._known_client(store, cui))}
            listed = [self._saga_waiting(store, client) for client in store.clients_with_saga_files()]
        finally:
            store.close()
        return {"ok": True, "clients": [entry for entry in listed if entry["files"]]}

    def saga_file(self, cui: str, name: str) -> Path:
        """One of the client's files waiting for SAGA, as it is in its folder now."""
        store = self._open_store()
        try:
            client = self._known_client(store, cui)
            placed = [self.cfg.data_dir / stored for stored in store.saga_placement(client)]
        finally:
            store.close()
        # Only the files on record, by name: nothing else in the folder, and nothing outside it.
        path = next((each for each in placed if each.name == name), None)
        if path is None:
            raise EfacturaError(NOT_FOUND, f"No file named {name} waits for SAGA for {client}.")
        if not path.is_file():
            raise EfacturaError(NOT_FOUND, f"The file is gone from the client's folder: {path}")
        return path

    def confirm_saga_import(self, cui: str, version: str | None = None, source: str = "api") -> dict:
        """SAGA has imported this client's files: mark every invoice in them as imported,
        and move the files, as SAGA got them, to the archive.

        The invoices are those the program put in the files when it last wrote them, which
        is what SAGA read. Refused, changing nothing, when `version` is given and the files
        have changed since it was read, or when the files are not up to date. With nothing
        waiting, the answer's archive is None.
        """
        if source not in SAGA_IMPORT_SOURCES:
            raise EfacturaError(INVALID_INPUT, f"source must be one of: {', '.join(SAGA_IMPORT_SOURCES)}.")
        version = (version or "").strip() or None
        store = self._open_store()
        try:
            client = self._known_client(store, cui)
            # The same lock as every writer of the files: nothing rewrites them meanwhile.
            with _FileLock(
                self.cfg.saga_lock_path, wait=SAGA_LOCK_WAIT,
                busy="The files for SAGA are being written by another part of the program.",
            ):
                archive = self._archive_saga_files(store, client, version, source)
        finally:
            store.close()
        return {"ok": True, "archive": archive}

    def _archive_saga_files(self, store: Store, cui: str, version: str | None, source: str) -> dict | None:
        waiting = self._saga_waiting(store, cui)
        if not waiting["files"]:
            return None
        if not waiting["up_to_date"]:
            raise EfacturaError(
                SAGA_FILES_STALE,
                f"The files for SAGA of {cui} are not up to date, so what SAGA imported is not known. "
                "Bring them up to date, import them again and confirm then.",
            )
        # Read once: the bytes compared with the version are the bytes archived.
        contents = []
        for file in waiting["files"]:
            try:
                contents.append((file["name"], Path(file["path"]).read_bytes()))
            except OSError as exc:
                raise EfacturaError(SAGA_FILES_STALE, f"A file for SAGA could not be read: {exc}") from exc
        if version and version != _version_of(contents):
            raise EfacturaError(
                SAGA_FILES_CHANGED,
                f"The files for SAGA of {cui} have changed since version {version} was read; nothing was "
                "marked. Read them again, import them and confirm with the new version.",
            )
        # What waits now, as the files would be written, against what they hold and were recorded
        # with: an account changed but not yet written, or a file written but not recorded, would
        # mark an invoice as SAGA never got it.
        folder, wanted = self._saga_files_now(store, cui)
        should_hold = {self._stored_path(folder / file.name): (sorted(file.ids), file.content) for file in wanted}
        holds = {
            stored: (sorted(ids), content)
            for (stored, ids), (_, content) in zip(store.saga_placement(cui).items(), contents)
        }
        if holds != should_hold:
            raise EfacturaError(
                SAGA_FILES_STALE,
                f"The files for SAGA of {cui} do not hold what is waiting now (something changed since they "
                "were written); nothing was marked. Bring them up to date, import them and confirm then.",
            )
        now = self._now()
        when = now.isoformat()
        try:
            folder = self._new_archive_folder(cui, now)
        except OSError as exc:
            raise EfacturaError(SAGA_ARCHIVE_ERROR, f"The archive folder could not be made: {exc}. Nothing was marked.") from exc
        ids = [message_id for file in waiting["files"] for message_id in file["ids"]]
        try:
            kept = []
            for name, content in contents:
                target = folder / name
                try:
                    _write_file(target, content)
                except OSError as exc:
                    raise EfacturaError(
                        SAGA_ARCHIVE_ERROR, f"The archive could not be written ({target}): {exc}. Nothing was marked."
                    ) from exc
                kept.append(target)
            import_id = store.record_saga_import(
                cui=cui, imported_at=when, source=source, folder=self._stored_path(folder),
                files=[file["name"] for file in waiting["files"]], ids=ids,
            )
        except BaseException:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        # The invoices wait no more, so bringing the folder up to date takes the files out of
        # it. One SAGA still holds open is noted, and removed at a later try.
        try:
            self._place_saga_files(store, cui, when)
            failure = None
        except Exception as exc:
            failure = exc
        self._note_saga_outcome(store, cui, failure, when)
        journal.record(
            "accounts", "saga.imported",
            f"Import in SAGA confirmed for {cui}: {len(ids)} invoice(s) marked as imported, the files archived.",
            cui=cui, client=store.client_name(cui), invoices=len(ids), source=source, import_id=import_id,
            files=[file["name"] for file in waiting["files"]],
        )
        return {
            "id": import_id, "cui": cui, "imported_at": when, "source": source, "invoices": len(ids), "ids": ids,
            "folder": str(folder), "files": [{"name": path.name, "path": str(path)} for path in kept],
        }

    def _new_archive_folder(self, cui: str, now: datetime) -> Path:
        """A folder of its own for one import: by client, then by its date and time."""
        base = self.cfg.data_dir / SAGA_ARCHIVE_DIR / cui / now.strftime("%Y-%m-%d_%H-%M-%S")
        folder, number = base, 1
        while folder.exists():
            number += 1
            folder = base.with_name(f"{base.name}_{number}")
        folder.mkdir(parents=True)
        return folder

    def _saga_waiting(self, store: Store, cui: str) -> dict:
        """One client's files for SAGA as the program last wrote them, for confirming an import."""
        files, written = [], store.saga_ledger(cui)
        for stored, ids in store.saga_placement(cui).items():
            path = self.cfg.data_dir / stored
            files.append({
                "name": path.name, "path": str(path), "invoices": len(ids), "ids": ids,
                "written_at": written.get(stored), "present": path.is_file(),
            })
        return {
            "cui": cui, "client": store.client_name(cui), "file_per": _saga_file_per(store),
            "folder": str(self._client_folder(store, cui)), "files": files,
            "invoices": sum(file["invoices"] for file in files),
            "up_to_date": store.saga_problem(cui) is None and all(file["present"] for file in files),
            "version": _saga_version([Path(file["path"]) for file in files]),
        }

    def _known_client(self, store: Store, cui: str) -> str:
        """A client in the list, or one taken off it whose files for SAGA are still kept: they
        are listed, so they can be confirmed too."""
        client = normalize_cui(cui)
        if store.client_enabled(client) is None and client not in store.clients_with_saga_files():
            raise EfacturaError(NOT_FOUND, f"No client with CUI {client}.")
        return client

    def saga_archive(self, cui: str) -> dict:
        """One client's confirmed imports, the newest first."""
        cui = normalize_cui(cui)
        store = self._open_store()
        try:
            imports = [self._present_import(entry) for entry in store.saga_imports(cui)]
        finally:
            store.close()
        return {"ok": True, "cui": cui, "imports": imports}

    def saga_archive_entry(self, import_id: int) -> dict:
        """One confirmed import, with its invoices as the lists give them."""
        store = self._open_store()
        try:
            entry = self._saga_import(store, import_id)
            rows = store.messages_by_ids(entry["ids"])
        finally:
            store.close()
        invoices = [self._present(row) for row in rows]
        counts = {
            "invoices": len(invoices),
            "received": sum(1 for row in rows if _is_received(row["message_type"])),
            "issued": sum(1 for row in rows if _is_issued(row["message_type"])),
            "unmarked": sum(1 for row in rows if not row["uploaded_to_accounting"]),
        }
        return {"ok": True, "import": {**self._present_import({**entry, **counts}), "invoices": invoices}}

    def saga_archive_file(self, import_id: int, name: str) -> Path:
        """One of the files of a confirmed import, as SAGA got it."""
        store = self._open_store()
        try:
            entry = self._saga_import(store, import_id)
        finally:
            store.close()
        if name not in entry["files"]:  # only the names on record: nothing outside the entry
            raise EfacturaError(NOT_FOUND, f"Import {import_id} has no file named {name}.")
        path = self.cfg.data_dir / entry["folder"] / name
        if not path.is_file():
            raise EfacturaError(NOT_FOUND, f"The archived file is gone: {path}")
        return path

    def open_saga_archive(self, import_id: int) -> dict:
        """Show the folder of a confirmed import in the file manager."""
        store = self._open_store()
        try:
            entry = self._saga_import(store, import_id)
        finally:
            store.close()
        folder = self.cfg.data_dir / entry["folder"]
        if not folder.is_dir():
            raise EfacturaError(NOT_FOUND, f"The archive folder is gone: {folder}")
        _reveal(folder)
        return {"ok": True, "folder": str(folder)}

    def _saga_import(self, store: Store, import_id: int) -> dict:
        entry = store.saga_import(int(import_id))
        if entry is None:
            raise EfacturaError(NOT_FOUND, f"No import with id {import_id}.")
        return entry

    def _present_import(self, entry: dict) -> dict:
        """An import as the commands return it: its folder and files with full paths, and
        whether each file is still there."""
        folder = self.cfg.data_dir / entry["folder"]
        shown = {key: value for key, value in entry.items() if key != "ids"}
        return {
            **shown, "folder": str(folder),
            "files": [{"name": name, "path": str(folder / name), "present": (folder / name).is_file()} for name in entry["files"]],
        }

    def choose_folder(self, purpose: str = "saga") -> dict:
        """Let the person pick a folder in the computer's own dialog; None if they cancel.
        The dialog says which folder it is asking for, and starts where that one is now."""
        if purpose == "saga":
            store = self._open_store()
            try:
                start, title = str(self._saga_dir(store)), "Folderul pentru SAGA"
            finally:
                store.close()
        elif purpose == "backups":
            from . import backup  # here, because that module imports this one

            now = backup.status(self.cfg)
            start = now["folder"] if now["folder_found"] else str(Path.home())
            title = "Folderul pentru copiile de siguranță"
        else:
            raise EfacturaError(INVALID_INPUT, "purpose must be 'saga' or 'backups'.")
        return {"ok": True, "folder": _ask_for_folder(start, title)}

    def open_saga_folder(self, cui: str | None = None, message_id: str | None = None) -> dict:
        """Show a folder in the file manager: the one holding an invoice's SAGA file, or
        the SAGA folder itself, or one client's part of it.

        By invoice, it is the folder the file is really in. That differs from the folder
        set now when the setting was changed after the file was written.
        """
        if message_id is not None:
            folder = self._folder_of_saga_file(message_id)
        else:
            store = self._open_store()
            try:
                if cui:
                    client = normalize_cui(cui)
                    # Its folder gets its name of now first. Made here beside one under an
                    # earlier name, it would keep that one from being renamed whole.
                    self._write_saga_files(store, client)
                    folder = self._client_folder(store, client)
                else:
                    folder = self._saga_dir(store)
            finally:
                store.close()
            folder.mkdir(parents=True, exist_ok=True)
        _reveal(folder)
        return {"ok": True, "folder": str(folder)}

    def open_folder(self, folder: str | None) -> dict:
        """Show any folder the program knows of in the file manager (the backup folder)."""
        if not folder or not Path(folder).is_dir():
            raise EfacturaError(NOT_FOUND, f"The folder was not found: {folder}")
        _reveal(Path(folder))
        return {"ok": True, "folder": str(folder)}

    def _folder_of_saga_file(self, message_id: str) -> Path:
        store = self._open_store()
        try:
            row = store.get_message(message_id)
        finally:
            store.close()
        if row is None:
            raise EfacturaError(NOT_FOUND, f"No saved message with id: {message_id}")
        folder = (self.cfg.data_dir / row["saga_xml_path"]).parent if row["saga_xml_path"] else None
        if folder is None or not folder.is_dir():
            raise EfacturaError(NOT_FOUND, "This invoice has no file for SAGA.")
        return folder

    def secrets(self) -> dict:
        """Every key the tool holds, in full. Only for the person at this computer."""
        tokens = auth.load_tokens(self.cfg.token_file)
        values = {
            "openrouter_api_key": self.cfg.openrouter_api_key,
            "anaf_client_id": self.cfg.client_id,
            "anaf_client_secret": self.cfg.client_secret,
            "api_key": self.cfg.api_key,
            "anaf_access_token": tokens.access_token if tokens else "",
            "anaf_refresh_token": (tokens.refresh_token or "") if tokens else "",
        }
        return {
            "ok": True,
            "secrets": [
                {"key": key, "value": value, "editable": key in EDITABLE_SECRETS}
                for key, value in values.items()
            ],
        }

    def set_secret(self, key: str, value: str) -> dict:
        """Change a key. An empty value goes back to what config.toml says."""
        if key not in EDITABLE_SECRETS:
            raise EfacturaError(
                INVALID_INPUT, f"Only these can be changed here: {', '.join(EDITABLE_SECRETS)}."
            )
        value = str(value or "").strip()
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            # A line break inside a key ends up quoted in the error of the first call that uses it.
            raise EfacturaError(INVALID_INPUT, "A key is one line of text: no line breaks or other control characters.")
        self._save_setting(key, value)
        return self.secrets()

    def _save_setting(self, key: str, value: str) -> None:
        store = self._open_store()
        try:
            if value:
                store.set_setting(key, value)
            else:
                store.delete_setting(key)
        finally:
            store.close()
        self.cfg = _with_saved_settings(self._file_cfg)
        # Never the value: it may be a key.
        journal.record(
            "settings", "settings.secret_changed" if key in EDITABLE_SECRETS else "settings.changed",
            f"Setting {key} changed.", name=key,
        )

    # --- rules and accounts ---------------------------------------------------

    def rules_overview(self) -> dict:
        """Everything the rules screen shows."""
        store = self._open_store()
        try:
            return {
                "ok": True,
                "accounts": store.accounts(),
                "issued_accounts": store.accounts(ISSUED_KIND),
                "rules": store.rules(),
                "jev_instructions": store.get_setting(JEV_INSTRUCTIONS) or "",
                "jev_line_instructions": store.get_setting(JEV_LINE_INSTRUCTIONS) or DEFAULT_JEV_LINE_INSTRUCTIONS,
                **_issued_questions(store),
                "min_confidence": _min_confidence(store),
                "jev_configured": bool(self.cfg.openrouter_api_key),  # whether Jev can be asked at all
            }
        finally:
            store.close()

    def save_account(self, cont: str, description: str = "", kind: str = RECEIVED_KIND) -> dict:
        """Add an account Jev may choose, or change its description, in the list for one kind
        of invoice: received, or issued by the client."""
        cont, kind = _checked_account(cont), _checked_kind(kind)
        store = self._open_store()
        try:
            store.save_account(cont, str(description or "").strip(), kind)
            journal.record(
                "rules", "account.saved", f"Account {cont} saved in Jev's list{_for_kind(kind)}.", cont=cont, kind=kind,
            )
        finally:
            store.close()
        return self.rules_overview()

    def delete_account(self, cont: str, kind: str = RECEIVED_KIND) -> dict:
        kind = _checked_kind(kind)
        store = self._open_store()
        try:
            store.delete_account(str(cont).strip(), kind)
            journal.record(
                "rules", "account.removed", f"Account {cont} removed from Jev's list{_for_kind(kind)}.",
                cont=str(cont).strip(), kind=kind,
            )
        finally:
            store.close()
        return self.rules_overview()

    def save_rule(
        self,
        rule_id: int | None = None,
        *,
        name: str,
        cont: str,
        keywords=(),
        item_codes=(),
        commodity_prefixes=(),
        supplier_cuis=(),
        client_cui: str | None = None,
        enabled: bool = True,
        direction: str | None = None,
    ) -> dict:
        """Add a rule (rule_id None) or replace one. `client_cui` None: for every client.
        `direction` says which invoices it decides, received (to begin with) or issued; a
        rule replaced without it keeps its own."""
        tidy = _rule_from(
            str(name or "").strip(), _checked_account(cont),
            keywords=keywords, item_codes=item_codes,
            commodity_prefixes=commodity_prefixes, supplier_cuis=supplier_cuis,
        )
        if not tidy.name:
            raise EfacturaError(INVALID_INPUT, "A rule needs a name.")
        if not any(getattr(tidy, condition) for condition in CONDITIONS):
            raise EfacturaError(
                INVALID_INPUT,
                "A rule needs at least one condition: a keyword, a code or a supplier.",
            )
        fields = {
            "name": tidy.name,
            "cont": tidy.cont,
            **{condition: getattr(tidy, condition) for condition in CONDITIONS},
            "client_cui": normalize_cui(client_cui) if client_cui else None,
            "enabled": bool(enabled),
        }
        if direction is not None:
            fields["direction"] = _checked_kind(direction)
        store = self._open_store()
        try:
            kind = fields.get("direction")
            if kind is None:
                kept = next((rule["direction"] for rule in store.rules() if rule["id"] == rule_id), RECEIVED_KIND)
                kind = kept
            if kind == ISSUED_KIND and tidy.supplier_cuis:
                raise EfacturaError(
                    INVALID_INPUT,
                    "A rule for issued invoices cannot name a supplier: the supplier is always the client itself.",
                )
            if rule_id is None:
                store.add_rule(**fields)
            else:
                store.update_rule(rule_id, **fields)
            journal.record(
                "rules", "rule.added" if rule_id is None else "rule.changed",
                f"Rule {tidy.name!r} for {tidy.cont} {'added' if rule_id is None else 'changed'}.",
                name=tidy.name, cont=tidy.cont, rule_id=rule_id, client=fields["client_cui"], kind=kind,
                looks_for=", ".join((*tidy.keywords, *tidy.supplier_cuis, *tidy.item_codes, *tidy.commodity_prefixes)),
            )
        finally:
            store.close()
        return self.rules_overview()

    def delete_rule(self, rule_id: int) -> dict:
        store = self._open_store()
        try:
            store.delete_rule(rule_id)
            journal.record("rules", "rule.removed", f"Rule {rule_id} removed.", rule_id=rule_id)
        finally:
            store.close()
        return self.rules_overview()

    def move_rule(self, rule_id: int, up: bool) -> dict:
        """Move a rule one place earlier or later in the order the rules are checked."""
        store = self._open_store()
        try:
            store.move_rule(rule_id, up)
        finally:
            store.close()
        return self.rules_overview()

    # --- proposed rules -------------------------------------------------------

    def rule_suggestions(self) -> dict:
        """Rules worth creating: what Jev or a person decided lately, for invoices that no
        rule would decide today. Invoices that would get the same rule are one proposal."""
        store = self._open_store()
        try:
            since = self._recent()
            rulebooks: dict[str, Rulebook] = {}
            proposals: dict[tuple, dict] = {}
            for row in store.decided_without_rule(since):
                subject = _stored_subject(row["rule_subject"])
                if subject is None:
                    continue
                if row["cui"] not in rulebooks:
                    rulebooks[row["cui"]] = _rulebook_for(store, row["cui"])
                proposal = propose(subject, row["cont"])
                if proposal is None or rulebooks[row["cui"]].rule_for(subject):
                    continue
                listed = proposals.setdefault(proposal.key, {
                    "cont": proposal.cont,
                    "keywords": list(proposal.keywords),
                    "supplier_cuis": list(proposal.supplier_cuis),
                    "supplier_name": row["supplier_name"] if proposal.supplier_cuis else None,
                    "invoice_ids": [],
                })
                listed["invoice_ids"].append(row["id"])
            # The one most invoices stand behind first; of equals, the latest decision
            # (the rows came newest first, and the sort keeps their order).
            shown = sorted(proposals.values(), key=lambda listed: -len(listed["invoice_ids"]))
            shown = shown[:MAX_LISTED_SUGGESTIONS]
            classified = _subjects(store.classified_subjects(since))
        finally:
            store.close()
        rules = [
            Rule("", listed["cont"], listed["keywords"], supplier_cuis=listed["supplier_cuis"])
            for listed in shown
        ]
        # Few invoices match any of the proposals; only those are tried on each one.
        proposals_together = any_of(rules)
        matched_by_some = [pair for pair in classified if proposals_together.matches(pair[1])]
        for listed, rule in zip(shown, rules):
            listed.update(_evidence(rule, matched_by_some))
        return {"ok": True, "count": len(proposals), "days": RECENT_DAYS, "suggestions": shown}

    def rule_preview(
        self,
        *,
        keywords=(),
        item_codes=(),
        commodity_prefixes=(),
        supplier_cuis=(),
        client_cui: str | None = None,
    ) -> dict:
        """How a rule with these conditions would have done on the invoices given an
        account lately: how many it matches, and on which accounts those are."""
        rule = _rule_from(
            "", "", keywords=keywords, item_codes=item_codes,
            commodity_prefixes=commodity_prefixes, supplier_cuis=supplier_cuis,
        )
        store = self._open_store()
        try:
            classified = _subjects(store.classified_subjects(
                self._recent(), normalize_cui(client_cui) if client_cui else None
            ))
        finally:
            store.close()
        return {"ok": True, **_evidence(rule, classified), "days": RECENT_DAYS}

    def dismiss_rule_suggestions(self, ids: list[str]) -> dict:
        """ "Not now": stop proposing a rule for these invoices, unless their account changes."""
        ids = [str(i) for i in ids]
        if not ids:
            raise EfacturaError(INVALID_INPUT, "Give at least one message id.")
        store = self._open_store()
        try:
            store.dismiss_suggestions(ids)
            journal.record(
                "rules", "rule.proposal_turned_down", f"Proposed rule turned down for {len(ids)} invoice(s).", invoices=len(ids)
            )
        finally:
            store.close()
        return {"ok": True, "dismissed": ids}

    def _recent(self) -> str:
        """The moment RECENT_DAYS ago, as decisions are dated."""
        return (self._now() - timedelta(days=RECENT_DAYS)).isoformat()

    def _rule_suggestion(self, store: Store, row: dict) -> dict | None:
        """The rule to propose on one invoice's screen, however old the invoice is. Proposed
        rules are for received invoices only, so far."""
        if not _is_received(row["message_type"]):
            return None
        if row["classification_status"] != CLASSIFIED or row["classification_method"] == "rules":
            return None
        state = store.suggestion_state(row["id"])
        subject = _stored_subject(state["rule_subject"])
        if subject is None or state["suggestion_dismissed_for"] == row["cont"]:
            return None
        if propose(subject, row["cont"]) is None or _rulebook_for(store, row["cui"]).rule_for(subject):
            return None
        return _suggestion_dict(subject, row["cont"], row["supplier_name"])

    def set_min_confidence(self, value: float) -> dict:
        """The confidence below which a Jev answer goes to a person, from 0 to 1."""
        usable = isinstance(value, (int, float)) and not isinstance(value, bool)
        if not usable or not 0 <= value <= 1:  # NaN fails the comparison too
            raise EfacturaError(INVALID_INPUT, "The confidence level must be a number from 0 to 1.")
        store = self._open_store()
        try:
            store.set_setting(MIN_CONFIDENCE, repr(float(value)))
            journal.record("settings", "settings.confidence", f"Confidence level set to {float(value)}.", level_set=float(value))
        finally:
            store.close()
        log.info("Confidence level set to %s", value)
        return self.classification_settings()

    def test_rules(
        self, *, lines: list[dict], supplier_name: str = "", supplier_cui: str = "",
        client_cui: str | None = None, currency: str = "RON", credit_note: bool = False,
        ask: str = "rules_then_jev",
    ) -> dict:
        """Classify a made-up invoice the way a received one is, and save nothing but what
        asking Jev cost. The order of the checks is that of _classify_one: line by line, as
        for a client with an account per line (and with no client chosen, as for a new one),
        or by the largest line for a client with one account per invoice."""
        if ask not in TRIAL_ASKS:
            raise EfacturaError(INVALID_INPUT, f"ask must be one of: {', '.join(TRIAL_ASKS)}.")
        client = normalize_cui(client_cui) if client_cui else None
        invoice = _trial_invoice(lines, supplier_name, supplier_cui, currency, credit_note)
        store = self._open_store()
        try:
            # The rules for every client, plus those of the chosen one.
            rulebook = _rulebook_for(store, client)
            level = _min_confidence(store)
            per_line = (client is None or store.client_per_line(client)) and len(invoice.lines) > 1
            trial = _Trial(store, rulebook, client, level, ask == "jev_only")
            if per_line:
                result = self._try_lines(trial, invoice)
            else:
                result = self._try_rules_then_jev(trial, invoice)
        finally:
            store.close()
        result.update(
            per_line=per_line, accounts=rulebook.accounts, jev_calls=trial.calls,
            cost_usd=trial.cost_usd if trial.calls else None, jev_stopped=trial.stopped,
            suggestion=_trial_suggestion(invoice, rulebook, result["lines"]),
        )
        journal.record(
            "rules", "rule.tested", f"Rules tried on a trial invoice: {result['reason']}",
            decided_by=result["decided_by"], cont=result["cont"], asked_jev=trial.calls > 0,
            cost_usd=result["cost_usd"],
        )
        return {"ok": True, **result}

    def _try_rules_then_jev(self, trial: "_Trial", invoice: Invoice) -> dict:
        """One account for the whole trial invoice, decided by its largest line."""
        heaviest = deciding_line(invoice)
        entry = _trial_line(heaviest) if heaviest else {}
        result = {
            "decided_by": "nobody", "cont": None, "account_description": None,
            "deciding_line": heaviest.description if heaviest else None,
            "rule": None, "jev": None, "why_not": None, "reason": "",
        }

        def answer(**said) -> dict:
            said = {**result, **said}
            if said["cont"]:
                said["account_description"] = trial.rulebook.accounts.get(said["cont"]) or None
            line = {**entry, **{key: said[key] for key in _TRIAL_LINE_SAYS}}
            return {**said, "lines": [line] if heaviest else []}

        subject = subject_of(invoice)
        matching = [] if trial.jev_only or subject is None else trial.rulebook.rules_for(subject)
        if matching:
            rule = matching[0]
            reason = f'Rule "{rule.name}" matched line {heaviest.number}, the largest on the invoice.'
            return answer(decided_by="rule", cont=rule.cont, reason=reason, rule=_rule_said(matching, subject, heaviest.number))
        if not invoice.lines:
            return answer(why_not="no_lines", reason="The invoice has no lines to decide from.")
        cannot = self._why_jev_cannot_be_asked(trial.rulebook)
        if cannot:
            return answer(why_not=cannot[0], reason=f"{trial.not_matched}, and {cannot[1]}")

        request = jev_request(invoice, trial.rulebook, self.cfg.jev_model)
        if not request["state"]["linii"]:
            return answer(why_not="jev_failed", reason="The invoice and the list of accounts do not fit in one request to Jev.")
        cont, why_not, reason, said = self._trial_ask(trial, request, "invoice", heaviest.number)
        return answer(decided_by="jev" if cont else "nobody", cont=cont, why_not=why_not, reason=reason, jev=said)

    def _try_lines(self, trial: "_Trial", invoice: Invoice) -> dict:
        """Each line of the trial invoice on its own, as _classify_lines decides a real one:
        the rules first; a discount or a line worth nothing takes the account of the largest
        line; Jev for the rest, one question per distinct line. The invoice has more than one line."""
        largest = deciding_line(invoice)
        entries: dict[int, dict] = {}
        for item in invoice.lines:
            subject = line_subject(invoice, item)
            matching = [] if trial.jev_only else trial.rulebook.rules_for(subject)
            if matching:
                entries[item.number] = _trial_line(
                    item, decided_by="rule", cont=matching[0].cont, rule=_rule_said(matching, subject, item.number),
                    reason=f'Rule "{matching[0].name}" matched line {item.number}.',
                )
            elif follows_largest(invoice, item):
                entries[item.number] = _trial_line(
                    item, decided_by="follows", follows=largest.number,
                    reason=f"Takes the account of line {largest.number}, the largest on the invoice.",
                )
        groups: dict[tuple, list[Line]] = {}
        for item in invoice.lines:
            if item.number not in entries:
                groups.setdefault(same_question(item), []).append(item)
        cannot = self._why_jev_cannot_be_asked(trial.rulebook) if groups else None
        for items in groups.values():
            first = items[0]
            if cannot:
                said = {"why_not": cannot[0], "reason": f"{trial.not_matched}{'' if trial.jev_only else ' this line'}, and {cannot[1]}"}
            elif trial.stopped:
                said = {"why_not": "not_asked", "reason": f"Not sent to Jev: OpenRouter failed on line {trial.stopped['line']}."}
            else:
                request = jev_line_request(invoice, first, trial.rulebook, self.cfg.jev_model)
                if fits(request):
                    cont, why_not, reason, jev_said = self._trial_ask(trial, request, "line", first.number)
                    said = {"decided_by": "jev" if cont else "nobody", "cont": cont, "why_not": why_not, "reason": reason, "jev": jev_said}
                else:
                    said = {"why_not": "jev_failed", "reason": "This line and the list of accounts do not fit in one request to Jev."}
            for item in items:
                entries[item.number] = _trial_line(item, same_as=first.number if item is not first else None, **said)

        head = entries[largest.number]
        for entry in entries.values():
            if entry["decided_by"] == "follows":
                entry["cont"] = head["cont"]
        lines = [entries[item.number] for item in invoice.lines]
        for entry in lines:
            entry["account_description"] = trial.rulebook.accounts.get(entry["cont"]) or None if entry["cont"] else None
        waiting = sum(1 for entry in lines if not entry["cont"])
        whole = {key: head[key] for key in _TRIAL_LINE_SAYS}
        if waiting:  # as the program keeps an invoice: an account only once every line has one
            whole.update(decided_by="nobody", cont=None, account_description=None, why_not=head["why_not"] or "lines_left")
        return {
            **whole, "deciding_line": largest.description, "lines": lines, "waiting": waiting,
            "reason": _trial_lines_summary(lines),
        }

    def _why_jev_cannot_be_asked(self, rulebook: Rulebook) -> tuple[str, str] | None:
        if not self.cfg.openrouter_api_key:
            return "no_key", "OpenRouter is not set up ([openrouter] api_key in config.toml)."
        if not rulebook.accounts:
            return "no_accounts", "there are no accounts for Jev to choose from."
        return None

    def _trial_ask(
        self, trial: "_Trial", request: dict, about: str, line: int,
    ) -> tuple[str | None, str | None, str, dict]:
        """Ask Jev once about a trial invoice or one of its lines, and keep only what it cost.
        One attempt, whatever it costs: the person is waiting, and every attempt is paid for.
        Returns the account (None when there is none), why not, the reason, and what Jev said
        and was sent."""
        call = jev.ask(self._http, self.cfg.openrouter_api_key, request)
        answer, error = None, call.error
        if call.ok:
            try:
                answer = read_jev_answer(call.response, trial.rulebook)
            except EfacturaError as exc:
                error = exc.message
        trial.store.add_jev_call(
            message_id=RULE_TEST,
            cui=trial.client,
            called_at=self._now().isoformat(),
            model=call.model or self.cfg.jev_model,
            request_json=json.dumps(request, ensure_ascii=False),
            response_json=json.dumps(call.response, ensure_ascii=False) if call.response is not None else None,
            http_status=call.status,
            input_tokens=call.input_tokens,
            output_tokens=call.output_tokens,
            cost_usd=call.cost_usd,
            duration_ms=call.duration_ms,
            error=error,
        )
        trial.calls += 1
        trial.cost_usd += call.cost_usd or 0
        said = {
            "choice": answer.choice if answer else None,
            "confidence": answer.confidence if answer else None,
            "threshold": trial.level,
            "refused": answer.refused if answer else False,
            "probabilities": dict(answer.probabilities) if answer else {},
            "cost_usd": call.cost_usd,
            "duration_ms": call.duration_ms,
            "error": None if answer else (error or "Jev gave no answer."),
            # None when OpenRouter was not reached. A refused key or an empty account (401,
            # 402, 403) is not helped by waiting, and the screen says so.
            "http_status": call.status,
            # What left the program: the question and what it was asked about.
            "sent": {"question": request["questions"][QUESTION]["instructions"], "state": request["state"]},
        }
        if answer is None:
            if call.service_wide:
                trial.stopped = {"line": line, "http_status": call.status, "error": said["error"]}
            return None, "jev_failed", f"Jev could not decide this {about}: {said['error']}", said
        cont, reason, _ = _judged(answer, trial.level)
        if cont:
            return cont, None, reason, said
        below = not answer.refused and answer.choice is not None and answer.confidence is not None
        return None, "below_threshold" if below else "jev_declined", reason, said

    def costs(
        self, since: str | None = None, cui: str | None = None, until: str | None = None,
        group: str = "month",
    ) -> dict:
        """What the Jev calls have cost between two days, in total and per day, week,
        month or year."""
        _check_date(since)
        _check_date(until, "until")
        if group not in COST_GROUPS:
            raise EfacturaError(INVALID_INPUT, f"group must be one of: {', '.join(COST_GROUPS)}.")
        cui = normalize_cui(cui) if cui else None
        store = self._open_store()
        try:
            totals = store.jev_costs(since=since, cui=cui, until=until, group=group)
        finally:
            store.close()
        return {
            "ok": True,
            "since": since,
            "until": until,
            "cui": cui,
            "group": group,
            **totals,
            # Only what the invoices cost: a trial in the rule test is in the total, not here.
            "average_cost_per_invoice_usd": (
                totals["invoice_cost_usd"] / totals["invoices"] if totals["invoices"] else None
            ),
        }

    def jev_calls(
        self, since: str | None = None, until: str | None = None, cui: str | None = None,
        limit: int = 200,
    ) -> dict:
        """What Jev was asked, newest first: which invoice, what it answered, what it cost."""
        _check_date(since)
        _check_date(until, "until")
        if not 1 <= limit <= MAX_LISTED_CALLS:
            raise EfacturaError(INVALID_INPUT, f"limit must be from 1 to {MAX_LISTED_CALLS}.")
        store = self._open_store()
        try:
            rows = store.jev_call_list(since, until, normalize_cui(cui) if cui else None, limit)
        finally:
            store.close()
        calls = []
        for row in rows:
            answer = _jev_answer_in(row.pop("response_json"))
            calls.append({**row, "choice": answer.get("choice"), "confidence": answer.get("confidence")})
        return {"ok": True, "count": len(calls), "calls": calls}

    def invoice_view(self, message_id: str) -> dict:
        """Everything the screen shows for one message: the stored row, the invoice read
        from the XML, both XML texts, Jev's last answer and the rule worth creating from it."""
        store = self._open_store()
        try:
            row = store.get_message(message_id, include_xml=True)
            if row is None:
                raise EfacturaError(NOT_FOUND, f"No saved message with id: {message_id}")
            last_call = store.last_jev_call(message_id)
            client_name = store.client_name(row["cui"])
            rule_suggestion = self._rule_suggestion(store, row)
            saga_state = self._saga_state(store, row["cui"])
            saga_import = store.saga_import_of(message_id)
        finally:
            store.close()
        shown = {**self._present(row), "saga_import": saga_import}
        xml = shown.pop("invoice_xml")
        shown.pop("signature_xml")
        invoice = parse_invoice(xml or "")
        return {
            "ok": True,
            "invoice": shown,
            "client_name": client_name,
            "document": _as_json(invoice) if invoice else None,
            "xml": xml,
            "saga_xml": _own_saga_xml(invoice, row),
            "saga": saga_state,
            "jev": last_call and {
                "called_at": last_call["called_at"],
                "model": last_call["model"],
                "cost_usd": last_call["cost_usd"],
                "error": last_call["error"],
                "probabilities": _jev_answer_in(last_call["response_json"]).get("probabilities"),
            },
            "rule_suggestion": rule_suggestion,
        }

    def decision_history(self, message_id: str) -> dict:
        """How an invoice got its account, each time it changed, the newest first."""
        store = self._open_store()
        try:
            if store.get_message(message_id) is None:
                raise EfacturaError(NOT_FOUND, f"No saved message with id: {message_id}")
            return {"ok": True, "decisions": store.decisions(message_id)}
        finally:
            store.close()

    def _classify_waiting(self, store: Store, cui: str, result: dict) -> None:
        """Classify what this sync saved, plus anything left waiting by an earlier one.

        Never fails the sync: the messages are saved either way, and an invoice that could
        not be classified simply waits for the next run.
        """
        tally = _new_tally()
        waiting = store.pending_classification(cui)
        log.debug("%s invoice(s) of %s wait for an account", len(waiting), cui)
        counts, _, _ = self._classify_each(store, waiting, tally)

        self._write_saga_files(store, cui)
        result["new"] = [self._present(store.get_message(entry["id"])) for entry in result["new"]]
        result["classification"] = {
            **counts,
            "skipped": sum(entry["classification_status"] is None for entry in result["new"]),
            **tally,
        }
        if counts[CLASSIFIED]:
            result["saga_folder"] = str(self._client_folder(store, cui))

    def _classify_each(
        self, store: Store, ids: list[str], tally: dict, jev: bool = True, again: bool = False,
    ) -> tuple[dict, int, bool]:
        """Decide these invoices one after another: how many ended in each state, how many
        left classification, and whether OpenRouter stopped answering on the way. One that
        cannot be decided now stays as it was; the others are still tried."""
        counts = {CLASSIFIED: 0, REVIEW: 0, PENDING: 0}
        left_out, jev_down = 0, False
        for message_id in ids:
            how = _Pass(source=AGAIN if again else DOWNLOAD, jev_allowed=jev and not jev_down)
            try:
                status = self._classify_one(store, message_id, tally, how)
            except EfacturaError as exc:
                if exc.code == NOT_CLASSIFIABLE:
                    # Waiting again would change nothing: it leaves classification, with why.
                    store.set_classification(message_id, classification_status=None, classification_error=exc.message)
                    log.warning("Message %s left out of classification: %s", message_id, exc.message)
                    left_out += 1
                    continue
                # OpenRouter itself is failing (connection, key, credit, rate limit), so
                # the invoices after this one are not sent in this run either.
                jev_down = jev_down or exc.code == JEV_ERROR
                status = _status_now(store, message_id) if again else PENDING
                log.warning("Message %s not classified: %s", message_id, exc.message)
            except Exception as exc:
                log.exception("Could not classify message %s", message_id)
                _note_error(store, message_id, f"{type(exc).__name__}: {exc}")
                # A download sends only invoices that wait, and they go on waiting.
                status = _status_now(store, message_id) if again else PENDING
            if status in counts:
                counts[status] += 1
        return counts, left_out, jev_down

    def classify_again(self, cui: str, jev: bool = True) -> dict:
        """Send this client's invoices that wait for a person or for Jev, received and
        issued, back through the rules and, with `jev`, Jev; as a download would, but on
        purpose, after a rule or an account changed or once OpenRouter answers again.

        What is already decided stays: a line a person chose, and a line Jev was sure of
        unless a rule now matches it. Without `jev`, what Jev said before stays too, and an
        invoice waiting for Jev goes on waiting."""
        cui = normalize_cui(cui)
        tally = _new_tally()
        counts, left_out, jev_down = {CLASSIFIED: 0, REVIEW: 0, PENDING: 0}, 0, False
        with self._lock():
            store = self._open_store()
            try:
                client = store.client_name(cui)
                ids = store.to_classify_again(cui)
                if ids:
                    began = time.monotonic()
                    try:
                        counts, left_out, jev_down = self._classify_each(store, ids, tally, jev=jev, again=True)
                    finally:
                        self._write_saga_files(store, cui)
                    journal.record(
                        "accounts", "classification.again",
                        f"Classified again for {cui}: {len(ids)} invoice(s), {counts[CLASSIFIED]} got an account, "
                        f"{counts[REVIEW]} still to check, {counts[PENDING]} waiting for Jev.",
                        level="warning" if jev_down else "info",
                        cui=cui, client=client, total=len(ids), classified=counts[CLASSIFIED], review=counts[REVIEW],
                        waiting=counts[PENDING], skipped=left_out, jev_asked=jev, jev_stopped=jev_down, **tally,
                        duration_ms=_since(began),
                    )
            finally:
                store.close()
        return {
            "ok": True, "cui": cui, "client": client, "total": len(ids),
            "classified": counts[CLASSIFIED], "review": counts[REVIEW], "waiting": counts[PENDING], "skipped": left_out,
            "jev_asked": jev, "jev_stopped": jev_down, **tally,
        }

    def classify_again_all(self, jev: bool = True) -> dict:
        """`classify_again` for every client in the list with an invoice to check or waiting
        for Jev, one after another. Once Jev stops answering, it is not asked for the
        clients after."""
        store = self._open_store()
        try:
            cuis = [client["cui"] for client in store.clients() if client["review_count"] or client["waiting_count"]]
        finally:
            store.close()
        results, ask = [], jev
        for cui in cuis:
            result = self.classify_again(cui, jev=ask)
            ask = ask and not result["jev_stopped"]
            results.append(result)
        totals = {
            key: sum(result[key] for result in results)
            for key in ("total", "classified", "review", "waiting", "skipped", "jev_calls", "jev_cost_usd")
        }
        return {"ok": True, **totals, "clients": results}

    def _classifiable(
        self, store: Store, message_id: str, force: bool, classified_ok: bool
    ) -> tuple[dict, Invoice]:
        """The saved row and its invoice, or the reason it may not be classified."""
        row = store.get_message(message_id, include_xml=True)
        if row is None:
            raise EfacturaError(NOT_FOUND, f"No saved message with id: {message_id}")
        if not _gets_an_account(row["message_type"]):
            raise EfacturaError(
                NOT_CLASSIFIABLE,
                f"Only invoices, received or issued, are classified; this message is: {row['message_type']}.",
            )
        invoice = parse_invoice(row["invoice_xml"] or "")
        if invoice is None:
            raise EfacturaError(NOT_CLASSIFIABLE, "The saved XML cannot be read as an invoice.")
        if row["uploaded_to_accounting"]:
            # The accounting program already has it; a new file would change nothing there.
            raise EfacturaError(
                NOT_CLASSIFIABLE,
                "This invoice is marked as uploaded to accounting. Clear the flag first "
                "(mark-uploaded --undo) if its account really has to change.",
            )
        if row["classification_status"] is None and not force:
            raise EfacturaError(
                NOT_CLASSIFIABLE,
                "This invoice was saved outside classification (before it existed, or with "
                "classification switched off). Pass force to classify it anyway.",
            )
        if row["classification_status"] == CLASSIFIED and not classified_ok:
            raise EfacturaError(
                NOT_CLASSIFIABLE,
                f"Already classified on {row['cont']}. Pass force to classify it again, or "
                "set another account with set-cont.",
            )
        return row, invoice

    def _classify_one(self, store: Store, message_id: str, tally: dict, how: _Pass = _Pass()) -> str:
        """Decide one invoice and return its new status.

        `how.again`: an invoice that waits for a person or for Jev, sent back on purpose
        (classify_again). The lines a person chose stay, and so does a line Jev was sure of
        unless a rule now matches it. Without Jev allowed, whatever no rule decides is left
        as it was. One that goes back to a person is a detail in the journal."""
        again, jev_allowed = how.again, how.jev_allowed
        row = store.get_message(message_id, include_xml=True)
        invoice = parse_invoice(row["invoice_xml"] or "")
        if invoice is None:
            raise EfacturaError(NOT_CLASSIFIABLE, "The saved XML cannot be read as an invoice.")

        to_review = partial(self._to_review, how=how)
        issued = _is_issued(row["message_type"])
        rulebook = _rulebook_for(store, row["cui"], issued=issued)
        # One line is one account either way: such an invoice is decided, shown and booked whole.
        # Unless told, one decided line by line stays so, whatever the client's switch says: a
        # person may have split it. One with one account follows the switch.
        if how.per_line is not None:
            shaped = how.per_line
        else:
            shaped = _stored_lines(row) is not None or store.client_per_line(row["cui"])
        per_line = (shaped or how.line is not None) and len(invoice.lines) > 1
        chosen = {
            entry["line"]: entry for entry in _stored_lines(row) or () if entry["method"] in BY_A_PERSON
        } if again and per_line else {}
        earlier = _same_invoice_saved_before(store, row)
        sent_twice = _sent_twice(earlier) if earlier else None
        if how.line is not None:
            # One line on purpose. An invoice held back for a person stays held back: that line
            # waits for the person too, with the reason, and the other lines stay as they are.
            held_back = sent_twice or _parties_misfit(row["cui"], invoice, issued)
            if held_back:
                entries = _aligned(_stored_lines(row) or [], invoice)
                follows = follows_largest(invoice, next(item for item in invoice.lines if item.number == how.line))
                entries = [
                    _line_entry(entry["line"], None, FOLLOWS if follows else None, held_back) if entry["line"] == how.line
                    else entry
                    for entry in entries
                ]
                return self._record_lines(store, row, invoice, entries, why=held_back, how=how)
            return self._classify_lines(store, row, invoice, rulebook, tally, how)
        if earlier:
            # Booking it automatically would enter the invoice in SAGA a second time.
            why = sent_twice
            if per_line:  # every line waits for the person, as it would have been decided
                open_lines = [
                    chosen.get(item.number)
                    or _line_entry(item.number, None, FOLLOWS if follows_largest(invoice, item) else None, why)
                    for item in invoice.lines
                ]
                return self._record_lines(store, row, invoice, open_lines, why=why, how=how)
            return to_review(store, row, why)
        misfit = _parties_misfit(row["cui"], invoice, issued)
        if misfit:
            # SAGA files an invoice by its supplier: one whose parties do not fit its kind
            # would land on the wrong side, so a person looks at it first.
            return to_review(store, row, misfit)

        if per_line:
            return self._classify_lines(store, row, invoice, rulebook, tally, how, chosen)

        decision = None if how.skip_rules else decide_by_rules(invoice, rulebook)
        log.debug(
            "Message %s, %s line(s), one account for the invoice: %s", message_id, len(invoice.lines),
            f"rule {decision.rule!r} matched line {decision.line}, account {decision.cont}" if decision
            else "the rules were skipped" if how.skip_rules else "no rule matched",
        )
        if decision:
            return self._finish(
                store, row, invoice, decision.cont, "rules",
                f'Rule "{decision.rule}" matched line {decision.line}, the largest on the invoice.',
                how=how, noted={"rule": decision.rule, "match": _match_said(decision.match)},
            )
        if again and not jev_allowed:
            return row["classification_status"]  # no rule decides it: left as it was, Jev's word too
        if not invoice.lines:
            return to_review(store, row, "The invoice has no lines to decide from.")
        no_rule = "The rules were skipped" if how.skip_rules else "No rule matched"
        if not self.cfg.openrouter_api_key:
            return to_review(
                store, row,
                f"{no_rule}, and OpenRouter is not set up ([openrouter] api_key in config.toml).",
            )
        if not rulebook.accounts:
            return to_review(store, row, f"{no_rule}, and there are no accounts for Jev to choose from.")
        if not jev_allowed:
            _note_error(store, message_id, "Not sent to Jev: OpenRouter failed earlier in this run.")
            return PENDING

        request = jev_request(invoice, rulebook, self.cfg.jev_model)
        log.debug(
            "Message %s goes to Jev: %s line(s) sent, %s left out to fit, %s account(s) to choose from",
            message_id, len(request["state"]["linii"]), request["state"]["linii_omise"], len(rulebook.accounts),
        )
        if not request["state"]["linii"]:
            # Not even the deciding line fits beside the list of accounts.
            return to_review(
                store, row, "The invoice and the list of accounts do not fit in one request to Jev."
            )
        try:
            answer = self._ask_jev(store, row, request, rulebook, tally)
        except _JevCouldNotDecide as exc:
            return to_review(store, row, f"Jev could not decide this invoice: {exc}")
        cont, reason, jev_said = _judged(answer, _min_confidence(store))
        noted = {"probabilities": answer.probabilities}
        if cont is None:
            return to_review(store, row, reason, noted=noted, **jev_said)
        return self._finish(store, row, invoice, cont, "jev", reason, how=how, noted=noted, **jev_said)

    def _classify_lines(
        self, store: Store, row: dict, invoice: Invoice, rulebook: Rulebook, tally: dict, how: _Pass,
        chosen: dict[int, dict] | None = None,
    ) -> str:
        """Decide each line on its own: the rules first; a discount or a line worth nothing
        takes the account of the largest line; Jev for the rest, one question per distinct
        line; a person for whatever is left. While OpenRouter is failing as a whole the
        invoice keeps waiting, with the lines Jev has already answered: the next run asks
        only about the others, so a long invoice is not paid for again from the start. The
        invoice has more than one line.

        `how.again` (see _classify_one): the lines in `chosen`, which a person chose, are kept
        as they are, and Jev's earlier account for a line no rule matches now. When Jev is not
        asked this time (not allowed, no key, no accounts), every line no rule decides stays
        as it was, and an invoice that was decided whole stays whole, with Jev's proposal.

        `how.line`: only that line is decided, the others stay as they are; with the rules
        skipped, Jev is asked about it whatever it is, a discount included. `how.skip_rules`:
        no rule is tried."""
        again, jev_allowed = how.again, how.jev_allowed
        largest = deciding_line(invoice).number
        by_number = {item.number: item for item in invoice.lines}
        waiting = row["classification_status"] == PENDING
        stored = _stored_lines(row)
        if how.line is not None:
            entries = {entry["line"]: entry for entry in _aligned(stored or [], invoice) if entry["line"] != how.line}
        else:
            entries = dict(chosen or {})
        for number, rule in ({} if how.skip_rules else rules_by_line(invoice, rulebook)).items():
            if number not in entries:
                entries[number] = _line_entry(
                    number, rule.cont, "rules", f'Rule "{rule.name}" matched line {number}.', rule=rule.name,
                    match=_match_said(rule.match(line_subject(invoice, by_number[number]))),
                )
        asked_for_this_line = how.line is not None and how.skip_rules
        for item in invoice.lines:
            if item.number not in entries and follows_largest(invoice, item) and not asked_for_this_line:
                entries[item.number] = _line_entry(
                    item.number, None, FOLLOWS, f"Takes the account of line {largest}, the largest on the invoice."
                )
        asked = [item for item in invoice.lines if item.number not in entries]
        why_not = None
        no_rule = "The rules were skipped" if how.skip_rules else "No rule matched this line"
        if asked and not self.cfg.openrouter_api_key:
            why_not = f"{no_rule}, and OpenRouter is not set up ([openrouter] api_key in config.toml)."
        elif asked and not rulebook.accounts:
            why_not = f"{no_rule}, and there are no accounts for Jev to choose from."
        if again and asked and (not jev_allowed or (why_not and not waiting)):
            # Jev is not asked this time: what no rule decides now stays as it was.
            if waiting:
                return PENDING  # it goes on waiting for Jev, untouched
            if stored is None:
                return row["classification_status"]  # decided whole before: whole, with Jev's proposal
            # What Jev said stays; an account from a rule that no longer matches does not.
            kept = {entry["line"]: entry for entry in stored if entry.get("asked")}
            for item in asked:
                entries[item.number] = kept.get(item.number) or _line_entry(
                    item.number, reason=why_not or "No rule matched this line, and Jev was not asked this time."
                )
            return self._record_lines(store, row, invoice, [entries[item.number] for item in invoice.lines], how=how)
        if asked and not why_not and not jev_allowed:
            _note_error(store, row["id"], "Not sent to Jev: OpenRouter failed earlier in this run.")
            return PENDING
        answered = [entry for entry in stored or () if entry.get("asked")]
        if waiting and how.line is None:
            # Answers kept by an earlier run that OpenRouter stopped. One line asked about on
            # purpose is asked again.
            earlier = {entry["line"]: entry for entry in answered}
        elif again:
            earlier = {entry["line"]: entry for entry in answered if entry["cont"]}  # Jev was sure of these
        else:
            earlier = {}  # a decision made again from the start, on purpose
        groups: dict[tuple, list[Line]] = {}
        for item in asked:
            groups.setdefault(same_question(item), []).append(item)
        level = _min_confidence(store) if groups and not why_not else None
        answered_now = False
        for items in groups.values():
            cont, reason, jev_said, asked = None, why_not, {}, False
            known = next((earlier[item.number] for item in items if item.number in earlier), None)
            if known is not None:
                cont, reason, asked = known["cont"], known["reason"], True
                jev_said = {key: known.get(key) for key in ("suggested_cont", "confidence", "confidence_threshold", "probabilities")}
            elif not why_not:
                request = jev_line_request(invoice, items[0], rulebook, self.cfg.jev_model)
                if not fits(request):
                    reason = "This line and the list of accounts do not fit in one request to Jev."
                else:
                    asked = True
                    try:
                        answer = self._ask_jev(store, row, request, rulebook, tally, line=items[0].number)
                    except _JevCouldNotDecide as exc:
                        reason = f"Jev could not decide this line: {exc}"
                    except EfacturaError:
                        if waiting:
                            _keep_answered(store, row, invoice, entries)
                        elif again and answered_now:
                            # Sent back on purpose: what Jev answered so far is paid for and kept, the
                            # other lines stay as they were. Left as it was if nothing was answered.
                            self._record_lines(store, row, invoice, _merged(invoice, entries, stored), how=how)
                        raise
                    else:
                        answered_now = True
                        cont, reason, jev_said = _judged(answer, level)
                        jev_said["probabilities"] = answer.probabilities
            for item in items:
                entries[item.number] = _line_entry(
                    item.number, cont, "jev" if cont else None, reason, asked=asked, **jev_said
                )
        return self._record_lines(store, row, invoice, [entries[item.number] for item in invoice.lines], how=how)

    def _record_lines(
        self, store: Store, row: dict, invoice: Invoice, entries: list[dict], why: str | None = None,
        how: _Pass = _Pass(),
    ) -> str:
        """Record each line's account, and in the invoice's history each line that changed.
        The invoice is ready for SAGA once every line has one; until then it waits for a
        person, for `why` when it is given. Its own `cont` and the fields beside it are those
        of its largest line, so whatever reads one account per invoice keeps working. An
        invoice sent back on purpose (`how.again`) that waits for a person is a detail in
        the journal."""
        quiet = how.again
        largest = deciding_line(invoice).number
        head = next(entry for entry in entries if entry["line"] == largest)
        for entry in entries:
            if entry["method"] == FOLLOWS:
                entry["cont"] = head["cont"]
        left = [entry for entry in entries if not entry["cont"]]
        subject = subject_of(invoice)
        common = {
            "line_accounts": json.dumps(entries, ensure_ascii=False),
            "rule_subject": subject.to_json() if subject else None,
            "suggested_cont": head["suggested_cont"],
            "confidence": head["confidence"],
            "confidence_threshold": head["confidence_threshold"],
            "classification_error": None,
        }
        details = {"id": row["id"], "cui": row["cui"], "invoice_number": row.get("invoice_number"),
                   "supplier": row.get("supplier_name"), "lines": len(entries)}
        if left:
            reason = why or _lines_left(left)
            to_choose = [entry for entry in left if entry["method"] != FOLLOWS] or left
            store.set_classification(
                row["id"], classification_status=REVIEW, cont=None, classification_method=None,
                classification_reason=reason, classified_at=None, **common,
            )
            self._note_decisions(store, row, how, entries)
            journal.record(
                "accounts", "account.to_review", f"Message {row['id']} needs a person: {reason}",
                level="detail" if quiet else "warning", **details, reason=reason, lines_left=len(to_choose),
            )
            return REVIEW
        reason = _lines_summary(entries)
        forgotten = _not_now_forgotten(store, row["id"], head["cont"])
        store.set_classification(
            row["id"], classification_status=CLASSIFIED, cont=head["cont"],
            classification_method=head["method"], classification_reason=reason,
            classified_at=self._now().isoformat(), **common, **forgotten,
        )
        self._note_decisions(store, row, how, entries)
        methods = [entry["method"] for entry in entries]
        journal.record(
            "accounts", "account.by_lines", f"Message {row['id']} booked line by line: {reason}",
            **details, cont=head["cont"], accounts=sorted({entry["cont"] for entry in entries}),
            by_rules=methods.count("rules"), by_jev=methods.count("jev"),
            by_person=methods.count("human") + methods.count("jev_accepted"), following=methods.count(FOLLOWS),
            as_invoice=methods.count(FROM_INVOICE),
        )
        return CLASSIFIED

    def _note_decisions(self, store: Store, row: dict, how: _Pass, entries: list[dict]) -> None:
        """Add to the invoice's history what changed: `entries` have just replaced what `row`,
        as it was read before, held. Written after the invoice, so the history never tells
        of a change that was not saved."""
        store.add_decisions(_changes(row, entries, how, self._now().isoformat()))

    def _ask_jev(
        self, store: Store, row: dict, request: dict, rulebook: Rulebook, tally: dict, line: int | None = None,
    ):
        """Ask Jev, storing every request and reply.

        Raises jev_error when OpenRouter as a whole is failing, and _JevCouldNotDecide when
        only this invoice could not be answered.
        """
        error, service_wide = None, True
        for attempt in range(JEV_ATTEMPTS):
            call = jev.ask(self._http, self.cfg.openrouter_api_key, request)
            answer, error, service_wide = None, call.error, call.service_wide
            if call.ok:
                try:
                    answer = read_jev_answer(call.response, rulebook)
                except EfacturaError as exc:
                    error, service_wide = exc.message, False
            store.add_jev_call(
                message_id=row["id"],
                cui=row["cui"],
                called_at=self._now().isoformat(),
                model=call.model or self.cfg.jev_model,
                request_json=json.dumps(request, ensure_ascii=False),
                response_json=(
                    json.dumps(call.response, ensure_ascii=False) if call.response is not None else None
                ),
                http_status=call.status,
                input_tokens=call.input_tokens,
                output_tokens=call.output_tokens,
                cost_usd=call.cost_usd,
                duration_ms=call.duration_ms,
                error=error,
            )
            tally["jev_calls"] += 1
            about = f"message {row['id']}" + (f", line {line}" if line is not None else "")
            journal.record(
                "jev", "jev.answered" if answer is not None else "jev.failed",
                f"Jev answered for {about}." if answer is not None
                else f"Jev gave no usable answer for {about}: {error}",
                # One line of an invoice among many is a detail; the invoice gets its own line.
                level=("info" if line is None else "detail") if answer is not None else "warning",
                id=row["id"], invoice_number=row.get("invoice_number"), line=line, status=call.status,
                cost_usd=call.cost_usd, error=error, duration_ms=call.duration_ms,
            )
            tally["jev_cost_usd"] += call.cost_usd or 0
            if answer is not None:
                log.debug(
                    "Jev's answer for %s: %s, confidence %s, %s other account(s) weighed",
                    about, answer.choice or ("a refusal" if answer.refused else "none of these"),
                    answer.confidence, max(len(answer.probabilities) - 1, 0),
                )
                return answer
            log.debug(
                "Jev's call %s of %s for %s failed (%s): %s", attempt + 1, JEV_ATTEMPTS, about,
                "worth trying again" if call.transient else "not worth trying again", error,
            )
            if not call.transient or attempt == JEV_ATTEMPTS - 1:
                break
            _pause(JEV_RETRY_DELAY)
        if not service_wide:
            raise _JevCouldNotDecide(error)
        # The invoice stays as it was: waiting, in review, or with its earlier account.
        _note_error(store, row["id"], error)
        raise EfacturaError(JEV_ERROR, error or "Jev gave no answer.")

    def _finish(
        self, store: Store, row: dict, invoice: Invoice, cont: str, method: str, reason: str,
        how: _Pass = _Pass(), noted: dict | None = None, **jev_said,
    ) -> str:
        """Record the decision: `cont` on every line. The files for SAGA follow from what is
        recorded (_write_saga_files), so SAGA never finds a decision that was not. `noted`
        is what only the history keeps: the rule and what it found, or how likely Jev found
        each account."""
        subject = subject_of(invoice)
        forgotten = _not_now_forgotten(store, row["id"], cont)
        store.set_classification(
            row["id"],
            classification_status=CLASSIFIED,
            cont=cont,
            classification_method=method,
            classification_reason=reason,
            classified_at=self._now().isoformat(),
            classification_error=None,
            line_accounts=None,
            # Kept so rules can be tried on this invoice later without its XML.
            rule_subject=subject.to_json() if subject else None,
            **forgotten,
            **jev_said,
        )
        self._note_decisions(store, row, how, [_line_entry(None, cont, method, reason, **(noted or {}), **jev_said)])
        journal.record(
            "accounts", {"rules": "account.by_rule", "jev": "account.by_jev"}.get(method, "account.by_person"),
            f"Message {row['id']} booked on {cont} ({method}).",
            id=row["id"], cui=row["cui"], invoice_number=row.get("invoice_number"),
            supplier=row.get("supplier_name"), cont=cont, method=method, reason=reason,
            confidence=jev_said.get("confidence"),
        )
        return CLASSIFIED

    def _to_review(
        self, store: Store, row: dict, reason: str, how: _Pass = _Pass(), noted: dict | None = None, **jev_said,
    ) -> str:
        """The invoice waits for a person, for `reason`. Sent back on purpose (`how.again`),
        it is written in the journal as a detail: it was waiting for one already."""
        quiet = how.again
        store.set_classification(
            row["id"],
            classification_status=REVIEW,
            cont=None,
            classification_method=None,
            classification_reason=reason,
            classified_at=None,
            classification_error=None,
            line_accounts=None,
            **jev_said,
        )
        self._note_decisions(store, row, how, [_line_entry(None, reason=reason, **(noted or {}), **jev_said)])
        journal.record(
            "accounts", "account.to_review", f"Message {row['id']} needs a person: {reason}",
            level="detail" if quiet else "warning",
            id=row["id"], cui=row["cui"], invoice_number=row.get("invoice_number"),
            supplier=row.get("supplier_name"), reason=reason, suggested=jev_said.get("suggested_cont"),
            confidence=jev_said.get("confidence"),
        )
        return REVIEW

    # --- the files for SAGA ---------------------------------------------------------

    def _write_saga_files(self, store: Store, cui: str) -> None:
        """Make this client's folder hold exactly the invoices SAGA has not got yet: those
        with an account that are not marked as imported, in one file or in a file each.

        Called after anything that changes that set. It never fails the action that led
        here: the decision is recorded already. Whatever goes wrong (a file open in SAGA,
        the stick unplugged, the database busy) is noted for the screen and the journal,
        and tried again at the next change, at the next start, or when a person asks.
        """
        when = self._now().isoformat()
        try:
            # One writer at a time, also across processes. What is waiting is read inside,
            # so the writer that comes last writes what is true last.
            with _FileLock(
                self.cfg.saga_lock_path, wait=SAGA_LOCK_WAIT,
                busy="The files for SAGA are being written by another part of the program.",
            ):
                try:
                    self._place_saga_files(store, cui, when)
                    failure = None
                except Exception as exc:
                    failure = exc
                self._note_saga_outcome(store, cui, failure, when)
        except Exception as exc:  # the lock was not had, or the outcome could not be noted
            self._note_saga_outcome(store, cui, exc, when)

    def _note_saga_outcome(self, store: Store, cui: str, failure: Exception | None, when: str) -> None:
        """Keep, or clear, the reason this client's files are not up to date. Never raises."""
        try:
            if failure is None:
                if store.saga_problem(cui):
                    store.set_saga_problem(cui, None, when)
                    journal.record(
                        "accounts", "saga.files_written", f"The files for SAGA of {cui} are up to date again.",
                        cui=cui, client=store.client_name(cui),
                    )
                return
            reason = (
                failure.message if isinstance(failure, EfacturaError) else f"{type(failure).__name__}: {failure}"
            )
            if not isinstance(failure, (OSError, EfacturaError)):
                log.error("Bringing the files for SAGA of %s up to date failed", cui, exc_info=failure)
            store.set_saga_problem(cui, reason, when)
            journal.record(
                "accounts", "saga.files_failed",
                f"The files for SAGA of {cui} could not be brought up to date: {reason}",
                level="warning", cui=cui, client=store.client_name(cui), error=reason,
            )
        except Exception:
            log.exception("Could not note how bringing the files for SAGA of %s up to date ended", cui)

    def _saga_files_now(self, store: Store, cui: str) -> tuple[Path, list]:
        """The client's folder for SAGA, and the files it should hold for what waits now."""
        waiting = []
        for row in store.waiting_for_saga(cui):
            invoice = parse_invoice(row["invoice_xml"] or "")
            if invoice is None:  # it was read when it was given its account
                log.warning("Message %s has an account but its invoice cannot be read", row["id"])
                continue
            waiting.append(saga.Entry(
                invoice, row["cont"], row["id_solicitare"], row["id"], _line_conts(row), issued=_is_sale(cui, invoice),
            ))
        return self._client_folder(store, cui), saga.files_for(waiting, _saga_file_per(store))

    def _client_folder(self, store: Store, cui: str) -> Path:
        """The client's folder inside the folder for SAGA as it is set now: "<name> - <CUI>".
        A company that is not in the client list (taken off it, or never put on) keeps the
        folder it had, or gets one named by its CUI alone."""
        saga_dir = self._saga_dir(store)
        name = store.client_name(cui)
        if name:
            return saga_dir / saga.client_folder_name(name, cui)
        kept = self._folder_names_kept(store, cui)
        if kept:
            return saga_dir / kept[0]
        # No name was kept (every try since the folder got its name failed): where its files are.
        for stored in store.saga_ledger(cui):
            parent = (self.cfg.data_dir / stored).parent
            if parent.parent == saga_dir and saga.is_client_folder(parent.name, cui):
                return parent
        return saga_dir / cui

    def _folder_names_kept(self, store: Store, cui: str) -> list[str]:
        """The names the program keeps for this client's folder: first the one it last used,
        then any earlier ones that were still there when it last looked (held by another
        program, or holding files it did not write). One setting, the names apart by "/",
        which no folder's name can have."""
        kept = store.get_setting(SAGA_FOLDER_OF + cui) or ""
        return [
            name for name in kept.split("/")
            if name and "\\" not in name and saga.is_client_folder(name, cui)
        ]

    def _earlier_folders(self, store: Store, cui: str, folder: Path, there: bool) -> list[Path]:
        """The client's folders under other names, beside the one it should have: those the
        program keeps, the one an earlier version named by the CUI alone, and those its files
        are on record in. Only inside the folder for SAGA as it is set now. `there`: that
        folder can be reached."""
        saga_dir = folder.parent
        found = [saga_dir / name for name in (*self._folder_names_kept(store, cui), cui)]
        on_record = [
            parent for parent in ((self.cfg.data_dir / stored).parent for stored in store.saga_ledger(cui))
            if parent.parent == saga_dir and saga.is_client_folder(parent.name, cui)
        ]
        found += on_record
        if there and any(not parent.is_dir() for parent in dict.fromkeys(on_record)):
            # Files are on record in a folder that is not there: it was renamed by hand. Whatever
            # folder carries the CUI is looked at, so its files are not left behind, unknown.
            found += sorted(path for path in saga_dir.glob(f"* - {cui}") if path.is_dir())
        # Compared as written: to Windows two paths are the same whatever their capitals, and a
        # name changed only in its capitals is still a folder to rename.
        return [old for old in dict.fromkeys(found) if str(old) != str(folder)]

    def _rename_into_place(self, store: Store, cui: str, earlier: list[Path], folder: Path) -> None:
        """Give the client's folder its name of now by renaming the one it has, whole: what
        the program did not write goes with it.

        A folder that cannot be renamed (SAGA has a file of it open, another program holds
        it, both folders are there) is left to the way that follows: the files are written
        in the new folder and the old ones removed one by one. It is tried again at every
        later pass, for as long as the folder is there.
        """
        for old in earlier:
            try:
                # A name that changed only in capital letters is the same folder to Windows.
                if not old.is_dir() or (folder.exists() and not _same_file(old, folder)):
                    continue
                old.rename(folder)
            except OSError as exc:
                log.info("The folder for SAGA %s could not be renamed to %s: %s", old, folder.name, exc)
                continue
            journal.record(
                "accounts", "saga.folder_moved",
                f"The folder for SAGA of {cui} was renamed from {old.name} to {folder.name}.",
                cui=cui, client=store.client_name(cui), old=old.name, new=folder.name,
            )
            return

    def _records_follow(self, store: Store, cui: str, folder: Path) -> None:
        """A file on record in a folder of the client that it is no longer in is put on record
        in the client's folder of now, where a file of that name is, and keeps the time it
        was written at. The folder was renamed: by the program a moment ago, by the program
        before it was stopped or the database refused, or by hand. Done before anything is
        written or forgotten, so no file is left in the folder that the program does not know."""
        saga_dir = folder.parent
        known = store.saga_ledger(cui)
        moved = {}
        for stored in known:
            old = self.cfg.data_dir / stored
            new = folder / old.name
            if str(old) == str(new) or self._stored_path(new) in known:
                continue
            if old.parent.parent != saga_dir or not saga.is_client_folder(old.parent.name, cui):
                continue
            # Gone from where it was; or, to Windows, the same file under other capitals.
            if new.is_file() and (not old.exists() or _same_file(old, new)):
                moved[stored] = self._stored_path(new)
        if moved:
            store.move_saga_files(cui, moved)

    def _note_client_folder(self, store: Store, cui: str, folder: Path, left: list[Path]) -> None:
        """Keep the name the client's folder now has, and after it the earlier folders that are
        still there, so each is tried again. One that stays is said once, when it is first left."""
        if not folder.parent.is_dir():
            return  # the folder for SAGA away: what is kept still says where the folder was
        kept = self._folder_names_kept(store, cui)
        names = [folder.name, *dict.fromkeys(old.name for old in left)]
        if names == kept:
            return
        store.set_setting(SAGA_FOLDER_OF + cui, "/".join(names))
        for old in left:
            if old.name in kept[1:]:
                continue
            empty = _is_empty(old)
            why = "another program holds it" if empty else "it holds files the program did not write"
            journal.record(
                "accounts", "saga.folder_left",
                f"The earlier folder for SAGA of {cui}, {old.name}, is still there: {why}. The program writes "
                f"this client's files in {folder.name} and removes the earlier folder once it can.",
                level="warning", cui=cui, client=store.client_name(cui), old=old.name, new=folder.name, empty=empty,
            )

    def _place_saga_files(self, store: Store, cui: str, when: str) -> None:
        folder, files = self._saga_files_now(store, cui)
        log.debug(
            "Files for SAGA of %s in %s: %s file(s), %s invoice(s)%s", cui, folder, len(files),
            sum(len(file.ids) for file in files),
            # The first few by name: with one file per invoice there may be hundreds.
            ": " + "; ".join(f"{file.name} with {len(file.ids)}" for file in files[:5]) + ("; …" if len(files) > 5 else "")
            if files else "",
        )
        saga_dir = folder.parent
        # Asked once: a share that does not answer makes every question wait.
        there = saga_dir.is_dir()
        earlier = self._earlier_folders(store, cui, folder, there)
        if there:
            self._rename_into_place(store, cui, earlier, folder)
            self._records_follow(store, cui, folder)
        known = store.saga_ledger(cui)
        if not there and any(
            _is_inside(old, saga_dir) and old.parent != folder for old in (self.cfg.data_dir / stored for stored in known)
        ):
            # Files wait in a folder of the client that is to be moved, and the folder for SAGA
            # is away (a stick, a share). Writing now would make an empty folder for SAGA in
            # its place and forget them: nothing is done until it is back.
            raise FileNotFoundError(f"The folder for SAGA cannot be reached: {saga_dir}")
        wanted: dict[str, Path] = {}
        placed: dict[str, str] = {}
        for file in files:
            path = folder / file.name
            stored = self._stored_path(path)
            wanted[stored] = path
            placed.update(dict.fromkeys(file.ids, stored))
            if _holds(path, file.content):
                # As it should be already: SAGA may have it open, so it is left alone. One the
                # records do not know here (a copy of the folder made by hand) goes on record.
                if stored not in known:
                    store.note_saga_file(stored, cui, when)
                continue
            # On record before it exists, so the folder never holds a file nobody knows of.
            store.note_saga_file(stored, cui, known.get(stored) or when)
            folder.mkdir(parents=True, exist_ok=True)
            _write_file(path, file.content)
            store.note_saga_file(stored, cui, when)
        store.place_in_saga_files(cui, placed, when)
        # Only now the files that are no longer wanted: the new ones are in place.
        failure = None
        emptied: list[Path] = []
        for stored in known:
            if stored in wanted:
                continue
            old = self.cfg.data_dir / stored
            try:
                if not any(_same_file(old, new) for new in wanted.values()):
                    if _is_inside(old, saga_dir) and not saga_dir.is_dir():
                        # Gone, or only away (a stick, a share)? Not forgotten until it is known.
                        raise FileNotFoundError(f"The folder for SAGA cannot be reached: {saga_dir}")
                    if not _is_inside(old, saga_dir) and not old.parent.parent.is_dir():
                        # In a folder for SAGA left behind that cannot be reached now: kept on record
                        # without holding anything up, and removed once it can be reached again.
                        continue
                    old.unlink(missing_ok=True)
                    if saga.is_client_folder(old.parent.name, cui):
                        emptied.append(old.parent)
            except OSError as exc:
                failure = failure or exc  # it stays on record and is tried again
                continue
            store.forget_saga_file(stored)
        # A folder of the client under an earlier name goes once it is empty. What is in it
        # that the program did not write is never removed, so such a folder stays, and so
        # does one another program holds; both are kept in mind and tried again.
        left = []
        for old in dict.fromkeys([*(earlier if there else []), *emptied]):
            if str(old) == str(folder) or _same_file(old, folder):
                continue
            try:
                old.rmdir()
            except OSError:
                if old in earlier and old.is_dir():
                    left.append(old)
        if failure:
            raise failure
        self._note_client_folder(store, cui, folder, left)

    def _saga_dir(self, store: Store) -> Path:
        """The folder for SAGA as it is set now. Another part of the program may have
        changed it since this Service was made (a download can run for minutes)."""
        saved = store.get_setting("saga_dir")
        return Path(saved) if saved else self._file_cfg.saga_dir

    def _saga_state(self, store: Store, cui: str, with_version: bool = False) -> dict:
        """How this client's files for SAGA stand, for the screen. The version, which reads
        every file, only where the screen sends it back: with the list of received invoices."""
        written = [when for when in store.saga_ledger(cui).values() if when]
        placed = [self.cfg.data_dir / stored for stored in store.saga_placement(cui)]
        problem = store.saga_problem(cui)
        state = {
            "file_per": _saga_file_per(store),
            "written_at": max(written, default=None),
            "problem": problem,
            # A file gone from the folder (by hand, a stick unplugged) is not up to date either.
            "up_to_date": problem is None and all(path.is_file() for path in placed),
        }
        if with_version:
            # What the screen sends back when a person confirms the import, as a program does.
            state["version"] = _saga_version(placed)
        return state

    def _stored_path(self, path: Path) -> str:
        """Relative to the data folder when inside it, so the folder can be moved."""
        try:
            return path.relative_to(self.cfg.data_dir).as_posix()
        except ValueError:
            return str(path)

    # --- internals ----------------------------------------------------------------

    def _open_store(self) -> Store:
        return Store(self.cfg.db_path)

    def _lock(self) -> "_FileLock":
        return _FileLock(self.cfg.lock_path)

    def _present(self, row: dict) -> dict:
        """A stored row as the commands return it: the file paths made absolute, and what
        the invoice is worth with VAT, which is not always what is left to pay."""
        shown = dict(row)
        for key in ("xml_path", "saga_xml_path"):
            if shown.get(key):
                shown[key] = str(self.cfg.data_dir / shown[key])
        if "line_accounts" in shown:
            shown["line_accounts"] = _stored_lines(shown)
        shown["total_with_vat"] = _plain(total_with_vat_of(shown))
        return shown

    def _anaf_service(self, lock_held: bool) -> AnafService:
        """An AnafService that takes its access token from the saved login.

        The tokens handed out are remembered: when ANAF rejects one, the renewal can tell
        whether another process has already replaced it.
        """
        handed_out: list[str] = []

        def get_token(force_refresh: bool) -> str:
            rejected = handed_out[-1] if force_refresh and handed_out else None
            token = self._access_token(force_refresh, lock_held, rejected)
            handed_out.append(token)
            return token

        return AnafService(self.cfg, self._http, get_token)

    def _access_token(self, force_refresh: bool, lock_held: bool, rejected: str | None) -> str:
        """The saved access token, renewed first when it has expired or ANAF rejected it.

        `rejected` is the token ANAF just refused, when this is a forced renewal.
        """
        now = self._now()
        tokens = auth.load_tokens(self.cfg.token_file)
        if auth.token_state(tokens, now) == auth.VALID and not force_refresh:
            log.debug("The saved ANAF access is used; valid until %s", tokens.access_expires_at.isoformat())
            return tokens.access_token
        log.debug(
            "The ANAF access is renewed: %s",
            "ANAF rejected the one sent" if force_refresh else f"it is {auth.token_state(tokens, now)}",
        )
        with nullcontext() if lock_held else self._lock():
            if not lock_held:
                # Another process may have renewed the login while this one was deciding.
                # Its refresh token replaced ours, so renewing with ours would be refused.
                tokens = auth.load_tokens(self.cfg.token_file)
            state = auth.token_state(tokens, now)
            if state == auth.VALID and (not force_refresh or tokens.access_token != rejected):
                return tokens.access_token
            if tokens is None or not tokens.refresh_token or state == auth.NEEDS_LOGIN:
                raise EfacturaError(
                    LOGIN_NEEDED,
                    "No usable saved login. Plug in the USB token and run the login "
                    "(efactura login, or login-start then login-finish).",
                )
            renewed = auth.refresh_tokens(self.cfg, self._http, tokens, now)
            auth.save_tokens(self.cfg.token_file, renewed)
            journal.record(
                "anaf", "anaf.renewed", "The ANAF login was renewed without the certificate.",
                valid_until=renewed.access_expires_at.isoformat(),
            )
        log.info("Login renewed; access valid until %s", renewed.access_expires_at.isoformat())
        return renewed.access_token

def configure_logging(cfg: Config) -> None:
    """Log to the data folder. Nothing is logged to standard output: that is for the JSON.

    Information and up goes to the text file and to the journal, where the page shows it.
    Debug records go to the journal's technical side only, which keeps them a few days."""
    logger = logging.getLogger("efactura")
    has_file = False
    for existing in list(logger.handlers):
        if isinstance(existing, logging.FileHandler):
            if existing.baseFilename == os.path.abspath(cfg.log_path):
                has_file = True
                continue
            logger.removeHandler(existing)
            existing.close()
    if not has_file:
        cfg.data_dir.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(cfg.log_path, encoding="utf-8")
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    journal.configure(cfg.db_path)
    _remember_keys(cfg)
    if not any(isinstance(existing, journal.JournalHandler) for existing in logger.handlers):
        logger.addHandler(journal.JournalHandler())
    if not any(isinstance(existing, technical.TechnicalHandler) for existing in logger.handlers):
        logger.addHandler(technical.TechnicalHandler())


def _remember_keys(cfg: Config) -> None:
    """The keys this program holds are never written in the journal or its technical side."""
    redact.remember(cfg.client_id, cfg.client_secret, cfg.api_key, cfg.openrouter_api_key)


def _last_day(window: "_Window"):
    """The last day a window reaches into: one that ends at midnight stops the day before."""
    return (window.finish - timedelta(microseconds=1)).date()


def _window_days(
    default_days: int, covered_until: str | None, days: int | None, now: datetime,
    cover_gap: bool = False,
) -> int:
    """Days to ask ANAF for. `covered_until` is when everything was last known to be saved.

    A given `days` is taken as it is, unless cover_gap asks for it to be a minimum.
    """
    if days is not None:
        if not 1 <= days <= MAX_DAYS:
            raise EfacturaError(INVALID_INPUT, f"days must be from 1 to {MAX_DAYS}.")
        if not cover_gap:
            return days
    window = days or default_days
    if covered_until:
        # Reach back to that point, plus a day of overlap.
        gap = now - datetime.fromisoformat(covered_until)
        window = max(window, math.ceil(gap.total_seconds() / 86400) + 1)
    return min(window, MAX_DAYS)


@dataclass(frozen=True)
class _Window:
    """The period one sync asks ANAF for."""

    begin: datetime
    finish: datetime
    days: int
    reaches_back: bool  # runs up to now, from at or before the point everything was saved to


def _plan_window(
    default_days: int, covered_until: str | None, days: int | None,
    start: str | None, end: str | None, now: datetime, cover_gap: bool = False,
) -> _Window:
    if start is None and end is None:
        window_days = _window_days(default_days, covered_until, days, now, cover_gap)
        return _Window(
            *_window(now, window_days), window_days, _reaches_back(now, window_days, covered_until)
        )
    if days is not None:
        raise EfacturaError(INVALID_INPUT, "Give either a number of days or dates, not both.")
    if start is None:
        raise EfacturaError(INVALID_INPUT, "A date range needs its first day.")

    today = now.date()
    first, last = _day(start), _day(end) if end else today
    begin = _midnight(first, now)
    if first > last or last > today:
        raise EfacturaError(
            INVALID_INPUT, "The first day must not be after the last, and neither after today."
        )
    if first < (now - timedelta(days=MAX_DAYS)).date():
        raise EfacturaError(INVALID_INPUT, f"ANAF keeps messages for {MAX_DAYS} days only.")
    # The sixtieth day back is allowed, from the hour ANAF still reaches.
    begin = max(begin, now - timedelta(days=MAX_DAYS) + OLDEST_MARGIN)
    end_of_last_day = _midnight(last + timedelta(days=1), now)
    finish = min(end_of_last_day, now - CLOCK_MARGIN)
    if begin >= finish:
        # The sixtieth day back in its last minutes, or today in its first: nothing lies between.
        raise EfacturaError(INVALID_INPUT, "ANAF has no moment left to be asked for in these days.")
    # A range that stops before today leaves the days after it unfetched, so it cannot
    # move the "everything is saved up to here" mark.
    covers_gap = covered_until is None or begin <= datetime.fromisoformat(covered_until)
    return _Window(
        begin=begin,
        finish=finish,
        days=(last - first).days + 1,
        reaches_back=last == today and covers_gap,
    )


def _midnight(day: date, now: datetime) -> datetime:
    """The start of `day` on the clock `now` was read from. Local time keeps the offset of
    that day: an offset copied from today's would put a day across the change of the clocks
    an hour off, and its first or last hour would never be asked for. A clock that is not the
    local one (another zone's) keeps its own offset."""
    midnight = datetime.combine(day, datetime.min.time())
    if now.utcoffset() == now.astimezone().utcoffset():
        return midnight.astimezone()
    return midnight.replace(tzinfo=now.tzinfo)


def _day(text: str) -> date:
    try:
        return date.fromisoformat(str(text))
    except ValueError:
        raise EfacturaError(INVALID_INPUT, "Dates are written like 2026-11-03.") from None


def _reaches_back(now: datetime, window_days: int, covered_until: str | None) -> bool:
    """Did this window start at or before the point up to which everything was saved?

    A run that did not (a short --days after a long pause) must not count as caught up,
    or the messages in between would never be fetched. Sixty days is all ANAF keeps.
    """
    if covered_until is None or window_days >= MAX_DAYS:
        return True
    return now - timedelta(days=window_days) <= datetime.fromisoformat(covered_until)


def _window(now: datetime, window_days: int) -> tuple[datetime, datetime]:
    end = now - CLOCK_MARGIN
    oldest = now - timedelta(days=MAX_DAYS) + OLDEST_MARGIN
    return max(end - timedelta(days=window_days), oldest), end


def _login_summary(tokens: auth.Tokens | None, now: datetime) -> dict:
    return {
        "state": auth.token_state(tokens, now),
        "access_expires_at": tokens.access_expires_at.isoformat() if tokens else None,
        "refresh_expires_at": (
            tokens.refresh_expires_at.isoformat() if tokens and tokens.refresh_expires_at else None
        ),
        "access_days_left": _days_left(tokens.access_expires_at if tokens else None, now),
        # When this reaches zero the USB token and PIN are needed again.
        "refresh_days_left": _days_left(tokens.refresh_expires_at if tokens else None, now),
    }


def _days_left(expires_at: datetime | None, now: datetime) -> int | None:
    return max(0, (expires_at - now).days) if expires_at else None


def _failure(entry: dict, error: EfacturaError) -> dict:
    return {
        "id": entry["id"],
        "message_type": str(entry.get("tip") or ""),
        "error": {"code": error.code, "message": error.message},
    }


def _tidy_name(name) -> str:
    return " ".join(str(name or "").split())


def _problem_with(name: str, written_cui: str) -> str | None:
    """Why a row of a client file cannot be used, as a code; None when it can."""
    if not written_cui:
        return "missing_cui"
    try:
        normalize_cui(written_cui)
    except EfacturaError:
        return INVALID_CUI
    return None if name else "missing_name"


def _with_saved_settings(cfg: Config) -> Config:
    """config.toml overlaid with what was changed on screen."""
    store = Store(cfg.db_path)
    try:
        saved = {field: store.get_setting(key) for key, field in SAVED_SETTINGS.items()}
    finally:
        store.close()
    changed = {
        field: Path(value) if field == "saga_import_dir" else value
        for field, value in saved.items()
        if value
    }
    return replace(cfg, **changed) if changed else cfg


# A web page is never told a folder's path, so the dialog is opened by this program, on
# the computer it runs on. It gets a process of its own because it needs its own main thread.
_FOLDER_DIALOG = """
import sys, tkinter
from tkinter import filedialog
window = tkinter.Tk()
window.withdraw()
window.attributes("-topmost", True)  # in front of the browser
chosen = filedialog.askdirectory(initialdir=sys.argv[1], title=sys.argv[2])
# As UTF-8 bytes: printed as text, Windows' code page cannot hold every Romanian letter.
sys.stdout.buffer.write(chosen.encode("utf-8"))
"""
FOLDER_DIALOG_TIMEOUT = 600  # seconds the dialog may stay open


def _ask_for_folder(start: str, title: str) -> str | None:
    try:
        dialog = subprocess.run(
            [sys.executable, "-c", _FOLDER_DIALOG, start, title],
            capture_output=True, timeout=FOLDER_DIALOG_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    chosen = dialog.stdout.decode("utf-8", errors="replace").strip()
    return str(Path(chosen)) if chosen else None


def _reveal(folder: Path) -> None:
    """Open a folder in the computer's file manager."""
    if os.name == "nt":
        os.startfile(folder)  # noqa: S606 - a folder of ours, opened in Explorer
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(folder)])


def _since(began: float) -> int:
    """Milliseconds since `began`, a time.monotonic() reading."""
    return round((time.monotonic() - began) * 1000)


def _saga_version(paths: list[Path]) -> str | None:
    """A fingerprint of a client's files for SAGA as they are on disk; None when there are
    none. It changes when any of them does, and only then."""
    if not paths:
        return None
    contents = []
    for path in paths:
        try:
            contents.append((path.name, path.read_bytes()))
        except OSError:
            contents.append((path.name, None))
    return _version_of(contents)


def _version_of(contents: list[tuple[str, bytes | None]]) -> str:
    """The fingerprint of files given by name and bytes (None: the file could not be read)."""
    digest = hashlib.sha256()
    for name, content in sorted(contents, key=lambda named: named[0]):
        digest.update(name.encode("utf-8") + b"\0")
        digest.update(content if content is not None else b"\0missing")
        digest.update(b"\0")
    return digest.hexdigest()[:16]


def _is_received(message_type: str | None) -> bool:
    return (message_type or "").upper().startswith(RECEIVED)


def _is_issued(message_type: str | None) -> bool:
    return (message_type or "").upper().startswith(ISSUED)


def _gets_an_account(message_type: str | None) -> bool:
    """An invoice the client received, or one it issued: both are classified."""
    return _is_received(message_type) or _is_issued(message_type)


def _new_tally() -> dict:
    return {"jev_calls": 0, "jev_cost_usd": 0}


def _rulebook_for(store: Store, cui: str, issued: bool = False) -> Rulebook:
    """The accounts and the rules that apply to one client's invoices of one kind (received,
    or issued by the client): its own rules first, then the ones shared by every client,
    each group in the order set on the rules screen."""
    kind = ISSUED_KIND if issued else RECEIVED_KIND
    applicable = [
        rule for rule in store.rules()
        if rule["enabled"] and rule["client_cui"] in (None, cui) and rule["direction"] == kind
    ]
    applicable.sort(key=lambda rule: rule["client_cui"] is None)  # stable: keeps the order
    if issued:
        instructions = store.get_setting(JEV_ISSUED_INSTRUCTIONS) or DEFAULT_JEV_ISSUED_INSTRUCTIONS
        line_instructions = store.get_setting(JEV_ISSUED_LINE_INSTRUCTIONS) or ""
    else:
        instructions = store.get_setting(JEV_INSTRUCTIONS) or ""
        line_instructions = store.get_setting(JEV_LINE_INSTRUCTIONS) or ""
    return Rulebook(
        accounts=store.accounts(kind),
        rules=tuple(
            Rule(rule["name"], rule["cont"], **{name: rule[name] for name in CONDITIONS}, client_cui=rule["client_cui"])
            for rule in applicable
        ),
        instructions=instructions,
        line_instructions=line_instructions,
        issued=issued,
    )


def _issued_questions(store: Store) -> dict:
    """The two questions put to Jev about the invoices a client issued, as they are in force."""
    return {
        "jev_issued_instructions": store.get_setting(JEV_ISSUED_INSTRUCTIONS) or DEFAULT_JEV_ISSUED_INSTRUCTIONS,
        "jev_issued_line_instructions": (
            store.get_setting(JEV_ISSUED_LINE_INSTRUCTIONS) or DEFAULT_JEV_ISSUED_LINE_INSTRUCTIONS
        ),
    }


def _checked_kind(kind) -> str:
    if kind not in KINDS:
        raise EfacturaError(INVALID_INPUT, f"The kind of invoice must be one of: {', '.join(KINDS)}.")
    return kind


def _for_kind(kind: str) -> str:
    return " for issued invoices" if kind == ISSUED_KIND else ""


def _cui_digits(cui: str | None) -> str:
    """A fiscal code as compared: its digits, without "RO" or spaces."""
    return re.sub(r"\D", "", cui or "")


def _is_sale(cui: str, invoice: Invoice) -> bool:
    """Whether SAGA files this invoice among the client's sales ("Ieșiri"): it does so by the
    supplier, whatever ANAF listed the message as."""
    return _cui_digits(invoice.supplier.cui) == _cui_digits(cui)


def _parties_misfit(cui: str, invoice: Invoice, issued: bool) -> str | None:
    """Why the parties of an invoice do not fit its kind for this client, or None. SAGA
    files an invoice whose supplier is the company under "Ieșiri", any other under "Intrări"."""
    client = _cui_digits(cui)
    supplier, customer = _cui_digits(invoice.supplier.cui), _cui_digits(invoice.customer.cui)
    if supplier == client and customer == client:
        return "The client invoiced itself. Decide whether this invoice has to be booked, and how."
    if issued and supplier != client:
        return (
            "The supplier on this issued invoice is not the client, so SAGA would not file it among "
            "the sales. Check that it belongs to this client."
        )
    if not issued and supplier == client:
        return (
            "The client is the supplier of this received invoice, so SAGA would file it among the "
            "sales. Check that it belongs to this client."
        )
    return None


def _trial_number(value, what: str, number: int) -> Decimal | None:
    """A number as Romanians write it, or None when nothing was written. Spaces between the
    digits are dropped ("12 000"); with a comma, the comma is the decimal point and the dots
    group thousands ("1.234,50"); without one, a dot is the decimal point ("28.50")."""
    text = "".join(str(value if value is not None else "").split())
    if not text:
        return None
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        parsed = Decimal(text)
    except InvalidOperation:
        parsed = None
    if parsed is None or not parsed.is_finite():
        raise EfacturaError(INVALID_INPUT, f"The {what} of line {number} must be a number.")
    # Far beyond any invoice. Past it, multiplying overflows, or writing the number out for
    # Jev takes a million digits. Read from the digits and the exponent, so nothing is computed.
    if parsed.adjusted() >= MAX_TRIAL_DIGITS or parsed.as_tuple().exponent < -MAX_TRIAL_DECIMALS:
        raise EfacturaError(
            INVALID_INPUT,
            f"The {what} of line {number} must be a number with at most {MAX_TRIAL_DIGITS} digits "
            f"before the decimal point and {MAX_TRIAL_DECIMALS} after it.",
        )
    return parsed


def _trial_text(value, what: str, number: int) -> str | None:
    text = str(value).strip() if value is not None else ""
    if len(text) > MAX_TRIAL_TEXT:
        raise EfacturaError(
            INVALID_INPUT, f"The {what} of line {number} is longer than {MAX_TRIAL_TEXT} characters."
        )
    return text or None


def _trial_invoice(
    lines: list[dict], supplier_name: str, supplier_cui: str, currency: str, credit_note: bool
) -> Invoice:
    """An invoice built from what was typed on the rule-test screen."""
    if not isinstance(lines, list) or not all(isinstance(item, dict) for item in lines):
        raise EfacturaError(INVALID_INPUT, "lines must be a list of lines.")
    if len(lines) > MAX_TRIAL_LINES:
        raise EfacturaError(INVALID_INPUT, f"A trial invoice has at most {MAX_TRIAL_LINES} lines.")
    built = []
    for item in lines:
        number = len(built) + 1
        description = _trial_text(item.get("description"), "description", number)
        if description is None:
            continue  # an empty row on the screen
        # A row with a description alone is the most natural first try of a rule on a word,
        # which looks at neither number: one, at no price.
        quantity = _trial_number(item.get("quantity"), "quantity", number)
        quantity = Decimal(1) if quantity is None else quantity
        unit_price = _trial_number(item.get("unit_price"), "unit price", number)
        unit_price = Decimal(0) if unit_price is None else unit_price
        # Carried from a saved invoice, whose value may not be quantity × price (a line
        # discount, a price per several units). It decides which line counts, as it did there.
        value = _trial_number(item.get("value"), "value", number)
        codes = item.get("commodity_codes") or []
        details = _trial_text(item.get("details"), "details text", number)
        built.append(Line(
            number=number,
            description=description,
            # As the invoice parser keeps it: not when it says what the name says.
            details=details if details and normalise(details) != normalise(description) else None,
            seller_code=_trial_text(item.get("seller_code"), "seller code", number),
            barcode=_trial_text(item.get("barcode"), "barcode", number),
            commodity_codes=tuple(code for code in (_trial_text(c, "commodity code", number) for c in codes) if code),
            unit=_trial_text(item.get("unit"), "unit", number),
            quantity=quantity,
            unit_price=unit_price,
            value=quantity * unit_price if value is None else value,
            vat_percent=_trial_number(item.get("vat_percent"), "VAT rate", number),
            vat_category=None,
        ))
    cui = str(supplier_cui or "").strip()
    if cui:
        try:
            cui = normalize_cui(cui)
        except EfacturaError:
            cui = normalise_company_id(cui)  # a foreign supplier, as a saved invoice carries it
    nobody = {name: None for name in (
        "vat_id", "registration", "country", "county", "city", "address", "phone", "email", "bank", "iban"
    )}
    return Invoice(
        number="PROBA", issue_date=None, due_date=None, type_code="381" if credit_note else "380",
        currency=str(currency or "").strip().upper() or "RON", note=None, is_credit_note=bool(credit_note),
        vat_on_collection=False,
        supplier=Party(name=str(supplier_name or "").strip() or None, cui=cui or None, **nobody),
        customer=Party(name=None, cui=None, **nobody),
        lines=tuple(built), adjustments=(),
        total_without_vat=sum((item.value for item in built), Decimal(0)), total_vat=None, total_payable=None,
    )


@dataclass
class _Trial:
    """What one try of the rules works with, and what asking Jev has cost so far."""

    store: Store
    rulebook: Rulebook
    client: str | None
    level: float
    jev_only: bool
    calls: int = 0
    cost_usd: float = 0.0
    # Set once OpenRouter failed as a whole (no connection, key, credit, rate limit, server
    # trouble): as in _classify_lines, nothing more is sent. The line, the status, the error.
    stopped: dict | None = None

    @property
    def not_matched(self) -> str:
        return "The rules were skipped" if self.jev_only else "No rule matched"


# What a trial says about one line, and about the invoice as a whole.
_TRIAL_LINE_SAYS = ("decided_by", "cont", "account_description", "rule", "jev", "why_not", "reason")


def _trial_line(item: Line, **said) -> dict:
    """One line of a trial invoice: what it is, and how it was decided."""
    return {
        "line": item.number, "description": item.description, "details": item.details,
        "value": format(item.value, "f"),
        "decided_by": "nobody", "cont": None, "account_description": None, "rule": None, "jev": None,
        "why_not": None, "reason": "",
        "follows": None,  # the largest line, whose account a discount takes
        "same_as": None,  # the earlier line that says the same: Jev was asked once, about that one
        **said,
    }


def _rule_said(matching: list[Rule], subject: Subject, number: int) -> dict:
    """The rule that decided a line, which of its conditions the line meets, and the
    rules further down the list that would have matched too."""
    rule = matching[0]
    found = rule.match(subject)
    return {
        "name": rule.name, "line": number,
        "condition": found.condition if found else None,
        "found": found.found if found else None,
        "prefix": found.prefix if found else None,
        "matched": found.matched if found else None,  # the words of the line a keyword found
        "in_details": found.in_details if found else False,  # found in the line's description
        "client_only": rule.client_cui is not None,
        "also": [other.name for other in matching[1:]],
    }


def _trial_suggestion(invoice: Invoice, rulebook: Rulebook, lines: list[dict]) -> dict | None:
    """The rule worth creating: from the largest line Jev named an account for, sure enough
    or not, when no rule fits that line yet."""
    by_number = {item.number: item for item in invoice.lines}
    answered = [entry for entry in lines if entry["jev"] and entry["jev"]["choice"] and entry["same_as"] is None]
    for entry in sorted(answered, key=lambda entry: abs(by_number[entry["line"]].value), reverse=True):
        subject = line_subject(invoice, by_number[entry["line"]])
        cont = entry["cont"] or entry["jev"]["choice"]
        if not rulebook.rule_for(subject) and propose(subject, cont):
            return {**_suggestion_dict(subject, cont, invoice.supplier.name), "from_line": entry["line"]}
    return None


def _trial_lines_summary(lines: list[dict]) -> str:
    """For the journal: "4 lines: 1 by rules, 1 by Jev, 1 following the largest line, 1 left to check."."""
    counts = (
        (sum(entry["decided_by"] == "rule" for entry in lines), "by rules"),
        (sum(entry["decided_by"] == "jev" for entry in lines), "by Jev"),
        (sum(entry["decided_by"] == "follows" and bool(entry["cont"]) for entry in lines), "following the largest line"),
        (sum(not entry["cont"] for entry in lines), "left to check"),
    )
    return f"{len(lines)} lines: " + ", ".join(f"{count} {what}" for count, what in counts if count) + "."


def _suggestion_dict(subject: Subject, cont: str, supplier_name: str | None) -> dict:
    words = words_of_line(subject)
    return {
        "cont": cont,
        "line": subject.description,
        "details": subject.details,  # the line's description, which words come from too
        "words": list(words),
        "ticked": list(ticked_words(words)),
        "supplier_cui": subject.supplier_cui,
        "supplier_name": supplier_name,
    }


def _rule_from(name: str, cont: str, **conditions) -> Rule:
    """A rule as the matching reads it: the lists tidied, and each supplier's id written
    the way the invoice parser writes it, so the two can match."""
    if any(isinstance(entries, str) for entries in conditions.values()):
        raise EfacturaError(INVALID_INPUT, "Each condition of a rule is a list of entries.")
    tidy = Rule(name, cont, **conditions)
    return replace(
        tidy, supplier_cuis=tuple(normalise_company_id(entry) for entry in tidy.supplier_cuis)
    )


def _stored_subject(text: str | None) -> Subject | None:
    """A subject kept beside an invoice; None when there is none or it cannot be read
    (edited by hand, or written by a version that kept it differently). Such an invoice
    is left out of proposed rules instead of taking the whole list down."""
    try:
        return Subject.from_json(text) if text else None
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def _subjects(stored: list[tuple[str, str]]) -> list[tuple[str, Subject]]:
    read = ((cont, _stored_subject(subject)) for cont, subject in stored)
    return [(cont, subject) for cont, subject in read if subject is not None]


def _evidence(rule: Rule, classified: list[tuple[str, Subject]]) -> dict:
    """How a rule would have done on invoices that already have an account."""
    by_cont = Counter(cont for cont, subject in classified if rule.matches(subject))
    return {"matches": sum(by_cont.values()), "by_cont": dict(sorted(by_cont.items()))}


FOLLOWS = "follows"  # a line that takes the account of the invoice's largest line
FROM_INVOICE = "invoice"  # a line that kept the whole invoice's account when a person split it
BY_A_PERSON = ("human", "jev_accepted", FROM_INVOICE)  # lines a person decided: classify_again keeps them


def _line_entry(
    number: int | None, cont: str | None = None, method: str | None = None, reason: str | None = None,
    rule: str | None = None, suggested_cont: str | None = None, confidence: float | None = None,
    confidence_threshold: float | None = None, probabilities: dict | None = None, asked: bool = False,
    match: dict | None = None,
) -> dict:
    """One line's account as it is stored and shown: who chose it, why (the rule, and which of
    its conditions the line meets), what Jev said and how likely it found each account.
    `asked`: Jev was asked about this line. With `number` None, the whole invoice, as its
    history keeps it."""
    return {
        "line": number, "cont": cont, "method": method, "rule": rule, "match": match, "reason": reason or "",
        "suggested_cont": suggested_cont, "confidence": confidence, "confidence_threshold": confidence_threshold,
        "probabilities": probabilities, "asked": asked,
    }


def _match_said(match: RuleMatch | None) -> dict | None:
    """Which condition of a rule a line meets, and with what, as it is kept."""
    return asdict(match) if match is not None else None


# What a decision is, for telling whether it changed: not how likely Jev found each account,
# which a second question changes a little without changing the decision.
_DECIDED = ("cont", "method", "reason", "suggested_cont", "confidence", "confidence_threshold")
# A download or "Clasifică din nou" leaving a line as it was does not write it again because
# Jev, asked again, is a little more or less sure: its figures are left out of the comparison.
_FIGURES = re.compile(r"\d+(?:\.\d+)?")


def _same_decision(old: dict, new: dict, automatic: bool) -> bool:
    if not automatic:
        return all(old.get(key) == new.get(key) for key in _DECIDED)
    return all(old.get(key) == new.get(key) for key in ("cont", "method", "suggested_cont")) and (
        _FIGURES.sub("#", old.get("reason") or "") == _FIGURES.sub("#", new.get("reason") or "")
    )
# What the history keeps of a decision beside the account, the method and the reason.
_SAID = ("rule", "match", "suggested_cont", "confidence", "confidence_threshold", "probabilities")


def _held(row: dict) -> dict[int | None, dict]:
    """The decisions a saved invoice holds, by line (None: the whole invoice). An invoice
    that waits for Jev, or was never decided, holds none."""
    if row.get("classification_status") not in (CLASSIFIED, REVIEW):
        return {}
    whole = _line_entry(
        None, row.get("cont"), row.get("classification_method"), row.get("classification_reason"),
        suggested_cont=row.get("suggested_cont"), confidence=row.get("confidence"),
        confidence_threshold=row.get("confidence_threshold"),
    )
    entries = _stored_lines(row)
    if entries is not None:
        # The invoice as a whole is its largest line's: what it had before, should it be made whole.
        return {None: whole, **{entry["line"]: entry for entry in entries}}
    return {None: whole}


def _changes(row: dict, entries: list[dict], how: _Pass, at: str) -> list[dict]:
    """The rows of the history for `entries` (by line, or one with line None for the whole
    invoice): those whose decision differs from what the saved row held, each with what it
    had before. What a person asked to have decided again (the invoice, or `how.line`) is
    written even when it comes out the same: the history then shows that it was done."""
    held = _held(row)
    changed = []
    for entry in entries:
        old = held.get(entry["line"])
        asked_for = how.source == REDECIDE and how.line in (None, entry["line"])
        if old is not None and not asked_for and _same_decision(old, entry, how.source in (DOWNLOAD, AGAIN)):
            continue
        before = old or held.get(None)  # a line split off a whole invoice had the invoice's account
        changed.append({
            "message_id": row["id"], "at": at, "source": how.source, "line": entry["line"],
            "cont": entry["cont"], "method": entry["method"], "reason": entry["reason"] or "",
            "said": {
                **{key: entry.get(key) for key in _SAID},
                "jev_only": how.skip_rules,
                "before": {key: before.get(key) for key in ("cont", "method", "rule")} if before else None,
            },
        })
    return changed


def _stored_lines(row: dict) -> list[dict] | None:
    """The line accounts kept on a row; None for an invoice with one account, and for
    anything that cannot be read as line accounts."""
    stored = row.get("line_accounts")
    if stored is None:
        return None
    try:
        entries = stored if isinstance(stored, list) else json.loads(stored)
    except ValueError:
        entries = None
    usable = isinstance(entries, list) and all(
        isinstance(entry, dict) and type(entry.get("line")) is int for entry in entries
    )
    if not usable:
        log.warning("The line accounts of message %s cannot be read; it counts as one account.", row.get("id"))
        return None
    return [{**_line_entry(entry["line"]), **entry} for entry in entries]


def _aligned(entries: list[dict], invoice: Invoice) -> list[dict]:
    """One entry for each line of the invoice, in its order: the stored one where there is
    one, an empty one where there is not."""
    by_line = {entry["line"]: entry for entry in entries}
    return [by_line.get(item.number) or _line_entry(item.number) for item in invoice.lines]


def _not_now_forgotten(store: Store, message_id: str, cont: str) -> dict:
    """"Nu acum" was said about a rule for one account: another account is a new proposal, the
    same one (also after the invoice waited for a person in between) is not."""
    state = store.suggestion_state(message_id)
    dismissed = state["suggestion_dismissed_for"] if state else None
    return {"suggestion_dismissed_for": None} if dismissed and dismissed != cont else {}


def _merged(invoice: Invoice, entries: dict[int, dict], stored: list[dict] | None) -> list[dict]:
    """Each line as decided in this run, or else what Jev said about it before, or else waiting
    for Jev. An account a rule gave that no rule gives now does not come back."""
    before = {entry["line"]: entry for entry in stored or () if entry.get("asked")}
    waiting = "Waiting: OpenRouter failed before Jev was asked about this line."
    return [
        entries.get(item.number) or before.get(item.number) or _line_entry(item.number, reason=waiting)
        for item in invoice.lines
    ]


def _keep_answered(store: Store, row: dict, invoice: Invoice, entries: dict[int, dict]) -> None:
    """Keep what is decided so far on an invoice that goes on waiting because OpenRouter
    failed: the next run asks Jev only about the lines it has not answered."""
    waiting = "Waiting: OpenRouter failed before Jev was asked about this line."
    kept = [entries.get(item.number) or _line_entry(item.number, reason=waiting) for item in invoice.lines]
    store.set_classification(row["id"], line_accounts=json.dumps(kept, ensure_ascii=False))


def _judged(answer: JevAnswer, level: float) -> tuple[str | None, str, dict]:
    """Jev's answer weighed against the level: the account, or None and why not."""
    said = {"suggested_cont": answer.choice, "confidence": answer.confidence, "confidence_threshold": level}
    if answer.refused:
        return None, "Jev declined to answer.", said
    if answer.choice is None:
        return None, "Jev found that none of the accounts fits.", said
    if answer.confidence is None:
        return None, f"Jev suggested {answer.choice} without a confidence figure.", said
    if answer.confidence < level:
        return None, (
            f"Jev suggested {answer.choice} with confidence {answer.confidence:.2f}, below the level of {level:.2f}."
        ), said
    return answer.choice, f"Jev chose {answer.choice} with confidence {answer.confidence:.2f}.", said


def _choose_on_lines(entries: list[dict], cont: str | None, accept: bool, line: int | None) -> None:
    """A person's choice on an invoice decided line by line, made on `entries` in place."""
    if line is not None:
        chosen = [entry for entry in entries if entry["line"] == line]
        if not chosen:
            raise EfacturaError(INVALID_INPUT, f"The invoice has no line {line}.")
    elif accept:
        chosen = [entry for entry in entries if not entry["cont"] and entry["suggested_cont"]]
    else:
        chosen = entries
    for entry in chosen:
        if not accept:
            entry.update(cont=cont, method="human", reason="Set by a person.", rule=None, match=None)
        elif entry["suggested_cont"]:
            entry.update(
                cont=entry["suggested_cont"], method="jev_accepted", reason="Jev's suggestion, accepted by a person.",
                rule=None, match=None,
            )
        else:
            raise EfacturaError(INVALID_INPUT, f"Jev suggested no account for line {entry['line']}; give a cont.")
    if accept and not chosen:
        raise EfacturaError(INVALID_INPUT, "Jev suggested no account for the lines left; give a cont.")


def _lines_left(left: list[dict]) -> str:
    """Why an invoice decided line by line waits for a person. Lines that only follow the
    largest one are not named: they get its account once it has one."""
    named = [entry for entry in left if entry["method"] != FOLLOWS] or left
    if len(named) == 1:
        return f"Line {named[0]['line']} needs a person: {named[0]['reason']}"
    return f"{len(named)} lines need a person. " + " ".join(
        f"Line {entry['line']}: {entry['reason']}" for entry in named
    )


def _lines_summary(entries: list[dict]) -> str:
    """"3 lines: 2 by rules, 1 by Jev." """
    names = {"rules": "by rules", "jev": "by Jev", "jev_accepted": "by a person", "human": "by a person",
             FOLLOWS: "as the largest line", FROM_INVOICE: "as the whole invoice"}
    counts: dict[str, int] = {}
    for entry in entries:
        name = names.get(entry["method"], "by a person")
        counts[name] = counts.get(name, 0) + 1
    return f"{len(entries)} line{'s' if len(entries) != 1 else ''}: " + ", ".join(
        f"{count} {name}" for name, count in counts.items()
    ) + "."


def _checked_account(cont) -> str:
    cont = str(cont if cont is not None else "").strip()
    if len(cont) > MAX_ACCOUNT_LENGTH or not _ACCOUNT.match(cont):
        raise EfacturaError(
            INVALID_INPUT,
            "cont must be an account number such as 628, or an analytic one such as 371.01.",
        )
    return cont


def _min_confidence(store: Store) -> float:
    saved = store.get_setting(MIN_CONFIDENCE)
    return float(saved) if saved is not None else DEFAULT_MIN_CONFIDENCE


def _probabilities(store: Store, message_id: str) -> dict | None:
    """What Jev thought of each account, from its last stored reply for this invoice."""
    call = store.last_jev_call(message_id)
    return _jev_answer_in(call["response_json"]).get("probabilities") if call else None


def _jev_answer_in(response_json: str | None) -> dict:
    """Jev's answer inside a stored reply; empty when the call failed or made no sense."""
    try:
        answer = json.loads(response_json)["answers"]["cont"]
    except (TypeError, KeyError, ValueError):
        return {}
    return answer if isinstance(answer, dict) else {}


def _as_json(invoice: Invoice) -> dict:
    """The parsed invoice for the screen: amounts as text (no rounding), each line with
    the unit as SAGA will show it."""
    document = _plain(asdict(invoice))
    document["total_with_vat"] = _plain(invoice.total_with_vat)
    for described in document["lines"]:
        described["unit_name"] = saga.UNITS.get((described["unit"] or "").upper(), described["unit"])
    return document


def _plain(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _own_saga_xml(invoice: Invoice | None, row: dict) -> str | None:
    """One invoice as SAGA is given it, whichever file it is in, and also once it has been
    imported and is in none. None until it has an account."""
    if invoice is None or row["classification_status"] != CLASSIFIED or not row["cont"]:
        return None
    return saga.build_xml(
        invoice, row["cont"], row["id_solicitare"], row["id"], _line_conts(row), issued=_is_sale(row["cui"], invoice),
    ).decode(saga.ENCODING)


def _line_conts(row: dict) -> tuple[tuple[int, str], ...]:
    """Each line's account, for the file for SAGA; empty for an invoice on one account."""
    return tuple((entry["line"], entry["cont"]) for entry in _stored_lines(row) or () if entry.get("cont"))


def _checked_folder(folder: str) -> Path:
    """The folder for SAGA as a full path, made if it is not there yet."""
    text = str(folder or "").strip()
    path = Path(text).expanduser()
    if not text or not path.is_absolute():
        raise EfacturaError(
            INVALID_INPUT, "Give the folder's full path, for example C:\\SAGA Import."
        )
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise EfacturaError(INVALID_INPUT, f"The folder cannot be created: {exc}") from None
    return path


def _saga_file_per(store: Store) -> str:
    saved = store.get_setting(SAGA_FILE_PER)
    return saved if saved in saga.WAYS else saga.PER_CLIENT


def _show_issued(store: Store) -> bool:
    return store.get_setting(SHOW_ISSUED) == "1"


def _is_inside(path: Path, folder: Path) -> bool:
    try:
        path.relative_to(folder)
    except ValueError:
        return False
    return True


def _is_empty(folder: Path) -> bool:
    try:
        return not any(folder.iterdir())
    except OSError:
        return False


def _holds(path: Path, content: bytes) -> bool:
    try:
        return path.read_bytes() == content
    except OSError:
        return False


def _same_file(one: Path, other: Path) -> bool:
    """Windows does not tell file names apart by letter case: two names may be one file."""
    try:
        return one.samefile(other)
    except OSError:
        return False


def _sent_twice(earlier: str) -> str:
    """Why an invoice saved before under another ANAF id waits for a person."""
    return (
        f"The same invoice (supplier, number and date) is already saved as message "
        f"{earlier}. Decide whether it has to be booked again."
    )


def _same_invoice_saved_before(store: Store, row: dict) -> str | None:
    """The id of an earlier message carrying this very invoice: same supplier, number and
    date. A supplier who starts numbering again each year reuses numbers, but not on the
    same day. Looked up again each time: a message saved by an earlier version noted only
    the oldest one with that number, maybe of another year."""
    if not (row.get("possible_duplicate_of") and row.get("supplier_cui") and row.get("invoice_number")):
        return None
    return store.find_same_invoice(
        row["cui"], row["message_type"], row["supplier_cui"], row["invoice_number"], row.get("invoice_issue_date"),
        before=row["id"],
    )


def _status_now(store: Store, message_id: str) -> str | None:
    """The state an invoice is left in after its decision failed; None when even that
    cannot be read (the database busy), so it is not counted."""
    try:
        row = store.get_message(message_id)
    except sqlite3.Error:
        log.exception("Could not read message %s after its decision failed", message_id)
        return None
    return row["classification_status"] if row else None


def _note_error(store: Store, message_id: str, error: str) -> None:
    try:
        store.set_classification(message_id, classification_error=error)
    except (sqlite3.Error, EfacturaError):
        log.exception("Could not record why message %s was not classified", message_id)


def _check_date(day: str | None, name: str = "since") -> None:
    """Only YYYY-MM-DD: the stored times are compared with it as text, so "20261103", which
    Python reads as a date too, would match nothing."""
    if day is None:
        return
    try:
        if not _ISO_DAY.fullmatch(day):
            raise ValueError(day)
        date.fromisoformat(day)
    except ValueError:
        raise EfacturaError(INVALID_INPUT, f"{name} must be a date like 2026-11-11.") from None


def _failed_client(cui: str, name: str, code: str, message: str) -> dict:
    return {"cui": cui, "name": name, "ok": False, "error": {"code": code, "message": message}}


def _pause(seconds: float) -> None:
    time.sleep(seconds)


def _write_file(path: Path, content: bytes) -> None:
    """Write beside the target, then swap in: a reader never sees half a file."""
    partial = path.with_name(path.name + ".part")
    try:
        partial.write_bytes(content)
        os.replace(partial, path)
    except BaseException:
        # Windows refuses the swap while another program has the target open.
        partial.unlink(missing_ok=True)
        raise


class _FileLock:
    """Lets one in at a time, across processes: one sync or login renewal, or (a lock of
    its own) one writer of the files for SAGA.

    Without `wait` a second comer is refused at once; with it, it waits that many seconds
    for the first to finish. The operating system drops the lock if the process dies, so
    it cannot go stale.
    """

    POLL = 0.05  # seconds between two tries while waiting

    def __init__(
        self, path: Path, wait: float = 0,
        busy: str = "Another sync or login renewal is running. Try again when it has finished.",
    ):
        self._path = Path(path)
        self._wait = wait
        self._busy = busy
        self._handle = None

    def __enter__(self) -> "_FileLock":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self._path, "a+b")
        give_up_at = time.monotonic() + self._wait
        while True:
            try:
                _lock_handle(handle)
                break
            except OSError:
                if time.monotonic() >= give_up_at:
                    handle.close()
                    raise EfacturaError(BUSY, self._busy) from None
                time.sleep(self.POLL)
        self._handle = handle
        return self

    def __exit__(self, *exc_info) -> None:
        try:
            _unlock_handle(self._handle)
        finally:
            self._handle.close()
            self._handle = None


if os.name == "nt":
    import msvcrt

    def _lock_handle(handle) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock_handle(handle) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock_handle(handle) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock_handle(handle) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
