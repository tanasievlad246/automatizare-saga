"""The history of an invoice's account: each time it changed, by whom, why, and what it had
before. Written only when something changed, kept as long as the invoice."""

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
    monkeypatch.setattr(service_module, "_pause", lambda seconds: None)
    service = Service(cfg, http=anaf.client(), now=lambda: NOW)
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    return service


def history(service, message_id="3001"):
    return service.decision_history(message_id)["decisions"]


def by_line(rows):
    return {row["line"]: row for row in rows}


def downloaded(service, anaf, *lines):
    anaf.add("3001", xml=rich_invoice_xml(lines=list(lines)))
    service.sync(VALID_CUI)


def test_a_download_writes_what_each_line_got_and_why(service, anaf):
    downloaded(service, anaf, TONER, PAPER, COFFEE, DISCOUNT)

    rows = by_line(history(service))

    assert set(rows) == {1, 2, 3, 4}
    assert {row["source"] for row in rows.values()} == {"download"}
    toner = rows[1]
    assert (toner["cont"], toner["method"], toner["said"]["rule"]) == ("302", "rules", "consumabile")
    assert toner["said"]["match"] == {
        "condition": "keyword", "found": "*cartus*", "prefix": None, "matched": "Cartus", "in_details": True,
    }
    paper = rows[2]
    assert (paper["cont"], paper["method"], paper["said"]["confidence"], paper["said"]["confidence_threshold"]) == (
        "302", "jev", 0.95, 0.8,
    )
    assert paper["said"]["probabilities"]["302"] == 0.95
    coffee = rows[3]
    assert (coffee["cont"], coffee["method"], coffee["said"]["suggested_cont"], coffee["said"]["confidence"]) == (
        None, None, "623", 0.5,
    )
    assert "below the level" in coffee["reason"]
    assert (rows[4]["cont"], rows[4]["method"]) == ("302", "follows")
    assert all(row["said"]["before"] is None for row in rows.values())  # nothing was decided before


def test_a_person_choosing_one_line_writes_that_line_alone_with_what_it_had(service, anaf):
    downloaded(service, anaf, TONER, PAPER, COFFEE)
    before = len(history(service))

    service.set_cont("3001", cont="623", line=3)

    rows = history(service)
    assert len(rows) == before + 1
    newest = rows[0]
    assert (newest["source"], newest["line"], newest["cont"], newest["method"]) == ("person", 3, "623", "human")
    assert newest["said"]["before"] == {"cont": None, "method": None, "rule": None}


def test_accepting_jevs_proposal_is_written_as_accepted(service, anaf):
    downloaded(service, anaf, TONER, COFFEE)

    service.set_cont("3001", accept=True, line=2)

    newest = history(service)[0]
    assert (newest["line"], newest["cont"], newest["method"]) == (2, "623", "jev_accepted")


def test_a_person_changing_a_decided_line_shows_what_was_there_before(service, anaf):
    downloaded(service, anaf, TONER, PAPER)

    service.set_cont("3001", cont="628", line=1)

    newest = history(service)[0]
    assert newest["said"]["before"] == {"cont": "302", "method": "rules", "rule": "consumabile"}


def test_a_person_choosing_a_line_a_rule_had_decided_keeps_no_rule_in_the_history(service, anaf):
    downloaded(service, anaf, TONER, PAPER)

    service.set_cont("3001", cont="628", line=1)

    newest = history(service)[0]
    assert (newest["method"], newest["said"]["rule"], newest["said"]["match"]) == ("human", None, None)


def test_an_invoice_on_lines_made_whole_says_what_it_had(service, anaf):
    downloaded(service, anaf, TONER, PAPER)

    service.classify("3001", force=True, per_line=False)

    newest = history(service)[0]
    assert newest["line"] is None
    assert newest["said"]["before"] == {"cont": "302", "method": "rules", "rule": None}


def test_classifying_again_writes_nothing_when_only_jevs_figures_move(service, anaf, openrouter):
    downloaded(service, anaf, TONER, COFFEE)
    before = len(history(service))
    openrouter.answer_for("cafea", "623", confidence=0.47)  # unsure again, by another hair

    service.classify_again(VALID_CUI)

    assert len(history(service)) == before


def test_classifying_again_that_changes_nothing_writes_nothing(service, anaf, openrouter):
    downloaded(service, anaf, TONER, COFFEE)
    before = len(history(service))

    service.classify_again(VALID_CUI, jev=False)
    service.classify_again(VALID_CUI)  # Jev unsure again, with the same figures

    assert len(history(service)) == before


def test_classifying_again_that_decides_a_line_writes_it_as_again(service, anaf, openrouter):
    downloaded(service, anaf, TONER, COFFEE)
    openrouter.answer_for("cafea", "623", confidence=0.9)

    service.classify_again(VALID_CUI)

    newest = history(service)[0]
    assert (newest["source"], newest["line"], newest["cont"], newest["method"]) == ("again", 2, "623", "jev")
    assert newest["said"]["before"] == {"cont": None, "method": None, "rule": None}


def test_an_invoice_with_one_account_writes_one_row_with_the_rule_and_its_word(service, anaf):
    service.set_client_per_line(VALID_CUI, False)

    downloaded(service, anaf, TONER, PAPER)

    (row,) = history(service)
    assert (row["line"], row["cont"], row["method"], row["said"]["rule"]) == (None, "302", "rules", "consumabile")
    assert row["said"]["match"]["matched"] == "Cartus"


def test_an_invoice_with_one_account_decided_by_jev_keeps_how_likely_each_account_was(service, anaf):
    service.set_client_per_line(VALID_CUI, False)

    downloaded(service, anaf, PAPER)

    (row,) = history(service)
    assert (row["cont"], row["method"], row["said"]["confidence"]) == ("302", "jev", 0.95)
    assert row["said"]["probabilities"]["302"] == 0.95


def test_an_invoice_with_one_account_changed_by_a_person(service, anaf):
    service.set_client_per_line(VALID_CUI, False)
    downloaded(service, anaf, PAPER)

    service.set_cont("3001", cont="628")

    newest = history(service)[0]
    assert (newest["source"], newest["line"], newest["cont"], newest["method"]) == ("person", None, "628", "human")
    assert newest["said"]["before"] == {"cont": "302", "method": "jev", "rule": None}


def test_an_issued_invoice_has_its_history_too(service, anaf):
    service.save_rule(name="montaj", cont="704", keywords=["montaj*"], direction="issued")
    xml = rich_invoice_xml(
        lines=[line("Montaj instalatie", "900.00"), line("Teava PPR", "100.00")],
        supplier_cui=f"RO{VALID_CUI}", supplier_name="Alfa Construct SRL", customer_cui="87654321",
        customer_name="Beta Instal SRL",
    )
    anaf.add("3001", tip="FACTURA TRIMISA", xml=xml)
    service.sync(VALID_CUI)

    rows = by_line(history(service))

    assert (rows[1]["cont"], rows[1]["method"], rows[1]["said"]["rule"]) == ("704", "rules", "montaj")


def test_the_history_of_an_unknown_invoice_is_not_found(service):
    with pytest.raises(EfacturaError) as info:
        service.decision_history("9999")

    assert info.value.code == "not_found"


def test_a_database_of_an_earlier_version_gains_the_history_when_opened(cfg):
    store = Store(cfg.db_path)
    store._conn.execute("DROP TABLE decisions")
    store.close()

    store = Store(cfg.db_path)
    try:
        assert store.decisions("3001") == []
    finally:
        store.close()
