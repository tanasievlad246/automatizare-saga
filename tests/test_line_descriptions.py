"""A line's description (cbc:Description) beside its name: read from the invoice, looked at by
the rules, sent to Jev, offered in proposed rules and in the rule test."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from efactura import auth, service as service_module
from efactura.auth import Tokens
from efactura.classify import jev_line_request, jev_request, line_subject, rules_by_line, same_question, subject_of
from efactura.config import load_config
from efactura.errors import EfacturaError
from efactura.invoice import parse_invoice
from efactura.rules import Rule, Rulebook, Subject
from efactura.service import Service
from efactura.store import Store
from efactura.suggestions import propose

from helpers import VALID_CUI, FakeAnaf, FakeOpenRouter, line, rich_invoice_xml, set_rulebook

NOW = datetime(2026, 11, 11, 9, 30, tzinfo=timezone(timedelta(hours=2)))
TONER = line("Cartus toner", "540.00", description="Cartus toner compatibil HP 85A, negru")
BOOK = Rulebook(
    accounts={"302": "Materiale consumabile.", "628": "Alte servicii."},
    rules=(Rule("consumabile", "302", keywords=("compatibil",)),),
    instructions="Alege contul facturii.",
)


def invoice_of(*lines):
    return parse_invoice(rich_invoice_xml(lines=list(lines)))


# --- reading the invoice -------------------------------------------------------------


def test_a_line_keeps_its_name_and_its_description_apart():
    (item,) = invoice_of(TONER).lines

    assert (item.description, item.details) == ("Cartus toner", "Cartus toner compatibil HP 85A, negru")


def test_a_description_that_says_what_the_name_says_is_not_kept_twice():
    (item,) = invoice_of(line("Cartuș toner", "10.00", description="CARTUS  TONER")).lines

    assert (item.description, item.details) == ("Cartuș toner", None)


def test_a_line_without_a_name_has_its_description_as_its_name_as_before():
    xml = rich_invoice_xml(lines=[line("X", "10.00", description="Servicii de paza")]).replace(b"<cbc:Name>X</cbc:Name>", b"")

    (item,) = parse_invoice(xml).lines

    assert (item.description, item.details) == ("Servicii de paza", None)


def test_a_line_without_a_description_has_none():
    assert invoice_of(line("Motorina", "10.00")).lines[0].details is None


# --- what the rules read ----------------------------------------------------------------


def test_the_subject_of_an_invoice_and_of_a_line_carry_the_description():
    invoice = invoice_of(TONER)

    assert subject_of(invoice).details == "Cartus toner compatibil HP 85A, negru"
    assert line_subject(invoice, invoice.lines[0]).details == "Cartus toner compatibil HP 85A, negru"


def test_a_keyword_found_only_in_the_description_decides_the_line():
    invoice = invoice_of(TONER, line("Transport", "20.00"))

    assert {number: rule.name for number, rule in rules_by_line(invoice, BOOK).items()} == {1: "consumabile"}


def test_the_rule_says_it_found_the_word_in_the_description():
    subject = Subject(None, "Cartus toner", details="Cartus compatibil HP")

    found = BOOK.rules[0].match(subject)

    assert (found.matched, found.in_details) == ("compatibil", True)
    assert Rule("r", "302", keywords=("toner",)).match(subject).in_details is False


def test_a_phrase_does_not_run_from_the_name_into_the_description():
    subject = Subject(None, "Hartie", details="copiator A4")

    assert not Rule("r", "302", keywords=("hartie copiator",)).matches(subject)
    assert Rule("r", "302", keywords=("hartie", "copiator")).matches(subject)


def test_a_subject_with_a_description_survives_being_stored_and_one_stored_before_still_reads():
    subject = Subject("87654321", "Cartus toner", details="compatibil HP 85A")

    assert Subject.from_json(subject.to_json()) == subject
    assert Subject.from_json('{"supplier_cui": "1", "description": "Toner"}').details is None


# --- what Jev is sent -------------------------------------------------------------------


def test_jev_gets_the_description_beside_the_name_only_when_there_is_one():
    invoice = invoice_of(TONER, line("Hartie A4", "100.00"))

    asked = jev_line_request(invoice, invoice.lines[0], BOOK, "jev")["state"]["linia"]
    plain = jev_line_request(invoice, invoice.lines[1], BOOK, "jev")["state"]["linia"]

    assert (asked["descriere"], asked["detalii"]) == ("Cartus toner", "Cartus toner compatibil HP 85A, negru")
    assert "detalii" not in plain
    assert [item.get("detalii") for item in jev_request(invoice, BOOK, "jev")["state"]["linii"]] == [
        "Cartus toner compatibil HP 85A, negru", None,
    ]


def test_two_lines_with_one_name_and_two_descriptions_are_two_questions():
    one, other, again = invoice_of(
        line("Servicii", "10.00", description="Transport marfa"),
        line("Servicii", "20.00", description="Reparatie compresor"),
        line("Servicii", "30.00", description="Transport marfa"),
    ).lines

    assert same_question(one) != same_question(other)
    assert same_question(one) == same_question(again)


# --- proposed rules ---------------------------------------------------------------------


def test_a_proposed_rule_takes_its_word_from_the_description_when_the_name_says_nothing():
    proposal = propose(Subject("87654321", "Servicii conform contract", details="Reparatie compresor"), "628")

    assert proposal.keywords == ("reparatie",)


def test_the_words_of_the_name_come_before_those_of_the_description():
    proposal = propose(Subject("87654321", "Toner negru", details="Compatibil HP"), "302")

    assert proposal.keywords == ("toner",)


# --- the program: received and issued, and the rule test ----------------------------------


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
    return FakeOpenRouter()


@pytest.fixture
def anaf(openrouter):
    fake = FakeAnaf()
    fake.openrouter = openrouter
    return fake


@pytest.fixture
def service(cfg, anaf, monkeypatch):
    monkeypatch.setattr(service_module, "_pause", lambda seconds: None)
    service = Service(cfg, http=anaf.client(), now=lambda: NOW)
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    service.save_rule(name="montaj", cont="704", keywords=["montaj*"], direction="issued")
    return service


def saved(cfg, message_id="3001"):
    store = Store(cfg.db_path)
    try:
        return store.get_message(message_id)
    finally:
        store.close()


def test_a_received_line_is_decided_by_a_word_of_its_description(service, anaf, openrouter, cfg):
    anaf.add("3001", xml=rich_invoice_xml(lines=[TONER, line("Hartie A4", "100.00")]))

    service.sync(VALID_CUI)

    first = json.loads(saved(cfg)["line_accounts"])[0]
    assert (first["cont"], first["method"], first["rule"]) == ("302", "rules", "consumabile")
    (asked,) = openrouter.requests  # only the other line went to Jev
    assert asked["state"]["linia"]["descriere"] == "Hartie A4"


def test_an_issued_line_is_decided_by_a_word_of_its_description(service, anaf, openrouter, cfg):
    xml = rich_invoice_xml(
        lines=[line("Lucrari", "900.00", description="Montajul instalatiei sanitare")],
        supplier_cui=f"RO{VALID_CUI}", supplier_name="Alfa Construct SRL", customer_cui="87654321",
        customer_name="Beta Instal SRL",
    )
    anaf.add("3001", tip="FACTURA TRIMISA", xml=xml)

    service.sync(VALID_CUI)

    row = saved(cfg)
    assert (row["cont"], row["classification_method"]) == ("704", "rules")
    assert openrouter.requests == []


def test_the_stored_subject_keeps_the_description_for_proposed_rules(service, anaf, cfg):
    anaf.add("3001", xml=rich_invoice_xml(lines=[line("Servicii", "100.00", description="Reparatie compresor")]))

    service.sync(VALID_CUI)

    store = Store(cfg.db_path)
    try:
        assert Subject.from_json(store.suggestion_state("3001")["rule_subject"]).details == "Reparatie compresor"
    finally:
        store.close()


def test_the_rule_test_reads_and_returns_a_lines_description(service):
    result = service.test_rules(lines=[{"description": "Cartus toner", "details": "Compatibil HP 85A"}])

    (entry,) = result["lines"]
    assert (entry["decided_by"], entry["cont"], entry["details"]) == ("rule", "302", "Compatibil HP 85A")
    assert entry["rule"]["in_details"] is True


def test_a_description_in_the_rule_test_is_at_most_500_characters(service):
    with pytest.raises(EfacturaError) as info:
        service.test_rules(lines=[{"description": "Toner", "details": "x" * 501}])

    assert info.value.code == "invalid_input"
