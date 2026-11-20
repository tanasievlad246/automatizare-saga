"""SQLite storage: one row per ANAF message, plus a log of sync runs."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from datetime import date
from pathlib import Path
from typing import Iterable

from . import rules as rule_examples
from .errors import BUSY, NOT_FOUND, EfacturaError

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

-- The same, for the invoices a client issued itself: income accounts (701, 704, 707...).
CREATE TABLE IF NOT EXISTS issued_accounts (
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
    enabled            INTEGER NOT NULL DEFAULT 1,
    direction          TEXT NOT NULL DEFAULT 'received'  -- received | issued: the invoices it decides
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

-- The journal's technical side (see technical.py): each HTTP exchange with ANAF and OpenRouter,
-- and the program's debug records, filed under the journal's traces. Every secret is hidden
-- before a row is written and binary bodies are never kept; KEEP_DAYS, KEEP_RECORDS and
-- TOTAL_BYTES there bound it. `head` is what the list shows, `body` is read only when one is opened.
CREATE TABLE IF NOT EXISTS technical (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    at      TEXT NOT NULL,
    trace   TEXT,
    kind    TEXT NOT NULL,                  -- http | log
    level   TEXT NOT NULL,                  -- debug | info | warning | error
    summary TEXT NOT NULL,                  -- one line, for the saved journal
    head    TEXT NOT NULL DEFAULT '{}',     -- JSON: method, url, status, duration; or logger, where
    body    TEXT NOT NULL DEFAULT '{}',     -- JSON: headers and bodies; or the exception
    size    INTEGER NOT NULL DEFAULT 0      -- bytes of summary, head and body, for the cap on the whole
);
CREATE INDEX IF NOT EXISTS idx_technical_trace ON technical (trace);
CREATE INDEX IF NOT EXISTS idx_technical_at ON technical (at);

-- The companies whose invoices are fetched. Removing one leaves its invoices in place.
CREATE TABLE IF NOT EXISTS clients (
    cui      TEXT PRIMARY KEY,
    name     TEXT NOT NULL,
    added_at TEXT NOT NULL,
    enabled  INTEGER NOT NULL DEFAULT 1,
    per_line INTEGER NOT NULL DEFAULT 1   -- 1: each invoice line gets its own account
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

-- An import in SAGA confirmed, by the automation or on screen: the client's files as SAGA
-- got them, kept in `folder` (relative to the data folder), and the invoices they held.
CREATE TABLE IF NOT EXISTS saga_imports (
    id          INTEGER PRIMARY KEY,
    cui         TEXT NOT NULL,
    imported_at TEXT NOT NULL,
    source      TEXT NOT NULL,   -- api | screen
    folder      TEXT NOT NULL,
    files       TEXT NOT NULL    -- the file names, as a JSON list
);
CREATE TABLE IF NOT EXISTS saga_import_invoices (
    import_id  INTEGER NOT NULL REFERENCES saga_imports(id),
    message_id TEXT NOT NULL,
    position   INTEGER NOT NULL,   -- the invoice's place in the files
    PRIMARY KEY (import_id, message_id)
);
CREATE INDEX IF NOT EXISTS idx_saga_import_invoices_message ON saga_import_invoices (message_id);

-- How an invoice got its account, each time it changed: by whom, why, and what it had before.
-- Kept as long as the invoice; the journal is cleared after 30 days.
CREATE TABLE IF NOT EXISTS decisions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL,
    at         TEXT NOT NULL,
    source     TEXT NOT NULL,              -- download | again | redecide | person | split
    line       INTEGER,                    -- NULL: the whole invoice
    cont       TEXT,                       -- NULL: no account, it waits for a person
    method     TEXT,                       -- rules | jev | jev_accepted | human | follows | invoice; NULL while it waits
    reason     TEXT NOT NULL DEFAULT '',   -- the program's English explanation
    said       TEXT NOT NULL DEFAULT '{}'  -- JSON: rule, match, suggested_cont, confidence,
                                           -- confidence_threshold, probabilities, jev_only, before
);
CREATE INDEX IF NOT EXISTS idx_decisions_message ON decisions (message_id, id);
CREATE INDEX IF NOT EXISTS idx_saga_imports_cui ON saga_imports (cui, imported_at);
"""

RECEIVED_SQL = "message_type LIKE 'FACTURA PRIMITA%'"
ISSUED_SQL = "message_type LIKE 'FACTURA TRIMISA%'"  # the invoices a client issued itself
# "New" on screen: an invoice brought in by that client's latest sync that brought any of
# its kind (received or issued), and not yet marked as uploaded to accounting. `m` is the
# messages row being judged; the query must also join LATEST_RUN_JOIN, which works out each
# client's latest runs once (asking again for every row made a long list take minutes).
LATEST_RUN_JOIN = (
    "LEFT JOIN (SELECT cui AS latest_cui, "
    f"MAX(CASE WHEN {RECEIVED_SQL} THEN sync_run_id END) AS latest_run, "
    f"MAX(CASE WHEN {ISSUED_SQL} THEN sync_run_id END) AS latest_issued_run "
    "FROM messages GROUP BY cui) ON latest_cui = "
)
IS_NEW_SQL = (
    "(m.uploaded_to_accounting = 0 AND m.sync_run_id IS NOT NULL AND ("
    f"(m.{RECEIVED_SQL} AND m.sync_run_id = latest_run) OR "
    f"(m.{ISSUED_SQL} AND m.sync_run_id = latest_issued_run)))"
)

RULE_FIELDS = ("name", "cont", *rule_examples.CONDITIONS, "client_cui", "enabled", "direction")
RECEIVED, ISSUED = "received", "issued"  # the two kinds of invoice: a rule and an account list are for one
KINDS = (RECEIVED, ISSUED)
JEV_INSTRUCTIONS = "jev_instructions"
JEV_LINE_INSTRUCTIONS = "jev_line_instructions"  # the question about one line; unset: the default
# The two questions for the invoices a client issued; unset: the default ones.
JEV_ISSUED_INSTRUCTIONS = "jev_issued_instructions"
JEV_ISSUED_LINE_INSTRUCTIONS = "jev_issued_line_instructions"
_EXAMPLES_ADDED = "examples_added"
_ISSUED_EXAMPLES_ADDED = "issued_examples_added"
# Set once the issued invoices saved before they were classified have been put to wait.
ISSUED_BACKLOG = "issued_backlog_added"
# Written in the database once it is brought up to date (PRAGMA user_version). A database that
# carries it is opened by reading alone: bringing one up to date takes the write lock, and would
# make every page request wait for a long write by another program. Raise it with every change
# to SCHEMA or to _migrate.
SCHEMA_VERSION = 2  # 2: the table `technical`
_ACCOUNT_TABLES = {RECEIVED: "accounts", ISSUED: "issued_accounts"}

# What "Șterge toate datele" empties: everything the program gathered and the accountant built.
# In this order, so that no row is left pointing at one already gone (messages -> sync_runs,
# saga_import_invoices -> saga_imports). The example accounts and rules come back afterwards.
WIPED = (
    "decisions", "saga_import_invoices", "saga_imports", "saga_files", "saga_problems", "jev_calls",
    "messages", "sync_runs", "rules", "accounts", "issued_accounts", "clients",
)
# What it keeps: the settings (folders, the keys typed on screen, the schedule, Jev's questions)
# and the journal. A new table must be put in one list or the other; a test checks.
KEPT_BY_WIPE = ("settings", "events")
# Left out of a table's fingerprint: large, and written once with the row, never changed.
_NOT_FINGERPRINTED = {
    "messages": {"invoice_xml", "signature_xml", "raw_metadata_json"},
    "jev_calls": {"request_json", "response_json"},
}


def fingerprints(connection: sqlite3.Connection) -> dict[str, tuple[int, str]]:
    """For each table a wipe empties: how many rows it holds, and a digest of what they say.

    Two databases with the same fingerprints hold the same rows: a row added, removed or
    changed (an invoice ticked as imported, a rule renamed) changes its table's digest."""
    found = {}
    for table in WIPED:
        left_out = _NOT_FINGERPRINTED.get(table, set())
        columns = [row[1] for row in connection.execute(f"PRAGMA table_info({table})") if row[1] not in left_out]
        digest, count = hashlib.sha256(), 0
        for row in connection.execute(f"SELECT {', '.join(columns)} FROM {table} ORDER BY rowid"):
            digest.update(repr(tuple(row)).encode("utf-8"))
            count += 1
        found[table] = (count, digest.hexdigest())
    return found

# Added to `messages` after the first version; existing databases gain them on opening.
CLASSIFICATION_COLUMNS = {
    # NULL: not subject to classification (saved before it existed, or not a received
    # invoice). Otherwise: pending | classified | review.
    "classification_status": "TEXT",
    "cont": "TEXT",                   # the account of the invoice (of its largest line, when decided line by line)
    "classification_method": "TEXT",  # rules | jev | jev_accepted | human
    "classification_reason": "TEXT",
    "suggested_cont": "TEXT",         # Jev's pick, kept even when a person overrules it
    "confidence": "REAL",             # Jev's confidence in that pick
    "confidence_threshold": "REAL",   # the level in force when Jev answered
    "classified_at": "TEXT",
    "saga_xml_path": "TEXT",          # relative to the data folder
    # For an invoice decided line by line: a JSON list, one entry per line, with the line's
    # account and who chose it. NULL: one account for the whole invoice (`cont`).
    "line_accounts": "TEXT",
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
        self._conn.executescript(SCHEMA)  # takes no lock when the tables are there already
        if self._conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
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
            of_clients = {row["name"] for row in self._conn.execute("PRAGMA table_info(clients)")}
            if "enabled" not in of_clients:
                self._conn.execute("ALTER TABLE clients ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1")
            # Each line of an invoice gets its own account, for every client until it is
            # switched off; the clients of an earlier version start with it on as well.
            if "per_line" not in of_clients:
                self._conn.execute("ALTER TABLE clients ADD COLUMN per_line INTEGER NOT NULL DEFAULT 1")
            # Every rule of an earlier version was for received invoices.
            of_rules = {row["name"] for row in self._conn.execute("PRAGMA table_info(rules)")}
            if "direction" not in of_rules:
                self._conn.execute("ALTER TABLE rules ADD COLUMN direction TEXT NOT NULL DEFAULT 'received'")
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
            if not self._has_setting(_ISSUED_EXAMPLES_ADDED):
                self._conn.executemany(
                    "INSERT OR IGNORE INTO issued_accounts (cont, description) VALUES (?, ?)",
                    rule_examples.EXAMPLE_ISSUED_ACCOUNTS.items(),
                )
                self._conn.execute("INSERT INTO settings (key, value) VALUES (?, '1')", (_ISSUED_EXAMPLES_ADDED,))
            if not self._has_setting(ISSUED_BACKLOG):
                # Once: the invoices a client issued were saved and never classified before. Those
                # that could be read and that SAGA has not got yet wait for the client's next download.
                self._conn.execute(
                    f"UPDATE messages SET classification_status = 'pending' WHERE {ISSUED_SQL} "
                    "AND classification_status IS NULL AND uploaded_to_accounting = 0 "
                    "AND invoice_number IS NOT NULL"
                )
                self._conn.execute("INSERT INTO settings (key, value) VALUES (?, '1')", (ISSUED_BACKLOG,))
            self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self._conn.execute("COMMIT")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise

    def _has_setting(self, key: str) -> bool:
        return self._conn.execute("SELECT 1 FROM settings WHERE key = ?", (key,)).fetchone() is not None

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

    def wipe(self, expected: dict[str, tuple[int, str]]) -> dict[str, int]:
        """Empty every table in WIPED in one transaction, then put back the example accounts
        and rules, as on the first day. The settings and the journal are not touched.

        `expected` is the fingerprints of the copy made just before. They are taken again
        here, under the write lock: a row saved or changed after the copy was made (a rule
        edited on another tab) is in no copy, so then nothing is deleted. The deleted rows
        are overwritten, not only let go of. Returns how many rows each table lost."""
        self._conn.execute("PRAGMA secure_delete = ON")  # this connection only; it is closed after
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            found = fingerprints(self._conn)
            differ = [table for table in WIPED if found[table] != tuple(expected.get(table) or ())]
            if differ:
                raise EfacturaError(
                    BUSY,
                    f"The copy and the database do not hold the same rows ({', '.join(differ)}): "
                    "something changed while the copy was being made. Nothing was deleted; try again.",
                )
            for table in WIPED:
                self._conn.execute(f"DELETE FROM {table}")
            self._add_examples()
            self._conn.executemany(
                "INSERT OR IGNORE INTO issued_accounts (cont, description) VALUES (?, ?)",
                rule_examples.EXAMPLE_ISSUED_ACCOUNTS.items(),
            )
            self._conn.execute("COMMIT")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        return {table: rows for table, (rows, _) in found.items()}

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
        self, cui: str, message_type: str, supplier_cui: str, invoice_number: str, issue_date: str | None,
        before: str | None = None,
    ) -> str | None:
        """The first message saved with this very invoice: the same supplier, number and date
        (a supplier who numbers again each year reuses numbers, not dates). `before`: a
        message already saved; only those saved before it count. No date, no match."""
        if not issue_date:
            return None
        # In the order the rows were written: one download saves all its messages with the same
        # time, and ANAF's ids do not sort in the order they were saved.
        earlier, params = "", [cui, message_type, supplier_cui, invoice_number, issue_date]
        if before is not None:
            earlier = "AND rowid < (SELECT rowid FROM messages WHERE id = ?) "
            params.append(before)
        row = self._conn.execute(
            "SELECT id FROM messages WHERE cui = ? AND message_type = ? AND supplier_cui = ? "
            f"AND invoice_number = ? AND invoice_issue_date = ? {earlier}ORDER BY rowid LIMIT 1",
            params,
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
            if not type_prefix:
                # "New" alone keeps the meaning it always had for other programs: received
                # invoices. The new issued ones are asked for with their type.
                where.append(f"m.{RECEIVED_SQL}")
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

    def messages_by_ids(self, ids: list[str]) -> list[dict]:
        """These messages as the lists give them, in the order of `ids`; an unknown id is left out."""
        found: dict[str, dict] = {}
        for start in range(0, len(ids), _CHUNK):
            chunk = ids[start : start + _CHUNK]
            marks = ",".join("?" * len(chunk))
            rows = self._conn.execute(
                f"SELECT {', '.join(SUMMARY_COLUMNS)}, {IS_NEW_SQL} AS is_new "
                f"FROM messages m {LATEST_RUN_JOIN}m.cui WHERE id IN ({marks})",
                chunk,
            )
            found.update((row["id"], _to_dict(row)) for row in rows)
        return [found[message_id] for message_id in ids if message_id in found]

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
        found = self.existing_ids(wanted)
        missing = [i for i in wanted if i not in found]
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

    def to_classify_again(self, cui: str) -> list[str]:
        """Ids of this company's invoices, received or issued, that wait for a person or for
        Jev and are not yet in the accounting program, oldest first."""
        rows = self._conn.execute(
            "SELECT id FROM messages WHERE cui = ? AND classification_status IN ('review', 'pending') "
            "AND uploaded_to_accounting = 0 ORDER BY first_seen_at, id",
            (cui,),
        )
        return [row["id"] for row in rows]

    # --- the files for SAGA -------------------------------------------------

    def waiting_for_saga(self, cui: str) -> list[dict]:
        """This company's invoices that have an account and are not yet marked as imported,
        the one that has waited longest first. Each comes with its XML."""
        rows = self._conn.execute(
            "SELECT id, message_type, id_solicitare, cont, line_accounts, invoice_xml FROM messages "
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

    def saga_placement(self, cui: str) -> dict[str, list[str]]:
        """Which invoices each of this company's files for SAGA holds, as the program last
        wrote them: the file's path (as in saga_xml_path), then the message ids in the order
        the file has them."""
        placed: dict[str, list[str]] = {}
        for row in self._conn.execute(
            "SELECT id, saga_xml_path FROM messages WHERE cui = ? AND saga_xml_path IS NOT NULL "
            "ORDER BY first_seen_at, id",
            (cui,),
        ):
            placed.setdefault(row["saga_xml_path"], []).append(row["id"])
        return placed

    # --- the archive of imports in SAGA --------------------------------------------------

    def record_saga_import(
        self, *, cui: str, imported_at: str, source: str, folder: str, files: list[str], ids: list[str],
    ) -> int:
        """Keep an import in SAGA and mark its invoices as imported at `imported_at`. All or
        nothing: an unknown id keeps nothing and marks nothing."""
        wanted = list(dict.fromkeys(ids))
        found = self.existing_ids(wanted)
        missing = [i for i in wanted if i not in found]
        if missing:
            raise EfacturaError(NOT_FOUND, f"No saved message with id: {', '.join(missing)}")
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO saga_imports (cui, imported_at, source, folder, files) VALUES (?, ?, ?, ?, ?)",
                (cui, imported_at, source, folder, json.dumps(files, ensure_ascii=False)),
            )
            import_id = cursor.lastrowid
            self._conn.executemany(
                "INSERT INTO saga_import_invoices (import_id, message_id, position) VALUES (?, ?, ?)",
                [(import_id, message_id, position) for position, message_id in enumerate(wanted)],
            )
            self._conn.executemany(
                "UPDATE messages SET uploaded_to_accounting = 1, uploaded_at = ? WHERE id = ?",
                [(imported_at, message_id) for message_id in wanted],
            )
        return import_id

    def saga_imports(self, cui: str) -> list[dict]:
        """This company's imports, the newest first, each with how many invoices it held,
        of which kind, and how many of them are no longer marked as imported."""
        rows = self._conn.execute(
            "SELECT i.id, i.cui, i.imported_at, i.source, i.folder, i.files, "
            "COUNT(m.id) AS invoices, "
            f"COALESCE(SUM(CASE WHEN m.{RECEIVED_SQL} THEN 1 ELSE 0 END), 0) AS received, "
            f"COALESCE(SUM(CASE WHEN m.{ISSUED_SQL} THEN 1 ELSE 0 END), 0) AS issued, "
            "COALESCE(SUM(CASE WHEN m.uploaded_to_accounting = 0 THEN 1 ELSE 0 END), 0) AS unmarked "
            "FROM saga_imports i "
            "LEFT JOIN saga_import_invoices l ON l.import_id = i.id "
            "LEFT JOIN messages m ON m.id = l.message_id "
            "WHERE i.cui = ? GROUP BY i.id ORDER BY i.id DESC",  # in the order made: clock text repeats an hour in autumn
            (cui,),
        )
        return [{**dict(row), "files": json.loads(row["files"])} for row in rows]

    def saga_import(self, import_id: int) -> dict | None:
        """One import, with the ids of its invoices in the order the files held them."""
        row = self._conn.execute(
            "SELECT id, cui, imported_at, source, folder, files FROM saga_imports WHERE id = ?", (import_id,)
        ).fetchone()
        if row is None:
            return None
        ids = [
            found["message_id"] for found in self._conn.execute(
                "SELECT message_id FROM saga_import_invoices WHERE import_id = ? ORDER BY position", (import_id,)
            )
        ]
        return {**dict(row), "files": json.loads(row["files"]), "ids": ids}

    def saga_import_of(self, message_id: str) -> dict | None:
        """The latest import an invoice was in."""
        row = self._conn.execute(
            "SELECT i.id, i.imported_at, i.source FROM saga_imports i "
            "JOIN saga_import_invoices l ON l.import_id = i.id WHERE l.message_id = ? "
            "ORDER BY i.id DESC LIMIT 1",
            (message_id,),
        ).fetchone()
        return dict(row) if row else None

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
            f"WHERE {RECEIVED_SQL} AND classification_status = 'classified' AND {NOT_BY_RULE_SQL} "
            "AND rule_subject IS NOT NULL "
            "AND (suggestion_dismissed_for IS NULL OR suggestion_dismissed_for != cont) "
            f"{recent} ORDER BY julianday(classified_at) DESC, id",  # by the instant, whatever the offset
            params,
        )
        return [dict(row) for row in rows]

    def classified_subjects(
        self, since: str | None = None, cui: str | None = None
    ) -> list[tuple[str, str]]:
        """The account and the stored subject of every invoice that has an account: what a
        rule is tried on to see how it would have done."""
        # Received invoices only: proposed rules and the rule test are about those, so far.
        where, params = [RECEIVED_SQL, "classification_status = 'classified'", "rule_subject IS NOT NULL"], []
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
        found = self.existing_ids(wanted)
        missing = [i for i in wanted if i not in found]
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
            "SELECT c.cui, c.name, c.added_at, c.enabled, c.per_line, "
            f"{count('m.' + RECEIVED_SQL)} AS invoices, "
            f"{count('m.' + ISSUED_SQL)} AS issued_count, "
            f"{count(f'm.{RECEIVED_SQL} AND {IS_NEW_SQL}')} AS new_count, "
            f"{count(f'm.{ISSUED_SQL} AND {IS_NEW_SQL}')} AS issued_new_count, "
            f"{count(waiting('review'))} AS review_count, "
            f"{count(f'm.{ISSUED_SQL} AND ' + waiting('review'))} AS issued_review_count, "
            f"{count(waiting('pending'))} AS waiting_count, "
            f"{count(waiting('classified'))} AS ready_count, "
            "(SELECT MAX(r.started_at) FROM sync_runs r WHERE r.cui = c.cui "
            " AND r.status IN ('ok', 'partial')) AS last_sync_at "
            f"FROM clients c LEFT JOIN messages m ON m.cui = c.cui {LATEST_RUN_JOIN}c.cui "
            "GROUP BY c.cui ORDER BY c.name COLLATE NOCASE, c.cui"
        )
        return [
            {**row, "enabled": bool(row["enabled"]), "per_line": bool(row["per_line"])}
            for row in map(dict, rows)
        ]

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

    def client_per_line(self, cui: str) -> bool:
        """Does each line of this company's invoices get its own account? Yes, unless the
        client was switched to one account per invoice. A company that is not in the client
        list is classified as before: one account for the whole invoice."""
        row = self._conn.execute("SELECT per_line FROM clients WHERE cui = ?", (cui,)).fetchone()
        return row is not None and bool(row["per_line"])

    def set_client_per_line(self, cui: str, per_line: bool) -> bool:
        """Returns whether anything changed."""
        if self.client_enabled(cui) is None:
            raise EfacturaError(NOT_FOUND, f"No client with CUI {cui}.")
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE clients SET per_line = ? WHERE cui = ? AND per_line <> ?",
                (1 if per_line else 0, cui, 1 if per_line else 0),
            )
        return cursor.rowcount > 0

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

    def accounts(self, kind: str = RECEIVED) -> dict[str, str]:
        """The accounts for one kind of invoice: received, or issued by the client."""
        rows = self._conn.execute(f"SELECT cont, description FROM {_ACCOUNT_TABLES[kind]} ORDER BY cont")
        return {row["cont"]: row["description"] for row in rows}

    def save_account(self, cont: str, description: str, kind: str = RECEIVED) -> None:
        with self._conn:
            self._conn.execute(
                f"INSERT INTO {_ACCOUNT_TABLES[kind]} (cont, description) VALUES (?, ?) "
                "ON CONFLICT(cont) DO UPDATE SET description = excluded.description",
                (cont, description),
            )

    def delete_account(self, cont: str, kind: str = RECEIVED) -> None:
        with self._conn:
            cursor = self._conn.execute(f"DELETE FROM {_ACCOUNT_TABLES[kind]} WHERE cont = ?", (cont,))
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
        """Swap the rule with its neighbour of the same kind (received or issued) in the
        checking order; at the end of its kind it stays."""
        rows = list(self._conn.execute("SELECT id, direction FROM rules ORDER BY position, id"))
        ids = [row["id"] for row in rows]
        if rule_id not in ids:
            raise EfacturaError(NOT_FOUND, f"No rule with id {rule_id}.")
        here = ids.index(rule_id)
        kin = [index for index, row in enumerate(rows) if row["direction"] == rows[here]["direction"]]
        place = kin.index(here) + (-1 if up else 1)
        if 0 <= place < len(kin):
            there = kin[place]
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

    def add_decisions(self, rows: list[dict]) -> None:
        """Add to the history of invoices' accounts: each row has message_id, at, source,
        line, cont, method, reason and said (an object)."""
        if not rows:
            return
        with self._conn:
            self._conn.executemany(
                "INSERT INTO decisions (message_id, at, source, line, cont, method, reason, said) "
                "VALUES (:message_id, :at, :source, :line, :cont, :method, :reason, :said)",
                [{**row, "said": json.dumps(row["said"], ensure_ascii=False)} for row in rows],
            )

    def decisions(self, message_id: str) -> list[dict]:
        """The history of one invoice's account, the newest first."""
        rows = self._conn.execute(
            "SELECT id, at, source, line, cont, method, reason, said FROM decisions "
            "WHERE message_id = ? ORDER BY id DESC",
            (message_id,),
        )
        return [{**dict(row), "said": json.loads(row["said"])} for row in rows]

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
            "m.supplier_name, m.customer_name, m.message_type, m.invoice_number, m.classification_status, m.cont, "
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
            "AND advances_coverage = 1 ORDER BY id DESC LIMIT 1",  # the run started last
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
