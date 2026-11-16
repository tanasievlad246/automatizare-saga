"""One function per command. The terminal commands and the local API both call these,
so they return the same plain dictionaries either way."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from contextlib import nullcontext
from dataclasses import asdict, dataclass, replace
from decimal import Decimal, InvalidOperation
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

import httpx

from . import __version__, auth, certificate_login, jev, journal, saga, schedule
from .anaf import TYPE_PREFIXES, AnafService, normalize_cui, parse_created_at, type_slug
from .classify import (
    JevAnswer,
    decide_by_rules,
    deciding_line,
    fits,
    follows_largest,
    jev_line_request,
    jev_request,
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
from .rules import CONDITIONS, DEFAULT_JEV_LINE_INSTRUCTIONS, Rule, Rulebook, Subject, any_of
from .store import JEV_INSTRUCTIONS, JEV_LINE_INSTRUCTIONS, RULE_TEST, Store
from .suggestions import propose, ticked_words, words_of

log = logging.getLogger(__name__)

DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

# sync_all: how long and how often a client waits for a download made by hand
BUSY_PAUSE = 5.0
BUSY_TRIES = 12
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
RECEIVED = TYPE_PREFIXES["primita"]  # only received invoices get an account
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
# Bringing a client's files up to date takes a moment; a second writer waits this long for it.
SAGA_LOCK_WAIT = 30.0


class _JevCouldNotDecide(Exception):
    """Jev was reached but gave nothing usable for this one invoice (it refused the
    request, or its answer made no sense). The next invoice may well be fine."""


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

    def login_finish(self, address: str) -> dict:
        code = auth.code_from_redirect(address)
        now = self._now()
        with self._lock():
            tokens = auth.exchange_code(self.cfg, self._http, code, now)
            auth.save_tokens(self.cfg.token_file, tokens)
            journal.record("anaf", "anaf.connected", "Connected to ANAF with the certificate.")
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
        return self.login_finish(address)

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
                    cui, days=days, start=self._within_reach(start), end=end, cover_gap=cover_gap
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
    ) -> dict:
        """List, skip what is already saved, download and save the rest. Then give the
        received invoices just saved an account and write their SAGA files.

        The period is the last `days` days, or the days from `start` to `end` (dates such
        as 2026-11-03; `end` defaults to today). With neither, it is the default number of
        days, widened to reach back to the last complete run. With cover_gap, `days` is a
        minimum that is widened the same way, so no day since the last run is skipped.

        With classify=False the messages are only saved, and stay outside classification
        for good (for a first run that brings in invoices already booked by hand).
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

        saved: list[dict] = []
        failed: list[dict] = []
        network_failures = 0
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
                level="warning", id=entry["id"], cui=cui, error=error.message,
            )
            log.warning("Message %s failed: %s: %s", entry["id"], error.code, error.message)
            network_failures = network_failures + 1 if error.code == NETWORK_ERROR else 0
            if network_failures >= MAX_NETWORK_FAILURES:
                skipped = EfacturaError(
                    NETWORK_ERROR, "Skipped: ANAF was unreachable for the messages before this one."
                )
                failed.extend(_failure(rest, skipped) for rest in unseen[position + 1 :])
                break

        return {
            "ok": True,
            "cui": cui,
            "window_days": window.days,
            "listed": len(entries),
            "new_count": len(saved),
            # Of those: the invoices the client received, which get an account, and the ones
            # it issued, which are only kept. Errors and other messages are in neither.
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

        duplicate_of = None
        if fields["invoice_number"] and fields["supplier_cui"]:
            duplicate_of = store.find_same_invoice(
                cui, message_type, fields["supplier_cui"], fields["invoice_number"]
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
                        if classify and _is_received(message_type)
                        and parse_invoice(extracted.xml) is not None
                        else None
                    ),
                }
            )
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return self._present(store.get_message(message_id))

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
                "saga": self._saga_state(store, normalize_cui(cui)),
                "issued_count": store.issued_count(normalize_cui(cui)),
            } if cui else {}
        finally:
            store.close()
        return {"ok": True, "count": len(rows), "invoices": [self._present(r) for r in rows], **of_client}

    def invoice(self, message_id: str, include_xml: bool = False) -> dict:
        store = self._open_store()
        try:
            row = store.get_message(message_id, include_xml=include_xml)
        finally:
            store.close()
        if row is None:
            raise EfacturaError(NOT_FOUND, f"No saved message with id: {message_id}")
        return {"ok": True, "invoice": self._present(row)}

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

    def classify(self, message_id: str, force: bool = False) -> dict:
        """Give one saved invoice its account: the rules first, Jev if they cannot decide.

        Without force this only works on invoices that are waiting or in review. An invoice
        saved outside classification, or one already classified, needs force.
        """
        with self._lock():
            store = self._open_store()
            try:
                row, _ = self._classifiable(store, message_id, force, classified_ok=force)
                try:
                    self._classify_one(store, message_id, _new_tally())
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
                {**self._present(row), "jev_probabilities": _probabilities(store, row["id"])}
                for row in rows
            ]
            level = _min_confidence(store)
            accounts = store.accounts()
        finally:
            store.close()
        return {
            "ok": True,
            "count": len(invoices),
            "min_confidence": level,
            "accounts": accounts,
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
                    _choose_on_lines(entries, cont, accept, line)
                    self._record_lines(store, row, invoice, entries)
                    self._write_saga_files(store, row["cui"])
                    return {"ok": True, "invoice": self._present(store.get_message(message_id))}
                if line is not None:
                    raise EfacturaError(
                        INVALID_INPUT,
                        "This invoice has one account for all its lines. Classify it again to decide it line by line.",
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
                self._finish(store, row, invoice, cont, method, reason)
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
            }
        finally:
            store.close()

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
            store.save_client(cui, name, self._now().isoformat())
            journal.record("clients", "client.saved", f"Client {cui} saved.", cui=cui, client=name)
        finally:
            store.close()
        return self.clients()

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
                journal.record(
                    "settings", "settings.show_issued",
                    f"The invoices a client issued are now {'shown' if shown else 'hidden'}.", shown=shown,
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
            clients = [normalize_cui(cui)] if cui else store.clients_with_saga_files()
            problems = []
            for client in clients:
                self._write_saga_files(store, client)
                problem = store.saga_problem(client)
                if problem:
                    problems.append({"cui": client, **problem})
        finally:
            store.close()
        return {"ok": True, "clients": len(clients), "problems": problems}

    def choose_folder(self, purpose: str = "saga") -> dict:
        """Let the person pick a folder in the computer's own dialog; None if they cancel.
        The dialog says which folder it is asking for, and starts where that one is now."""
        if purpose == "saga":
            start, title = str(self.cfg.saga_dir), "Folderul pentru SAGA"
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
            folder = self.cfg.saga_dir / normalize_cui(cui) if cui else self.cfg.saga_dir
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
                "rules": store.rules(),
                "jev_instructions": store.get_setting(JEV_INSTRUCTIONS) or "",
                "min_confidence": _min_confidence(store),
            }
        finally:
            store.close()

    def save_account(self, cont: str, description: str = "") -> dict:
        """Add an account Jev may choose, or change its description."""
        cont = _checked_account(cont)
        store = self._open_store()
        try:
            store.save_account(cont, str(description or "").strip())
            journal.record("rules", "account.saved", f"Account {cont} saved in Jev's list.", cont=cont)
        finally:
            store.close()
        return self.rules_overview()

    def delete_account(self, cont: str) -> dict:
        store = self._open_store()
        try:
            store.delete_account(str(cont).strip())
            journal.record("rules", "account.removed", f"Account {cont} removed from Jev's list.", cont=str(cont).strip())
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
    ) -> dict:
        """Add a rule (rule_id None) or replace one. `client_cui` None: for every client."""
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
        store = self._open_store()
        try:
            if rule_id is None:
                store.add_rule(**fields)
            else:
                store.update_rule(rule_id, **fields)
            journal.record(
                "rules", "rule.added" if rule_id is None else "rule.changed",
                f"Rule {tidy.name!r} for {tidy.cont} {'added' if rule_id is None else 'changed'}.",
                name=tidy.name, cont=tidy.cont, rule_id=rule_id, client=fields["client_cui"],
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
        """The rule to propose on one invoice's screen, however old the invoice is."""
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
        asking Jev cost. The order of the checks is that of _classify_one."""
        if ask not in TRIAL_ASKS:
            raise EfacturaError(INVALID_INPUT, f"ask must be one of: {', '.join(TRIAL_ASKS)}.")
        client = normalize_cui(client_cui) if client_cui else None
        invoice = _trial_invoice(lines, supplier_name, supplier_cui, currency, credit_note)
        subject = subject_of(invoice)
        store = self._open_store()
        try:
            # The rules for every client, plus those of the chosen one.
            rulebook = _rulebook_for(store, client)
            result = self._try_rules_then_jev(store, invoice, rulebook, client, ask == "jev_only")
            cont = result["cont"] or (result["jev"] or {}).get("choice")
            if cont and subject and not rulebook.rule_for(subject) and propose(subject, cont):
                result["suggestion"] = _suggestion_dict(subject, cont, invoice.supplier.name)
        finally:
            store.close()
        asked = result["jev"] is not None
        journal.record(
            "rules", "rule.tested", f"Rules tried on a trial invoice: {result['reason']}",
            decided_by=result["decided_by"], cont=result["cont"], asked_jev=asked,
            cost_usd=result["jev"]["cost_usd"] if asked else None,
        )
        return {"ok": True, **result}

    def _try_rules_then_jev(
        self, store: Store, invoice: Invoice, rulebook: Rulebook, client: str | None, jev_only: bool
    ) -> dict:
        heaviest = deciding_line(invoice)
        result = {
            "decided_by": "nobody", "cont": None, "account_description": None,
            "deciding_line": heaviest.description if heaviest else None,
            "rule": None, "jev": None, "why_not": None, "reason": "", "suggestion": None,
        }

        def decided(by: str, cont: str, reason: str) -> dict:
            return {
                **result, "decided_by": by, "cont": cont, "reason": reason,
                "account_description": rulebook.accounts.get(cont) or None,
            }

        def left(why: str, reason: str, **more) -> dict:
            return {**result, "why_not": why, "reason": reason, **more}

        decision = None if jev_only else decide_by_rules(invoice, rulebook)
        if decision:
            reason = f'Rule "{decision.rule}" matched line {decision.line}, the largest on the invoice.'
            return {**decided("rule", decision.cont, reason), "rule": {"name": decision.rule, "line": decision.line}}
        if not invoice.lines:
            return left("no_lines", "The invoice has no lines to decide from.")
        if not self.cfg.openrouter_api_key:
            return left(
                "no_key",
                "No rule matched, and OpenRouter is not set up ([openrouter] api_key in config.toml).",
            )
        if not rulebook.accounts:
            return left("no_accounts", "No rule matched, and there are no accounts for Jev to choose from.")

        request = jev_request(invoice, rulebook, self.cfg.jev_model)
        if not request["state"]["linii"]:
            return left(
                "jev_failed", "The invoice and the list of accounts do not fit in one request to Jev."
            )
        # One attempt, whatever it costs: the person is waiting, and every attempt is paid for.
        call = jev.ask(self._http, self.cfg.openrouter_api_key, request)
        answer, error = None, call.error
        if call.ok:
            try:
                answer = read_jev_answer(call.response, rulebook)
            except EfacturaError as exc:
                error = exc.message
        store.add_jev_call(
            message_id=RULE_TEST,
            cui=client,
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
        level = _min_confidence(store)
        said = {
            "choice": answer.choice if answer else None,
            "confidence": answer.confidence if answer else None,
            "threshold": level,
            "refused": answer.refused if answer else False,
            "probabilities": dict(answer.probabilities) if answer else {},
            "cost_usd": call.cost_usd,
            "duration_ms": call.duration_ms,
            "error": None if answer else (error or "Jev gave no answer."),
            # None when OpenRouter was not reached. A refused key or an empty account (401,
            # 402, 403) is not helped by waiting, and the screen says so.
            "http_status": call.status,
        }
        if answer is None:
            return left("jev_failed", f"Jev could not decide this invoice: {said['error']}", jev=said)
        if answer.refused:
            return left("jev_declined", "Jev declined to answer.", jev=said)
        if answer.choice is None:
            return left("jev_declined", "Jev found that none of the accounts fits.", jev=said)
        if answer.confidence is None:
            return left(
                "jev_declined", f"Jev suggested {answer.choice} without a confidence figure.", jev=said
            )
        if answer.confidence < level:
            return left(
                "below_threshold",
                f"Jev suggested {answer.choice} with confidence {answer.confidence:.2f}, "
                f"below the level of {level:.2f}.",
                jev=said,
            )
        reason = f"Jev chose {answer.choice} with confidence {answer.confidence:.2f}."
        return {**decided("jev", answer.choice, reason), "jev": said}

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
        finally:
            store.close()
        shown = self._present(row)
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

    def _classify_waiting(self, store: Store, cui: str, result: dict) -> None:
        """Classify what this sync saved, plus anything left waiting by an earlier one.

        Never fails the sync: the messages are saved either way, and an invoice that could
        not be classified simply waits for the next run.
        """
        counts = {CLASSIFIED: 0, REVIEW: 0, PENDING: 0}
        tally = _new_tally()
        jev_down = False
        for message_id in store.pending_classification(cui):
            try:
                status = self._classify_one(store, message_id, tally, jev_allowed=not jev_down)
            except EfacturaError as exc:
                # OpenRouter itself is failing (connection, key, credit, rate limit), so
                # the invoices after this one are not sent in this run either.
                jev_down = jev_down or exc.code == JEV_ERROR
                status = PENDING
                log.warning("Message %s not classified: %s", message_id, exc.message)
            except Exception as exc:
                log.exception("Could not classify message %s", message_id)
                status = PENDING
                _note_error(store, message_id, f"{type(exc).__name__}: {exc}")
            counts[status] += 1

        self._write_saga_files(store, cui)
        result["new"] = [self._present(store.get_message(entry["id"])) for entry in result["new"]]
        result["classification"] = {
            **counts,
            "skipped": sum(entry["classification_status"] is None for entry in result["new"]),
            **tally,
        }
        if counts[CLASSIFIED]:
            result["saga_folder"] = str(self.cfg.saga_dir / cui)

    def _classifiable(
        self, store: Store, message_id: str, force: bool, classified_ok: bool
    ) -> tuple[dict, Invoice]:
        """The saved row and its invoice, or the reason it may not be classified."""
        row = store.get_message(message_id, include_xml=True)
        if row is None:
            raise EfacturaError(NOT_FOUND, f"No saved message with id: {message_id}")
        if not _is_received(row["message_type"]):
            raise EfacturaError(
                NOT_CLASSIFIABLE,
                f"Only received invoices are classified; this message is: {row['message_type']}.",
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

    def _classify_one(
        self, store: Store, message_id: str, tally: dict, jev_allowed: bool = True
    ) -> str:
        """Decide one invoice and return its new status."""
        row = store.get_message(message_id, include_xml=True)
        invoice = parse_invoice(row["invoice_xml"] or "")
        if invoice is None:
            raise EfacturaError(NOT_CLASSIFIABLE, "The saved XML cannot be read as an invoice.")

        rulebook = _rulebook_for(store, row["cui"])
        earlier = _same_invoice_saved_before(store, row)
        if earlier:
            # Booking it automatically would enter the invoice in SAGA a second time.
            return self._to_review(
                store, row,
                f"The same invoice (supplier, number and date) is already saved as message "
                f"{earlier}. Decide whether it has to be booked again.",
            )

        if store.client_per_line(row["cui"]):
            return self._classify_lines(store, row, invoice, rulebook, tally, jev_allowed)

        decision = decide_by_rules(invoice, rulebook)
        if decision:
            return self._finish(
                store, row, invoice, decision.cont, "rules",
                f'Rule "{decision.rule}" matched line {decision.line}, the largest on the invoice.',
            )
        if not invoice.lines:
            return self._to_review(store, row, "The invoice has no lines to decide from.")
        if not self.cfg.openrouter_api_key:
            return self._to_review(
                store, row,
                "No rule matched, and OpenRouter is not set up ([openrouter] api_key in config.toml).",
            )
        if not rulebook.accounts:
            return self._to_review(
                store, row, "No rule matched, and there are no accounts for Jev to choose from."
            )
        if not jev_allowed:
            _note_error(store, message_id, "Not sent to Jev: OpenRouter failed earlier in this run.")
            return PENDING

        request = jev_request(invoice, rulebook, self.cfg.jev_model)
        if not request["state"]["linii"]:
            # Not even the deciding line fits beside the list of accounts.
            return self._to_review(
                store, row, "The invoice and the list of accounts do not fit in one request to Jev."
            )
        try:
            answer = self._ask_jev(store, row, request, rulebook, tally)
        except _JevCouldNotDecide as exc:
            return self._to_review(store, row, f"Jev could not decide this invoice: {exc}")
        cont, reason, jev_said = _judged(answer, _min_confidence(store))
        if cont is None:
            return self._to_review(store, row, reason, **jev_said)
        return self._finish(store, row, invoice, cont, "jev", reason, **jev_said)

    def _classify_lines(
        self, store: Store, row: dict, invoice: Invoice, rulebook: Rulebook, tally: dict, jev_allowed: bool,
    ) -> str:
        """Decide each line on its own: the rules first; a discount or a line worth nothing
        takes the account of the largest line; Jev for the rest, one question per distinct
        line; a person for whatever is left. Nothing is recorded while OpenRouter is failing
        as a whole: the invoice then waits, whole, for the next run."""
        if not invoice.lines:
            return self._to_review(store, row, "The invoice has no lines to decide from.")
        largest = deciding_line(invoice).number
        entries = {
            number: _line_entry(number, rule.cont, "rules", f'Rule "{rule.name}" matched line {number}.', rule=rule.name)
            for number, rule in rules_by_line(invoice, rulebook).items()
        }
        for item in invoice.lines:
            if item.number not in entries and follows_largest(invoice, item):
                entries[item.number] = _line_entry(
                    item.number, None, FOLLOWS, f"Takes the account of line {largest}, the largest on the invoice."
                )
        asked = [item for item in invoice.lines if item.number not in entries]
        why_not = None
        if asked and not self.cfg.openrouter_api_key:
            why_not = "No rule matched this line, and OpenRouter is not set up ([openrouter] api_key in config.toml)."
        elif asked and not rulebook.accounts:
            why_not = "No rule matched this line, and there are no accounts for Jev to choose from."
        elif asked and not jev_allowed:
            _note_error(store, row["id"], "Not sent to Jev: OpenRouter failed earlier in this run.")
            return PENDING
        groups: dict[tuple, list[Line]] = {}
        for item in asked:
            groups.setdefault(same_question(item), []).append(item)
        level = _min_confidence(store) if groups and not why_not else None
        for items in groups.values():
            cont, reason, jev_said = None, why_not, {}
            if not why_not:
                request = jev_line_request(invoice, items[0], rulebook, self.cfg.jev_model)
                if not fits(request):
                    reason = "This line and the list of accounts do not fit in one request to Jev."
                else:
                    try:
                        answer = self._ask_jev(store, row, request, rulebook, tally, line=items[0].number)
                    except _JevCouldNotDecide as exc:
                        reason = f"Jev could not decide this line: {exc}"
                    else:
                        cont, reason, jev_said = _judged(answer, level)
            for item in items:
                entries[item.number] = _line_entry(item.number, cont, "jev" if cont else None, reason, **jev_said)
        return self._record_lines(store, row, invoice, [entries[item.number] for item in invoice.lines])

    def _record_lines(self, store: Store, row: dict, invoice: Invoice, entries: list[dict]) -> str:
        """Record each line's account. The invoice is ready for SAGA once every line has one;
        until then it waits for a person. Its own `cont` and the fields beside it are those of
        its largest line, so whatever reads one account per invoice keeps working."""
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
            reason = _lines_left(left)
            store.set_classification(
                row["id"], classification_status=REVIEW, cont=None, classification_method=None,
                classification_reason=reason, classified_at=None, **common,
            )
            journal.record(
                "accounts", "account.to_review", f"Message {row['id']} needs a person: {reason}",
                level="warning", **details, reason=reason, lines_left=len(left),
            )
            return REVIEW
        reason = _lines_summary(entries)
        forgotten = {"suggestion_dismissed_for": None} if head["cont"] != row.get("cont") else {}
        store.set_classification(
            row["id"], classification_status=CLASSIFIED, cont=head["cont"],
            classification_method=head["method"], classification_reason=reason,
            classified_at=self._now().isoformat(), **common, **forgotten,
        )
        methods = [entry["method"] for entry in entries]
        journal.record(
            "accounts", "account.by_lines", f"Message {row['id']} booked line by line: {reason}",
            **details, cont=head["cont"], accounts=sorted({entry["cont"] for entry in entries}),
            by_rules=methods.count("rules"), by_jev=methods.count("jev"),
            by_person=methods.count("human") + methods.count("jev_accepted"), following=methods.count(FOLLOWS),
        )
        return CLASSIFIED

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
                level="info" if answer is not None else "warning",
                id=row["id"], invoice_number=row.get("invoice_number"), line=line, status=call.status,
                cost_usd=call.cost_usd, error=error, duration_ms=call.duration_ms,
            )
            tally["jev_cost_usd"] += call.cost_usd or 0
            if answer is not None:
                return answer
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
        **jev_said,
    ) -> str:
        """Record the decision: `cont` on every line. The files for SAGA follow from what is
        recorded (_write_saga_files), so SAGA never finds a decision that was not."""
        subject = subject_of(invoice)
        # "Not now" was said about a rule for the account the invoice had; a new account is
        # a new proposal.
        forgotten = {"suggestion_dismissed_for": None} if cont != row.get("cont") else {}
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
        journal.record(
            "accounts", {"rules": "account.by_rule", "jev": "account.by_jev"}.get(method, "account.by_person"),
            f"Message {row['id']} booked on {cont} ({method}).",
            id=row["id"], cui=row["cui"], invoice_number=row.get("invoice_number"),
            supplier=row.get("supplier_name"), cont=cont, method=method, reason=reason,
            confidence=jev_said.get("confidence"),
        )
        return CLASSIFIED

    def _to_review(self, store: Store, row: dict, reason: str, **jev_said) -> str:
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
        journal.record(
            "accounts", "account.to_review", f"Message {row['id']} needs a person: {reason}", level="warning",
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

    def _place_saga_files(self, store: Store, cui: str, when: str) -> None:
        waiting = []
        for row in store.waiting_for_saga(cui):
            invoice = parse_invoice(row["invoice_xml"] or "")
            if invoice is None:  # it was read when it was given its account
                log.warning("Message %s has an account but its invoice cannot be read", row["id"])
                continue
            waiting.append(saga.Entry(invoice, row["cont"], row["id_solicitare"], row["id"]))
        saga_dir = self._saga_dir(store)
        folder = saga_dir / cui
        known = store.saga_ledger(cui)
        wanted: dict[str, Path] = {}
        placed: dict[str, str] = {}
        for file in saga.files_for(waiting, _saga_file_per(store)):
            path = folder / file.name
            stored = self._stored_path(path)
            wanted[stored] = path
            placed.update(dict.fromkeys(file.ids, stored))
            if _holds(path, file.content):
                continue  # as it should be already: SAGA may have it open, so it is left alone
            # On record before it exists, so the folder never holds a file nobody knows of.
            store.note_saga_file(stored, cui, known.get(stored) or when)
            folder.mkdir(parents=True, exist_ok=True)
            _write_file(path, file.content)
            store.note_saga_file(stored, cui, when)
        store.place_in_saga_files(cui, placed, when)
        # Only now the files that are no longer wanted: the new ones are in place.
        failure = None
        for stored in known:
            if stored in wanted:
                continue
            old = self.cfg.data_dir / stored
            try:
                if not any(_same_file(old, new) for new in wanted.values()):
                    if _is_inside(old, saga_dir) and not saga_dir.is_dir():
                        # Gone, or only away (a stick, a share)? Not forgotten until it is known.
                        raise FileNotFoundError(f"The folder for SAGA cannot be reached: {saga_dir}")
                    old.unlink(missing_ok=True)
            except OSError as exc:
                failure = failure or exc  # it stays on record and is tried again
                continue
            store.forget_saga_file(stored)
        if failure:
            raise failure

    def _saga_dir(self, store: Store) -> Path:
        """The folder for SAGA as it is set now. Another part of the program may have
        changed it since this Service was made (a download can run for minutes)."""
        saved = store.get_setting("saga_dir")
        return Path(saved) if saved else self._file_cfg.saga_dir

    def _saga_state(self, store: Store, cui: str) -> dict:
        """How this client's files for SAGA stand, for the screen."""
        written = [when for when in store.saga_ledger(cui).values() if when]
        return {
            "file_per": _saga_file_per(store),
            "written_at": max(written, default=None),
            "problem": store.saga_problem(cui),
        }

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
            return tokens.access_token
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
            journal.record("anaf", "anaf.renewed", "The ANAF login was renewed without the certificate.")
        log.info("Login renewed; access valid until %s", renewed.access_expires_at.isoformat())
        return renewed.access_token

def configure_logging(cfg: Config) -> None:
    """Log to the data folder. Nothing is logged to standard output: that is for the JSON."""
    logger = logging.getLogger("efactura")
    for existing in list(logger.handlers):
        if isinstance(existing, logging.FileHandler):
            if existing.baseFilename == os.path.abspath(cfg.log_path):
                return
            logger.removeHandler(existing)
            existing.close()
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(cfg.log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    # The same lines go into the journal, where the page can show them.
    journal.configure(cfg.db_path)
    if not any(isinstance(existing, journal.JournalHandler) for existing in logger.handlers):
        logger.addHandler(journal.JournalHandler())


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
    begin = datetime(first.year, first.month, first.day, tzinfo=now.tzinfo)
    if first > last or last > today:
        raise EfacturaError(
            INVALID_INPUT, "The first day must not be after the last, and neither after today."
        )
    if first < (now - timedelta(days=MAX_DAYS)).date():
        raise EfacturaError(INVALID_INPUT, f"ANAF keeps messages for {MAX_DAYS} days only.")
    # The sixtieth day back is allowed, from the hour ANAF still reaches.
    begin = max(begin, now - timedelta(days=MAX_DAYS) + OLDEST_MARGIN)
    end_of_last_day = datetime(last.year, last.month, last.day, tzinfo=now.tzinfo) + timedelta(days=1)
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


def _is_received(message_type: str | None) -> bool:
    return (message_type or "").upper().startswith(RECEIVED)


def _new_tally() -> dict:
    return {"jev_calls": 0, "jev_cost_usd": 0}


def _rulebook_for(store: Store, cui: str) -> Rulebook:
    """The accounts and the rules that apply to one client: its own rules first, then the
    ones shared by every client, each group in the order set on the rules screen."""
    applicable = [
        rule for rule in store.rules() if rule["enabled"] and rule["client_cui"] in (None, cui)
    ]
    applicable.sort(key=lambda rule: rule["client_cui"] is None)  # stable: keeps the order
    return Rulebook(
        accounts=store.accounts(),
        rules=tuple(
            Rule(rule["name"], rule["cont"], **{name: rule[name] for name in CONDITIONS})
            for rule in applicable
        ),
        instructions=store.get_setting(JEV_INSTRUCTIONS) or "",
        line_instructions=store.get_setting(JEV_LINE_INSTRUCTIONS) or "",
    )


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
        built.append(Line(
            number=number,
            description=description,
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


def _suggestion_dict(subject: Subject, cont: str, supplier_name: str | None) -> dict:
    words = words_of(subject.description)
    return {
        "cont": cont,
        "line": subject.description,
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


def _line_entry(
    number: int, cont: str | None = None, method: str | None = None, reason: str | None = None,
    rule: str | None = None, suggested_cont: str | None = None, confidence: float | None = None,
    confidence_threshold: float | None = None,
) -> dict:
    """One line's account as it is stored and shown: who chose it, why, what Jev said."""
    return {
        "line": number, "cont": cont, "method": method, "rule": rule, "reason": reason or "",
        "suggested_cont": suggested_cont, "confidence": confidence, "confidence_threshold": confidence_threshold,
    }


def _stored_lines(row: dict) -> list[dict] | None:
    """The line accounts kept on a row; None for an invoice with one account."""
    stored = row.get("line_accounts")
    if stored is None or isinstance(stored, list):
        return stored
    try:
        entries = json.loads(stored)
    except ValueError:
        log.warning("The line accounts of message %s cannot be read; it counts as one account.", row.get("id"))
        return None
    return entries if isinstance(entries, list) else None


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
            entry.update(cont=cont, method="human", reason="Set by a person.")
        elif entry["suggested_cont"]:
            entry.update(cont=entry["suggested_cont"], method="jev_accepted", reason="Jev's suggestion, accepted by a person.")
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
             FOLLOWS: "as the largest line"}
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
    return saga.build_xml(invoice, row["cont"], row["id_solicitare"], row["id"]).decode(saga.ENCODING)


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


def _same_invoice_saved_before(store: Store, row: dict) -> str | None:
    """The id of an earlier message carrying this very invoice: same supplier and number
    (noted when it was saved) and the same date. A supplier who starts numbering again
    each year reuses numbers, but not on the same day."""
    earlier_id = row.get("possible_duplicate_of")
    if not earlier_id:
        return None
    earlier = store.get_message(earlier_id)
    if earlier and earlier["invoice_issue_date"] == row["invoice_issue_date"]:
        return earlier_id
    return None


def _note_error(store: Store, message_id: str, error: str) -> None:
    try:
        store.set_classification(message_id, classification_error=error)
    except (sqlite3.Error, EfacturaError):
        log.exception("Could not record why message %s was not classified", message_id)


def _check_date(day: str | None, name: str = "since") -> None:
    if day is None:
        return
    try:
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
