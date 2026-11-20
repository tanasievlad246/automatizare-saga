"""An import in SAGA confirmed by the automation or on screen: the invoices in the client's
files are marked as imported, and the files, as SAGA got them, go to the archive."""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from efactura import auth, journal, service as service_module
from efactura.api import create_app
from efactura.auth import Tokens
from efactura.config import load_config
from efactura.errors import EfacturaError
from efactura.rules import Rule, Rulebook
from efactura.service import Service
from efactura.store import Store

from helpers import OTHER_VALID_CUI, VALID_CUI, FakeAnaf, FakeOpenRouter, line, rich_invoice_xml, set_rulebook

NOW = datetime(2026, 11, 17, 10, 42, tzinfo=timezone(timedelta(hours=2)))
LATER = NOW + timedelta(minutes=5)

BOOK = Rulebook(
    accounts={"6022": "Combustibil.", "628": "Alte servicii."},
    rules=(Rule("combustibil", "6022", keywords=("motorina",)),),
    instructions="Alege contul facturii.",
)
FUEL = [line("Motorina Euro 5", "450.00", quantity="60", unit="LTR", price="7.50")]


def name_of(number):
    return f"F_87654321_{number}_09.11.2026.xml"


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[anaf]\nclient_id = "my-client"\nclient_secret = "my-secret"\n'
        f"token_file = '{tmp_path / 'private' / 'tokens.json'}'\n"
        '[openrouter]\napi_key = "or-test-key"\n[api]\nkey = "local-key"\n',
        encoding="utf-8",
    )
    cfg = load_config(path)
    set_rulebook(cfg.db_path, BOOK)
    return cfg


@pytest.fixture
def anaf():
    fake = FakeAnaf()
    fake.openrouter = FakeOpenRouter()
    return fake


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(service_module, "_pause", lambda seconds: None)


@pytest.fixture(autouse=True)
def logged_in(cfg):
    auth.save_tokens(
        cfg.token_file,
        Tokens("access-1", "refresh-1", NOW + timedelta(days=30), NOW + timedelta(days=300), NOW),
    )


@pytest.fixture
def clock():
    return {"now": NOW}


@pytest.fixture
def service(cfg, anaf, clock):
    desk = Service(cfg, http=anaf.client(), now=lambda: clock["now"])
    for cui, name in ((VALID_CUI, "Alfa Construct SRL"), (OTHER_VALID_CUI, "Beta Instal SRL")):
        desk.save_client(cui, name)
    return desk


def downloaded(service, anaf, *numbers, cui=VALID_CUI, first_id=3001):
    """Invoices with these numbers, downloaded and booked by the rule."""
    for position, number in enumerate(numbers):
        anaf.add(str(first_id + position), xml=rich_invoice_xml(lines=FUEL, number=number, customer_cui=cui), cui=cui)
    return service.sync(cui)["new"]


def folder(cfg, cui=VALID_CUI) -> Path:
    name = {VALID_CUI: "Alfa Construct SRL", OTHER_VALID_CUI: "Beta Instal SRL"}[cui]
    return cfg.saga_dir / f"{name} - {cui}"


def files_in(path) -> list[str]:
    return sorted(found.name for found in Path(path).glob("*")) if Path(path).exists() else []


def imported(service, *ids):
    return [service.invoice(message_id)["invoice"]["uploaded_to_accounting"] for message_id in ids]


# --- what waits, for the automation -------------------------------------------------------


def test_the_list_gives_each_client_with_a_file_its_path_count_and_version(service, anaf, cfg):
    downloaded(service, anaf, "A1", "A2")
    downloaded(service, anaf, "B1", cui=OTHER_VALID_CUI, first_id=4001)

    listed = service.saga_files()["clients"]

    assert [(entry["cui"], entry["client"], entry["invoices"]) for entry in listed] == [
        (VALID_CUI, "Alfa Construct SRL", 2), (OTHER_VALID_CUI, "Beta Instal SRL", 1)]
    first = listed[0]
    assert first["files"] == [{
        "name": name_of("A1"), "path": str(folder(cfg) / name_of("A1")), "invoices": 2, "ids": ["3001", "3002"],
        "written_at": NOW.isoformat(), "present": True,
    }]
    assert (first["file_per"], first["up_to_date"], first["folder"]) == ("client", True, str(folder(cfg)))
    assert len(first["version"]) == 16 and first["version"] != listed[1]["version"]
    assert service.saga_files(VALID_CUI) == {"ok": True, **first}


def test_the_version_changes_with_the_file_and_only_with_it(service, anaf, clock):
    downloaded(service, anaf, "A1")
    before = service.saga_files(VALID_CUI)["version"]
    clock["now"] = LATER
    service.write_saga_files(VALID_CUI)  # written again, the same

    assert service.saga_files(VALID_CUI)["version"] == before
    downloaded(service, anaf, "A2", first_id=3002)
    assert service.saga_files(VALID_CUI)["version"] != before


def test_a_client_with_nothing_waiting_has_no_file_and_no_version(service, cfg):
    assert service.saga_files(VALID_CUI) == {
        "ok": True, "cui": VALID_CUI, "client": "Alfa Construct SRL", "file_per": "client",
        "folder": str(folder(cfg)), "files": [], "invoices": 0, "up_to_date": True, "version": None,
    }
    assert service.saga_files()["clients"] == []


def test_the_screen_state_carries_the_same_version(service, anaf):
    downloaded(service, anaf, "A1")

    assert service.invoices(cui=VALID_CUI)["saga"]["version"] == service.saga_files(VALID_CUI)["version"]


# --- confirming an import -----------------------------------------------------------------


def test_confirming_marks_the_invoices_in_the_file_and_moves_it_to_the_archive(service, anaf, cfg):
    downloaded(service, anaf, "A1", "A2")
    waiting = service.saga_files(VALID_CUI)
    sent_to_saga = (folder(cfg) / name_of("A1")).read_bytes()

    archive = service.confirm_saga_import(VALID_CUI, version=waiting["version"])["archive"]

    kept = cfg.data_dir / "saga-archive" / VALID_CUI / "2026-11-17_10-42-00" / name_of("A1")
    assert kept.read_bytes() == sent_to_saga and files_in(folder(cfg)) == []
    assert imported(service, "3001", "3002") == [True, True]
    assert archive == {
        "id": archive["id"], "cui": VALID_CUI, "imported_at": NOW.isoformat(), "source": "api",
        "invoices": 2, "ids": ["3001", "3002"], "folder": str(kept.parent),
        "files": [{"name": name_of("A1"), "path": str(kept)}],
    }
    assert service.saga_files(VALID_CUI)["files"] == []


def test_without_a_version_whatever_the_file_holds_is_confirmed(service, anaf):
    downloaded(service, anaf, "A1", "A2")

    archive = service.confirm_saga_import(VALID_CUI)["archive"]

    assert archive["ids"] == ["3001", "3002"] and imported(service, "3001", "3002") == [True, True]


def test_a_file_changed_since_its_version_was_read_is_refused_and_nothing_changes(service, anaf, cfg):
    downloaded(service, anaf, "A1")
    read_by_the_automation = service.saga_files(VALID_CUI)["version"]
    downloaded(service, anaf, "A2", first_id=3002)  # an automatic download, while SAGA was importing

    with pytest.raises(EfacturaError) as refused:
        service.confirm_saga_import(VALID_CUI, version=read_by_the_automation)

    assert refused.value.code == "saga_files_changed"
    assert imported(service, "3001", "3002") == [False, False] and files_in(folder(cfg)) == [name_of("A1")]
    assert not (cfg.data_dir / "saga-archive").exists() and service.saga_archive(VALID_CUI)["imports"] == []


def test_files_that_are_not_up_to_date_are_refused(service, anaf, cfg, monkeypatch):
    downloaded(service, anaf, "A1")
    real_write = service_module._write_file

    def refuse(path, content):
        if "SAGA Import" in str(path):
            raise PermissionError("folder is read-only")
        real_write(path, content)

    monkeypatch.setattr(service_module, "_write_file", refuse)
    downloaded(service, anaf, "A2", first_id=3002)  # the file could not take it

    with pytest.raises(EfacturaError) as refused:
        service.confirm_saga_import(VALID_CUI)

    assert refused.value.code == "saga_files_stale" and imported(service, "3001") == [False]
    assert service.saga_files(VALID_CUI)["up_to_date"] is False


def test_a_file_gone_from_the_folder_is_refused(service, anaf, cfg):
    downloaded(service, anaf, "A1")
    (folder(cfg) / name_of("A1")).unlink()

    with pytest.raises(EfacturaError) as refused:
        service.confirm_saga_import(VALID_CUI)

    assert refused.value.code == "saga_files_stale" and imported(service, "3001") == [False]


def test_with_nothing_waiting_the_answer_is_empty(service, cfg):
    assert service.confirm_saga_import(VALID_CUI) == {"ok": True, "archive": None}
    assert not (cfg.data_dir / "saga-archive").exists()


def test_an_unknown_or_malformed_client_is_refused(service):
    with pytest.raises(EfacturaError) as unknown:
        service.confirm_saga_import("18547290")
    with pytest.raises(EfacturaError) as malformed:
        service.confirm_saga_import("123")

    assert (unknown.value.code, malformed.value.code) == ("not_found", "invalid_cui")


def test_a_client_taken_off_the_list_can_still_have_its_waiting_files_confirmed(service, anaf, cfg):
    downloaded(service, anaf, "A1")
    service.remove_client(VALID_CUI)
    version = service.saga_files(VALID_CUI)["version"]

    archive = service.confirm_saga_import(VALID_CUI, version=version)["archive"]

    assert archive["ids"] == ["3001"]
    assert files_in(folder(cfg)) == []


def test_a_change_saved_but_not_yet_written_to_the_file_is_refused_and_nothing_is_marked(service, anaf, cfg):
    downloaded(service, anaf, "A1")
    version = service.saga_files(VALID_CUI)["version"]
    store = Store(cfg.db_path)
    try:  # a person changed the account; the writer of the files is still waiting for its turn
        store.set_classification("3001", cont="628")
    finally:
        store.close()

    with pytest.raises(EfacturaError) as info:
        service.confirm_saga_import(VALID_CUI, version=version)

    assert info.value.code == "saga_files_stale"
    assert imported(service, "3001") == [False]


def test_files_written_but_not_recorded_are_refused_rather_than_marking_an_invoice_saga_never_got(
    service, anaf, cfg, monkeypatch,
):
    downloaded(service, anaf, "A1", "A2")
    store = Store(cfg.db_path)
    try:
        store.set_classification("3002", classification_status="review", cont=None)  # back to a person
    finally:
        store.close()

    def database_busy(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(Store, "place_in_saga_files", database_busy)
    monkeypatch.setattr(Store, "set_saga_problem", database_busy)
    service.write_saga_files(VALID_CUI)  # the file now holds A1 alone; the record still says A1 and A2
    monkeypatch.undo()
    version = service.saga_files(VALID_CUI)["version"]

    with pytest.raises(EfacturaError) as info:
        service.confirm_saga_import(VALID_CUI, version=version)

    assert info.value.code == "saga_files_stale"
    assert imported(service, "3001", "3002") == [False, False]


def test_only_the_named_client_is_confirmed(service, anaf, cfg):
    downloaded(service, anaf, "A1")
    downloaded(service, anaf, "B1", cui=OTHER_VALID_CUI, first_id=4001)

    service.confirm_saga_import(VALID_CUI)

    assert imported(service, "3001", "4001") == [True, False] and files_in(folder(cfg, OTHER_VALID_CUI)) == [name_of("B1")]


def test_with_a_file_per_invoice_every_file_goes_into_one_entry(service, anaf, cfg):
    service.change_settings(saga_file_per="invoice")
    downloaded(service, anaf, "A1", "A2")

    archive = service.confirm_saga_import(VALID_CUI)["archive"]

    assert [entry["name"] for entry in archive["files"]] == [name_of("A1"), name_of("A2")]
    assert files_in(Path(archive["folder"])) == [name_of("A1"), name_of("A2")] and files_in(folder(cfg)) == []


def test_two_confirmations_in_the_same_second_keep_both_archives(service, anaf):
    downloaded(service, anaf, "A1")
    first = service.confirm_saga_import(VALID_CUI)["archive"]
    downloaded(service, anaf, "A2", first_id=3002)

    second = service.confirm_saga_import(VALID_CUI)["archive"]

    assert first["folder"] != second["folder"] and Path(first["folder"]).is_dir() and Path(second["folder"]).is_dir()


def test_a_file_saga_keeps_open_stays_until_it_can_go(service, anaf, cfg, monkeypatch):
    downloaded(service, anaf, "A1")
    real_unlink = Path.unlink

    def locked(path, *args, **kwargs):
        if "SAGA Import" in str(path):
            raise PermissionError("The process cannot access the file because it is being used by another process")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", locked)
    archive = service.confirm_saga_import(VALID_CUI)["archive"]

    # Marked and archived all the same; the file is noted and removed at the next try.
    assert imported(service, "3001") == [True] and Path(archive["files"][0]["path"]).is_file()
    assert service.invoices(cui=VALID_CUI)["saga"]["problem"] is not None
    monkeypatch.setattr(Path, "unlink", real_unlink)
    service.write_saga_files(VALID_CUI)
    assert files_in(folder(cfg)) == []


def test_a_confirmation_from_the_screen_says_so_and_goes_to_the_journal(service, anaf, cfg):
    downloaded(service, anaf, "A1")

    archive = service.confirm_saga_import(VALID_CUI, source="screen")["archive"]

    assert archive["source"] == "screen"
    (line_,) = [event for event in journal.events(cfg.db_path)["events"] if event["event"] == "saga.imported"]
    assert line_["data"]["invoices"] == 1 and line_["data"]["source"] == "screen" and line_["data"]["cui"] == VALID_CUI
    with pytest.raises(EfacturaError) as refused:
        service.confirm_saga_import(VALID_CUI, source="somewhere")
    assert refused.value.code == "invalid_input"


# --- the archive --------------------------------------------------------------------------


def test_the_archive_lists_the_imports_newest_first_with_their_counts(service, anaf, clock):
    downloaded(service, anaf, "A1")
    service.confirm_saga_import(VALID_CUI)
    clock["now"] = LATER
    downloaded(service, anaf, "A2", "A3", first_id=3002)
    service.confirm_saga_import(VALID_CUI, source="screen")

    imports = service.saga_archive(VALID_CUI)["imports"]

    assert [(entry["imported_at"], entry["source"], entry["invoices"], entry["received"], entry["unmarked"]) for entry in imports] == [
        (LATER.isoformat(), "screen", 2, 2, 0), (NOW.isoformat(), "api", 1, 1, 0)]
    assert imports[0]["files"] == [{"name": name_of("A2"), "path": str(Path(imports[0]["folder"]) / name_of("A2")), "present": True}]


def test_an_entry_gives_its_invoices_as_the_lists_do(service, anaf):
    downloaded(service, anaf, "A1", "A2")
    archive = service.confirm_saga_import(VALID_CUI)["archive"]

    entry = service.saga_archive_entry(archive["id"])["import"]

    assert [invoice["invoice_number"] for invoice in entry["invoices"]] == ["A1", "A2"]
    assert entry["invoices"][0]["cont"] == "6022" and entry["invoices"][0]["uploaded_to_accounting"] is True


def test_an_archived_file_can_be_read_back_and_nothing_outside_the_entry(service, anaf):
    downloaded(service, anaf, "A1")
    archive = service.confirm_saga_import(VALID_CUI)["archive"]

    path = service.saga_archive_file(archive["id"], name_of("A1"))

    assert path.read_bytes().startswith(b"<?xml")
    for wrong in ("F_other.xml", "../../efactura.db", f"..\\{name_of('A1')}"):
        with pytest.raises(EfacturaError) as refused:
            service.saga_archive_file(archive["id"], wrong)
        assert refused.value.code == "not_found"
    with pytest.raises(EfacturaError):
        service.saga_archive_entry(999)


def test_a_file_removed_by_hand_is_said_to_be_gone(service, anaf):
    downloaded(service, anaf, "A1")
    archive = service.confirm_saga_import(VALID_CUI)["archive"]
    Path(archive["files"][0]["path"]).unlink()

    assert service.saga_archive(VALID_CUI)["imports"][0]["files"][0]["present"] is False
    with pytest.raises(EfacturaError) as refused:
        service.saga_archive_file(archive["id"], name_of("A1"))
    assert refused.value.code == "not_found"


def test_an_invoice_knows_the_import_it_went_to_saga_in(service, anaf):
    downloaded(service, anaf, "A1")
    archive = service.confirm_saga_import(VALID_CUI)["archive"]

    assert service.invoice("3001")["invoice"]["saga_import"] == {"id": archive["id"], "imported_at": NOW.isoformat(), "source": "api"}
    # The invoice's own screen reads it from there too.
    assert service.invoice_view("3001")["invoice"]["saga_import"]["id"] == archive["id"]


def test_an_invoice_unmarked_after_its_import_goes_back_to_the_file_and_the_entry_counts_it(service, anaf, cfg):
    downloaded(service, anaf, "A1", "A2")
    service.confirm_saga_import(VALID_CUI)

    service.mark_uploaded(["3002"], undo=True)

    assert files_in(folder(cfg)) == [name_of("A2")]
    assert service.saga_archive(VALID_CUI)["imports"][0]["unmarked"] == 1


# --- over the local API -------------------------------------------------------------------

KEY = {"X-API-Key": "local-key"}


@pytest.fixture
def api(cfg, anaf, clock, service):  # `service` adds the two clients
    return TestClient(create_app(cfg, service_factory=lambda cfg: Service(cfg, http=anaf.client(), now=lambda: clock["now"])))


def test_the_automation_reads_what_waits_and_confirms_it_over_the_api(api, service, anaf, cfg):
    downloaded(service, anaf, "A1")

    listed = api.get("/saga-files", headers=KEY).json()["clients"]
    one = api.get(f"/saga-files/{VALID_CUI}", headers=KEY).json()
    confirmed = api.post(f"/saga-files/{VALID_CUI}/imported", headers=KEY, json={"version": one["version"]})

    assert [entry["cui"] for entry in listed] == [VALID_CUI] and one["files"][0]["path"] == str(folder(cfg) / name_of("A1"))
    assert confirmed.status_code == 200 and confirmed.json()["archive"]["ids"] == ["3001"]
    assert api.post(f"/saga-files/{VALID_CUI}/imported", headers=KEY, json={}).json() == {"ok": True, "archive": None}


def test_a_changed_file_answers_409_over_the_api(api, service, anaf):
    downloaded(service, anaf, "A1")
    version = api.get(f"/saga-files/{VALID_CUI}", headers=KEY).json()["version"]
    downloaded(service, anaf, "A2", first_id=3002)

    refused = api.post(f"/saga-files/{VALID_CUI}/imported", headers=KEY, json={"version": version, "source": "screen"})

    assert (refused.status_code, refused.json()["error"]["code"]) == (409, "saga_files_changed")


@pytest.mark.parametrize("call", [
    lambda api: api.get("/saga-files/18547290", headers=KEY),
    lambda api: api.post("/saga-files/18547290/imported", headers=KEY, json={}),
    lambda api: api.get("/saga-archive/999", headers=KEY),
    lambda api: api.get("/saga-archive/999/files/F.xml", headers=KEY),
    lambda api: api.get("/saga-files/18547290/files/F.xml", headers=KEY),
    lambda api: api.get(f"/saga-files/{VALID_CUI}/files/F_nu-asteapta.xml", headers=KEY),
    lambda api: api.get(f"/saga-files/{VALID_CUI}/files/..%2F..%2Fefactura.db", headers=KEY),
])
def test_what_does_not_exist_is_404(api, call):
    assert call(api).status_code == 404


def test_a_waiting_file_is_read_over_the_api_as_it_is_in_the_clients_folder(api, service, anaf, cfg):
    downloaded(service, anaf, "A1", "A2")

    file = api.get(f"/saga-files/{VALID_CUI}/files/{name_of('A1')}", headers=KEY)

    assert file.status_code == 200
    assert file.content == (folder(cfg) / name_of("A1")).read_bytes()
    assert file.headers["content-type"].startswith("application/xml")
    assert api.get(f"/saga-files/{VALID_CUI}/files/{name_of('A1')}").status_code == 401


def test_the_routes_need_the_key(api):
    assert api.get("/saga-files").status_code == 401
    assert api.post(f"/saga-files/{VALID_CUI}/imported", json={}).status_code == 401


def test_the_archive_over_the_api(api, service, anaf, monkeypatch):
    downloaded(service, anaf, "A1")
    archive = service.confirm_saga_import(VALID_CUI)["archive"]
    shown = []
    monkeypatch.setattr(service_module, "_reveal", shown.append)

    listed = api.get("/saga-archive", headers=KEY, params={"cui": VALID_CUI}).json()["imports"]
    entry = api.get(f"/saga-archive/{archive['id']}", headers=KEY).json()["import"]
    file = api.get(f"/saga-archive/{archive['id']}/files/{name_of('A1')}", headers=KEY)
    opened = api.post(f"/saga-archive/{archive['id']}/open", headers=KEY)

    assert [item["id"] for item in listed] == [archive["id"]] and entry["invoices"][0]["id"] == "3001"
    assert file.status_code == 200 and file.content.startswith(b"<?xml")
    assert file.headers["content-type"].startswith("application/xml")
    assert f'filename="{name_of("A1")}"' in file.headers["content-disposition"]
    assert opened.status_code == 200 and [str(path) for path in shown] == [archive["folder"]]


# --- after the review ---------------------------------------------------------------------


def test_the_screen_state_says_a_missing_file_is_not_up_to_date(service, anaf, cfg):
    downloaded(service, anaf, "A1")
    assert service.invoices(cui=VALID_CUI)["saga"]["up_to_date"] is True

    (folder(cfg) / name_of("A1")).unlink()  # by hand, or a stick unplugged

    assert service.invoices(cui=VALID_CUI)["saga"]["up_to_date"] is False


def test_an_archive_that_cannot_be_written_says_so_and_marks_nothing(service, anaf, cfg, monkeypatch):
    downloaded(service, anaf, "A1")
    real_write = service_module._write_file

    def full(path, content):
        if "saga-archive" in str(path):
            raise OSError(28, "No space left on device")
        real_write(path, content)

    monkeypatch.setattr(service_module, "_write_file", full)

    with pytest.raises(EfacturaError) as refused:
        service.confirm_saga_import(VALID_CUI)

    assert refused.value.code == "saga_archive_error" and imported(service, "3001") == [False]
    assert files_in(cfg.data_dir / "saga-archive" / VALID_CUI) == [] and files_in(folder(cfg)) == [name_of("A1")]


def test_the_version_is_worked_out_only_where_it_is_sent_back(service, anaf):
    downloaded(service, anaf, "A1")

    assert service.invoices(cui=VALID_CUI, message_type="primita")["saga"]["version"] is not None
    assert "version" not in service.invoices(cui=VALID_CUI, message_type="trimisa")["saga"]
    assert "version" not in service.invoice_view("3001")["saga"]
