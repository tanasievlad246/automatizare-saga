"""The files for SAGA: a client's folder holds exactly the invoices SAGA has not got yet,
in one file per client or in one file per invoice."""

import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree

import pytest

from efactura import auth, service as service_module
from efactura.auth import Tokens
from efactura.config import load_config
from efactura.errors import EfacturaError
from efactura.rules import Rule, Rulebook
from efactura.service import Service
from efactura.store import Store

from helpers import OTHER_VALID_CUI, VALID_CUI, FakeAnaf, FakeOpenRouter, line, rich_invoice_xml, set_rulebook

NOW = datetime(2026, 11, 11, 9, 30, tzinfo=timezone(timedelta(hours=2)))
LATER = NOW + timedelta(hours=1)

BOOK = Rulebook(
    accounts={"6022": "Combustibil.", "626": "Telefonie si internet.", "628": "Alte servicii."},
    rules=(Rule("combustibil", "6022", keywords=("motorina",)),),
    instructions="Alege contul facturii.",
)
FUEL = [line("Motorina Euro 5", "450.00", quantity="60", unit="LTR", price="7.50")]
PARTS = [line("Piese de schimb", "900.00")]


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
def openrouter():
    return FakeOpenRouter()


@pytest.fixture
def anaf(openrouter):
    fake = FakeAnaf()
    fake.openrouter = openrouter
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


def add(anaf, message_id, number, lines=FUEL, cui=VALID_CUI):
    anaf.add(message_id, xml=rich_invoice_xml(lines=lines, number=number, customer_cui=cui), cui=cui)


def downloaded(service, anaf, *numbers, cui=VALID_CUI, first_id=3001):
    """Invoices with these numbers, downloaded and booked by the rule."""
    for position, number in enumerate(numbers):
        add(anaf, str(first_id + position), number, cui=cui)
    return service.sync(cui)["new"]


def folder(cfg, cui=VALID_CUI) -> Path:
    return cfg.saga_dir / cui


def files_in(folder_path) -> list[str]:
    return sorted(path.name for path in Path(folder_path).glob("*")) if Path(folder_path).exists() else []


def numbers_in(path) -> list[str]:
    return [node.text for node in ElementTree.parse(path).getroot().iter("FacturaNumar")]


def conts_in(path) -> list[str]:
    return [node.text for node in ElementTree.parse(path).getroot().iter("Cont")]


def saved(cfg, message_id):
    store = Store(cfg.db_path)
    try:
        return store.get_message(message_id)
    finally:
        store.close()


def state_of(service, cui=VALID_CUI):
    return service.invoices(cui=cui)["saga"]


def refuse_to_write(monkeypatch, reason="folder is read-only"):
    """No file for SAGA can be written; ANAF's own files are saved as usual."""
    real_write = service_module._write_file

    def refuse(path, content):
        if "SAGA Import" in str(path):
            raise PermissionError(reason)
        real_write(path, content)

    monkeypatch.setattr(service_module, "_write_file", refuse)


# --- one file per client ------------------------------------------------------------------


def test_a_clients_waiting_invoices_share_one_file_named_after_the_first(service, anaf, cfg):
    new = downloaded(service, anaf, "A1", "A2", "A3")

    assert files_in(folder(cfg)) == [name_of("A1")]
    assert numbers_in(folder(cfg) / name_of("A1")) == ["A1", "A2", "A3"]
    assert {entry["saga_xml_path"] for entry in new} == {str(folder(cfg) / name_of("A1"))}


def test_an_invoice_downloaded_later_joins_the_file(service, anaf, cfg):
    downloaded(service, anaf, "A1")

    (later,) = downloaded(service, anaf, "A2", first_id=3002)

    assert files_in(folder(cfg)) == [name_of("A1")]
    assert numbers_in(folder(cfg) / name_of("A1")) == ["A1", "A2"]
    assert later["saga_xml_path"] == str(folder(cfg) / name_of("A1"))


def test_each_client_has_its_own_file(service, anaf, cfg):
    downloaded(service, anaf, "A1")
    downloaded(service, anaf, "B1", cui=OTHER_VALID_CUI, first_id=4001)

    assert files_in(folder(cfg)) == [name_of("A1")]
    assert files_in(folder(cfg, OTHER_VALID_CUI)) == [name_of("B1")]
    assert numbers_in(folder(cfg, OTHER_VALID_CUI) / name_of("B1")) == ["B1"]


def test_marking_as_imported_takes_the_invoice_out_of_the_file(service, anaf, cfg):
    downloaded(service, anaf, "A1", "A2")

    service.mark_uploaded(["3001"])

    # The file is named after its first invoice, so it has a new name now.
    assert files_in(folder(cfg)) == [name_of("A2")]
    assert numbers_in(folder(cfg) / name_of("A2")) == ["A2"]
    assert saved(cfg, "3001")["saga_xml_path"] is None
    assert saved(cfg, "3002")["saga_xml_path"] == f"SAGA Import/{VALID_CUI}/{name_of('A2')}"


def test_no_file_is_left_once_everything_is_imported(service, anaf, cfg):
    downloaded(service, anaf, "A1", "A2")

    service.mark_uploaded(["3001", "3002"])

    assert files_in(folder(cfg)) == []


def test_taking_the_imported_mark_off_puts_the_invoice_back(service, anaf, cfg):
    downloaded(service, anaf, "A1", "A2")
    service.mark_uploaded(["3001", "3002"])

    service.mark_uploaded(["3002"], undo=True)

    assert files_in(folder(cfg)) == [name_of("A2")]
    assert numbers_in(folder(cfg) / name_of("A2")) == ["A2"]


def test_a_changed_account_is_changed_in_the_file(service, anaf, cfg):
    downloaded(service, anaf, "A1", "A2")

    changed = service.set_cont("3002", cont="626")["invoice"]

    assert conts_in(folder(cfg) / name_of("A1")) == ["6022", "626"]
    assert changed["saga_xml_path"] == str(folder(cfg) / name_of("A1"))


def test_an_invoice_that_goes_back_to_checking_leaves_the_file(service, anaf, cfg, openrouter):
    add(anaf, "3001", "A1")
    add(anaf, "3002", "A2", lines=PARTS)
    openrouter.answer_for("piese", "628")
    service.sync(VALID_CUI)
    openrouter.answer_for("piese", "628", confidence=0.41)

    again = service.classify("3002", force=True)["invoice"]

    assert (again["classification_status"], again["saga_xml_path"]) == ("review", None)
    assert numbers_in(folder(cfg) / name_of("A1")) == ["A1"]


def test_an_invoice_given_its_account_by_a_person_joins_the_file(service, anaf, cfg, openrouter):
    add(anaf, "3001", "A1")
    add(anaf, "3002", "A2", lines=PARTS)
    openrouter.answer_for("piese", "628", confidence=0.41)
    service.sync(VALID_CUI)  # A2 waits for a person

    decided = service.set_cont("3002", cont="628")["invoice"]

    assert numbers_in(folder(cfg) / name_of("A1")) == ["A1", "A2"]
    assert decided["saga_xml_path"] == str(folder(cfg) / name_of("A1"))


# --- one file per invoice, and the choice between the two ---------------------------------


def test_one_file_per_client_is_the_way_until_another_is_chosen(service):
    assert service.app_settings()["saga_file_per"] == "client"


def test_one_file_per_invoice_when_that_is_chosen(service, anaf, cfg):
    chosen = service.set_saga_output(per="invoice")

    new = downloaded(service, anaf, "A1", "A2")

    assert chosen["saga_file_per"] == "invoice"
    assert files_in(folder(cfg)) == [name_of("A1"), name_of("A2")]
    assert [entry["saga_xml_path"] for entry in new] == [
        str(folder(cfg) / name_of("A1")), str(folder(cfg) / name_of("A2"))
    ]


def test_with_one_file_per_invoice_an_imported_invoices_file_goes_too(service, anaf, cfg):
    service.set_saga_output(per="invoice")
    downloaded(service, anaf, "A1", "A2")

    service.mark_uploaded(["3001"])

    assert files_in(folder(cfg)) == [name_of("A2")]


def test_choosing_the_other_way_rewrites_what_is_waiting_for_every_client(service, anaf, cfg):
    downloaded(service, anaf, "A1", "A2")
    downloaded(service, anaf, "B1", "B2", cui=OTHER_VALID_CUI, first_id=4001)

    service.set_saga_output(per="invoice")

    assert files_in(folder(cfg)) == [name_of("A1"), name_of("A2")]
    assert files_in(folder(cfg, OTHER_VALID_CUI)) == [name_of("B1"), name_of("B2")]
    assert numbers_in(folder(cfg) / name_of("A1")) == ["A1"]  # no longer the file of both

    service.set_saga_output(per="client")

    assert files_in(folder(cfg)) == [name_of("A1")]
    assert numbers_in(folder(cfg) / name_of("A1")) == ["A1", "A2"]
    assert files_in(folder(cfg, OTHER_VALID_CUI)) == [name_of("B1")]


@pytest.mark.parametrize("per", ["both", "", None, "CLIENT", "per_client", 1])
def test_only_one_of_the_two_ways_can_be_chosen(service, per):
    with pytest.raises(EfacturaError) as refused:
        service.set_saga_output(per=per)

    assert refused.value.code == "invalid_input"
    assert service.app_settings()["saga_file_per"] == "client"


def test_the_choice_is_kept_for_the_next_start(service, cfg, anaf):
    service.set_saga_output(per="invoice")

    again = Service(cfg, http=anaf.client(), now=lambda: NOW)

    assert again.app_settings()["saga_file_per"] == "invoice"


# --- the folder ---------------------------------------------------------------------------


def test_changing_the_folder_moves_what_is_waiting(service, anaf, cfg, tmp_path):
    downloaded(service, anaf, "A1", "A2")
    old, new = folder(cfg), tmp_path / "pentru saga" / VALID_CUI

    service.set_saga_output(folder=str(tmp_path / "pentru saga"))

    assert files_in(old) == []
    assert numbers_in(new / name_of("A1")) == ["A1", "A2"]
    assert service.invoice("3001")["invoice"]["saga_xml_path"] == str(new / name_of("A1"))


def test_a_file_put_in_the_folder_by_hand_is_never_touched(service, anaf, cfg):
    downloaded(service, anaf, "A1")
    by_hand = folder(cfg) / "F_99999999_manual_01.11.2026.xml"
    by_hand.write_text("<Facturi/>", encoding="utf-8")

    service.mark_uploaded(["3001"])

    assert files_in(folder(cfg)) == [by_hand.name]


# --- coming from a version that wrote one file per invoice and kept them --------------------


def earlier_version(cfg, service, anaf, *numbers, imported=()):
    """What an earlier version left behind: a file per invoice, kept after the import, each
    path remembered only by its invoice. Returns the program as it starts after the update."""
    service.set_saga_output(per="invoice")
    downloaded(service, anaf, *numbers)
    store = Store(cfg.db_path)
    store.set_uploaded(list(imported), True, NOW.isoformat())
    store._conn.execute("DELETE FROM saga_files")
    store._conn.execute("DELETE FROM settings WHERE key = 'saga_file_per'")
    store._conn.commit()
    store.close()
    return Service(cfg, http=anaf.client(), now=lambda: NOW)


def test_files_left_by_an_earlier_version_give_way_to_the_clients_file(service, anaf, cfg):
    updated = earlier_version(cfg, service, anaf, "A1", "A2", "A3", imported=("3003",))
    assert files_in(folder(cfg)) == [name_of("A1"), name_of("A2"), name_of("A3")]

    result = updated.write_saga_files()

    assert result == {"ok": True, "clients": 1, "problems": []}
    assert files_in(folder(cfg)) == [name_of("A1")]
    assert numbers_in(folder(cfg) / name_of("A1")) == ["A1", "A2"]
    assert saved(cfg, "3003")["saga_xml_path"] is None


def test_an_earlier_versions_client_with_everything_imported_has_its_folder_emptied(service, anaf, cfg):
    updated = earlier_version(cfg, service, anaf, "A1", "A2", imported=("3001", "3002"))
    assert files_in(folder(cfg)) == [name_of("A1"), name_of("A2")]

    result = updated.write_saga_files()

    assert result == {"ok": True, "clients": 1, "problems": []}
    assert files_in(folder(cfg)) == []


def test_an_earlier_versions_files_are_still_known_when_their_removal_was_cut_short(
    service, anaf, cfg, monkeypatch
):
    updated = earlier_version(cfg, service, anaf, "A1", "A2", imported=("3001", "3002"))

    def cut(self, missing_ok=False):
        raise RuntimeError("the PC was switched off")

    with monkeypatch.context() as broken:
        broken.setattr(Path, "unlink", cut)
        updated.write_saga_files()

    Service(cfg, http=anaf.client(), now=lambda: NOW).write_saga_files()  # the next start

    assert files_in(folder(cfg)) == []


# --- when a file cannot be written or removed ----------------------------------------------


def test_a_file_that_cannot_be_written_is_a_problem_to_show_not_a_lost_decision(
    service, anaf, cfg, monkeypatch
):
    refuse_to_write(monkeypatch)

    (entry,) = downloaded(service, anaf, "A1")

    assert (entry["classification_status"], entry["cont"]) == ("classified", "6022")
    assert entry["saga_xml_path"] is None
    assert files_in(folder(cfg)) == []
    problem = state_of(service)["problem"]
    assert "read-only" in problem["message"] and problem["at"] == NOW.isoformat()


def test_writing_again_brings_the_file_up_to_date_and_clears_the_problem(
    service, anaf, cfg, monkeypatch
):
    with monkeypatch.context() as broken:
        refuse_to_write(broken)
        downloaded(service, anaf, "A1")

    result = service.write_saga_files(VALID_CUI)

    assert result == {"ok": True, "clients": 1, "problems": []}
    assert numbers_in(folder(cfg) / name_of("A1")) == ["A1"]
    assert state_of(service)["problem"] is None
    assert saved(cfg, "3001")["saga_xml_path"] == f"SAGA Import/{VALID_CUI}/{name_of('A1')}"


def test_writing_again_says_which_clients_still_have_a_problem(service, anaf, monkeypatch):
    refuse_to_write(monkeypatch, "the file is open in another program")
    downloaded(service, anaf, "A1")

    result = service.write_saga_files()

    assert result["clients"] == 1
    (problem,) = result["problems"]
    assert problem["cui"] == VALID_CUI and "open in another program" in problem["message"]


def test_the_next_change_tries_again_by_itself(service, anaf, cfg, monkeypatch):
    with monkeypatch.context() as broken:
        refuse_to_write(broken)
        downloaded(service, anaf, "A1")

    downloaded(service, anaf, "A2", first_id=3002)

    assert numbers_in(folder(cfg) / name_of("A1")) == ["A1", "A2"]
    assert state_of(service)["problem"] is None


def test_an_old_file_that_cannot_be_removed_is_remembered_and_removed_later(
    service, anaf, cfg, monkeypatch
):
    downloaded(service, anaf, "A1", "A2")
    real_unlink = Path.unlink

    def held_open(self, missing_ok=False):
        if self.name == name_of("A1"):
            raise PermissionError("the file is open in another program")
        real_unlink(self, missing_ok=missing_ok)

    with monkeypatch.context() as broken:
        broken.setattr(Path, "unlink", held_open)
        service.mark_uploaded(["3001"])

        assert files_in(folder(cfg)) == [name_of("A1"), name_of("A2")]
        assert "open in another program" in state_of(service)["problem"]["message"]
        assert numbers_in(folder(cfg) / name_of("A2")) == ["A2"]  # the new file is in place

    service.write_saga_files(VALID_CUI)

    assert files_in(folder(cfg)) == [name_of("A2")]
    assert state_of(service)["problem"] is None


def test_a_file_that_already_says_the_same_is_not_written_again(service, anaf, cfg, clock, monkeypatch):
    downloaded(service, anaf, "A1")
    clock["now"] = LATER
    written = []
    monkeypatch.setattr(service_module, "_write_file", lambda path, content: written.append(path))

    service.write_saga_files()

    assert written == []
    assert state_of(service)["written_at"] == NOW.isoformat()


def test_a_problem_never_fails_the_action_that_met_it(service, anaf, cfg, monkeypatch):
    downloaded(service, anaf, "A1", "A2")
    refuse_to_write(monkeypatch)

    changed = service.set_cont("3001", cont="626")
    marked = service.mark_uploaded(["3002"])

    assert changed["invoice"]["cont"] == "626" and marked["ok"] is True
    assert state_of(service)["problem"] is not None
    assert conts_in(folder(cfg) / name_of("A1")) == ["6022", "6022"]  # the file as it was last written


# --- what the screens are told -------------------------------------------------------------


def test_a_clients_invoice_list_says_how_its_files_stand(service, anaf, cfg, clock):
    downloaded(service, anaf, "A1")
    clock["now"] = LATER
    downloaded(service, anaf, "A2", first_id=3002)

    assert state_of(service) == {"file_per": "client", "written_at": LATER.isoformat(), "problem": None}
    assert "saga" not in service.invoices()  # only when one client is asked for


def test_an_invoice_is_shown_its_own_part_for_saga_also_after_it_was_imported(service, anaf):
    downloaded(service, anaf, "A1", "A2")
    service.mark_uploaded(["3002"])

    shown = service.invoice_view("3002")["saga_xml"]

    assert "<FacturaNumar>A2</FacturaNumar>" in shown and "<FacturaNumar>A1</FacturaNumar>" not in shown
    assert shown.count("<Factura>") == 1


def test_bringing_every_client_up_to_date_counts_them(service, anaf):
    downloaded(service, anaf, "A1")
    downloaded(service, anaf, "B1", cui=OTHER_VALID_CUI, first_id=4001)

    assert service.write_saga_files() == {"ok": True, "clients": 2, "problems": []}


def test_an_invoices_own_screen_is_told_when_its_clients_files_are_not_up_to_date(service, anaf, monkeypatch):
    downloaded(service, anaf, "A1")
    assert service.invoice_view("3001")["saga"]["problem"] is None
    refuse_to_write(monkeypatch)

    service.set_cont("3001", cont="626")

    assert "read-only" in service.invoice_view("3001")["saga"]["problem"]["message"]


# --- more than a file can go wrong -----------------------------------------------------------


def test_an_error_that_is_not_about_a_file_is_a_problem_too_and_never_fails_the_action(
    service, anaf, monkeypatch
):
    downloaded(service, anaf, "A1", "A2")

    def locked(self, cui, placed, when):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(Store, "place_in_saga_files", locked)

    marked = service.mark_uploaded(["3001"])

    assert marked["ok"] is True
    assert "database is locked" in state_of(service)["problem"]["message"]


def test_one_clients_failure_does_not_keep_the_others_from_being_brought_up_to_date(
    service, anaf, cfg, monkeypatch
):
    downloaded(service, anaf, "A1", "A2")
    downloaded(service, anaf, "B1", "B2", cui=OTHER_VALID_CUI, first_id=4001)
    real = Service._place_saga_files

    def fails_for_the_first(self, store, cui, when):
        if cui == VALID_CUI:
            raise RuntimeError("something unforeseen")
        real(self, store, cui, when)

    monkeypatch.setattr(Service, "_place_saga_files", fails_for_the_first)

    result = service.set_saga_output(per="invoice")

    assert [problem["cui"] for problem in result["problems"]] == [VALID_CUI]
    assert files_in(folder(cfg, OTHER_VALID_CUI)) == [name_of("B1"), name_of("B2")]


def test_with_a_file_each_one_that_cannot_be_written_is_shown_and_writing_again_repairs_it(
    service, anaf, cfg, monkeypatch
):
    service.set_saga_output(per="invoice")
    real_write = service_module._write_file

    def refuse_the_second(path, content):
        if path.name == name_of("A2"):
            raise PermissionError("the file is open in another program")
        real_write(path, content)

    with monkeypatch.context() as broken:
        broken.setattr(service_module, "_write_file", refuse_the_second)
        downloaded(service, anaf, "A1", "A2")
        assert state_of(service)["problem"] is not None

    service.write_saga_files(VALID_CUI)

    assert files_in(folder(cfg)) == [name_of("A1"), name_of("A2")]
    assert state_of(service)["problem"] is None


def test_an_attempt_that_failed_does_not_change_when_the_file_was_written(
    service, anaf, clock, monkeypatch
):
    downloaded(service, anaf, "A1")
    clock["now"] = LATER
    with monkeypatch.context() as broken:
        refuse_to_write(broken)
        service.set_cont("3001", cont="626")

    service.set_cont("3001", cont="6022")  # back to what the file says

    assert state_of(service) == {"file_per": "client", "written_at": NOW.isoformat(), "problem": None}


def test_marking_invoices_of_two_clients_at_once_brings_both_folders_up_to_date(service, anaf, cfg):
    downloaded(service, anaf, "A1", "A2")
    downloaded(service, anaf, "B1", cui=OTHER_VALID_CUI, first_id=4001)

    service.mark_uploaded(["3001", "4001"])

    assert files_in(folder(cfg)) == [name_of("A2")]
    assert files_in(folder(cfg, OTHER_VALID_CUI)) == []


# --- the folder away, or changed by another part of the program ----------------------------------


def test_a_file_is_not_forgotten_while_the_folder_for_saga_cannot_be_reached(service, anaf, cfg, tmp_path):
    downloaded(service, anaf, "A1")
    cfg.saga_dir.rename(tmp_path / "the stick, taken out")

    service.mark_uploaded(["3001"])  # nothing waits now, so nothing is written; the file must go

    assert "cannot be reached" in state_of(service)["problem"]["message"]

    (tmp_path / "the stick, taken out").rename(cfg.saga_dir)
    service.write_saga_files(VALID_CUI)

    assert files_in(folder(cfg)) == []
    assert state_of(service)["problem"] is None


def test_a_folder_that_was_left_behind_and_cannot_be_reached_is_let_go(service, anaf, cfg, tmp_path):
    downloaded(service, anaf, "A1")
    cfg.saga_dir.rename(tmp_path / "the stick, lost")

    result = service.set_saga_output(folder=str(tmp_path / "nou"))

    assert result["problems"] == []
    assert files_in(tmp_path / "nou" / VALID_CUI) == [name_of("A1")]


def test_a_service_made_before_the_folder_was_changed_writes_to_the_new_one(service, anaf, cfg, tmp_path):
    downloaded(service, anaf, "A1")
    Service(cfg, http=anaf.client(), now=lambda: NOW).set_saga_output(folder=str(tmp_path / "nou"))

    downloaded(service, anaf, "A2", first_id=3002)  # `service` was made while the old folder was set

    assert files_in(folder(cfg)) == []
    assert numbers_in(tmp_path / "nou" / VALID_CUI / name_of("A1")) == ["A1", "A2"]


def test_writing_the_same_folder_in_other_letters_does_not_delete_what_is_in_it(service, anaf, tmp_path):
    (tmp_path / "Pentru SAGA").mkdir()
    if not (tmp_path / "pentru saga").exists():
        pytest.skip("this disk tells file names apart by letter case; Windows does not")
    service.set_saga_output(folder=str(tmp_path / "Pentru SAGA"))
    downloaded(service, anaf, "A1", "A2")

    service.set_saga_output(folder=str(tmp_path / "pentru saga"))

    assert numbers_in(tmp_path / "Pentru SAGA" / VALID_CUI / name_of("A1")) == ["A1", "A2"]


def test_two_writers_are_never_in_a_clients_folder_at_once(service, anaf, cfg, monkeypatch):
    downloaded(service, anaf, "A1")
    inside, seen = [], []
    real = Service._place_saga_files

    def watched(self, store, cui, when):
        inside.append(1)
        seen.append(len(inside))
        time.sleep(0.05)
        real(self, store, cui, when)
        inside.pop()

    monkeypatch.setattr(Service, "_place_saga_files", watched)
    writers = [
        threading.Thread(
            target=Service(cfg, http=anaf.client(), now=lambda: NOW).write_saga_files, args=(VALID_CUI,)
        )
        for _ in range(4)
    ]
    for writer in writers:
        writer.start()
    for writer in writers:
        writer.join()

    assert seen == [1, 1, 1, 1]
    assert state_of(service)["problem"] is None
