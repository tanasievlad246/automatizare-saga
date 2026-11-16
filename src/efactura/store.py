"""SQLite storage: one row per ANAF message, plus a log of sync runs."""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import date
from pathlib import Path
from typing import Iterable

from . import rules as rule_examples
from .errors import NOT_FOUND, EfacturaError

SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    cui         TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    finished_at TEXT,
    window_days INTEGER NOT NULL,
    listed      INTEGER,
    new         INTEGER,
    failed      INTEGER,
    status      TEXT NOT NULL DEFAULT 'running',   -- running | ok | partial | error
    error       TEXT,
    -- 1 when nothing failed AND the window reached back to the previous such run, so
    -- everything up to started_at is saved. Later runs widen their window from here.
    advances_coverage INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS messages (
    id                     TEXT PRIMARY KEY,       -- ANAF message id: the duplicate check
    cui                    TEXT NOT NULL,          -- the CUI that was queried
    message_type           TEXT NOT NULL,          -- ANAF "tip"
    anaf_created_at        TEXT,
    id_solicitare          TEXT,
    detalii                TEXT,
    invoice_number         TEXT,
    invoice_issue_date     TEXT,
    invoice_due_date       TEXT,
    invoice_type_code      TEXT,
    supplier_cui           TEXT,
    supplier_name          TEXT,
    customer_cui           TEXT,
    customer_name          TEXT,
    currency               TEXT,
    total_without_vat      TEXT,                   -- amounts kept as text: no rounding
    total_vat              TEXT,
    total_payable          TEXT,
    invoice_xml            TEXT,
    signature_xml          TEXT,
    raw_metadata_json      TEXT NOT NULL,
    zip_sha256             TEXT,
    xml_path               TEXT,                   -- relative to the data folder
    first_seen_at          TEXT NOT NULL,
    sync_run_id            INTEGER REFERENCES sync_runs(id),
    possible_duplicate_of  TEXT,
    uploaded_to_accounting INTEGER NOT NULL DEFAULT 0 CHECK (uploaded_to_accounting IN (0, 1)),
    uploaded_at            TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_cui_uploaded ON messages (cui, uploaded_to_accounting);
CREATE INDEX IF NOT EXISTS idx_messages_invoice ON messages (cui, supplier_cui, invoice_number);

-- Every request sent to the Jev model, whether it worked or not: what was asked, what
-- came back and what it cost. The API key is never part of the request body.
CREATE TABLE IF NOT EXISTS jev_calls (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id    TEXT NOT NULL,
    cui           TEXT,
    called_at     TEXT NOT NULL,
    model         TEXT,
    request_json  TEXT NOT NULL,
    response_json TEXT,
    http_status   INTEGER,
    input_tokens  INTEGER,
    output_tokens INTEGER,
    cost_usd      REAL,
    duration_ms   INTEGER,
    error         TEXT
);

CREATE INDEX IF NOT EXISTS idx_jev_calls_message ON jev_calls (message_id);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- The accounts Jev may choose from. The description is what Jev reads.
CREATE TABLE IF NOT EXISTS accounts (
    cont        TEXT PRIMARY KEY,
    description TEXT NOT NULL DEFAULT ''
);

-- Classification rules, checked in `position` order. The four condition columns hold
-- JSON lists; a line matches when any entry of any list matches (see rules.py).
CREATE TABLE IF NOT EXISTS rules (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    position           INTEGER NOT NULL,
    name               TEXT NOT NULL,
    cont               TEXT NOT NULL,
    keywords           TEXT NOT NULL DEFAULT '[]',
    item_codes         TEXT NOT NULL DEFAULT '[]',
    commodity_prefixes TEXT NOT NULL DEFAULT '[]',
    supplier_cuis      TEXT NOT NULL DEFAULT '[]',
    client_cui         TEXT,                        -- NULL: the rule is for every client
    enabled            INTEGER NOT NULL DEFAULT 1
);

-- The journal: what the program did, line by line (see journal.py). `trace` ties together
-- the lines of one operation; `data` is a JSON object of details, never a key or a token.
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    at          TEXT NOT NULL,
    level       TEXT NOT NULL,                      -- detail | info | warning | error
    area        TEXT NOT NULL,
    event       TEXT,                               -- a stable code; NULL for a plain log line
    message     TEXT NOT NULL,
    data        TEXT NOT NULL DEFAULT '{}',
    trace       TEXT,
    duration_ms INTEGER
);
CREATE INDEX IF NOT EXISTS idx_events_at ON events (at);
CREATE INDEX IF NOT EXISTS idx_events_trace ON events (trace);

-- The companies whose invoices are fetched. Removing one leaves its invoices in place.
CREATE TABLE IF NOT EXISTS clients (
    cui      TEXT PRIMARY KEY,
    name     TEXT NOT NULL,
    added_at TEXT NOT NULL,
    enabled  INTEGER NOT NULL DEFAULT 1
);

-- Every file the program has written for SAGA and not removed since. Only these are ever
-- deleted from the SAGA folder; a file put there by hand is none of the program's business.
CREATE TABLE IF NOT EXISTS saga_files (
    path       TEXT PRIMARY KEY,   -- as in messages.saga_xml_path
    cui        TEXT NOT NULL,
    written_at TEXT NOT NULL
);

-- Why a client's files for SAGA could not be brought up to date, until they are.
CREATE TABLE IF NOT EXISTS saga_problems (
    cui     TEXT PRIMARY KEY,
    message TEXT NOT NULL,
    at      TEXT NOT NULL
);
"""

RECEIVED_SQL = "message_type LIKE 'FACTURA PRIMITA%'"
ISSUED_SQL = "message_type LIKE 'FACTURA TRIMISA%'"  # the invoices a client issued itself
# "New" on screen: a received invoice brought in by that client's latest sync that brought
# any, and not yet marked as uploaded to accounting. `m` is the messages row being judged;
# the query must also join LATEST_RUN_JOIN, which works out each client's latest run once
# (asking again for every row made a long list take minutes).
LATEST_RUN_JOIN = (
    "LEFT JOIN (SELECT cui AS latest_cui, MAX(sync_run_id) AS latest_run FROM messages "
    f"WHERE {RECEIVED_SQL} GROUP BY cui) ON latest_cui = "
)
IS_NEW_SQL = (
    f"(m.{RECEIVED_SQL} AND m.uploaded_to_accounting = 0 AND m.sync_run_id IS NOT NULL "
    "AND m.sync_run_id = latest_run)"
)

RULE_FIELDS = ("name", "cont", *rule_examples.CONDITIONS, "client_cui", "enabled")
JEV_INSTRUCTIONS = "jev_instructions"
_EXAMPLES_ADDED = "examples_added"

# Added to `messages` after the first version; existing databases gain them on opening.
CLASSIFICATION_COLUMNS = {
    # NULL: not subject to classification (saved before it existed, or not a received
    # invoice). Otherwise: pending | classified | review.
    "classification_status": "TEXT",
    "cont": "TEXT",                   # the account every line is booked on
    "classification_method": "TEXT",  # rules | jev | jev_accepted | human
    "classification_reason": "TEXT",
    "suggested_cont": "TEXT",         # Jev's pick, kept even when a person overrules it
    "confidence": "REAL",             # Jev's confidence in that pick
    "confidence_threshold": "REAL",   # the level in force when Jev answered
    "classified_at": "TEXT",
    "saga_xml_path": "TEXT",          # relative to the data folder
    "classification_error": "TEXT",   # why the last attempt did not finish
}

# Added to `messages` later as well, but never listed with a message: proposed rules are
# worked out from them.
SUGGESTION_COLUMNS = {
    "rule_subject": "TEXT",              # what the rules read from the invoice (rules.Subject), as JSON
    "suggestion_dismissed_for": "TEXT",  # the account whose proposed rule a person turned down
}
# The account was chosen by Jev or by a person, not by a rule.
NOT_BY_RULE_SQL = "classification_method IN ('jev', 'jev_accepted', 'human')"

INSERT_COLUMNS = (
    "id", "cui", "message_type", "anaf_created_at", "id_solicitare", "detalii",
    "invoice_number", "invoice_issue_date", "invoice_due_date", "invoice_type_code",
    "supplier_cui", "supplier_name", "customer_cui", "customer_name",
    "currency", "total_without_vat", "total_vat", "total_payable",
    "invoice_xml", "signature_xml", "raw_metadata_json", "zip_sha256", "xml_path",
    "first_seen_at", "sync_run_id", "possible_duplicate_of", "classification_status",
)

XML_COLUMNS = ("invoice_xml", "signature_xml")

SUMMARY_COLUMNS = tuple(
    c for c in INSERT_COLUMNS
    if c not in XML_COLUMNS + ("raw_metadata_json", "zip_sha256", "classification_status")
) + ("uploaded_to_accounting", "uploaded_at") + tuple(CLASSIFICATION_COLUMNS)

JEV_CALL_COLUMNS = (
    "message_id", "cui", "called_at", "model", "request_json", "response_json",
    "http_status", "input_tokens", "output_tokens", "cost_usd", "duration_ms", "error",
)

# What stands in `message_id` of a Jev call made from the rule test: no invoice behind it.
RULE_TEST = "rule-test"

_CHUNK = 500  # stay well under SQLite's bound-parameter limit
# How long to keep trying to switch a new database file to WAL (about five seconds).
WAL_ATTEMPTS = 100
WAL_RETRY_DELAY = 0.05


class Store:
    def __init__(self, db_path: Path):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, timeout=30)
        self._conn.row_factory = sqlite3.Row
        self._use_wal()
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        self._migrate()

    def close(self) -> None:
        self._conn.close()

    def _use_wal(self) -> None:
        """WAL lets the page and a command read while another one writes.

        Switching a new file to it needs the file alone for an instant. SQLite does not
        wait for that by itself (the connection's timeout does not apply), so wait here
        when several programs open a new database at the same moment.
        """
        for attempt in range(WAL_ATTEMPTS):
            try:
                self._conn.execute("PRAGMA journal_mode=WAL")
                return
            except sqlite3.OperationalError:
                if attempt == WAL_ATTEMPTS - 1:
                    raise
                time.sleep(WAL_RETRY_DELAY)

    def _migrate(self) -> None:
        """Bring a database made by an earlier version up to date, keeping its rows.

        Several programs, or several requests, may open a new database in the same instant.
        BEGIN IMMEDIATE lets one of them in at a time and makes the others wait, so each
        sees what the one before it did instead of repeating it.
        """
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            present = {row["name"] for row in self._conn.execute("PRAGMA table_info(messages)")}
            for name, kind in {**CLASSIFICATION_COLUMNS, **SUGGESTION_COLUMNS}.items():
                if name not in present:
                    self._conn.execute(f"ALTER TABLE messages ADD COLUMN {name} {kind}")
            # A client switched off is left out of every download; all start switched on.
            if "enabled" not in {row["name"] for row in self._conn.execute("PRAGMA table_info(clients)")}:
                self._conn.execute("ALTER TABLE clients ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1")
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_classification "
                "ON messages (cui, classification_status)"
            )
            # Everything the lists count by, so counting never has to read the stored XML.
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_state ON messages "
                "(cui, message_type, sync_run_id, uploaded_to_accounting, classification_status)"
            )
            # Proposed rules look only at the invoices given an account lately.
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_classified_at ON messages (classified_at)"
            )
            if not self._conn.execute(
                "SELECT 1 FROM settings WHERE key = ?", (_EXAMPLES_ADDED,)
            ).fetchone():
                self._add_examples()
            self._conn.execute("COMMIT")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise

    def _add_examples(self) -> None:
        """Once per database: example accounts and rules, and the question for Jev. The
        flag stops them coming back after the accountant has deleted them. Runs inside
        _migrate's transaction, so nothing here commits."""
        self._conn.executemany(
            "INSERT OR IGNORE INTO accounts (cont, description) VALUES (?, ?)",
            rule_examples.EXAMPLE_ACCOUNTS.items(),
        )
        for position, example in enumerate(rule_examples.EXAMPLE_RULES, start=1):
            stored = _rule_columns({
                **dict.fromkeys(rule_examples.CONDITIONS, ()), "client_cui": None, "enabled": True,
                **example,
            })
            self._conn.execute(
                f"INSERT INTO rules (position, {', '.join(stored)}) "
                f"VALUES (?, {', '.join('?' * len(stored))})",
                (position, *stored.values()),
            )
        self._conn.executemany(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            [(JEV_INSTRUCTIONS, rule_examples.DEFAULT_JEV_INSTRUCTIONS), (_EXAMPLES_ADDED, "1")],
        )

    # --- messages -----------------------------------------------------------

    def existing_ids(self, ids: Iterable[str]) -> set[str]:
        wanted = list(ids)
        found: set[str] = set()
        for start in range(0, len(wanted), _CHUNK):
            chunk = wanted[start : start + _CHUNK]
            marks = ",".join("?" * len(chunk))
            rows = self._conn.execute(f"SELECT id FROM messages WHERE id IN ({marks})", chunk)
            found.update(row["id"] for row in rows)
        return found

    def insert_message(self, row: dict) -> None:
        columns = ", ".join(INSERT_COLUMNS)
        marks = ", ".join(f":{c}" for c in INSERT_COLUMNS)
        with self._conn:
            self._conn.execute(
                f"INSERT INTO messages ({columns}) VALUES ({marks})",
                {"classification_status": None, **row},
            )

    def find_same_invoice(
        self, cui: str, message_type: str, supplier_cui: str, invoice_number: str
    ) -> str | None:
        row = self._conn.execute(
            "SELECT id FROM messages WHERE cui = ? AND message_type = ? "
            "AND supplier_cui = ? AND invoice_number = ? ORDER BY first_seen_at, id LIMIT 1",
            (cui, message_type, supplier_cui, invoice_number),
        ).fetchone()
        return row["id"] if row else None

    def list_messages(
        self,
        cui: str | None = None,
        pending: bool = False,
        type_prefix: str | None = None,
        since: str | None = None,
        classification: str | None = None,
        only_new: bool = False,
    ) -> list[dict]:
        where, params = [], []
        if only_new:
            where.append(IS_NEW_SQL)
        if classification:
            where.append("classification_status = ?")
            params.append(classification)
        if cui:
            where.append("cui = ?")
            params.append(cui)
        if pending:
            where.append("uploaded_to_accounting = 0")
        if type_prefix:
            where.append("message_type LIKE ? ESCAPE '\\'")
            params.append(_like_prefix(type_prefix))
        if since:
            where.append("first_seen_at >= ?")
            params.append(since)
        sql = (
            f"SELECT {', '.join(SUMMARY_COLUMNS)}, {IS_NEW_SQL} AS is_new "
            f"FROM messages m {LATEST_RUN_JOIN}m.cui"
        )
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY first_seen_at, id"
        return [_to_dict(row) for row in self._conn.execute(sql, params)]

    def issued_count(self, cui: str) -> int:
        """How many invoices this client issued itself are saved."""
        return self._conn.execute(
            f"SELECT COUNT(*) FROM messages WHERE cui = ? AND {ISSUED_SQL}", (cui,)
        ).fetchone()[0]

    def get_message(self, message_id: str, include_xml: bool = False) -> dict | None:
        columns = SUMMARY_COLUMNS + (XML_COLUMNS if include_xml else ())
        row = self._conn.execute(
            f"SELECT {', '.join(columns)}, {IS_NEW_SQL} AS is_new "
            f"FROM messages m {LATEST_RUN_JOIN}m.cui WHERE id = ?",
            (message_id,),
        ).fetchone()
        return _to_dict(row) if row else None

    def set_uploaded(self, ids: Iterable[str], uploaded: bool, when: str) -> None:
        """All or nothing: an unknown id leaves every row untouched."""
        wanted = list(dict.fromkeys(ids))
        missing = [i for i in wanted if i not in self.existing_ids(wanted)]
        if missing:
            raise EfacturaError(NOT_FOUND, f"No saved message with id: {', '.join(missing)}")
        with self._conn:
            self._conn.executemany(
                "UPDATE messages SET uploaded_to_accounting = ?, uploaded_at = ? WHERE id = ?",
                [(1 if uploaded else 0, when if uploaded else None, i) for i in wanted],
            )

    # --- classification -----------------------------------------------------

    def pending_classification(self, cui: str) -> list[str]:
        """Ids of this company's messages still waiting for an account, oldest first."""
        rows = self._conn.execute(
            "SELECT id FROM messages WHERE cui = ? AND classification_status = 'pending' "
            "AND uploaded_to_accounting = 0 ORDER BY first_seen_at, id",
            (cui,),
        )
        return [row["id"] for row in rows]

    # --- the files for SAGA -------------------------------------------------

    def waiting_for_saga(self, cui: str) -> list[dict]:
        """This company's invoices that have an account and are not yet marked as imported,
        the one that has waited longest first. Each comes with its XML."""
        rows = self._conn.execute(
            "SELECT id, id_solicitare, cont, invoice_xml FROM messages "
            "WHERE cui = ? AND classification_status = 'classified' AND cont IS NOT NULL "
            "AND uploaded_to_accounting = 0 ORDER BY first_seen_at, id",
            (cui,),
        )
        return [dict(row) for row in rows]

    def clients_with_saga_files(self) -> list[str]:
        """Every company with an invoice waiting for SAGA, with a file still on record, or
        whose files could not be brought up to date the last time."""
        rows = self._conn.execute(
            "SELECT cui FROM messages WHERE saga_xml_path IS NOT NULL "
            "OR (classification_status = 'classified' AND uploaded_to_accounting = 0) "
            "UNION SELECT cui FROM saga_files UNION SELECT cui FROM saga_problems ORDER BY cui"
        )
        return [row["cui"] for row in rows]

    def saga_ledger(self, cui: str) -> dict[str, str | None]:
        """Every file the program has for this company, with when it was last written.
        A file written by a version that kept no such record has no time."""
        ledger: dict[str, str | None] = {
            row["saga_xml_path"]: None
            for row in self._conn.execute(
                "SELECT DISTINCT saga_xml_path FROM messages "
                "WHERE cui = ? AND saga_xml_path IS NOT NULL",
                (cui,),
            )
        }
        for row in self._conn.execute(
            "SELECT path, written_at FROM saga_files WHERE cui = ?", (cui,)
        ):
            ledger[row["path"]] = row["written_at"]
        return ledger

    def note_saga_file(self, path: str, cui: str, when: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO saga_files (path, cui, written_at) VALUES (?, ?, ?) "
                "ON CONFLICT(path) DO UPDATE SET cui = excluded.cui, written_at = excluded.written_at",
                (path, cui, when),
            )

    def forget_saga_file(self, path: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM saga_files WHERE path = ?", (path,))

    def place_in_saga_files(self, cui: str, placed: dict[str, str], when: str) -> None:
        """Which file each of this company's invoices is in: `placed` by message id, and no
        file for all its other invoices. All or nothing.

        A path that only an invoice remembered (an earlier version kept no other record)
        goes on record first, so its file is still known once the invoice has forgotten it.
        """
        with self._conn:
            self._conn.execute(
                "INSERT OR IGNORE INTO saga_files (path, cui, written_at) "
                "SELECT DISTINCT saga_xml_path, cui, ? FROM messages "
                "WHERE cui = ? AND saga_xml_path IS NOT NULL",
                (when, cui),
            )
            self._conn.execute("UPDATE messages SET saga_xml_path = NULL WHERE cui = ?", (cui,))
            self._conn.executemany(
                "UPDATE messages SET saga_xml_path = ? WHERE id = ? AND cui = ?",
                [(path, message_id, cui) for message_id, path in placed.items()],
            )

    def saga_problem(self, cui: str) -> dict | None:
        row = self._conn.execute(
            "SELECT message, at FROM saga_problems WHERE cui = ?", (cui,)
        ).fetchone()
        return dict(row) if row else None

    def set_saga_problem(self, cui: str, message: str | None, when: str) -> None:
        """Note why this company's files are not up to date; None when they are again."""
        with self._conn:
            if message is None:
                self._conn.execute("DELETE FROM saga_problems WHERE cui = ?", (cui,))
            else:
                self._conn.execute(
                    "INSERT INTO saga_problems (cui, message, at) VALUES (?, ?, ?) "
                    "ON CONFLICT(cui) DO UPDATE SET message = excluded.message, at = excluded.at",
                    (cui, message, when),
                )

    def cuis_of(self, ids: Iterable[str]) -> list[str]:
        """The companies these messages belong to."""
        wanted = list(dict.fromkeys(ids))
        found: set[str] = set()
        for start in range(0, len(wanted), _CHUNK):
            chunk = wanted[start : start + _CHUNK]
            marks = ",".join("?" * len(chunk))
            rows = self._conn.execute(f"SELECT DISTINCT cui FROM messages WHERE id IN ({marks})", chunk)
            found.update(row["cui"] for row in rows)
        return sorted(found)

    def set_classification(self, message_id: str, **fields) -> None:
        unknown = set(fields) - set(CLASSIFICATION_COLUMNS) - set(SUGGESTION_COLUMNS)
        if unknown:
            raise ValueError(f"Not classification fields: {', '.join(sorted(unknown))}")
        assignments = ", ".join(f"{name} = ?" for name in fields)
        with self._conn:
            cursor = self._conn.execute(
                f"UPDATE messages SET {assignments} WHERE id = ?", (*fields.values(), message_id)
            )
        if cursor.rowcount == 0:
            raise EfacturaError(NOT_FOUND, f"No saved message with id: {message_id}")

    # --- what proposed rules rest on ----------------------------------------------

    def decided_without_rule(self, since: str | None = None) -> list[dict]:
        """Invoices whose account Jev or a person chose, the newest decision first, leaving
        out those whose proposed rule was turned down for the account they have now."""
        recent, params = ("AND classified_at >= ?", [since]) if since else ("", [])
        rows = self._conn.execute(
            "SELECT id, cui, cont, supplier_name, rule_subject FROM messages "
            f"WHERE classification_status = 'classified' AND {NOT_BY_RULE_SQL} "
            "AND rule_subject IS NOT NULL "
            "AND (suggestion_dismissed_for IS NULL OR suggestion_dismissed_for != cont) "
            f"{recent} ORDER BY classified_at DESC, id",
            params,
        )
        return [dict(row) for row in rows]

    def classified_subjects(
        self, since: str | None = None, cui: str | None = None
    ) -> list[tuple[str, str]]:
        """The account and the stored subject of every invoice that has an account: what a
        rule is tried on to see how it would have done."""
        where, params = ["classification_status = 'classified'", "rule_subject IS NOT NULL"], []
        if since:
            where.append("classified_at >= ?")
            params.append(since)
        if cui:
            where.append("cui = ?")
            params.append(cui)
        rows = self._conn.execute(
            f"SELECT cont, rule_subject FROM messages WHERE {' AND '.join(where)}", params
        )
        return [(row["cont"], row["rule_subject"]) for row in rows]

    def suggestion_state(self, message_id: str) -> dict | None:
        """One message's stored subject, and the account its proposed rule was turned down for."""
        row = self._conn.execute(
            f"SELECT {', '.join(SUGGESTION_COLUMNS)} FROM messages WHERE id = ?", (message_id,)
        ).fetchone()
        return dict(row) if row else None

    def dismiss_suggestions(self, ids: Iterable[str]) -> None:
        """Turn down the proposed rule of these invoices, for the account each has now.
        All or nothing: an unknown id leaves every row untouched."""
        wanted = list(dict.fromkeys(ids))
        missing = [i for i in wanted if i not in self.existing_ids(wanted)]
        if missing:
            raise EfacturaError(NOT_FOUND, f"No saved message with id: {', '.join(missing)}")
        with self._conn:
            self._conn.executemany(
                "UPDATE messages SET suggestion_dismissed_for = cont WHERE id = ?",
                [(i,) for i in wanted],
            )

    def get_setting(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def delete_setting(self, key: str) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM settings WHERE key = ?", (key,))

    def set_setting(self, key: str, value: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    # --- clients ------------------------------------------------------------

    def clients(self) -> list[dict]:
        """Every client by name, with what the first screen shows about its invoices."""

        def count(condition: str) -> str:  # 0, not NULL, for a client without messages
            return f"COALESCE(SUM({condition}), 0)"

        def waiting(status: str) -> str:  # in that state and not yet in the accounting program
            return f"m.uploaded_to_accounting = 0 AND m.classification_status = '{status}'"

        rows = self._conn.execute(
            "SELECT c.cui, c.name, c.added_at, c.enabled, "
            f"{count('m.' + RECEIVED_SQL)} AS invoices, "
            f"{count(IS_NEW_SQL)} AS new_count, "
            f"{count(waiting('review'))} AS review_count, "
            f"{count(waiting('classified'))} AS ready_count, "
            "(SELECT MAX(r.started_at) FROM sync_runs r WHERE r.cui = c.cui "
            " AND r.status IN ('ok', 'partial')) AS last_sync_at "
            f"FROM clients c LEFT JOIN messages m ON m.cui = c.cui {LATEST_RUN_JOIN}c.cui "
            "GROUP BY c.cui ORDER BY c.name COLLATE NOCASE, c.cui"
        )
        return [{**row, "enabled": bool(row["enabled"])} for row in map(dict, rows)]

    def client_name(self, cui: str) -> str | None:
        row = self._conn.execute("SELECT name FROM clients WHERE cui = ?", (cui,)).fetchone()
        return row["name"] if row else None

    def client_enabled(self, cui: str) -> bool | None:
        """Is this client switched on? None when it is not in the list."""
        row = self._conn.execute("SELECT enabled FROM clients WHERE cui = ?", (cui,)).fetchone()
        return None if row is None else bool(row["enabled"])

    def set_client_enabled(self, cui: str, enabled: bool) -> None:
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE clients SET enabled = ? WHERE cui = ?", (1 if enabled else 0, cui)
            )
        if cursor.rowcount == 0:
            raise EfacturaError(NOT_FOUND, f"No client with CUI {cui}.")

    def clients_switched_on(self) -> list[dict]:
        """The clients a download goes through, in the order of the list."""
        rows = self._conn.execute(
            "SELECT cui, name FROM clients WHERE enabled = 1 ORDER BY name COLLATE NOCASE, cui"
        )
        return [dict(row) for row in rows]

    def client_switch_counts(self) -> tuple[int, int]:
        """How many clients are switched on, and how many off."""
        row = self._conn.execute(
            "SELECT COALESCE(SUM(enabled = 1), 0) AS on_, COALESCE(SUM(enabled = 0), 0) AS off FROM clients"
        ).fetchone()
        return row["on_"], row["off"]

    def save_client(self, cui: str, name: str, when: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO clients (cui, name, added_at) VALUES (?, ?, ?) "
                "ON CONFLICT(cui) DO UPDATE SET name = excluded.name",
                (cui, name, when),
            )

    def delete_client(self, cui: str) -> None:
        with self._conn:
            cursor = self._conn.execute("DELETE FROM clients WHERE cui = ?", (cui,))
        if cursor.rowcount == 0:
            raise EfacturaError(NOT_FOUND, f"No client with CUI {cui}.")

    # --- accounts and rules ---------------------------------------------------

    def accounts(self) -> dict[str, str]:
        rows = self._conn.execute("SELECT cont, description FROM accounts ORDER BY cont")
        return {row["cont"]: row["description"] for row in rows}

    def save_account(self, cont: str, description: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO accounts (cont, description) VALUES (?, ?) "
                "ON CONFLICT(cont) DO UPDATE SET description = excluded.description",
                (cont, description),
            )

    def delete_account(self, cont: str) -> None:
        with self._conn:
            cursor = self._conn.execute("DELETE FROM accounts WHERE cont = ?", (cont,))
        if cursor.rowcount == 0:
            raise EfacturaError(NOT_FOUND, f"No account {cont} in the list.")

    def rules(self) -> list[dict]:
        """Every rule in checking order, its condition lists decoded."""
        rows = self._conn.execute("SELECT * FROM rules ORDER BY position, id")
        return [
            {
                **dict(row),
                **{name: json.loads(row[name]) for name in rule_examples.CONDITIONS},
                "enabled": bool(row["enabled"]),
            }
            for row in rows
        ]

    def add_rule(self, **fields) -> int:
        stored = _rule_columns(fields)
        columns = ", ".join(stored)
        marks = ", ".join("?" * len(stored))
        with self._conn:
            cursor = self._conn.execute(
                f"INSERT INTO rules (position, {columns}) "
                f"VALUES ((SELECT COALESCE(MAX(position), 0) + 1 FROM rules), {marks})",
                tuple(stored.values()),
            )
        return cursor.lastrowid

    def update_rule(self, rule_id: int, **fields) -> None:
        stored = _rule_columns(fields)
        assignments = ", ".join(f"{name} = ?" for name in stored)
        with self._conn:
            cursor = self._conn.execute(
                f"UPDATE rules SET {assignments} WHERE id = ?", (*stored.values(), rule_id)
            )
        if cursor.rowcount == 0:
            raise EfacturaError(NOT_FOUND, f"No rule with id {rule_id}.")

    def delete_rule(self, rule_id: int) -> None:
        with self._conn:
            cursor = self._conn.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
        if cursor.rowcount == 0:
            raise EfacturaError(NOT_FOUND, f"No rule with id {rule_id}.")

    def move_rule(self, rule_id: int, up: bool) -> None:
        """Swap the rule with its neighbour in the checking order; at the end it stays."""
        ids = [row["id"] for row in self._conn.execute("SELECT id FROM rules ORDER BY position, id")]
        if rule_id not in ids:
            raise EfacturaError(NOT_FOUND, f"No rule with id {rule_id}.")
        here = ids.index(rule_id)
        there = here - 1 if up else here + 1
        if 0 <= there < len(ids):
            ids[here], ids[there] = ids[there], ids[here]
        with self._conn:
            self._conn.executemany(
                "UPDATE rules SET position = ? WHERE id = ?",
                [(position, each) for position, each in enumerate(ids, start=1)],
            )

    # --- Jev calls and their cost -------------------------------------------

    def add_jev_call(self, **call) -> None:
        columns = ", ".join(JEV_CALL_COLUMNS)
        marks = ", ".join(f":{c}" for c in JEV_CALL_COLUMNS)
        with self._conn:
            self._conn.execute(f"INSERT INTO jev_calls ({columns}) VALUES ({marks})", call)

    def jev_calls(self) -> list[dict]:
        return [dict(row) for row in self._conn.execute("SELECT * FROM jev_calls ORDER BY id")]

    def last_jev_call(self, message_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM jev_calls WHERE message_id = ? ORDER BY id DESC LIMIT 1", (message_id,)
        ).fetchone()
        return dict(row) if row else None

    def jev_costs(
        self, since: str | None = None, cui: str | None = None, until: str | None = None,
        group: str = "month",
    ) -> dict:
        """Calls, tokens and cost between two days (both included), in total and per
        `group`: day, week, month or year."""
        condition, params = _calls_between(since, until, cui)
        rows = self._conn.execute(
            "SELECT called_at, message_id, input_tokens, output_tokens, cost_usd, error "
            f"FROM jev_calls j{condition} ORDER BY called_at",
            params,
        ).fetchall()
        periods: dict[str, list] = {}
        for row in rows:
            periods.setdefault(_period(row["called_at"], group), []).append(row)
        return {
            **_cost_summary(rows),
            "by_period": [
                {"period": period, **_cost_summary(calls)} for period, calls in sorted(periods.items())
            ],
        }

    def jev_call_list(
        self, since: str | None = None, until: str | None = None, cui: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        """The latest calls, newest first, each with the invoice it was about."""
        condition, params = _calls_between(since, until, cui)
        rows = self._conn.execute(
            "SELECT j.called_at, j.message_id, j.cui, j.model, j.response_json, j.http_status, "
            "j.input_tokens, j.output_tokens, j.cost_usd, j.error, "
            "m.supplier_name, m.invoice_number, m.classification_status, m.cont, "
            "(SELECT c.name FROM clients c WHERE c.cui = j.cui) AS client_name "
            f"FROM jev_calls j LEFT JOIN messages m ON m.id = j.message_id{condition} "
            "ORDER BY j.id DESC LIMIT ?",
            (*params, limit),
        )
        return [dict(row) for row in rows]

    # --- run log ------------------------------------------------------------

    def start_run(self, cui: str, window_days: int, started_at: str) -> int:
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO sync_runs (cui, started_at, window_days) VALUES (?, ?, ?)",
                (cui, started_at, window_days),
            )
        return cursor.lastrowid

    def finish_run(
        self,
        run_id: int,
        finished_at: str,
        *,
        listed: int,
        new: int,
        failed: int,
        status: str,
        error: str | None = None,
        advances_coverage: bool = False,
    ) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE sync_runs SET finished_at = ?, listed = ?, new = ?, failed = ?, "
                "status = ?, error = ?, advances_coverage = ? WHERE id = ?",
                (finished_at, listed, new, failed, status, error, int(advances_coverage), run_id),
            )

    def last_clean_run_start(self, cui: str) -> str | None:
        """Start of the latest run for this CUI up to which everything is known to be saved."""
        row = self._conn.execute(
            "SELECT started_at FROM sync_runs WHERE cui = ? AND status = 'ok' "
            "AND advances_coverage = 1 ORDER BY started_at DESC LIMIT 1",
            (cui,),
        ).fetchone()
        return row["started_at"] if row else None

    def runs(self) -> list[dict]:
        return [dict(row) for row in self._conn.execute("SELECT * FROM sync_runs ORDER BY id")]


def _calls_between(since: str | None, until: str | None, cui: str | None) -> tuple[str, list]:
    """A WHERE clause for jev_calls (as `j`): from `since` to `until`, both days included."""
    where, params = [], []
    for comparison, day in ((">=", since), ("<=", until)):
        if day:
            where.append(f"substr(j.called_at, 1, 10) {comparison} ?")
            params.append(day)
    if cui:
        where.append("j.cui = ?")
        params.append(cui)
    return (" WHERE " + " AND ".join(where)) if where else "", params


def _period(called_at: str, group: str) -> str:
    """The day, ISO week, month or year a call belongs to, in the caller's local time."""
    day = called_at[:10]
    if group == "week":
        year, week, _ = date.fromisoformat(day).isocalendar()
        return f"{year}-W{week:02d}"
    return day[: {"day": 10, "month": 7, "year": 4}[group]]


def _cost_summary(calls: list) -> dict:
    belonging = [call for call in calls if call["message_id"] != RULE_TEST]
    return {
        "calls": len(calls),
        "failed_calls": sum(call["error"] is not None for call in calls),
        "calls_without_cost": sum(
            call["error"] is None and call["cost_usd"] is None for call in calls
        ),
        # A trial from the rule test is a call, and costs, but is not an invoice.
        "invoices": len({call["message_id"] for call in belonging}),
        "input_tokens": sum(call["input_tokens"] or 0 for call in calls),
        "output_tokens": sum(call["output_tokens"] or 0 for call in calls),
        "cost_usd": sum(call["cost_usd"] or 0 for call in calls),
        "invoice_cost_usd": sum(call["cost_usd"] or 0 for call in belonging),
    }


def _rule_columns(fields: dict) -> dict:
    """Rule fields as stored: the condition lists as JSON, the switch as 0 or 1."""
    unknown = set(fields) - set(RULE_FIELDS)
    if unknown:
        raise ValueError(f"Not rule fields: {', '.join(sorted(unknown))}")
    stored = dict(fields)
    for name in rule_examples.CONDITIONS:
        if name in stored:
            stored[name] = json.dumps(list(stored[name]), ensure_ascii=False)
    if "enabled" in stored:
        stored["enabled"] = int(bool(stored["enabled"]))
    return stored


def _like_prefix(prefix: str) -> str:
    escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return escaped + "%"


def _to_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    for flag in ("uploaded_to_accounting", "is_new"):
        data[flag] = bool(data[flag])
    return data
