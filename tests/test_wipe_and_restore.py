"""Starting again from zero, and putting back a copy made by another version of the program.

All names, codes and amounts here are made up.
"""

import shutil
import sqlite3
import zipfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from efactura import backup, background, journal, technical
from efactura import rules as rule_examples
from efactura.api import create_app
from efactura.config import load_config
from efactura.errors import EfacturaError
from efactura.service import _FileLock
from efactura.store import KEPT_BY_WIPE, SCHEMA, SCHEMA_VERSION, WIPED, Store
from helpers import VALID_CUI, make_row

NOW = datetime(2026, 11, 14, 9, 0, tzinfo=timezone(timedelta(hours=2)))
LATER = NOW + timedelta(hours=3)
HEALTHY = {"ok": True, "service": "efactura", "version": "0.3.0"}
KEY = {"X-API-Key": "local-key"}
BEFORE_WIPE = "autosaga-20261114-090000-before-wipe.zip"
MARKER = "TEXT-DE-PROBA-CARE-TREBUIE-SA-DISPARA"  # in the made-up invoice, to look for after a wipe
RECEIVED = "TEXT-PRIMIT-DE-LA-ANAF-CARE-TREBUIE-SA-DISPARA"  # in the made-up reply from ANAF, the same


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "program" / "config.toml"
    path.parent.mkdir()
    path.write_text('[api]\nkey = "local-key"\nport = 9001\n', encoding="utf-8")
    cfg = load_config(path)
    Store(cfg.db_path).close()
    journal.configure(cfg.db_path)
    return cfg


@pytest.fixture
def folder(tmp_path, cfg):
    chosen = tmp_path / "stick" / "Copii AutoSaga"
    backup.set_folder(cfg, str(chosen))
    return chosen


@pytest.fixture
def computer(monkeypatch):
    """The running program, as background.py sees it: stopped and started on request."""
    state = SimpleNamespace(answer=None, asked_to_stop=[], spawned=[])

    def spawn_command(config_path, output, *command):
        state.spawned.append(command)
        if command == ("serve",):
            state.answer = HEALTHY

    def ask_to_stop(port, key):
        state.asked_to_stop.append(port)
        state.answer = None

    monkeypatch.setattr(background, "probe", lambda port: state.answer)
    monkeypatch.setattr(background, "spawn_command", spawn_command)
    monkeypatch.setattr(background, "ask_to_stop", ask_to_stop)
    monkeypatch.setattr(background, "pause", lambda seconds: None)
    return state


def fill(cfg) -> None:
    """One of everything the program gathers and the accountant builds, plus settings."""
    store = Store(cfg.db_path)
    try:
        when = NOW.isoformat()
        store.save_client(VALID_CUI, "Alfa Construct SRL", when)
        run = store.start_run(VALID_CUI, 60, when)
        store.insert_message(make_row(sync_run_id=run, invoice_xml=f"<Invoice>{MARKER}</Invoice>"))
        store.save_account("6588", "Cont de probă")
        store.save_account("7588", "Venit de probă", kind="issued")
        store.add_rule(name="Regulă de probă", cont="6588", keywords=["proba"])
        store.add_decisions([{"message_id": "3001", "at": when, "source": "person", "line": None,
                              "cont": "6588", "method": "human", "reason": "", "said": {}}])
        store.note_saga_file(f"saga/{VALID_CUI}/F_87654321_FV-1042_09.11.2026.xml", VALID_CUI, when)
        store.set_saga_problem(VALID_CUI, "Folderul nu se poate scrie.", when)
        store.record_saga_import(cui=VALID_CUI, imported_at=when, source="screen", folder="saga-archive/1",
                                 files=["F_87654321_FV-1042_09.11.2026.xml"], ids=["3001"])
        store.add_jev_call(message_id="3001", cui=VALID_CUI, called_at=when, model="made-up-model",
                           request_json="{}", response_json="{}", http_status=200, input_tokens=10,
                           output_tokens=5, cost_usd=0.001, duration_ms=100, error=None)
        store.set_setting("openrouter_api_key", "sk-made-up-for-the-test")
        store.set_setting("saga_dir", r"C:\SAGA Import")
    finally:
        store.close()
    with journal.trace(fresh=True):  # one operation: its journal line, and what it asked of ANAF
        call_anaf()
        journal.record("sync", "sync.finished", "An old line.", now=NOW - timedelta(days=1))


def call_anaf() -> None:
    """One made-up call to ANAF, kept on the journal's technical side with what came back."""
    anaf = technical.watch(httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"mesaje": [{"detalii": RECEIVED}]}),
    )))
    anaf.get(f"https://api.anaf.ro/prod/FCTEL/rest/listaMesajeFactura?zile=60&cif={VALID_CUI}")


def technical_records(cfg) -> list[dict]:
    return technical.records(cfg.db_path)["records"]


def on_disk(cfg) -> bytes:
    """The database file and the files SQLite keeps beside it, as they are on the disk."""
    return b"".join(path.read_bytes() for path in cfg.data_dir.glob("efactura.db*"))


def counts(db_path) -> dict[str, int]:
    with sqlite3.connect(db_path) as database:
        return {table: database.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in WIPED}


def opened(zip_path, tmp_path):
    target = tmp_path / f"opened-{zip_path.name}"
    with zipfile.ZipFile(zip_path) as archive:
        archive.extract("efactura.db", target)
    return target / "efactura.db"


def rewritten(zip_path, tmp_path, change) -> None:
    """The copy in the folder, with `change` made to the database inside it."""
    database = opened(zip_path, tmp_path)
    connection = sqlite3.connect(database)
    try:
        change(connection)
        connection.commit()
    finally:
        connection.close()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(database, "efactura.db")


def setting(cfg, key):
    store = Store(cfg.db_path)
    try:
        return store.get_setting(key)
    finally:
        store.close()


def events(cfg):
    return [line["event"] for line in journal.events(cfg.db_path, oldest_first=True)["events"]]


# --- the wipe -----------------------------------------------------------------------------------


def test_a_wipe_keeps_a_checked_copy_then_empties_the_data(folder, cfg, tmp_path):
    fill(cfg)
    before = counts(cfg.db_path)

    result = backup.wipe(cfg, now=NOW)

    assert (result["ok"], result["kept_as"], result["kept_at"]) == (True, BEFORE_WIPE, "2026-11-14T09:00:00")
    assert result["deleted"] == before
    # The copy holds every row that was deleted.
    assert counts(opened(folder / BEFORE_WIPE, tmp_path)) == before
    left = counts(cfg.db_path)
    assert {table: n for table, n in left.items() if n} == {
        "accounts": len(rule_examples.EXAMPLE_ACCOUNTS),
        "issued_accounts": len(rule_examples.EXAMPLE_ISSUED_ACCOUNTS),
        "rules": len(rule_examples.EXAMPLE_RULES),
    }
    store = Store(cfg.db_path)
    try:
        # As on the first day: the examples are back, what the accountant added is not.
        assert store.accounts() == rule_examples.EXAMPLE_ACCOUNTS
        assert "6588" not in store.accounts() and "7588" not in store.accounts("issued")
        assert "Regulă de probă" not in [rule["name"] for rule in store.rules()]
        assert store.clients() == []
    finally:
        store.close()


def test_the_settings_the_journal_and_the_files_on_disk_stay(folder, cfg):
    fill(cfg)
    invoice_file = cfg.data_dir / "invoices" / "11-11-2026" / "12345674_primita_3001.xml"
    invoice_file.parent.mkdir(parents=True)
    invoice_file.write_text("<Invoice/>", encoding="utf-8")
    config_before = cfg.path.read_bytes()

    backup.wipe(cfg, now=NOW)

    assert setting(cfg, "openrouter_api_key") == "sk-made-up-for-the-test"
    assert setting(cfg, "saga_dir") == r"C:\SAGA Import"
    assert setting(cfg, backup.FOLDER) == str(folder)
    assert "sync.finished" in events(cfg)  # the journal from before is still there
    assert events(cfg)[-1] == "wipe.finished"
    assert invoice_file.read_text(encoding="utf-8") == "<Invoice/>"
    assert cfg.path.read_bytes() == config_before


def test_the_names_kept_for_the_clients_folders_for_saga_go_with_the_clients(folder, cfg, tmp_path):
    fill(cfg)
    kept = f"Alfa Construct SRL - {VALID_CUI}"
    store = Store(cfg.db_path)
    try:
        store.set_setting(f"saga_folder:{VALID_CUI}", kept)
        store.set_setting("saga_folder:14399840", "Beta Instal SRL - 14399840/14399840")
        store.set_setting("saga_file_per", "invoice")  # chosen on screen: a setting, not something known of a client
        store.set_setting("sagaXfolder:1", "a name that only looks alike")
    finally:
        store.close()

    backup.wipe(cfg, now=NOW)

    assert setting(cfg, f"saga_folder:{VALID_CUI}") is None
    assert setting(cfg, "saga_folder:14399840") is None
    assert setting(cfg, "saga_file_per") == "invoice"
    assert setting(cfg, "sagaXfolder:1") == "a name that only looks alike"
    assert setting(cfg, "saga_dir") == r"C:\SAGA Import"
    # The copy made before the wipe still has them: a restore brings the clients back with their folders' names.
    with sqlite3.connect(opened(folder / BEFORE_WIPE, tmp_path)) as copy:
        assert copy.execute("SELECT value FROM settings WHERE key = ?", (f"saga_folder:{VALID_CUI}",)).fetchone() == (kept,)


def test_the_journals_technical_records_are_deleted_and_the_copy_holds_them(folder, cfg, tmp_path):
    fill(cfg)
    (kept,) = technical_records(cfg)

    result = backup.wipe(cfg, now=NOW)

    assert technical_records(cfg) == []
    assert result["deleted"]["technical"] == 1
    in_the_copy = technical.record(opened(folder / BEFORE_WIPE, tmp_path), kept["id"])
    assert RECEIVED in in_the_copy["body"]["response"]["body"]["text"]


def test_a_technical_record_written_while_the_copy_was_made_does_not_refuse_the_wipe(folder, cfg, monkeypatch):
    fill(cfg)
    make = backup.snapshot

    def with_a_record_meanwhile(*args, **kwargs):
        made = make(*args, **kwargs)
        call_anaf()  # the program writes these by itself all the time: nobody's work, so no reason to stop
        return made

    monkeypatch.setattr(backup, "snapshot", with_a_record_meanwhile)

    result = backup.wipe(cfg, now=NOW)

    assert technical_records(cfg) == []
    assert (result["ok"], result["deleted"]["technical"]) == (True, 2)
    assert counts(cfg.db_path)["clients"] == 0


def test_the_journals_technical_view_shows_nothing_from_before_the_wipe(folder, cfg):
    fill(cfg)
    (kept,) = technical_records(cfg)
    operation = kept["trace"]
    api = TestClient(create_app(cfg))

    before = api.get("/events?technical=true", headers=KEY).json()
    api.post("/backups/wipe", headers=KEY)
    after = api.get("/events?technical=true", headers=KEY).json()

    assert before["technical"][operation]["http"] == 1
    assert operation in {line["trace"] for line in after["events"]}  # the journal's own line stays
    assert operation not in after["technical"]
    assert api.get(f"/events/technical?trace={operation}", headers=KEY).json()["records"] == []
    assert api.get(f"/events/technical/{kept['id']}", headers=KEY).status_code == 404


def test_every_table_is_either_wiped_or_kept_on_purpose():
    database = sqlite3.connect(":memory:")
    database.executescript(SCHEMA)
    tables = {row[0] for row in database.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    tables.discard("sqlite_sequence")

    assert set(WIPED).isdisjoint(KEPT_BY_WIPE)
    assert tables == set(WIPED) | set(KEPT_BY_WIPE)


def test_nothing_is_deleted_before_a_backup_folder_is_chosen(cfg):
    fill(cfg)
    before = counts(cfg.db_path)

    with pytest.raises(EfacturaError) as refused:
        backup.wipe(cfg, now=NOW)

    assert refused.value.code == "backup_error"
    assert "Nothing was deleted" in refused.value.message
    assert counts(cfg.db_path) == before
    assert events(cfg)[-1] == "wipe.failed"


def test_nothing_is_deleted_when_the_copy_cannot_be_written(folder, cfg):
    fill(cfg)
    before = counts(cfg.db_path)
    shutil.rmtree(folder)  # the stick was pulled out

    with pytest.raises(EfacturaError) as refused:
        backup.wipe(cfg, now=NOW)

    assert refused.value.code == "backup_error"
    assert counts(cfg.db_path) == before


@pytest.mark.parametrize("damage", [
    lambda path, tmp_path: path.write_bytes(b"not a zip"),
    lambda path, tmp_path: rewritten(path, tmp_path, lambda db: db.execute("DROP TABLE rules")),
    lambda path, tmp_path: rewritten(path, tmp_path, lambda db: db.execute("DELETE FROM messages")),
], ids=["unreadable", "a table missing", "rows missing"])
def test_nothing_is_deleted_when_the_copy_does_not_read_back_whole(folder, cfg, tmp_path, monkeypatch, damage, request):
    fill(cfg)
    before = counts(cfg.db_path)
    make = backup.snapshot

    def damaged_after_writing(*args, **kwargs):
        made = make(*args, **kwargs)
        damage(folder / made["name"], tmp_path)
        return made

    monkeypatch.setattr(backup, "snapshot", damaged_after_writing)

    with pytest.raises(EfacturaError) as refused:
        backup.wipe(cfg, now=NOW)

    # A copy that holds other rows than the database is retried: a new copy is made then.
    assert refused.value.code == ("busy" if "rows missing" in request.node.name else "backup_error")
    assert counts(cfg.db_path) == before


@pytest.mark.parametrize("change", [
    lambda store: store.save_client("14399840", "Brutăria Soarelui SRL", NOW.isoformat()),
    lambda store: store.update_rule(store.rules()[-1]["id"], name="Regulă de probă, schimbată"),
    lambda store: store.set_uploaded(["3001"], False, NOW.isoformat()),  # fill() ticked it
], ids=["a client added", "a rule edited", "an invoice unticked as imported in SAGA"])
def test_nothing_is_deleted_when_something_was_saved_while_the_copy_was_made(folder, cfg, monkeypatch, change):
    fill(cfg)
    make = backup.snapshot

    def with_a_change_meanwhile(*args, **kwargs):
        made = make(*args, **kwargs)
        store = Store(cfg.db_path)
        change(store)  # on another tab, while the copy is being written and checked
        store.close()
        return made

    monkeypatch.setattr(backup, "snapshot", with_a_change_meanwhile)
    before = counts(cfg.db_path)

    with pytest.raises(EfacturaError) as refused:
        backup.wipe(cfg, now=NOW)

    assert refused.value.code == "busy"  # nothing wrong with the folder: trying again works
    assert "changed while the copy was being made" in refused.value.message
    assert all(counts(cfg.db_path)[table] >= rows for table, rows in before.items())  # nothing deleted


@pytest.mark.parametrize("held", ["efactura.lock", "update.lock", "restore.lock", "saga-files.lock"],
                         ids=["download or classification", "update", "restore", "files for SAGA"])
def test_a_wipe_is_refused_while_the_program_is_busy(folder, cfg, held):
    fill(cfg)
    before = counts(cfg.db_path)

    with _FileLock(cfg.data_dir / held), pytest.raises(EfacturaError) as refused:
        backup.wipe(cfg, now=NOW)

    assert refused.value.code == "busy"
    assert list(folder.iterdir()) == []  # refused before a copy was even made
    assert counts(cfg.db_path) == before


def test_a_restore_is_refused_while_a_wipe_runs(folder, cfg, computer):
    fill(cfg)
    name = backup.snapshot(cfg, now=NOW)["name"]

    with _FileLock(cfg.data_dir / "restore.lock"):  # what a wipe holds while it runs
        with pytest.raises(EfacturaError) as refused:
            backup.restore(cfg, name, now=LATER)

    assert refused.value.code == "busy"
    assert computer.asked_to_stop == []


def test_the_copy_made_before_a_wipe_brings_everything_back(folder, cfg, computer):
    fill(cfg)
    before = counts(cfg.db_path)
    kept = backup.wipe(cfg, now=NOW)["kept_as"]

    listed = backup.status(cfg, LATER)["snapshots"]
    backup.restore(cfg, kept, now=LATER)

    assert [(each["name"], each["kind"]) for each in listed] == [(BEFORE_WIPE, "before-wipe")]
    assert counts(cfg.db_path) == before
    assert setting(cfg, "openrouter_api_key") == "sk-made-up-for-the-test"


def test_the_running_program_sees_the_empty_database_at_once(folder, cfg):
    fill(cfg)
    api = TestClient(create_app(cfg))

    before = api.get("/clients", headers=KEY).json()
    wiped = api.post("/backups/wipe", headers=KEY)
    after = api.get("/clients", headers=KEY).json()
    listed = api.get("/backups", headers=KEY).json()

    assert len(before["clients"]) == 1
    assert (wiped.status_code, wiped.json()["ok"], wiped.json()["kept_as"].endswith("-before-wipe.zip")) == (200, True, True)
    assert after["clients"] == []
    assert [each["kind"] for each in listed["snapshots"]] == ["before-wipe"]


def test_a_wipe_over_the_api_needs_the_key_and_says_when_it_is_refused(folder, cfg):
    fill(cfg)
    api = TestClient(create_app(cfg))

    assert api.post("/backups/wipe").status_code == 401
    with _FileLock(cfg.lock_path):
        busy = api.post("/backups/wipe", headers=KEY)

    assert (busy.status_code, busy.json()["error"]["code"]) == (409, "busy")
    assert counts(cfg.db_path)["clients"] == 1


# --- restoring a copy made by another version ----------------------------------------------------


def test_a_copy_made_by_a_newer_version_is_refused_with_the_reason(folder, cfg, computer, tmp_path):
    fill(cfg)
    name = backup.snapshot(cfg, now=NOW)["name"]
    rewritten(folder / name, tmp_path, lambda db: db.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}"))
    before = counts(cfg.db_path)

    with pytest.raises(EfacturaError) as from_the_page:
        backup.start_restore_in_background(cfg, name)
    with pytest.raises(EfacturaError):
        backup.restore(cfg, name, now=LATER)  # from the terminal, or a page that skipped the check

    assert from_the_page.value.code == "snapshot_too_new"
    assert "newer version" in from_the_page.value.message
    assert computer.spawned == [] and computer.asked_to_stop == []
    assert counts(cfg.db_path) == before
    last = backup.status(cfg, LATER)["last_restore"]
    assert last["ok"] is False and "newer version" in last["error"]


def old_database(path) -> None:
    """A database as an early version of the program left it: no version number, and none of
    the columns and tables added since."""
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE sync_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, cui TEXT NOT NULL, started_at TEXT NOT NULL,
                finished_at TEXT, window_days INTEGER NOT NULL, listed INTEGER, new INTEGER, failed INTEGER,
                status TEXT NOT NULL DEFAULT 'running', error TEXT, advances_coverage INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE messages (id TEXT PRIMARY KEY, cui TEXT NOT NULL, message_type TEXT NOT NULL,
                anaf_created_at TEXT, id_solicitare TEXT, detalii TEXT, invoice_number TEXT, invoice_issue_date TEXT,
                invoice_due_date TEXT, invoice_type_code TEXT, supplier_cui TEXT, supplier_name TEXT, customer_cui TEXT,
                customer_name TEXT, currency TEXT, total_without_vat TEXT, total_vat TEXT, total_payable TEXT,
                invoice_xml TEXT, signature_xml TEXT, raw_metadata_json TEXT NOT NULL, zip_sha256 TEXT, xml_path TEXT,
                first_seen_at TEXT NOT NULL, sync_run_id INTEGER REFERENCES sync_runs(id), possible_duplicate_of TEXT,
                uploaded_to_accounting INTEGER NOT NULL DEFAULT 0, uploaded_at TEXT);
            CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE clients (cui TEXT PRIMARY KEY, name TEXT NOT NULL, added_at TEXT NOT NULL);
            INSERT INTO clients VALUES ('14399840', 'Brutăria Veche SRL', '2026-01-05T10:00:00+02:00');
            """
        )
        connection.commit()
    finally:
        connection.close()


def test_an_older_copy_is_brought_up_to_date_as_it_is_restored(folder, cfg, computer, tmp_path):
    fill(cfg)
    made = tmp_path / "old" / "efactura.db"
    made.parent.mkdir()
    old_database(made)
    name = "autosaga-20260105-100000-manual.zip"
    with zipfile.ZipFile(folder / name, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(made, "efactura.db")

    backup.start_restore_in_background(cfg, name)  # not refused: older is fine
    backup.restore(cfg, name, now=LATER)

    with sqlite3.connect(cfg.db_path) as database:
        assert database.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert database.execute("SELECT name FROM clients").fetchall() == [("Brutăria Veche SRL",)]
        clients = {row[1] for row in database.execute("PRAGMA table_info(clients)")}
        messages = {row[1] for row in database.execute("PRAGMA table_info(messages)")}
    assert {"enabled", "per_line"} <= clients
    assert {"classification_status", "line_accounts"} <= messages
    assert setting(cfg, backup.FOLDER) == str(folder)  # backups go on to the same folder


def test_an_older_copy_that_cannot_be_brought_up_to_date_is_refused_before_anything_is_touched(
    folder, cfg, computer, tmp_path, monkeypatch
):
    fill(cfg)
    made = tmp_path / "old" / "efactura.db"
    made.parent.mkdir()
    old_database(made)
    name = "autosaga-20260105-100000-manual.zip"
    with zipfile.ZipFile(folder / name, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(made, "efactura.db")
    computer.answer = HEALTHY
    before = counts(cfg.db_path)

    def cannot(self):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(Store, "_migrate", cannot)

    with pytest.raises(EfacturaError):
        backup.restore(cfg, name, now=LATER)

    assert computer.asked_to_stop == []  # the program was never stopped
    assert counts(cfg.db_path) == before
    assert "up to date" in backup.status(cfg, LATER)["last_restore"]["error"]


def test_the_restore_and_the_wipe_are_both_in_the_journal(folder, cfg, computer):
    fill(cfg)
    kept = backup.wipe(cfg, now=NOW)["kept_as"]
    wiped_line = [line for line in journal.events(cfg.db_path)["events"] if line["event"] == "wipe.finished"][0]

    backup.restore(cfg, kept, now=LATER)

    assert (wiped_line["data"]["kept_as"], wiped_line["data"]["deleted"]["clients"]) == (kept, 1)
    assert events(cfg)[-1] == "restore.finished"


def test_the_deleted_invoices_do_not_linger_in_the_file(folder, cfg):
    fill(cfg)

    backup.wipe(cfg, now=NOW)

    assert MARKER.encode() not in on_disk(cfg)  # not in a free page, nor in the journal file beside it


def test_what_anaf_and_jev_answered_does_not_linger_in_the_file_either(folder, cfg):
    fill(cfg)
    assert RECEIVED.encode() in on_disk(cfg)  # kept on the journal's technical side

    backup.wipe(cfg, now=NOW)

    assert RECEIVED.encode() not in on_disk(cfg)


def test_the_wipe_is_not_called_failed_when_only_its_last_tidying_goes_wrong(folder, cfg, monkeypatch):
    fill(cfg)

    def cannot(cfg):
        raise RuntimeError("the disk went away")

    monkeypatch.setattr(backup, "_compact", cannot)

    result = backup.wipe(cfg, now=NOW)  # the rows are gone: saying "nothing was deleted" would be false

    assert result["ok"] is True and counts(cfg.db_path)["clients"] == 0
    assert events(cfg)[-1] == "wipe.finished"


def test_the_newest_copy_made_before_a_wipe_is_never_rotated_away(folder, cfg):
    fill(cfg)
    kept = backup.wipe(cfg, now=NOW)["kept_as"]

    for hour in range(1, backup.MAX_SNAPSHOTS + 3):  # weeks of daily copies afterwards
        backup.snapshot(cfg, "auto", now=NOW + timedelta(hours=hour))
    # One that began before the wipe and ended after it judges by the moment it began.
    backup.snapshot(cfg, "manual", now=NOW - timedelta(minutes=1))

    names = sorted(path.name for path in folder.iterdir())
    assert kept in names
    assert len(names) == backup.MAX_SNAPSHOTS


def test_a_newer_copy_is_refused_from_the_terminal_with_its_own_code(folder, cfg, computer, tmp_path):
    fill(cfg)
    name = backup.snapshot(cfg, now=NOW)["name"]
    rewritten(folder / name, tmp_path, lambda db: db.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}"))

    with pytest.raises(EfacturaError) as refused:
        backup.restore(cfg, name, now=LATER)

    assert refused.value.code == "snapshot_too_new"
    assert "left as it was" in refused.value.message
