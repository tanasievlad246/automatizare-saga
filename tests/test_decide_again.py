""""Hotărăște din nou": one invoice, or one line of it, decided again on purpose, with the rules
then Jev, or with Jev alone."""

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from efactura import auth, service as service_module
from efactura.auth import Tokens
from efactura.config import load_config
from efactura.errors import EfacturaError
from efactura.rules import Rule, Rulebook
from efactura.service import Service
from efactura.store import Store

from helpers import VALID_CUI, FakeAnaf, FakeOpenRouter, line, rich_invoice_xml, set_rulebook

NOW = datetime(2026, 11, 11, 9, 30, tzinfo=timezone(timedelta(hours=2)))
BOOK = Rulebook(
    accounts={"302": "Materiale consumabile.", "623": "Protocol.", "628": "Alte servicii."},
    rules=(Rule("consumabile", "302", keywords=("*cartus*",)),),
    instructions="Alege contul facturii.",
)
TONER = line("Toner negru", "540.00", description="Cartus compatibil HP 85A")
PAPER = line("Hartie A4", "100.00")
COFFEE = line("Cafea boabe", "50.00")
DISCOUNT = line("Discount", "-10.00")


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
    fake = FakeOpenRouter()
    fake.answer_for("hartie", "302", confidence=0.95)
    fake.answer_for("cafea", "623", confidence=0.5)
    return fake


@pytest.fixture
def anaf(openrouter):
    fake = FakeAnaf()
    fake.openrouter = openrouter
    return fake


@pytest.fixture
def service(cfg, anaf, monkeypatch):
    """A client whose invoices are decided line by line."""
    monkeypatch.setattr(service_module, "_pause", lambda seconds: None)
    service = Service(cfg, http=anaf.client(), now=lambda: NOW)
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    return service


def saved(cfg, message_id="3001"):
    store = Store(cfg.db_path)
    try:
        return store.get_message(message_id)
    finally:
        store.close()


def lines_of(cfg, message_id="3001"):
    stored = saved(cfg, message_id)["line_accounts"]
    return {entry["line"]: entry for entry in json.loads(stored)} if stored else None


def downloaded(service, anaf, *lines):
    anaf.add("3001", xml=rich_invoice_xml(lines=list(lines)))
    service.sync(VALID_CUI)


def asked_about(openrouter, since):
    return [request["state"].get("linia", {}).get("descriere") for request in openrouter.requests[since:]]


def error_code(call):
    with pytest.raises(EfacturaError) as info:
        call()
    return info.value.code


# --- the whole invoice ---------------------------------------------------------------------


def test_jev_only_asks_jev_about_every_line_even_where_a_rule_matches(service, anaf, openrouter, cfg):
    downloaded(service, anaf, TONER, PAPER)
    before = len(openrouter.requests)

    service.classify("3001", force=True, ask="jev_only")

    assert sorted(asked_about(openrouter, before)) == ["Hartie A4", "Toner negru"]
    assert (lines_of(cfg)[1]["cont"], lines_of(cfg)[1]["method"]) == ("628", "jev")  # Jev's own choice


def test_jev_only_on_an_invoice_with_one_account_asks_about_the_invoice(service, anaf, openrouter, cfg):
    service.set_client_per_line(VALID_CUI, False)
    downloaded(service, anaf, TONER, PAPER)
    assert saved(cfg)["classification_method"] == "rules"

    before = len(openrouter.requests)

    service.classify("3001", force=True, ask="jev_only")

    row = saved(cfg)
    assert (row["cont"], row["classification_method"], row["line_accounts"]) == ("302", "jev", None)
    (asked,) = openrouter.requests[before:]
    assert [item["descriere"] for item in asked["state"]["linii"]] == ["Toner negru", "Hartie A4"]


def test_the_rules_then_jev_decide_the_invoice_from_the_start(service, anaf, cfg):
    downloaded(service, anaf, TONER, PAPER)
    service.set_cont("3001", cont="623", line=1)

    service.classify("3001", force=True)

    assert (lines_of(cfg)[1]["cont"], lines_of(cfg)[1]["method"]) == ("302", "rules")


def test_an_invoice_decided_line_by_line_keeps_its_shape_when_asked(service, anaf, cfg):
    downloaded(service, anaf, TONER, PAPER)
    service.set_client_per_line(VALID_CUI, False)

    service.classify("3001", force=True, per_line=True)

    assert lines_of(cfg) is not None


def test_without_per_line_an_invoice_on_lines_stays_on_lines_whatever_the_switch(service, anaf, cfg):
    downloaded(service, anaf, TONER, PAPER)
    service.set_client_per_line(VALID_CUI, False)

    service.classify("3001", force=True)

    assert lines_of(cfg) is not None  # a person may have split it


def test_without_per_line_an_invoice_with_one_account_follows_the_clients_switch_as_before(service, anaf, cfg):
    service.set_client_per_line(VALID_CUI, False)
    downloaded(service, anaf, TONER, PAPER)
    service.set_client_per_line(VALID_CUI, True)

    service.classify("3001", force=True)

    assert lines_of(cfg) is not None


def test_with_one_account_asked_for_an_invoice_is_decided_whole(service, anaf, cfg):
    downloaded(service, anaf, TONER, PAPER)

    service.classify("3001", force=True, per_line=False)

    assert (lines_of(cfg), saved(cfg)["cont"]) == (None, "302")


def test_the_history_says_the_invoice_was_decided_again_with_jev_only(service, anaf):
    downloaded(service, anaf, TONER, PAPER)

    service.classify("3001", force=True, ask="jev_only")

    newest = service.decision_history("3001")["decisions"][0]
    assert (newest["source"], newest["said"]["jev_only"]) == ("redecide", True)


# --- one line ----------------------------------------------------------------------------


def test_one_line_decided_again_changes_that_line_alone(service, anaf, openrouter, cfg):
    downloaded(service, anaf, TONER, PAPER, COFFEE)
    openrouter.answer_for("cafea", "623", confidence=0.9)
    before = len(openrouter.requests)
    other_lines = {number: entry for number, entry in lines_of(cfg).items() if number != 3}

    service.classify("3001", force=True, line=3)

    lines = lines_of(cfg)
    assert (lines[3]["cont"], lines[3]["method"]) == ("623", "jev")
    assert {number: entry for number, entry in lines.items() if number != 3} == other_lines
    assert asked_about(openrouter, before) == ["Cafea boabe"]
    assert saved(cfg)["classification_status"] == "classified"


def test_one_line_decided_again_with_the_rules_first_takes_a_rule_without_asking_jev(service, anaf, openrouter, cfg):
    downloaded(service, anaf, TONER, PAPER)
    service.set_cont("3001", cont="623", line=1)
    before = len(openrouter.requests)

    service.classify("3001", force=True, line=1)

    assert (lines_of(cfg)[1]["cont"], lines_of(cfg)[1]["method"]) == ("302", "rules")
    assert openrouter.requests[before:] == []


def test_the_largest_line_decided_again_moves_the_discount_that_follows_it(service, anaf, cfg):
    downloaded(service, anaf, TONER, PAPER, DISCOUNT)

    service.classify("3001", force=True, ask="jev_only", line=1)

    lines = lines_of(cfg)
    assert [lines[number]["cont"] for number in (1, 2, 3)] == ["628", "302", "628"]


def test_jev_only_on_a_discount_line_asks_jev_about_it(service, anaf, openrouter, cfg):
    downloaded(service, anaf, TONER, DISCOUNT)
    before = len(openrouter.requests)

    service.classify("3001", force=True, ask="jev_only", line=2)

    assert asked_about(openrouter, before) == ["Discount"]
    assert lines_of(cfg)[2]["method"] == "jev"


def test_the_history_writes_the_line_decided_again(service, anaf, openrouter):
    downloaded(service, anaf, TONER, COFFEE)
    openrouter.answer_for("cafea", "623", confidence=0.9)

    service.classify("3001", force=True, line=2, ask="jev_only")

    newest = service.decision_history("3001")["decisions"][0]
    assert (newest["source"], newest["line"], newest["cont"], newest["said"]["jev_only"]) == ("redecide", 2, "623", True)


def test_a_line_decided_again_to_the_same_result_is_still_written_and_only_that_line(service, anaf):
    downloaded(service, anaf, TONER, PAPER, COFFEE)  # Jev is unsure of the coffee
    rows = len(service.decision_history("3001")["decisions"])

    service.classify("3001", force=True, line=3, ask="jev_only")

    history = service.decision_history("3001")["decisions"]
    assert len(history) == rows + 1
    assert (history[0]["source"], history[0]["line"], history[0]["cont"]) == ("redecide", 3, None)


def test_an_invoice_decided_again_to_the_same_result_writes_every_line(service, anaf):
    downloaded(service, anaf, TONER, PAPER)
    rows = len(service.decision_history("3001")["decisions"])

    service.classify("3001", force=True)

    assert len(service.decision_history("3001")["decisions"]) == rows + 2


@pytest.mark.parametrize("line_number", [0, 7])
def test_a_line_the_invoice_does_not_have_is_bad_input(service, anaf, line_number):
    downloaded(service, anaf, TONER, PAPER)

    assert error_code(lambda: service.classify("3001", force=True, line=line_number)) == "invalid_input"


def test_one_line_of_an_invoice_with_one_account_points_to_splitting_first(service, anaf):
    service.set_client_per_line(VALID_CUI, False)
    downloaded(service, anaf, TONER, PAPER)

    with pytest.raises(EfacturaError) as info:
        service.classify("3001", force=True, line=2)

    assert info.value.code == "invalid_input" and "split" in info.value.message.lower()


# --- when it cannot be done ---------------------------------------------------------------


def test_one_line_of_an_invoice_sent_twice_decided_again_still_waits_for_a_person(service, anaf, cfg):
    xml = rich_invoice_xml(lines=[TONER, PAPER])
    anaf.add("3001", xml=xml)
    anaf.add("3002", xml=xml)  # the same invoice, under another ANAF id
    service.sync(VALID_CUI)
    assert saved(cfg, "3002")["classification_status"] == "review"

    service.classify("3002", force=True, line=1)

    row = saved(cfg, "3002")
    assert row["classification_status"] == "review"
    first = lines_of(cfg, "3002")[1]
    assert first["cont"] is None and first["reason"].startswith("The same invoice")
    assert row["saga_xml_path"] is None  # it is in no file for SAGA


def test_when_jev_fails_the_invoice_stays_as_it_was_and_the_history_writes_nothing(service, anaf, openrouter, cfg):
    downloaded(service, anaf, TONER, PAPER)
    lines, rows = lines_of(cfg), len(service.decision_history("3001")["decisions"])
    openrouter.fail_with = [402, 402]

    assert error_code(lambda: service.classify("3001", force=True, ask="jev_only")) == "jev_error"

    assert lines_of(cfg) == lines
    assert len(service.decision_history("3001")["decisions"]) == rows


def test_without_a_key_jev_only_leaves_the_line_to_a_person_and_says_the_rules_were_skipped(service, anaf, cfg):
    downloaded(service, anaf, TONER, PAPER)
    service.cfg = replace(service.cfg, openrouter_api_key=None)

    service.classify("3001", force=True, ask="jev_only", line=1)

    entry = lines_of(cfg)[1]
    assert entry["cont"] is None and entry["reason"].startswith("The rules were skipped")


def test_an_invoice_imported_in_saga_is_not_decided_again(service, anaf):
    downloaded(service, anaf, TONER, PAPER)
    service.mark_uploaded(["3001"])

    assert error_code(lambda: service.classify("3001", force=True, line=1)) == "not_classifiable"


def test_an_unknown_way_of_asking_is_bad_input(service, anaf):
    downloaded(service, anaf, TONER, PAPER)

    assert error_code(lambda: service.classify("3001", force=True, ask="jev_twice")) == "invalid_input"


def test_while_a_download_runs_nothing_is_decided_again(service, anaf, cfg):
    downloaded(service, anaf, TONER, PAPER)
    row = saved(cfg)

    with service._lock():
        assert error_code(lambda: service.classify("3001", force=True, ask="jev_only")) == "busy"

    assert saved(cfg) == row


def test_an_issued_line_is_decided_again_with_the_accounts_for_issued_invoices(service, anaf, openrouter, cfg):
    xml = rich_invoice_xml(
        lines=[line("Montaj instalatie", "900.00"), line("Teava PPR", "100.00")],
        supplier_cui=f"RO{VALID_CUI}", supplier_name="Alfa Construct SRL", customer_cui="87654321",
        customer_name="Beta Instal SRL",
    )
    anaf.add("3001", tip="FACTURA TRIMISA", xml=xml)
    service.sync(VALID_CUI)
    openrouter.default = {"choice": "707", "confidence": 0.95}
    before = len(openrouter.requests)

    service.classify("3001", force=True, ask="jev_only", line=1)

    (asked,) = openrouter.requests[before:]
    assert set(asked["questions"]["cont"]["criteria"]) == {"701", "704", "707", "altul"}
    assert lines_of(cfg)[1]["cont"] == "707"
