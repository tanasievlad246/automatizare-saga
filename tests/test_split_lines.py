""""Împarte pe linii": an invoice with one account becomes one decided line by line, each line
starting with the invoice's account, then changed or decided again one by one."""

import json
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
SOLD_BY_THE_CLIENT = {
    "supplier_cui": f"RO{VALID_CUI}", "supplier_name": "Alfa Construct SRL",
    "customer_cui": "87654321", "customer_name": "Beta Instal SRL",
}


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
    fake.answer_for("cafea", "623", confidence=0.5)
    return fake


@pytest.fixture
def anaf(openrouter):
    fake = FakeAnaf()
    fake.openrouter = openrouter
    return fake


@pytest.fixture
def service(cfg, anaf, monkeypatch):
    """A client whose invoices get one account each."""
    monkeypatch.setattr(service_module, "_pause", lambda seconds: None)
    service = Service(cfg, http=anaf.client(), now=lambda: NOW)
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    service.set_client_per_line(VALID_CUI, False)
    return service


def saved(cfg, message_id="3001"):
    store = Store(cfg.db_path)
    try:
        return store.get_message(message_id)
    finally:
        store.close()


def lines_of(cfg, message_id="3001"):
    return {entry["line"]: entry for entry in json.loads(saved(cfg, message_id)["line_accounts"])}


def downloaded(service, anaf, *lines, issued=False):
    xml = rich_invoice_xml(lines=list(lines), **(SOLD_BY_THE_CLIENT if issued else {}))
    anaf.add("3001", xml=xml, **({"tip": "FACTURA TRIMISA"} if issued else {}))
    service.sync(VALID_CUI)


def error_code(call):
    with pytest.raises(EfacturaError) as info:
        call()
    return info.value.code


def test_every_line_starts_with_the_invoices_account(service, anaf, cfg):
    downloaded(service, anaf, TONER, PAPER, DISCOUNT)
    assert (saved(cfg)["cont"], saved(cfg)["line_accounts"]) == ("302", None)

    service.split_into_lines("3001")

    lines = lines_of(cfg)
    assert (lines[1]["cont"], lines[1]["method"], lines[1]["rule"]) == ("302", "rules", "consumabile")
    assert lines[1]["match"]["matched"] == "Cartus"  # from the invoice's history, as the line writes it
    assert (lines[2]["cont"], lines[2]["method"]) == ("302", "invoice")
    assert (lines[3]["cont"], lines[3]["method"]) == ("302", "follows")
    row = saved(cfg)
    assert (row["classification_status"], row["cont"], row["classification_method"]) == ("classified", "302", "rules")


def test_the_file_for_saga_says_the_same_after_splitting(service, anaf):
    downloaded(service, anaf, TONER, PAPER, DISCOUNT)
    before = service.invoice_view("3001")["saga_xml"]

    service.split_into_lines("3001")

    assert service.invoice_view("3001")["saga_xml"] == before


def test_a_line_changed_afterwards_changes_that_line_alone_the_largest_included(service, anaf, cfg):
    downloaded(service, anaf, TONER, PAPER, DISCOUNT)
    service.split_into_lines("3001")

    service.set_cont("3001", cont="628", line=1)

    lines = lines_of(cfg)
    assert [lines[number]["cont"] for number in (1, 2, 3)] == ["628", "302", "628"]  # the discount follows line 1


def test_splitting_is_written_in_the_history_with_what_the_invoice_had(service, anaf):
    downloaded(service, anaf, TONER, PAPER)

    service.split_into_lines("3001")

    rows = [row for row in service.decision_history("3001")["decisions"] if row["source"] == "split"]
    assert sorted(row["line"] for row in rows) == [1, 2]
    assert {json.dumps(row["said"]["before"], sort_keys=True) for row in rows} == {
        json.dumps({"cont": "302", "method": "rules", "rule": None}, sort_keys=True),
    }


@pytest.mark.parametrize("why", ["no account yet", "one line", "already line by line"])
def test_splitting_is_refused_where_there_is_nothing_to_split(service, anaf, openrouter, cfg, why):
    if why == "no account yet":
        downloaded(service, anaf, COFFEE, PAPER)  # Jev is unsure of the invoice: it waits for a person
    elif why == "one line":
        downloaded(service, anaf, TONER)
    else:
        downloaded(service, anaf, TONER, PAPER)
        service.split_into_lines("3001")

    assert error_code(lambda: service.split_into_lines("3001")) == "invalid_input"


def test_an_invoice_imported_in_saga_is_not_split(service, anaf):
    downloaded(service, anaf, TONER, PAPER)
    service.mark_uploaded(["3001"])

    assert error_code(lambda: service.split_into_lines("3001")) == "not_classifiable"


def test_a_line_of_an_invoice_with_one_account_points_to_splitting_first(service, anaf):
    downloaded(service, anaf, TONER, PAPER)

    with pytest.raises(EfacturaError) as info:
        service.set_cont("3001", cont="628", line=2)

    assert info.value.code == "invalid_input" and "split" in info.value.message.lower()


def test_classifying_again_keeps_the_lines_kept_from_the_invoice(service, anaf, openrouter, cfg):
    downloaded(service, anaf, TONER, PAPER, COFFEE)
    service.split_into_lines("3001")
    service.classify("3001", force=True, line=3)  # Jev unsure of the coffee: the invoice waits for a person
    assert saved(cfg)["classification_status"] == "review"
    asked_before = len(openrouter.requests)

    service.classify_again(VALID_CUI)

    lines = lines_of(cfg)
    assert (lines[2]["cont"], lines[2]["method"]) == ("302", "invoice")
    assert [request["state"]["linia"]["descriere"] for request in openrouter.requests[asked_before:]] == ["Cafea boabe"]


@pytest.mark.parametrize("jev", [False, True])
def test_after_a_split_the_line_jev_decided_keeps_its_account_when_classified_again(service, anaf, openrouter, cfg, jev):
    openrouter.answers.clear()  # Jev is sure of the whole invoice: 628
    downloaded(service, anaf, PAPER, COFFEE)
    assert saved(cfg)["classification_method"] == "jev"
    service.split_into_lines("3001")
    openrouter.answer_for("cafea", "623", confidence=0.5)
    service.classify("3001", force=True, line=2)  # Jev unsure of the coffee: the invoice waits for a person
    assert saved(cfg)["classification_status"] == "review"
    asked_before = len(openrouter.requests)

    service.classify_again(VALID_CUI, jev=jev)

    assert (lines_of(cfg)[1]["cont"], lines_of(cfg)[1]["method"]) == ("628", "jev")
    assert all(request["state"]["linia"]["descriere"] != "Hartie A4" for request in openrouter.requests[asked_before:])


def test_an_issued_invoice_is_split_with_its_own_account(service, anaf, cfg):
    service.save_rule(name="montaj", cont="704", keywords=["montaj*"], direction="issued")

    downloaded(service, anaf, line("Montaj instalatie", "900.00"), line("Teava PPR", "100.00"), issued=True)
    service.split_into_lines("3001")

    lines = lines_of(cfg)
    assert [(lines[number]["cont"], lines[number]["method"]) for number in (1, 2)] == [("704", "rules"), ("704", "invoice")]
