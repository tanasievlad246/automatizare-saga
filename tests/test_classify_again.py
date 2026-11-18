"""The invoices left to check, classified again on purpose: for one client or for every
client, with Jev or with the rules alone. What a person or Jev already decided is kept."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from efactura import auth, journal, service as service_module
from efactura.auth import Tokens
from efactura.config import load_config
from efactura.errors import EfacturaError
from efactura.rules import Rule, Rulebook
from efactura.service import Service
from efactura.store import Store

from helpers import OTHER_VALID_CUI, VALID_CUI, FakeAnaf, FakeOpenRouter, line, rich_invoice_xml, set_rulebook

NOW = datetime(2026, 11, 18, 9, 30, tzinfo=timezone(timedelta(hours=2)))

BOOK = Rulebook(
    accounts={"6022": "Combustibil.", "626": "Telefonie.", "628": "Alte servicii."},
    rules=(Rule("combustibil", "6022", keywords=("motorina",)),),
    instructions="Alege contul facturii.",
)
FUEL = line("Motorina Euro 5", "450.00")
PARTS = line("Piese de schimb", "300.00")
OIL = line("Ulei motor", "90.00")
PHONE = line("Abonament telefonie", "200.00")


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
def service(cfg, anaf):
    desk = Service(cfg, http=anaf.client(), now=lambda: NOW)
    desk.save_client(VALID_CUI, "Alfa Construct SRL")  # line by line, as every client starts
    return desk


@pytest.fixture
def whole(service):
    """The same client, with one account for each invoice."""
    service.set_client_per_line(VALID_CUI, False)
    return service


def saved(cfg, message_id="3001"):
    store = Store(cfg.db_path)
    try:
        return store.get_message(message_id)
    finally:
        store.close()


def lines_of(service, message_id="3001"):
    return service.invoice(message_id)["invoice"]["line_accounts"]


def asked_about(openrouter, since=0):
    """The text Jev was asked about, request by request, from the `since`-th on."""
    return [
        " / ".join(item["descriere"] for item in (request["state"].get("linii") or [request["state"]["linia"]]))
        for request in openrouter.requests[since:]
    ]


def events(cfg, name, details=False):
    return [event for event in journal.events(cfg.db_path, details=details)["events"] if event["event"] == name]


def add_rule(service, name, cont, *words):
    service.save_rule(name=name, cont=cont, keywords=words)


# --- the rules -----------------------------------------------------------------------------


def test_a_rule_added_after_the_download_gives_an_invoice_to_check_its_account(whole, anaf, openrouter, cfg):
    openrouter.answer_for("piese", "628", confidence=0.5)
    anaf.add("3001", xml=rich_invoice_xml(lines=[PARTS]))
    whole.sync(VALID_CUI)
    assert saved(cfg)["classification_status"] == "review"
    add_rule(whole, "piese", "628", "piese")
    before = len(openrouter.requests)

    result = whole.classify_again(VALID_CUI)

    row = saved(cfg)
    assert (row["classification_status"], row["cont"], row["classification_method"]) == ("classified", "628", "rules")
    assert len(openrouter.requests) == before  # a rule decided it: Jev is not asked
    assert {key: result[key] for key in ("total", "classified", "review", "waiting", "skipped")} == {
        "total": 1, "classified": 1, "review": 0, "waiting": 0, "skipped": 0,
    }
    assert (result["cui"], result["client"], result["jev_asked"], result["jev_stopped"]) == (
        VALID_CUI, "Alfa Construct SRL", True, False,
    )
    assert (result["jev_calls"], result["jev_cost_usd"]) == (0, 0)
    assert row["saga_xml_path"]  # it is in the client's file for SAGA, as after a download


def test_a_rule_added_after_the_download_decides_the_lines_it_matches(service, anaf, openrouter, cfg):
    openrouter.answer_for("piese", "628", confidence=0.5)
    anaf.add("3001", xml=rich_invoice_xml(lines=[FUEL, PARTS]))
    service.sync(VALID_CUI)
    add_rule(service, "piese", "628", "piese")
    before = len(openrouter.requests)

    service.classify_again(VALID_CUI)

    assert saved(cfg)["classification_status"] == "classified"
    assert [(entry["cont"], entry["method"]) for entry in lines_of(service)] == [("6022", "rules"), ("628", "rules")]
    assert len(openrouter.requests) == before


# --- what is kept ----------------------------------------------------------------------------


def test_a_line_a_person_chose_keeps_its_account_and_jev_is_not_asked_about_it(service, anaf, openrouter, cfg):
    openrouter.answer_for("piese", "628", confidence=0.5)
    openrouter.answer_for("ulei", "628", confidence=0.4)
    anaf.add("3001", xml=rich_invoice_xml(lines=[FUEL, PARTS, OIL]))
    service.sync(VALID_CUI)
    service.set_cont("3001", cont="626", line=2)
    assert saved(cfg)["classification_status"] == "review"  # line 3 still has no account
    openrouter.answer_for("ulei", "628", confidence=0.95)
    before = len(openrouter.requests)

    service.classify_again(VALID_CUI)

    assert asked_about(openrouter, before) == ["Ulei motor"]
    assert [(entry["cont"], entry["method"]) for entry in lines_of(service)] == [
        ("6022", "rules"), ("626", "human"), ("628", "jev"),
    ]
    assert saved(cfg)["classification_status"] == "classified"


def test_a_line_jev_was_sure_of_is_not_asked_about_again(service, anaf, openrouter, cfg):
    openrouter.answer_for("abonament", "626", confidence=0.93)
    openrouter.answer_for("piese", "628", confidence=0.5)
    anaf.add("3001", xml=rich_invoice_xml(lines=[PHONE, PARTS]))
    service.sync(VALID_CUI)
    before = len(openrouter.requests)

    service.classify_again(VALID_CUI)

    assert asked_about(openrouter, before) == ["Piese de schimb"]
    first, second = lines_of(service)
    assert (first["cont"], first["method"], first["confidence"]) == ("626", "jev", 0.93)
    assert (second["cont"], second["suggested_cont"], second["confidence"]) == (None, "628", 0.5)  # asked again


def test_a_rule_that_now_matches_a_line_jev_decided_wins(service, anaf, openrouter, cfg):
    openrouter.answer_for("abonament", "626", confidence=0.93)
    openrouter.answer_for("piese", "628", confidence=0.5)
    anaf.add("3001", xml=rich_invoice_xml(lines=[PHONE, PARTS]))
    service.sync(VALID_CUI)
    add_rule(service, "abonamente", "628", "abonament")

    service.classify_again(VALID_CUI, jev=False)

    assert [(entry["cont"], entry["method"]) for entry in lines_of(service)][0] == ("628", "rules")


def test_invoices_with_an_account_or_imported_are_not_touched(service, anaf, openrouter, cfg):
    anaf.add("3001", xml=rich_invoice_xml(lines=[FUEL]))
    openrouter.answer_for("piese", "628", confidence=0.5)
    anaf.add("3002", xml=rich_invoice_xml(lines=[PARTS], number="FV-2"))
    service.sync(VALID_CUI)
    service.mark_uploaded(["3002"])
    decided = saved(cfg, "3001")
    before = len(openrouter.requests)

    result = service.classify_again(VALID_CUI)

    assert result["total"] == 0
    assert saved(cfg, "3001") == decided
    assert (saved(cfg, "3002")["classification_status"], saved(cfg, "3002")["uploaded_to_accounting"]) == ("review", 1)
    assert len(openrouter.requests) == before


def test_an_invoice_sent_twice_comes_back_to_check_without_jev(whole, anaf, openrouter, cfg):
    anaf.add("3001", xml=rich_invoice_xml(lines=[PARTS]))
    anaf.add("3002", xml=rich_invoice_xml(lines=[PARTS]))  # the same supplier, number and date
    whole.sync(VALID_CUI)
    assert saved(cfg, "3002")["possible_duplicate_of"] == "3001"
    before = len(openrouter.requests)

    result = whole.classify_again(VALID_CUI)

    assert saved(cfg, "3002")["classification_status"] == "review"
    assert "already saved as message 3001" in saved(cfg, "3002")["classification_reason"]
    assert len(openrouter.requests) == before
    assert result["review"] == 1


def test_on_an_invoice_sent_twice_the_lines_a_person_chose_stay(service, anaf, openrouter, cfg):
    anaf.add("3001", xml=rich_invoice_xml(lines=[FUEL, PARTS]))
    anaf.add("3002", xml=rich_invoice_xml(lines=[FUEL, PARTS]))
    service.sync(VALID_CUI)
    service.set_cont("3002", cont="626", line=2)

    service.classify_again(VALID_CUI)

    assert [(entry["cont"], entry["method"]) for entry in lines_of(service, "3002")] == [(None, None), ("626", "human")]


# --- without Jev -----------------------------------------------------------------------------


def test_without_jev_an_invoice_no_rule_decides_stays_exactly_as_it_was(whole, anaf, openrouter, cfg):
    openrouter.answer_for("piese", "628", confidence=0.5)
    anaf.add("3001", xml=rich_invoice_xml(lines=[PARTS]))
    whole.sync(VALID_CUI)
    before, row = len(openrouter.requests), saved(cfg)

    result = whole.classify_again(VALID_CUI, jev=False)

    assert saved(cfg) == row
    assert len(openrouter.requests) == before
    assert (result["review"], result["jev_asked"], result["jev_calls"]) == (1, False, 0)


def test_without_jev_the_rules_decide_their_lines_and_jevs_proposals_stay(service, anaf, openrouter, cfg):
    openrouter.answer_for("piese", "628", confidence=0.5)
    openrouter.answer_for("abonament", "626", confidence=0.6)
    anaf.add("3001", xml=rich_invoice_xml(lines=[FUEL, PARTS, PHONE]))
    service.sync(VALID_CUI)
    add_rule(service, "abonamente", "626", "abonament")
    before = len(openrouter.requests)

    service.classify_again(VALID_CUI, jev=False)

    assert len(openrouter.requests) == before
    first, second, third = lines_of(service)
    assert (third["cont"], third["method"]) == ("626", "rules")
    assert (second["cont"], second["suggested_cont"], second["confidence"], second["asked"]) == (None, "628", 0.5, True)
    assert saved(cfg)["classification_status"] == "review"


def test_without_jev_an_invoice_waiting_for_jev_goes_on_waiting(service, anaf, openrouter, cfg):
    openrouter.valid_keys = {"another-key"}
    anaf.add("3001", xml=rich_invoice_xml(lines=[FUEL, PARTS]))
    service.sync(VALID_CUI)
    row = saved(cfg)
    assert row["classification_status"] == "pending"

    result = service.classify_again(VALID_CUI, jev=False)

    assert saved(cfg) == row
    assert result["waiting"] == 1


def test_with_jev_an_invoice_waiting_for_jev_gets_its_answer_now(service, anaf, openrouter, cfg):
    openrouter.valid_keys = {"another-key"}
    anaf.add("3001", xml=rich_invoice_xml(lines=[FUEL, PARTS]))
    service.sync(VALID_CUI)
    openrouter.valid_keys = {"or-test-key"}

    result = service.classify_again(VALID_CUI)

    assert saved(cfg)["classification_status"] == "classified"
    assert (result["classified"], result["jev_calls"]) == (1, 1)
    assert result["jev_cost_usd"] == pytest.approx(openrouter.cost_per_call)


def test_without_jev_an_invoice_decided_whole_before_keeps_jevs_proposal(service, anaf, openrouter, cfg):
    service.set_client_per_line(VALID_CUI, False)
    openrouter.answer_for("piese", "628", confidence=0.5)
    anaf.add("3001", xml=rich_invoice_xml(lines=[PARTS, OIL]))
    service.sync(VALID_CUI)
    service.set_client_per_line(VALID_CUI, True)  # as every client became when lines got their own accounts
    row = saved(cfg)
    assert (row["suggested_cont"], row["line_accounts"]) == ("628", None)

    service.classify_again(VALID_CUI, jev=False)

    assert saved(cfg) == row


def test_without_an_openrouter_key_now_what_jev_said_before_stays(service, anaf, openrouter, cfg):
    openrouter.answer_for("piese", "628", confidence=0.5)
    anaf.add("3001", xml=rich_invoice_xml(lines=[FUEL, PARTS]))
    service.sync(VALID_CUI)
    keyless = Service(replace(cfg, openrouter_api_key=None), http=anaf.client(), now=lambda: NOW)

    keyless.classify_again(VALID_CUI)

    second = lines_of(service)[1]
    assert (second["cont"], second["suggested_cont"], second["confidence"]) == (None, "628", 0.5)


# --- when Jev stops answering ----------------------------------------------------------------


def test_when_jev_stops_answering_the_lines_of_the_invoices_after_keep_what_jev_said(service, anaf, openrouter, cfg):
    openrouter.answer_for("piese", "628", confidence=0.5)
    openrouter.answer_for("ulei", "628", confidence=0.4)
    anaf.add("3001", xml=rich_invoice_xml(lines=[FUEL, PARTS]))
    anaf.add("3002", xml=rich_invoice_xml(lines=[FUEL, OIL], number="FV-2"))
    service.sync(VALID_CUI)
    openrouter.valid_keys = {"another-key"}

    result = service.classify_again(VALID_CUI)

    assert result["jev_stopped"] is True
    second = lines_of(service, "3002")[1]
    assert (second["cont"], second["suggested_cont"], second["confidence"]) == (None, "628", 0.4)
    assert saved(cfg, "3002")["classification_status"] == "review"


def test_an_invoice_that_fails_for_another_reason_is_counted_as_it_stands_and_the_rest_go_on(
    whole, anaf, openrouter, cfg, monkeypatch,
):
    openrouter.answer_for("piese", "628", confidence=0.5)
    anaf.add("3001", xml=rich_invoice_xml(lines=[PARTS]))
    anaf.add("3002", xml=rich_invoice_xml(lines=[OIL], number="FV-2"))
    openrouter.answer_for("ulei", "628", confidence=0.5)
    whole.sync(VALID_CUI)
    add_rule(whole, "ulei", "628", "ulei")
    decide = Service._classify_one

    def breaks_on_the_first(self, store, message_id, *args, **kwargs):
        if message_id == "3001":
            raise RuntimeError("boom")
        return decide(self, store, message_id, *args, **kwargs)

    monkeypatch.setattr(Service, "_classify_one", breaks_on_the_first)

    result = whole.classify_again(VALID_CUI)

    assert (result["review"], result["classified"]) == (1, 1)
    assert saved(cfg, "3002")["classification_status"] == "classified"


# --- when Jev stops answering, across clients ------------------------------------------------


def test_when_jev_stops_answering_the_invoices_after_stay_as_they_were(whole, anaf, openrouter, cfg):
    openrouter.answer_for("piese", "628", confidence=0.5)
    anaf.add("3001", xml=rich_invoice_xml(lines=[PARTS]))
    anaf.add("3002", xml=rich_invoice_xml(lines=[OIL], number="FV-2"))
    openrouter.answer_for("ulei", "628", confidence=0.5)
    whole.sync(VALID_CUI)
    openrouter.valid_keys = {"another-key"}
    before = len(openrouter.requests)

    result = whole.classify_again(VALID_CUI)

    assert result["jev_stopped"] is True
    assert len(openrouter.requests) == before + 1  # the second invoice is not sent
    for message_id in ("3001", "3002"):
        row = saved(cfg, message_id)
        assert (row["classification_status"], row["suggested_cont"], row["confidence"]) == ("review", "628", 0.5)
    assert result["review"] == 2


def test_for_every_client_jev_is_not_asked_again_after_it_stopped_answering(service, anaf, openrouter, cfg):
    service.save_client(OTHER_VALID_CUI, "Beta Instal SRL")
    for cui in (VALID_CUI, OTHER_VALID_CUI):
        service.set_client_per_line(cui, False)
    openrouter.answer_for("piese", "628", confidence=0.5)
    anaf.add("3001", xml=rich_invoice_xml(lines=[PARTS]))
    service.sync(VALID_CUI)
    # The stand-in lists every message for any CUI: the one saved already is skipped.
    anaf.add("4001", xml=rich_invoice_xml(lines=[PARTS], number="FV-9", customer_cui=OTHER_VALID_CUI), cui=OTHER_VALID_CUI)
    service.sync(OTHER_VALID_CUI)
    service.save_client("18547290", "Fara Facturi SRL")  # nothing to check: left out
    openrouter.valid_keys = {"another-key"}
    before = len(openrouter.requests)

    result = service.classify_again_all()

    assert [(entry["cui"], entry["jev_asked"], entry["jev_stopped"]) for entry in result["clients"]] == [
        (VALID_CUI, True, True), (OTHER_VALID_CUI, False, False),
    ]
    assert len(openrouter.requests) == before + 1


def test_for_every_client_without_jev_none_is_asked(service, anaf, openrouter, cfg):
    openrouter.answer_for("piese", "628", confidence=0.5)
    anaf.add("3001", xml=rich_invoice_xml(lines=[PARTS]))
    service.sync(VALID_CUI)
    before = len(openrouter.requests)

    result = service.classify_again_all(jev=False)

    assert [entry["jev_asked"] for entry in result["clients"]] == [False]
    assert len(openrouter.requests) == before


# --- the journal, the lock, the CUI ---------------------------------------------------------


def test_the_journal_gets_one_line_for_the_client_and_the_invoices_left_to_check_as_details(whole, anaf, openrouter, cfg):
    openrouter.answer_for("piese", "628", confidence=0.5)
    anaf.add("3001", xml=rich_invoice_xml(lines=[PARTS]))
    anaf.add("3002", xml=rich_invoice_xml(lines=[OIL], number="FV-2"))
    openrouter.answer_for("ulei", "628", confidence=0.5)
    whole.sync(VALID_CUI)
    add_rule(whole, "ulei", "628", "ulei")
    shown, all_of_them = len(events(cfg, "account.to_review")), len(events(cfg, "account.to_review", details=True))

    whole.classify_again(VALID_CUI)

    (summary,) = events(cfg, "classification.again")
    assert summary["level"] == "info"
    assert {key: summary["data"][key] for key in ("cui", "client", "total", "classified", "review", "jev_asked")} == {
        "cui": VALID_CUI, "client": "Alfa Construct SRL", "total": 2, "classified": 1, "review": 1, "jev_asked": True,
    }
    assert len(events(cfg, "account.to_review")) == shown  # the one left to check is a detail
    assert len(events(cfg, "account.to_review", details=True)) == all_of_them + 1
    assert len(events(cfg, "account.by_rule")) == 1  # the one that got an account has its line, as always


def test_a_client_with_nothing_to_check_changes_nothing_and_writes_no_line(service, cfg):
    result = service.classify_again(VALID_CUI)

    assert {key: result[key] for key in ("total", "classified", "review", "waiting", "skipped")} == {
        "total": 0, "classified": 0, "review": 0, "waiting": 0, "skipped": 0,
    }
    assert events(cfg, "classification.again") == []


def test_while_a_download_runs_nothing_is_classified_again(whole, anaf, openrouter, cfg):
    openrouter.answer_for("piese", "628", confidence=0.5)
    anaf.add("3001", xml=rich_invoice_xml(lines=[PARTS]))
    whole.sync(VALID_CUI)
    add_rule(whole, "piese", "628", "piese")
    row = saved(cfg)

    with whole._lock():
        with pytest.raises(EfacturaError) as info:
            whole.classify_again(VALID_CUI)

    assert info.value.code == "busy"
    assert saved(cfg) == row


def test_a_cui_that_is_not_valid_is_refused(service):
    with pytest.raises(EfacturaError) as info:
        service.classify_again("123")
    assert info.value.code == "invalid_cui"
