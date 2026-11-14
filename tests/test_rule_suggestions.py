"""Proposed rules: what Jev or a person decided, offered as a rule for the next invoice."""

from datetime import datetime, timedelta, timezone

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
BOOK = Rulebook(
    accounts={"302": "Materiale.", "371": "Marfuri.", "6022": "Combustibil.", "628": "Alte servicii."},
    rules=(Rule("combustibil", "6022", keywords=("motorina",)),),
    instructions="Alege contul facturii.",
)
CEMENT = {"cont": "302", "keywords": ["ciment"], "supplier_cuis": [], "supplier_name": None}


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
        cfg.token_file,
        Tokens("access-1", "refresh-1", NOW + timedelta(days=30), NOW + timedelta(days=300), NOW),
    )
    return cfg


@pytest.fixture
def openrouter():
    jev = FakeOpenRouter()
    jev.answer_for("ciment", "302", confidence=0.93)
    return jev


@pytest.fixture
def anaf(openrouter):
    fake = FakeAnaf()
    fake.openrouter = openrouter
    return fake


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(service_module, "_pause", lambda seconds: None)


@pytest.fixture
def service(cfg, anaf):
    return Service(cfg, http=anaf.client(), now=lambda: NOW)


def receive(anaf, message_id, description, value="840.00", **invoice):
    """ANAF has one more invoice, with a single line. Each gets its own number."""
    anaf.add(message_id, xml=rich_invoice_xml(
        lines=[line(description, value)], number=f"FV-{message_id}", **invoice,
    ))


def proposal_on(service, message_id):
    return service.invoice_view(message_id)["rule_suggestion"]


# --- on the invoice ----------------------------------------------------------------------


def test_an_invoice_jev_decided_gets_a_proposed_rule(service, anaf):
    receive(anaf, "3001", "Ciment Portland 40 kg")
    service.sync(VALID_CUI)

    assert proposal_on(service, "3001") == {
        "cont": "302",
        "line": "Ciment Portland 40 kg",
        "words": ["ciment", "portland"],
        "ticked": ["ciment"],
        "supplier_cui": "87654321",
        "supplier_name": "Furnizor SRL",
    }


def test_an_invoice_a_rule_decided_gets_none(service, anaf):
    receive(anaf, "3001", "Motorina Euro 5")
    service.sync(VALID_CUI)

    assert proposal_on(service, "3001") is None


def test_an_invoice_waiting_for_a_person_gets_one_once_decided(service, anaf, openrouter):
    openrouter.answer_for("ciment", "302", confidence=0.41)
    receive(anaf, "3001", "Ciment Portland 40 kg")
    service.sync(VALID_CUI)

    waiting = proposal_on(service, "3001")
    service.set_cont("3001", accept=True)
    accepted = proposal_on(service, "3001")
    service.set_cont("3001", cont="371")
    chosen = proposal_on(service, "3001")

    assert waiting is None
    assert (accepted["cont"], accepted["ticked"]) == ("302", ["ciment"])
    assert chosen["cont"] == "371"


def test_a_line_that_says_nothing_telling_offers_its_words_unticked(service, anaf):
    receive(anaf, "3001", "Servicii diverse")
    service.sync(VALID_CUI)

    proposal = proposal_on(service, "3001")

    assert (proposal["words"], proposal["ticked"]) == (["servicii", "diverse"], [])
    assert proposal["supplier_cui"] == "87654321"


# --- the list ------------------------------------------------------------------------------


def test_proposals_are_listed_together_the_one_with_most_invoices_first(service, anaf):
    receive(anaf, "3001", "Revizie autoutilitară")
    receive(anaf, "3002", "Ciment Portland 40 kg")
    receive(anaf, "3003", "CIMENT alb 25 kg")
    service.sync(VALID_CUI)

    listed = service.rule_suggestions()

    assert (listed["ok"], listed["count"], listed["days"]) == (True, 2, 90)
    first, second = listed["suggestions"]
    assert first == {
        **CEMENT, "invoice_ids": ["3002", "3003"], "matches": 2, "by_cont": {"302": 2},
    }
    assert (second["cont"], second["keywords"], second["invoice_ids"]) == ("628", ["revizie"], ["3001"])


def test_a_line_that_says_nothing_telling_is_proposed_by_supplier(service, anaf):
    receive(anaf, "3001", "Servicii conform contract", supplier_name="Service Auto Nord SRL")
    service.sync(VALID_CUI)

    (proposal,) = service.rule_suggestions()["suggestions"]

    assert proposal == {
        "cont": "628", "keywords": [], "supplier_cuis": ["87654321"],
        "supplier_name": "Service Auto Nord SRL", "invoice_ids": ["3001"],
        "matches": 1, "by_cont": {"628": 1},
    }


def test_invoices_the_rules_decided_are_not_proposed(service, anaf):
    receive(anaf, "3001", "Motorina Euro 5")
    service.sync(VALID_CUI)

    assert service.rule_suggestions()["suggestions"] == []


def test_creating_the_rule_removes_the_proposal_everywhere(service, anaf):
    receive(anaf, "3001", "Ciment Portland 40 kg")
    receive(anaf, "3002", "Adeziv pe bază de ciment")
    service.sync(VALID_CUI)

    service.save_rule(name="ciment", cont="302", keywords=["ciment"])

    assert service.rule_suggestions()["count"] == 0
    assert proposal_on(service, "3001") is None
    assert proposal_on(service, "3002") is None


def test_a_rule_that_is_off_or_belongs_to_another_client_does_not_remove_it(service, anaf):
    receive(anaf, "3001", "Ciment Portland 40 kg")
    service.sync(VALID_CUI)

    service.save_rule(name="oprita", cont="302", keywords=["ciment"], enabled=False)
    service.save_rule(name="a altuia", cont="302", keywords=["ciment"], client_cui=OTHER_VALID_CUI)

    assert service.rule_suggestions()["count"] == 1
    assert proposal_on(service, "3001") is not None


def test_not_now_hides_the_proposal_until_the_account_changes(service, anaf):
    receive(anaf, "3001", "Ciment Portland 40 kg")
    service.sync(VALID_CUI)

    turned_down = service.dismiss_rule_suggestions(["3001"])
    hidden = (service.rule_suggestions()["count"], proposal_on(service, "3001"))
    service.set_cont("3001", cont="371")

    assert turned_down == {"ok": True, "dismissed": ["3001"]}
    assert hidden == (0, None)
    assert service.rule_suggestions()["suggestions"][0]["cont"] == "371"
    assert proposal_on(service, "3001")["cont"] == "371"


def test_not_now_is_forgotten_once_the_account_has_changed(service, anaf):
    receive(anaf, "3001", "Ciment Portland 40 kg")
    service.sync(VALID_CUI)

    service.dismiss_rule_suggestions(["3001"])
    service.set_cont("3001", cont="371")
    service.set_cont("3001", cont="302")

    assert proposal_on(service, "3001")["cont"] == "302"


def test_not_now_stays_when_the_same_account_is_chosen_again(service, anaf):
    receive(anaf, "3001", "Ciment Portland 40 kg")
    service.sync(VALID_CUI)

    service.dismiss_rule_suggestions(["3001"])
    service.set_cont("3001", cont="302")

    assert proposal_on(service, "3001") is None


def test_the_rule_made_from_a_proposal_covers_the_invoice_it_came_from(service, anaf):
    receive(anaf, "3001", "Office365 Business")
    service.sync(VALID_CUI)

    (proposal,) = service.rule_suggestions()["suggestions"]
    service.save_rule(name="licente", cont=proposal["cont"], keywords=proposal["keywords"])

    assert (proposal["keywords"], proposal["matches"]) == (["business"], 1)
    assert service.rule_suggestions()["count"] == 0
    assert proposal_on(service, "3001") is None


def test_a_stored_subject_that_cannot_be_read_is_left_out(service, anaf, cfg):
    receive(anaf, "3001", "Ciment Portland 40 kg")
    receive(anaf, "3002", "Ciment alb 25 kg")
    service.sync(VALID_CUI)
    store = Store(cfg.db_path)
    store.set_classification("3002", rule_subject="{not what was stored")
    store.close()

    (proposal,) = service.rule_suggestions()["suggestions"]

    assert (proposal["invoice_ids"], proposal["matches"]) == (["3001"], 1)
    assert service.rule_preview(keywords=["ciment"])["matches"] == 1
    assert proposal_on(service, "3002") is None


def test_not_now_needs_invoices_that_exist(service, anaf):
    receive(anaf, "3001", "Ciment Portland 40 kg")
    service.sync(VALID_CUI)

    with pytest.raises(EfacturaError) as nothing:
        service.dismiss_rule_suggestions([])
    with pytest.raises(EfacturaError) as unknown:
        service.dismiss_rule_suggestions(["3001", "nope"])

    assert (nothing.value.code, unknown.value.code) == ("invalid_input", "not_found")
    assert service.rule_suggestions()["count"] == 1


def test_old_decisions_are_not_listed_but_the_invoice_still_shows_its_proposal(cfg, anaf, service):
    receive(anaf, "3001", "Ciment Portland 40 kg")
    Service(cfg, http=anaf.client(), now=lambda: NOW - timedelta(days=91)).sync(VALID_CUI)

    assert service.rule_suggestions()["count"] == 0
    assert proposal_on(service, "3001")["cont"] == "302"


def test_at_most_twenty_proposals_are_listed_and_all_are_counted(service, anaf):
    for number, letter in enumerate("abcdefghijklmnopqrstu"):
        receive(anaf, str(3001 + number), f"Marfa{letter} diversa")
    service.sync(VALID_CUI)

    listed = service.rule_suggestions()

    assert (listed["count"], len(listed["suggestions"])) == (21, 20)


# --- how a rule would have done ----------------------------------------------------------


@pytest.fixture
def mixed(service, anaf):
    """Cement booked on 302 by Jev and on 371 by a person, fuel by rule, for one client;
    cement on 302 for another client."""
    receive(anaf, "3001", "Ciment Portland 40 kg")
    receive(anaf, "3002", "Ciment alb 25 kg")
    receive(anaf, "3003", "Motorina Euro 5")
    service.sync(VALID_CUI)
    service.set_cont("3002", cont="371")
    other = FakeAnaf()
    other.openrouter = anaf.openrouter
    receive(other, "4001", "Ciment vrac")
    Service(service.cfg, http=other.client(), now=lambda: NOW).sync(OTHER_VALID_CUI)
    return service


def test_each_proposal_says_how_it_would_have_done_on_recent_invoices(mixed):
    on_302, on_371 = mixed.rule_suggestions()["suggestions"]

    assert (on_302["cont"], on_302["invoice_ids"]) == ("302", ["3001", "4001"])
    assert (on_371["cont"], on_371["invoice_ids"]) == ("371", ["3002"])
    assert (on_302["matches"], on_302["by_cont"]) == (3, {"302": 2, "371": 1})
    assert (on_371["matches"], on_371["by_cont"]) == (3, {"302": 2, "371": 1})


def test_any_rule_can_be_tried_on_recent_invoices(mixed):
    by_word = mixed.rule_preview(keywords=["ciment"])
    by_supplier = mixed.rule_preview(supplier_cuis=["RO87654321"])
    for_one_client = mixed.rule_preview(keywords=["ciment"], client_cui=VALID_CUI)
    two_words = mixed.rule_preview(keywords=["portland", "motorină"])

    assert by_word == {"ok": True, "matches": 3, "by_cont": {"302": 2, "371": 1}, "days": 90}
    assert (by_supplier["matches"], by_supplier["by_cont"]) == (4, {"302": 2, "371": 1, "6022": 1})
    assert (for_one_client["matches"], for_one_client["by_cont"]) == (2, {"302": 1, "371": 1})
    assert (two_words["matches"], two_words["by_cont"]) == (2, {"302": 1, "6022": 1})


def test_a_rule_without_conditions_matches_nothing(mixed):
    assert mixed.rule_preview()["matches"] == 0


def test_trying_a_rule_needs_lists(mixed):
    with pytest.raises(EfacturaError) as info:
        mixed.rule_preview(keywords="ciment")

    assert info.value.code == "invalid_input"


def test_invoices_from_before_ninety_days_are_not_evidence(cfg, anaf, service):
    receive(anaf, "3001", "Ciment Portland 40 kg")
    Service(cfg, http=anaf.client(), now=lambda: NOW - timedelta(days=91)).sync(VALID_CUI)

    assert service.rule_preview(keywords=["ciment"])["matches"] == 0
