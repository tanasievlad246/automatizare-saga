"""A discount (or a charge) written on the whole invoice has its own account: it is a row
after the invoice's lines, decided like a line by the rules, then Jev, then a person. The
example is a ride: the fare on 704, its "Reducere" on 729."""

import json
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree

import pytest

from efactura import auth, service as service_module
from efactura.auth import Tokens
from efactura.config import load_config
from efactura.errors import EfacturaError
from efactura.rules import Rule, Rulebook
from efactura.service import Service
from efactura.store import Store

from helpers import VALID_CUI, FakeAnaf, FakeOpenRouter, adjustment, line, rich_invoice_xml, set_rulebook

NOW = datetime(2026, 11, 11, 9, 30, tzinfo=timezone(timedelta(hours=2)))
BOOK = Rulebook(
    accounts={"6022": "Combustibil.", "628": "Alte servicii."},
    rules=(Rule("combustibil", "6022", keywords=("motorina",)),),
    instructions="Alege contul facturii.",
)
FARE = line("Tarif de calatorie", "16.10", unit="E48", percent="0", category="Z")
DISCOUNT = adjustment("4.30", reason="Reducere", percent="0", category="Z")
A_RIDER = {
    "supplier_cui": f"RO{VALID_CUI}", "supplier_name": "Drum Bun Ride SRL",
    "customer_cui": "0000000000000", "customer_name": "Ana Popescu",
}


def ride(*lines, adjustments=(DISCOUNT,), **more):
    """An invoice the client issued for a ride, with a discount on the whole invoice."""
    return rich_invoice_xml(lines=list(lines) or [FARE], adjustments=list(adjustments), **A_RIDER, **more)


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
    auth.save_tokens(
        cfg.token_file, Tokens("access-1", "refresh-1", NOW + timedelta(days=30), NOW + timedelta(days=300), NOW),
    )
    return cfg


@pytest.fixture
def openrouter():
    """Jev knows a fare and a discount."""
    fake = FakeOpenRouter()
    fake.answer_for("tarif", "704", confidence=0.93)
    fake.answer_for("reducere", "729", confidence=0.9)
    return fake


@pytest.fixture
def anaf(openrouter):
    fake = FakeAnaf()
    fake.openrouter = openrouter
    return fake


@pytest.fixture
def service(cfg, anaf, monkeypatch):
    """A ride-sharing client, decided line by line, with an income account for discounts."""
    monkeypatch.setattr(service_module, "_pause", lambda seconds: None)
    service = Service(cfg, http=anaf.client(), now=lambda: NOW)
    service.save_client(VALID_CUI, "Drum Bun Ride SRL")
    service.save_account("729", "Reduceri acordate calatorilor.", kind="issued")
    return service


def downloaded(service, anaf, xml=None, message_id="3001"):
    anaf.add(message_id, tip="FACTURA TRIMISA", xml=xml or ride())
    service.sync(VALID_CUI)


def saved(cfg, message_id="3001"):
    store = Store(cfg.db_path)
    try:
        return store.get_message(message_id)
    finally:
        store.close()


def accounts(service, message_id="3001"):
    """Each row's account and who chose it, as the invoice's screen is given them."""
    return [(entry["line"], entry["cont"], entry["method"]) for entry in service.invoice_view(message_id)["invoice"]["line_accounts"]]


def booked(service, message_id="3001"):
    """Each line of the invoice in SAGA's file: its number, name and account."""
    root = ElementTree.fromstring(service.invoice_view(message_id)["saga_xml"].encode("utf-8"))
    return [
        (node.findtext("LinieNrCrt"), node.findtext("Descriere"), node.findtext("Cont"))
        for node in root.findall("Factura/Detalii/Continut/Linie")
    ]


def asked(openrouter):
    return [request["state"]["linia"]["descriere"] for request in openrouter.requests]


def error_code(call):
    with pytest.raises(EfacturaError) as info:
        call()
    return info.value.code


def without_the_discount_row(cfg, message_id="3001"):
    """The invoice as a version before this one kept it: an account for each line, none for
    the discount on the whole invoice, which was booked on the largest line's."""
    store = Store(cfg.db_path)
    try:
        row = store.get_message(message_id, include_xml=True)
        lines = row["invoice_xml"].count("<cac:InvoiceLine>")
        kept = [entry for entry in json.loads(row["line_accounts"]) if entry["line"] <= lines]
        store.set_classification(message_id, line_accounts=json.dumps(kept))
    finally:
        store.close()


# --- decided like a line: the rules, then Jev, then a person -------------------------------


def test_the_fare_and_its_discount_are_booked_on_their_own_accounts(service, anaf, openrouter, cfg):
    downloaded(service, anaf)

    row = saved(cfg)
    assert (row["classification_status"], row["cont"]) == ("classified", "704")  # the invoice's own: its largest line's
    assert accounts(service) == [(1, "704", "jev"), (2, "729", "jev")]
    assert booked(service) == [("1", "Tarif de calatorie", "704"), ("2", "Reducere", "729")]
    assert asked(openrouter) == ["Tarif de calatorie", "Reducere"]
    assert openrouter.requests[1]["state"]["linia"]["fel"] == "reducere pe toata factura"


def test_a_rule_gives_the_discount_its_account_and_jev_is_not_asked_about_it(service, anaf, openrouter):
    service.save_rule(name="reduceri", cont="729", keywords=["reducere"], direction="issued")

    downloaded(service, anaf)

    assert accounts(service) == [(1, "704", "jev"), (2, "729", "rules")]
    assert asked(openrouter) == ["Tarif de calatorie"]


def test_a_discount_jev_is_unsure_of_waits_for_a_person(service, anaf, openrouter, cfg):
    openrouter.answer_for("reducere", "729", confidence=0.5)

    downloaded(service, anaf)

    row = saved(cfg)
    assert (row["classification_status"], row["cont"]) == ("review", None)
    assert "Line 2 needs a person" in row["classification_reason"]
    assert accounts(service) == [(1, "704", "jev"), (2, None, None)]
    assert service.invoice_view("3001")["saga_xml"] is None  # out of the file until the row has an account


def test_a_person_chooses_the_account_of_the_discount(service, anaf, openrouter, cfg):
    openrouter.answer_for("reducere", "729", confidence=0.5)
    downloaded(service, anaf)

    service.set_cont("3001", cont="707", line=2)

    assert saved(cfg)["classification_status"] == "classified"
    assert accounts(service) == [(1, "704", "jev"), (2, "707", "human")]
    assert booked(service)[1] == ("2", "Reducere", "707")


def test_a_person_accepts_what_jev_proposed_for_the_discount(service, anaf, openrouter):
    openrouter.answer_for("reducere", "729", confidence=0.5)
    downloaded(service, anaf)

    service.set_cont("3001", accept=True, line=2)

    assert accounts(service) == [(1, "704", "jev"), (2, "729", "jev_accepted")]


def test_the_discount_decided_again_alone_is_asked_of_jev(service, anaf, openrouter):
    downloaded(service, anaf)
    service.set_cont("3001", cont="707", line=2)
    openrouter.requests.clear()

    service.classify("3001", force=True, line=2, ask="jev_only")

    assert accounts(service) == [(1, "704", "jev"), (2, "729", "jev")]
    assert asked(openrouter) == ["Reducere"]


def test_a_row_the_invoice_does_not_have_cannot_be_decided(service, anaf):
    downloaded(service, anaf)

    assert error_code(lambda: service.classify("3001", force=True, line=3)) == "invalid_input"
    assert error_code(lambda: service.set_cont("3001", cont="707", line=3)) == "invalid_input"


def test_an_extra_charge_on_the_whole_invoice_is_decided_the_same_way(service, anaf, openrouter):
    openrouter.answer_for("taxa", "707", confidence=0.9)

    downloaded(service, anaf, ride(adjustments=[adjustment("2.00", charge=True, reason="Taxa de drum", percent="0", category="Z")]))

    assert accounts(service) == [(1, "704", "jev"), (2, "707", "jev")]
    assert openrouter.requests[1]["state"]["linia"]["fel"] == "taxa pe toata factura"


def test_the_history_keeps_how_the_discount_got_its_account(service, anaf):
    downloaded(service, anaf)
    service.set_cont("3001", cont="707", line=2)

    of_the_discount = [entry for entry in service.decision_history("3001")["decisions"] if entry["line"] == 2]

    assert [(entry["cont"], entry["method"]) for entry in of_the_discount] == [("707", "human"), ("729", "jev")]


def test_openrouter_stopping_before_the_discount_keeps_the_fares_answer(service, anaf, openrouter, cfg):
    openrouter.fail_for["reducere"] = 402  # no credit left, found at the second question
    downloaded(service, anaf)
    assert saved(cfg)["classification_status"] == "pending"

    del openrouter.fail_for["reducere"]
    openrouter.requests.clear()
    service.sync(VALID_CUI)

    assert accounts(service) == [(1, "704", "jev"), (2, "729", "jev")]
    assert asked(openrouter) == ["Reducere"]  # the fare is not paid for again


def test_a_discount_on_a_credit_note_is_still_a_discount(service, anaf, openrouter):
    downloaded(service, anaf, ride(credit_note=True))

    assert accounts(service) == [(1, "704", "jev"), (2, "729", "jev")]
    assert openrouter.requests[1]["state"]["linia"]["fel"] == "reducere pe toata factura"
    root = ElementTree.fromstring(service.invoice_view("3001")["saga_xml"].encode("utf-8"))
    # SAGA has no credit notes: the amounts change sign, each row keeps its account.
    assert [(node.findtext("Valoare"), node.findtext("Cont")) for node in root.iter("Linie")] == [
        ("-16.10", "704"), ("4.30", "729"),
    ]


def test_an_invoice_sent_twice_waits_with_its_discount_open_too(service, anaf, openrouter, cfg):
    downloaded(service, anaf)
    openrouter.requests.clear()

    downloaded(service, anaf, message_id="3002")

    assert saved(cfg, "3002")["classification_status"] == "review"
    assert accounts(service, "3002") == [(1, None, None), (2, None, None)]
    assert openrouter.requests == []  # held back without asking Jev


# --- one account per invoice, and splitting ------------------------------------------------


def test_a_client_with_one_account_per_invoice_books_the_discount_with_the_invoice(service, anaf, openrouter):
    service.set_client_per_line(VALID_CUI, False)

    downloaded(service, anaf)

    assert service.invoice_view("3001")["invoice"]["line_accounts"] is None
    assert booked(service) == [("1", "Tarif de calatorie", "704"), ("2", "Reducere", "704")]
    assert len(openrouter.requests) == 1 and "linii" in openrouter.requests[0]["state"]  # asked once, about the invoice


def test_an_invoice_of_one_line_and_a_discount_can_be_split_to_give_the_discount_its_account(service, anaf, openrouter):
    service.set_client_per_line(VALID_CUI, False)
    downloaded(service, anaf)

    service.split_into_lines("3001")

    assert accounts(service) == [(1, "704", "jev"), (2, "704", "invoice")]  # each row starts with the invoice's account
    service.set_cont("3001", cont="729", line=2)
    assert booked(service) == [("1", "Tarif de calatorie", "704"), ("2", "Reducere", "729")]


def test_an_invoice_of_one_line_without_a_discount_is_still_decided_whole(service, anaf):
    downloaded(service, anaf, ride(adjustments=()))

    assert service.invoice_view("3001")["invoice"]["line_accounts"] is None
    assert error_code(lambda: service.split_into_lines("3001")) == "invalid_input"


def test_an_invoice_with_a_discount_and_no_line_goes_to_a_person(service, anaf, cfg):
    anaf.add("3001", tip="FACTURA TRIMISA", xml=rich_invoice_xml(lines=[], adjustments=[DISCOUNT], **A_RIDER))

    service.sync(VALID_CUI)

    row = saved(cfg)
    assert (row["classification_status"], row["line_accounts"]) == ("review", None)
    assert "no lines" in row["classification_reason"]


# --- invoices decided line by line before the discount could have its own account ----------


@pytest.fixture
def decided_before(service, anaf, openrouter, cfg):
    """Two lines by Jev, and a discount on the whole invoice that has no account of its own."""
    openrouter.answer_for("bagaj", "707", confidence=0.95)
    downloaded(service, anaf, ride(FARE, line("Transport bagaj", "5.00", percent="0", category="Z")))
    without_the_discount_row(cfg)
    openrouter.requests.clear()
    return service


def test_an_older_invoices_discount_goes_on_following_the_largest_line(decided_before, cfg):
    assert accounts(decided_before) == [(1, "704", "jev"), (2, "707", "jev"), (3, "704", "follows")]
    assert booked(decided_before)[2] == ("3", "Reducere", "704")


def test_choosing_another_lines_account_on_an_older_invoice_leaves_it_ready(decided_before, cfg, openrouter):
    decided_before.set_cont("3001", cont="701", line=1)

    assert saved(cfg)["classification_status"] == "classified"
    assert accounts(decided_before) == [(1, "701", "human"), (2, "707", "jev"), (3, "701", "follows")]
    assert openrouter.requests == []


def test_an_older_invoices_discount_can_be_given_its_own_account(decided_before):
    decided_before.set_cont("3001", cont="729", line=3)

    assert accounts(decided_before) == [(1, "704", "jev"), (2, "707", "jev"), (3, "729", "human")]
    assert booked(decided_before)[2] == ("3", "Reducere", "729")


def test_an_older_invoices_discount_decided_again_goes_to_jev(decided_before, openrouter):
    decided_before.classify("3001", force=True, line=3)

    assert accounts(decided_before)[2] == (3, "729", "jev")
    assert asked(openrouter) == ["Reducere"]


def test_classify_again_without_jev_leaves_an_older_invoices_discount_as_it_was(service, anaf, openrouter, cfg):
    openrouter.answer_for("bagaj", "707", confidence=0.4)  # the second line waits for a person
    downloaded(service, anaf, ride(FARE, line("Transport bagaj", "5.00", percent="0", category="Z")))
    without_the_discount_row(cfg)

    service.classify_again(VALID_CUI, jev=False)

    assert accounts(service) == [(1, "704", "jev"), (2, None, None), (3, "704", "follows")]
    service.set_cont("3001", cont="707", line=2)
    assert saved(cfg)["classification_status"] == "classified"


# --- what the screen is given ----------------------------------------------------------------


def test_the_screen_gets_each_discount_with_its_number_name_and_value(service, anaf):
    downloaded(service, anaf, ride(adjustments=[DISCOUNT, adjustment("2.00", charge=True, reason="", percent="0", category="Z")]))

    discount, charge = service.invoice_view("3001")["document"]["adjustments"]

    assert (discount["number"], discount["description"], discount["value"]) == (2, "Reducere", "-4.30")
    assert (discount["is_charge"], discount["reason"], discount["amount"]) == (False, "Reducere", "4.30")
    assert (charge["number"], charge["description"], charge["value"], charge["reason"]) == (3, "Taxă suplimentară", "2.00", None)
