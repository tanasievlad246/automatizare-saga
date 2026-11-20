"""A client's folder for SAGA carries the client's name and its CUI, and follows the name:
renamed whole when it can be, file by file when it cannot, and never at the cost of a file."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree

import pytest

from efactura import auth, journal, service as service_module
from efactura.auth import Tokens
from efactura.config import load_config
from efactura.rules import Rule, Rulebook
from efactura.service import Service
from efactura.store import Store

from helpers import OTHER_VALID_CUI, VALID_CUI, FakeAnaf, FakeOpenRouter, line, rich_invoice_xml, set_rulebook

NOW = datetime(2026, 11, 11, 9, 30, tzinfo=timezone(timedelta(hours=2)))
LATER = NOW + timedelta(hours=1)

BOOK = Rulebook(
    accounts={"6022": "Combustibil.", "628": "Alte servicii."},
    rules=(Rule("combustibil", "6022", keywords=("motorina",)),),
    instructions="Alege contul facturii.",
)
FUEL = [line("Motorina Euro 5", "450.00", quantity="60", unit="LTR", price="7.50")]

ALFA = f"Alfa Construct SRL - {VALID_CUI}"
ALFA_GRUP = f"Alfa Grup SRL - {VALID_CUI}"


def name_of(number):
    return f"F_87654321_{number}_09.11.2026.xml"


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[anaf]\nclient_id = "my-client"\nclient_secret = "my-secret"\n'
        f"token_file = '{tmp_path / 'private' / 'tokens.json'}'\n"
        '[openrouter]\napi_key = "or-test-key"\n',
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
    return Service(cfg, http=anaf.client(), now=lambda: clock["now"])


def downloaded(service, anaf, *numbers, cui=VALID_CUI, first_id=3001):
    """Invoices with these numbers, downloaded and booked by the rule."""
    for position, number in enumerate(numbers):
        anaf.add(str(first_id + position), xml=rich_invoice_xml(lines=FUEL, number=number, customer_cui=cui), cui=cui)
    return service.sync(cui)["new"]


def files_in(folder_path) -> list[str]:
    return sorted(path.name for path in Path(folder_path).glob("*")) if Path(folder_path).exists() else []


def folders_in(cfg) -> list[str]:
    return sorted(path.name for path in cfg.saga_dir.iterdir() if path.is_dir()) if cfg.saga_dir.exists() else []


def numbers_in(path) -> list[str]:
    return [node.text for node in ElementTree.parse(path).getroot().iter("FacturaNumar")]


def state_of(service, cui=VALID_CUI):
    return service.invoices(cui=cui)["saga"]


def path_of(service, message_id="3001"):
    return service.invoice(message_id)["invoice"]["saga_xml_path"]


def ledger(cfg, cui=VALID_CUI):
    store = Store(cfg.db_path)
    try:
        return store.saga_ledger(cui)
    finally:
        store.close()


def put_on_the_list_as_an_earlier_version_did(cfg, name="Alfa Construct SRL", cui=VALID_CUI):
    """In the client list without the folder following: what a version before the named
    folders left behind."""
    store = Store(cfg.db_path)
    try:
        store.save_client(cui, name, NOW.isoformat())
    finally:
        store.close()


def at_the_next_start(cfg, anaf, clock):
    """The program as it starts: every client's files are brought up to date once."""
    started = Service(cfg, http=anaf.client(), now=lambda: clock["now"])
    started.write_saga_files()
    return started


def events_named(cfg, name):
    return [event for event in journal.events(cfg.db_path, details=True)["events"] if event["event"] == name]


def no_folder_can_be_renamed(monkeypatch):
    """As when SAGA holds a file of the folder open: Windows refuses to rename the folder."""

    def refuse(self, target):
        raise PermissionError("the folder is used by another program")

    monkeypatch.setattr(Path, "rename", refuse)


# --- the name -------------------------------------------------------------------------------


def test_a_clients_files_go_in_a_folder_with_its_name_and_its_cui(service, anaf, cfg):
    service.save_client(VALID_CUI, "Alfa Construct SRL")

    downloaded(service, anaf, "A1")

    assert folders_in(cfg) == [ALFA]
    assert files_in(cfg.saga_dir / ALFA) == [name_of("A1")]
    assert path_of(service) == str(cfg.saga_dir / ALFA / name_of("A1"))


def test_a_company_that_is_not_in_the_client_list_gets_a_folder_named_by_its_cui(service, anaf, cfg):
    downloaded(service, anaf, "A1")

    assert folders_in(cfg) == [VALID_CUI]


def test_a_name_windows_would_refuse_is_made_safe_for_the_folder(service, anaf, cfg):
    service.save_client(VALID_CUI, 'S.C. ALFA/BETA "Construct": Nord S.R.L.')

    downloaded(service, anaf, "A1")

    assert folders_in(cfg) == [f"S.C. ALFA-BETA Construct Nord S.R.L. - {VALID_CUI}"]


def test_each_client_has_its_own_named_folder(service, anaf, cfg):
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    service.save_client(OTHER_VALID_CUI, "Alfa Construct SRL")  # the same name: the CUI tells them apart

    downloaded(service, anaf, "A1")
    downloaded(service, anaf, "B1", cui=OTHER_VALID_CUI, first_id=4001)

    assert folders_in(cfg) == sorted([ALFA, f"Alfa Construct SRL - {OTHER_VALID_CUI}"])


def test_the_folder_named_after_a_download_is_the_clients_own(service, anaf, cfg):
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL, number="A1", customer_cui=VALID_CUI), cui=VALID_CUI)

    assert service.sync(VALID_CUI)["saga_folder"] == str(cfg.saga_dir / ALFA)


# --- a renamed client -------------------------------------------------------------------------


def test_renaming_a_client_moves_its_folder_with_everything_in_it(service, anaf, cfg, clock):
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    downloaded(service, anaf, "A1", "A2")
    by_hand = cfg.saga_dir / ALFA / "note.txt"
    by_hand.write_text("de verificat cu clientul", encoding="utf-8")
    clock["now"] = LATER

    service.save_client(VALID_CUI, "Alfa Grup SRL")

    assert folders_in(cfg) == [ALFA_GRUP]
    assert files_in(cfg.saga_dir / ALFA_GRUP) == sorted([name_of("A1"), "note.txt"])
    assert numbers_in(cfg.saga_dir / ALFA_GRUP / name_of("A1")) == ["A1", "A2"]


def test_the_files_on_record_follow_a_renamed_folder(service, anaf, cfg, clock):
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    downloaded(service, anaf, "A1", "A2")
    clock["now"] = LATER

    service.save_client(VALID_CUI, "Alfa Grup SRL")

    moved = cfg.saga_dir / ALFA_GRUP / name_of("A1")
    assert path_of(service, "3001") == path_of(service, "3002") == str(moved)
    # Moved, not written again: it keeps the time it was written at.
    assert ledger(cfg) == {moved.relative_to(cfg.data_dir).as_posix(): NOW.isoformat()}
    state = state_of(service)
    assert (state["up_to_date"], state["problem"], state["written_at"]) == (True, None, NOW.isoformat())


def test_an_import_is_confirmed_from_the_folder_a_rename_moved_the_files_to(service, anaf, cfg):
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    downloaded(service, anaf, "A1")
    version = service.saga_files(VALID_CUI)["version"]

    service.save_client(VALID_CUI, "Alfa Grup SRL")
    waiting = service.saga_files(VALID_CUI)

    assert waiting["version"] == version  # the same file, in another place
    assert waiting["files"][0]["path"] == str(cfg.saga_dir / ALFA_GRUP / name_of("A1"))
    assert service.confirm_saga_import(VALID_CUI, version=version)["archive"]["invoices"] == 1
    assert files_in(cfg.saga_dir / ALFA_GRUP) == []


def test_renaming_a_client_with_nothing_waiting_moves_its_empty_folder_too(service, anaf, cfg):
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    downloaded(service, anaf, "A1")
    service.mark_uploaded(["3001"])

    service.save_client(VALID_CUI, "Alfa Grup SRL")

    assert folders_in(cfg) == [ALFA_GRUP]


def test_renaming_a_client_that_never_had_a_file_makes_no_folder(service, cfg):
    service.save_client(VALID_CUI, "Alfa Construct SRL")

    service.save_client(VALID_CUI, "Alfa Grup SRL")

    assert folders_in(cfg) == []


def test_a_new_name_from_an_imported_client_list_moves_the_folder(service, anaf, cfg):
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    downloaded(service, anaf, "A1")

    service.import_clients("clienti.csv", f"nume;cui\nAlfa Grup SRL;{VALID_CUI}\n".encode())

    assert folders_in(cfg) == [ALFA_GRUP]
    assert path_of(service) == str(cfg.saga_dir / ALFA_GRUP / name_of("A1"))


def test_a_name_that_changes_only_in_capital_letters_renames_the_folder(service, anaf, cfg):
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    downloaded(service, anaf, "A1")

    service.save_client(VALID_CUI, "ALFA CONSTRUCT SRL")

    assert folders_in(cfg) == [f"ALFA CONSTRUCT SRL - {VALID_CUI}"]
    assert files_in(cfg.saga_dir / f"ALFA CONSTRUCT SRL - {VALID_CUI}") == [name_of("A1")]
    assert state_of(service)["up_to_date"] is True


def test_a_folder_already_renamed_by_hand_is_taken_as_it_is(service, anaf, cfg, clock):
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    downloaded(service, anaf, "A1")
    (cfg.saga_dir / ALFA).rename(cfg.saga_dir / ALFA_GRUP)  # in Explorer, before the client was renamed here
    clock["now"] = LATER

    service.save_client(VALID_CUI, "Alfa Grup SRL")

    moved = cfg.saga_dir / ALFA_GRUP / name_of("A1")
    assert folders_in(cfg) == [ALFA_GRUP]
    assert path_of(service) == str(moved)
    assert list(ledger(cfg)) == [moved.relative_to(cfg.data_dir).as_posix()]  # known in its new place only
    state = state_of(service)
    assert (state["up_to_date"], state["problem"], bool(state["written_at"])) == (True, None, True)


def test_a_move_is_written_in_the_journal(service, anaf, cfg):
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    downloaded(service, anaf, "A1")

    service.save_client(VALID_CUI, "Alfa Grup SRL")

    (moved,) = events_named(cfg, "saga.folder_moved")
    assert (moved["data"]["cui"], moved["data"]["old"], moved["data"]["new"]) == (VALID_CUI, ALFA, ALFA_GRUP)


# --- a client taken off the list ----------------------------------------------------------------


def test_a_client_taken_off_the_list_keeps_its_folder(service, anaf, cfg):
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    downloaded(service, anaf, "A1")

    service.remove_client(VALID_CUI)
    service.set_cont("3001", "628")  # its file is written again

    assert folders_in(cfg) == [ALFA]
    assert path_of(service) == str(cfg.saga_dir / ALFA / name_of("A1"))


def test_a_client_taken_off_the_list_keeps_its_folder_also_once_it_was_emptied(service, anaf, cfg):
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    downloaded(service, anaf, "A1")
    service.remove_client(VALID_CUI)
    service.mark_uploaded(["3001"])

    service.mark_uploaded(["3001"], undo=True)  # it waits again

    assert folders_in(cfg) == [ALFA]
    assert files_in(cfg.saga_dir / ALFA) == [name_of("A1")]


# --- folders named by the CUI alone, from earlier versions --------------------------------------


def test_a_folder_named_by_cui_is_renamed_at_the_next_start_with_everything_in_it(service, anaf, cfg, clock):
    downloaded(service, anaf, "A1")
    (cfg.saga_dir / VALID_CUI / "pus de mana.xml").write_text("<Facturi/>", encoding="utf-8")
    put_on_the_list_as_an_earlier_version_did(cfg)
    clock["now"] = LATER

    started = at_the_next_start(cfg, anaf, clock)

    assert folders_in(cfg) == [ALFA]
    assert files_in(cfg.saga_dir / ALFA) == sorted([name_of("A1"), "pus de mana.xml"])
    assert path_of(started) == str(cfg.saga_dir / ALFA / name_of("A1"))
    state = state_of(started)
    assert (state["up_to_date"], state["problem"], state["written_at"]) == (True, None, NOW.isoformat())


def test_an_empty_folder_named_by_cui_is_renamed_at_the_next_start_too(service, anaf, cfg, clock):
    downloaded(service, anaf, "A1")
    service.mark_uploaded(["3001"])  # nothing waits: the folder is there, empty
    put_on_the_list_as_an_earlier_version_did(cfg)

    at_the_next_start(cfg, anaf, clock)

    assert folders_in(cfg) == [ALFA]


def test_the_folders_are_moved_once_and_a_second_start_changes_nothing(service, anaf, cfg, clock):
    downloaded(service, anaf, "A1")
    put_on_the_list_as_an_earlier_version_did(cfg)
    at_the_next_start(cfg, anaf, clock)

    at_the_next_start(cfg, anaf, clock)

    assert folders_in(cfg) == [ALFA]
    assert len(events_named(cfg, "saga.folder_moved")) == 1


def test_a_file_per_invoice_moves_with_its_folder_as_well(service, anaf, cfg, clock):
    service.set_saga_output(per="invoice")
    downloaded(service, anaf, "A1", "A2")
    put_on_the_list_as_an_earlier_version_did(cfg)

    started = at_the_next_start(cfg, anaf, clock)

    assert files_in(cfg.saga_dir / ALFA) == [name_of("A1"), name_of("A2")]
    assert path_of(started, "3002") == str(cfg.saga_dir / ALFA / name_of("A2"))


# --- a folder that cannot be renamed -----------------------------------------------------------


def test_a_folder_that_cannot_be_renamed_is_moved_file_by_file(service, anaf, cfg, monkeypatch):
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    downloaded(service, anaf, "A1")
    no_folder_can_be_renamed(monkeypatch)

    service.save_client(VALID_CUI, "Alfa Grup SRL")

    assert folders_in(cfg) == [ALFA_GRUP]  # the old folder went once it was empty
    assert files_in(cfg.saga_dir / ALFA_GRUP) == [name_of("A1")]
    assert path_of(service) == str(cfg.saga_dir / ALFA_GRUP / name_of("A1"))
    assert state_of(service)["problem"] is None


def test_a_file_the_program_did_not_write_is_never_deleted_with_the_old_folder(service, anaf, cfg, monkeypatch):
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    downloaded(service, anaf, "A1")
    (cfg.saga_dir / ALFA / "pus de mana.xml").write_text("<Facturi/>", encoding="utf-8")
    no_folder_can_be_renamed(monkeypatch)

    service.save_client(VALID_CUI, "Alfa Grup SRL")

    assert files_in(cfg.saga_dir / ALFA) == ["pus de mana.xml"]
    assert files_in(cfg.saga_dir / ALFA_GRUP) == [name_of("A1")]
    assert state_of(service)["problem"] is None  # the program's own files are where they should be
    (left,) = events_named(cfg, "saga.folder_left")
    assert (left["data"]["cui"], left["data"]["old"], left["data"]["new"]) == (VALID_CUI, ALFA, ALFA_GRUP)


def test_an_old_folder_left_with_someone_elses_file_is_said_once(service, anaf, cfg, monkeypatch):
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    downloaded(service, anaf, "A1")
    (cfg.saga_dir / ALFA / "pus de mana.xml").write_text("<Facturi/>", encoding="utf-8")
    no_folder_can_be_renamed(monkeypatch)
    service.save_client(VALID_CUI, "Alfa Grup SRL")

    downloaded(service, anaf, "A2", first_id=3002)
    service.write_saga_files()

    assert len(events_named(cfg, "saga.folder_left")) == 1
    assert files_in(cfg.saga_dir / ALFA) == ["pus de mana.xml"]


def test_a_file_held_open_keeps_the_move_unfinished_until_it_can_be_removed(service, anaf, cfg, monkeypatch):
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    downloaded(service, anaf, "A1")
    real_unlink = Path.unlink

    def held_open(self, missing_ok=False):
        if self.parent.name == ALFA:
            raise PermissionError("the file is open in another program")
        real_unlink(self, missing_ok=missing_ok)

    with monkeypatch.context() as saga_has_it_open:
        no_folder_can_be_renamed(saga_has_it_open)
        saga_has_it_open.setattr(Path, "unlink", held_open)

        service.save_client(VALID_CUI, "Alfa Grup SRL")  # the rename itself is never refused

        assert files_in(cfg.saga_dir / ALFA) == [name_of("A1")]  # not lost
        assert files_in(cfg.saga_dir / ALFA_GRUP) == [name_of("A1")]  # and already in its new place
        assert "open in another program" in state_of(service)["problem"]["message"]

    service.write_saga_files(VALID_CUI)

    assert folders_in(cfg) == [ALFA_GRUP]
    assert state_of(service)["problem"] is None


# --- the folder for SAGA away: a stick taken out, a share that does not answer ---------------------


def test_nothing_is_lost_when_a_client_is_renamed_while_the_folder_for_saga_is_away(service, anaf, cfg, tmp_path):
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    downloaded(service, anaf, "A1")
    before = ledger(cfg)
    cfg.saga_dir.rename(tmp_path / "the share, not answering")

    clients = service.save_client(VALID_CUI, "Alfa Grup SRL")  # the program keeps working

    assert [client["name"] for client in clients["clients"]] == ["Alfa Grup SRL"]
    assert state_of(service)["problem"] is not None
    assert ledger(cfg) == before  # the file is still known where it is
    assert files_in(tmp_path / "the share, not answering" / ALFA) == [name_of("A1")]


def test_the_move_is_made_once_the_folder_for_saga_is_back(service, anaf, cfg, tmp_path):
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    downloaded(service, anaf, "A1")
    cfg.saga_dir.rename(tmp_path / "the share, not answering")
    service.save_client(VALID_CUI, "Alfa Grup SRL")
    (tmp_path / "the share, not answering").rename(cfg.saga_dir)

    service.write_saga_files(VALID_CUI)

    assert folders_in(cfg) == [ALFA_GRUP]
    assert files_in(cfg.saga_dir / ALFA_GRUP) == [name_of("A1")]
    assert state_of(service)["problem"] is None


def test_an_empty_folder_is_still_moved_after_a_rename_made_while_the_folder_for_saga_was_away(
    service, anaf, cfg, tmp_path,
):
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    downloaded(service, anaf, "A1")
    service.mark_uploaded(["3001"])  # nothing waits, so nothing on record says where the folder is
    cfg.saga_dir.rename(tmp_path / "the share, not answering")
    service.save_client(VALID_CUI, "Alfa Grup SRL")
    (tmp_path / "the share, not answering").rename(cfg.saga_dir)

    service.write_saga_files()

    assert folders_in(cfg) == [ALFA_GRUP]


# --- the folder as it is set now ------------------------------------------------------------------


def test_opening_a_clients_folder_finds_it_by_cui(service, anaf, cfg, monkeypatch):
    shown = []
    monkeypatch.setattr(service_module, "_reveal", shown.append)
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    downloaded(service, anaf, "A1")

    assert service.open_saga_folder(cui=VALID_CUI)["folder"] == str(cfg.saga_dir / ALFA)
    assert shown == [cfg.saga_dir / ALFA]


def test_opening_a_clients_folder_uses_the_folder_for_saga_as_it_is_set_now(service, anaf, cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(service_module, "_reveal", lambda folder: None)
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    # Another part of the program changes the folder after this Service was made.
    Service(cfg, http=anaf.client(), now=lambda: NOW).set_saga_output(folder=str(tmp_path / "nou"))

    assert service.open_saga_folder(cui=VALID_CUI)["folder"] == str(tmp_path / "nou" / ALFA)
    assert service.open_saga_folder()["folder"] == str(tmp_path / "nou")


def test_a_download_names_the_folder_its_files_were_written_to(service, anaf, cfg, tmp_path):
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    Service(cfg, http=anaf.client(), now=lambda: NOW).set_saga_output(folder=str(tmp_path / "nou"))
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL, number="A1", customer_cui=VALID_CUI), cui=VALID_CUI)

    result = service.sync(VALID_CUI)  # `service` was made while the old folder was set

    assert result["saga_folder"] == str(tmp_path / "nou" / ALFA)
    assert files_in(tmp_path / "nou" / ALFA) == [name_of("A1")]


def test_the_folder_dialog_starts_at_the_folder_for_saga_as_it_is_set_now(service, anaf, cfg, tmp_path, monkeypatch):
    asked = []
    monkeypatch.setattr(service_module, "_ask_for_folder", lambda start, title: asked.append(start))
    Service(cfg, http=anaf.client(), now=lambda: NOW).set_saga_output(folder=str(tmp_path / "nou"))

    service.choose_folder("saga")

    assert asked == [str(tmp_path / "nou")]


# --- what waits, for the screen and the automation ------------------------------------------------


def test_what_waits_for_saga_names_the_clients_folder_and_when_each_file_was_written(service, anaf, cfg, clock):
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    downloaded(service, anaf, "A1")
    clock["now"] = LATER
    downloaded(service, anaf, "A2", first_id=3002)

    waiting = service.saga_files(VALID_CUI)

    assert waiting["folder"] == str(cfg.saga_dir / ALFA)
    (file,) = waiting["files"]
    assert (file["name"], file["written_at"], file["present"]) == (name_of("A1"), LATER.isoformat(), True)


def test_a_file_gone_from_the_folder_is_said_to_be_missing(service, anaf, cfg):
    downloaded(service, anaf, "A1")
    (cfg.saga_dir / VALID_CUI / name_of("A1")).unlink()

    (file,) = service.saga_files(VALID_CUI)["files"]

    assert file["present"] is False


def test_one_waiting_file_is_read_as_it_is_in_the_folder(service, anaf, cfg):
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    downloaded(service, anaf, "A1", "A2")

    path = service.saga_file(VALID_CUI, name_of("A1"))

    assert path == cfg.saga_dir / ALFA / name_of("A1")
    assert numbers_in(path) == ["A1", "A2"]


@pytest.mark.parametrize("name", ["../config.toml", "pus de mana.xml", "F_87654321_A9_09.11.2026.xml", ""])
def test_only_the_files_the_program_wrote_for_the_client_are_read(service, anaf, cfg, name):
    downloaded(service, anaf, "A1")
    (cfg.saga_dir / VALID_CUI / "pus de mana.xml").write_text("<Facturi/>", encoding="utf-8")

    with pytest.raises(service_module.EfacturaError) as refused:
        service.saga_file(VALID_CUI, name)

    assert refused.value.code == "not_found"


def test_a_waiting_file_that_is_gone_from_the_folder_is_not_found(service, anaf, cfg):
    downloaded(service, anaf, "A1")
    (cfg.saga_dir / VALID_CUI / name_of("A1")).unlink()

    with pytest.raises(service_module.EfacturaError) as refused:
        service.saga_file(VALID_CUI, name_of("A1"))

    assert refused.value.code == "not_found"
