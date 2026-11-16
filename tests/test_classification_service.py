"""Classification as the commands see it: inside sync, by id, review, costs."""

import json
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

from helpers import (
    ANAF_ERROR_NOTICE, OTHER_VALID_CUI, VALID_CUI, FakeAnaf, FakeOpenRouter, invoice_xml, line,
    make_row, rich_invoice_xml, set_rulebook,
)

NOW = datetime(2026, 11, 11, 9, 30, tzinfo=timezone(timedelta(hours=2)))
SAGA_NAME = "F_87654321_FV-1042_09.11.2026.xml"

BOOK = Rulebook(
    accounts={"6022": "Combustibil.", "626": "Telefonie si internet.", "628": "Alte servicii."},
    rules=(Rule("combustibil", "6022", keywords=("motorina",)),),
    instructions="Alege contul facturii.",
)

FUEL = [line("Motorina Euro 5", "450.00", quantity="60", unit="LTR", price="7.50")]
PARTS = [line("Piese de schimb", "900.00")]


def write_config(tmp_path, openrouter_key="or-test-key"):
    path = tmp_path / "config.toml"
    path.write_text(
        '[anaf]\nclient_id = "my-client"\nclient_secret = "my-secret"\n'
        f"token_file = '{tmp_path / 'private' / 'tokens.json'}'\n"
        + (f'[openrouter]\napi_key = "{openrouter_key}"\n' if openrouter_key else ""),
        encoding="utf-8",
    )
    cfg = load_config(path)
    set_rulebook(cfg.db_path, BOOK)
    return cfg


@pytest.fixture
def cfg(tmp_path):
    return write_config(tmp_path)


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
    return Service(cfg, http=anaf.client(), now=lambda: NOW)


def error_code(call):
    with pytest.raises(EfacturaError) as info:
        call()
    return info.value.code


def saved(cfg, message_id="3001"):
    store = Store(cfg.db_path)
    row = store.get_message(message_id)
    store.close()
    return row


def calls(cfg):
    store = Store(cfg.db_path)
    found = store.jev_calls()
    store.close()
    return found


def saga_file(cfg, name=SAGA_NAME, cui=VALID_CUI):
    return cfg.saga_dir / cui / name


def conts_in(path):
    return [node.text for node in ElementTree.parse(path).getroot().iter("Cont")]


# --- inside sync: the rules ----------------------------------------------------------


def test_sync_classifies_a_new_invoice_by_rule_and_writes_the_saga_file(service, anaf, cfg, openrouter):
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL + [line("Spalare", "50.00")]))

    (entry,) = service.sync(VALID_CUI)["new"]

    assert (entry["classification_status"], entry["cont"], entry["classification_method"]) == (
        "classified", "6022", "rules"
    )
    assert entry["saga_xml_path"] == str(saga_file(cfg))
    assert conts_in(saga_file(cfg)) == ["6022", "6022"]
    assert "combustibil" in entry["classification_reason"]
    assert entry["classified_at"] == NOW.isoformat()
    assert openrouter.requests == []


def test_saga_file_carries_anafs_ids_for_the_invoice(service, anaf, cfg):
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL), upload_index="5001")

    service.sync(VALID_CUI)

    antet = ElementTree.parse(saga_file(cfg)).getroot().find("Factura/Antet")
    assert antet.findtext("FacturaIndexSPV") == "5001"
    assert antet.findtext("FacturaIndexDescarcareSPV") == "3001"


def test_sync_reply_sums_up_the_classification(service, anaf, cfg):
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))

    result = service.sync(VALID_CUI)

    assert result["classification"] == {
        "classified": 1, "review": 0, "pending": 0, "skipped": 0, "jev_calls": 0, "jev_cost_usd": 0,
    }
    assert result["saga_folder"] == str(cfg.saga_dir / VALID_CUI)


def test_each_company_gets_its_own_saga_folder(cfg, anaf):
    other = Service(cfg, http=anaf.client(), now=lambda: NOW)
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))

    other.sync(OTHER_VALID_CUI)

    assert saga_file(cfg, cui=OTHER_VALID_CUI).exists()
    assert not saga_file(cfg).exists()


# --- inside sync: Jev ----------------------------------------------------------------


def test_an_invoice_the_rules_cannot_decide_is_decided_by_jev(service, anaf, cfg, openrouter):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))
    openrouter.answer_for("piese", "628", confidence=0.93)

    (entry,) = service.sync(VALID_CUI)["new"]

    assert (entry["classification_status"], entry["cont"], entry["classification_method"]) == (
        "classified", "628", "jev"
    )
    assert (entry["suggested_cont"], entry["confidence"], entry["confidence_threshold"]) == (
        "628", 0.93, 0.8
    )
    assert conts_in(saga_file(cfg)) == ["628"]


def test_jev_is_asked_with_the_configured_model_key_logic_and_accounts(service, anaf, openrouter):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))

    service.sync(VALID_CUI)

    (request,) = openrouter.requests
    assert request["model"] == "typesafe/jev-1.14"
    assert request["questions"]["cont"]["instructions"] == "Alege contul facturii."
    assert set(request["questions"]["cont"]["criteria"]) == {"6022", "626", "628", "altul"}
    assert openrouter.keys_seen == ["or-test-key"]


def test_every_jev_call_is_stored_with_request_response_and_cost(service, anaf, cfg, openrouter):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))

    result = service.sync(VALID_CUI)

    (call,) = calls(cfg)
    assert (call["message_id"], call["cui"], call["called_at"]) == ("3001", VALID_CUI, NOW.isoformat())
    assert json.loads(call["request_json"]) == openrouter.requests[0]
    assert json.loads(call["response_json"])["answers"]["cont"]["choice"] == "628"
    assert (call["input_tokens"], call["output_tokens"], call["cost_usd"]) == (400, 12, 0.00002)
    assert (call["http_status"], call["error"]) == (200, None)
    assert "or-test-key" not in call["request_json"] + call["response_json"]
    assert (result["classification"]["jev_calls"], result["classification"]["jev_cost_usd"]) == (
        1, 0.00002
    )


def test_an_answer_below_the_confidence_level_goes_to_review(service, anaf, cfg, openrouter):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))
    openrouter.answer_for("piese", "628", confidence=0.41)

    result = service.sync(VALID_CUI)

    (entry,) = result["new"]
    assert (entry["classification_status"], entry["cont"], entry["saga_xml_path"]) == ("review", None, None)
    assert (entry["suggested_cont"], entry["confidence"], entry["confidence_threshold"]) == ("628", 0.41, 0.8)
    assert "0.41" in entry["classification_reason"] and "0.80" in entry["classification_reason"]
    assert not cfg.saga_dir.exists()
    assert result["classification"]["review"] == 1
    assert result["saga_folder"] is None


def test_none_of_the_accounts_goes_to_review_without_a_suggestion(service, anaf, openrouter):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))
    openrouter.answer_for("piese", "altul", confidence=0.97)

    (entry,) = service.sync(VALID_CUI)["new"]

    assert (entry["classification_status"], entry["suggested_cont"], entry["confidence"]) == (
        "review", None, 0.97
    )


def test_a_refusal_goes_to_review(service, anaf, openrouter):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))
    openrouter.answers["piese"] = {"refusal": True}

    (entry,) = service.sync(VALID_CUI)["new"]

    assert (entry["classification_status"], entry["suggested_cont"]) == ("review", None)


def test_an_answer_without_a_confidence_goes_to_review_with_the_suggestion(service, anaf, openrouter):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))
    openrouter.answer_for("piese", "628", confidence=None)

    (entry,) = service.sync(VALID_CUI)["new"]

    assert (entry["classification_status"], entry["suggested_cont"], entry["confidence"]) == (
        "review", "628", None
    )


def test_an_invoice_without_lines_goes_to_review_without_asking_jev(service, anaf, openrouter):
    anaf.add("3001", xml=invoice_xml())

    (entry,) = service.sync(VALID_CUI)["new"]

    assert entry["classification_status"] == "review"
    assert openrouter.requests == []


def test_without_an_openrouter_key_the_rules_work_and_the_rest_goes_to_review(tmp_path, anaf):
    cfg = write_config(tmp_path, openrouter_key=None)
    anaf.openrouter = None  # any call to OpenRouter would fail the test
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL, number="A1"))
    anaf.add("3002", xml=rich_invoice_xml(lines=PARTS, number="A2"))

    by_fuel, by_parts = Service(cfg, http=anaf.client(), now=lambda: NOW).sync(VALID_CUI)["new"]

    assert by_fuel["classification_status"] == "classified"
    assert by_parts["classification_status"] == "review"
    assert "OpenRouter" in by_parts["classification_reason"]


# --- inside sync: when Jev cannot be reached ------------------------------------------


def test_when_jev_is_unreachable_the_invoice_waits_and_sync_still_succeeds(service, anaf, cfg, openrouter):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))
    openrouter.fail_with = ["unreachable", "unreachable"]

    result = service.sync(VALID_CUI)

    (entry,) = result["new"]
    assert result["ok"] is True and result["failed"] == []
    assert (entry["classification_status"], entry["cont"]) == ("pending", None)
    assert "reach" in entry["classification_error"]
    assert result["classification"]["pending"] == 1
    assert [call["error"] is not None for call in calls(cfg)] == [True, True]  # tried twice, both kept


def test_a_passing_failure_is_retried_at_once(service, anaf, openrouter):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))
    openrouter.fail_with = [503]

    (entry,) = service.sync(VALID_CUI)["new"]

    assert entry["classification_status"] == "classified"
    assert len(openrouter.requests) == 2


def test_running_out_of_credit_is_not_retried_at_once(service, anaf, cfg, openrouter):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))
    openrouter.fail_with = [402]

    (entry,) = service.sync(VALID_CUI)["new"]

    assert entry["classification_status"] == "pending"
    assert "credit" in entry["classification_error"]
    assert len(openrouter.requests) == 1


def test_after_jev_fails_the_remaining_invoices_wait_without_being_sent(service, anaf, openrouter):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS, number="A1"))
    anaf.add("3002", xml=rich_invoice_xml(lines=PARTS, number="A2"))
    anaf.add("3003", xml=rich_invoice_xml(lines=FUEL, number="A3"))
    openrouter.fail_with = [402]

    statuses = [entry["classification_status"] for entry in service.sync(VALID_CUI)["new"]]

    assert statuses == ["pending", "pending", "classified"]  # the rules still work
    assert len(openrouter.requests) == 1


def test_waiting_invoices_are_classified_by_the_next_sync(service, anaf, cfg, openrouter):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))
    openrouter.fail_with = [402]
    service.sync(VALID_CUI)

    result = service.sync(VALID_CUI)  # nothing new at ANAF this time

    assert result["new"] == []
    assert result["classification"]["classified"] == 1
    row = saved(cfg)
    assert (row["classification_status"], row["cont"], row["classification_error"]) == (
        "classified", "628", None
    )
    assert saga_file(cfg).exists()


# --- what is never classified ----------------------------------------------------------


def test_sent_invoices_error_notices_and_buyer_messages_are_left_alone(service, anaf, cfg):
    anaf.add("3001", tip="FACTURA TRIMISA", xml=rich_invoice_xml(lines=FUEL))
    anaf.add("3002", tip="ERORI FACTURA", xml=ANAF_ERROR_NOTICE.encode())
    anaf.add("3003", tip="MESAJ CUMPARATOR PRIMIT / MESAJ CUMPARATOR TRANSMIS", xml=b"<mesaj/>")

    result = service.sync(VALID_CUI)

    assert [entry["classification_status"] for entry in result["new"]] == [None, None, None]
    assert result["classification"]["skipped"] == 3
    assert not cfg.saga_dir.exists()


def test_a_received_message_that_is_not_an_invoice_is_left_alone(service, anaf):
    anaf.add("3001", xml=b"<ceva-necunoscut/>")

    (entry,) = service.sync(VALID_CUI)["new"]

    assert entry["classification_status"] is None


def test_sync_without_classification_saves_only(service, anaf, cfg, openrouter):
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))

    result = service.sync(VALID_CUI, classify=False)

    assert result["new"][0]["classification_status"] is None
    assert result["classification"] is None
    assert not cfg.saga_dir.exists()


def test_invoices_already_in_the_database_are_never_classified_by_sync(service, anaf, cfg):
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))
    service.sync(VALID_CUI, classify=False)  # as if saved before classification existed
    anaf.add("3002", xml=rich_invoice_xml(lines=FUEL, number="NEW-1"))

    result = service.sync(VALID_CUI)

    assert [entry["id"] for entry in result["new"]] == ["3002"]
    assert saved(cfg, "3001")["classification_status"] is None
    assert not saga_file(cfg).exists()  # the old invoice's file was never written
    assert saga_file(cfg, name="F_87654321_NEW-1_09.11.2026.xml").exists()


# --- by id -----------------------------------------------------------------------------


@pytest.fixture
def old_invoice(service, anaf):
    """Saved before classification: no status."""
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))
    service.sync(VALID_CUI, classify=False)


@pytest.fixture
def in_review(service, anaf, openrouter):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))
    openrouter.answer_for("piese", "628", confidence=0.41)
    service.sync(VALID_CUI)


def test_classify_by_id_refuses_an_old_invoice(service, cfg, old_invoice):
    assert error_code(lambda: service.classify("3001")) == "not_classifiable"
    assert saved(cfg)["classification_status"] is None


def test_classify_by_id_with_force_classifies_an_old_invoice(service, cfg, old_invoice):
    result = service.classify("3001", force=True)

    assert result["ok"] is True
    assert (result["invoice"]["classification_status"], result["invoice"]["cont"]) == ("classified", "6022")
    assert result["invoice"]["saga_xml_path"] == str(saga_file(cfg))
    assert saga_file(cfg).exists()


def test_classify_by_id_runs_again_for_an_invoice_in_review(service, openrouter, in_review):
    openrouter.answer_for("piese", "628", confidence=0.99)

    result = service.classify("3001")

    assert (result["invoice"]["classification_status"], result["invoice"]["classification_method"]) == (
        "classified", "jev"
    )


def test_classify_by_id_leaves_a_classified_invoice_alone_unless_forced(service, anaf, cfg):
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))
    service.sync(VALID_CUI)

    assert error_code(lambda: service.classify("3001")) == "not_classifiable"
    assert service.classify("3001", force=True)["invoice"]["cont"] == "6022"


def test_classify_by_id_of_an_unknown_message_is_not_found(service):
    assert error_code(lambda: service.classify("nope")) == "not_found"


def test_classify_by_id_refuses_what_is_not_a_received_invoice(service, anaf):
    anaf.add("3001", tip="FACTURA TRIMISA", xml=rich_invoice_xml(lines=FUEL))
    anaf.add("3002", xml=b"<ceva-necunoscut/>")
    service.sync(VALID_CUI)

    assert error_code(lambda: service.classify("3001", force=True)) == "not_classifiable"
    assert error_code(lambda: service.classify("3002", force=True)) == "not_classifiable"


def test_classify_by_id_reports_a_jev_failure_and_leaves_the_invoice_as_it_was(
    service, cfg, openrouter, in_review
):
    openrouter.fail_with = [402]

    assert error_code(lambda: service.classify("3001")) == "jev_error"
    row = saved(cfg)
    assert (row["classification_status"], row["suggested_cont"]) == ("review", "628")
    assert "credit" in row["classification_error"]
    assert len(calls(cfg)) == 2  # the first answer and the failed one


def test_a_forced_reclassification_that_cannot_reach_jev_keeps_the_earlier_result(
    service, anaf, cfg, openrouter
):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))
    service.sync(VALID_CUI)  # classified by Jev
    openrouter.fail_with = [402]

    assert error_code(lambda: service.classify("3001", force=True)) == "jev_error"
    row = saved(cfg)
    assert (row["classification_status"], row["cont"]) == ("classified", "628")
    assert saga_file(cfg).exists()


def test_a_database_problem_while_classifying_does_not_fail_the_sync(service, anaf, monkeypatch):
    import sqlite3

    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))

    def broken(self, cui):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(Store, "pending_classification", broken)

    result = service.sync(VALID_CUI)

    assert (result["ok"], result["new_count"], result["classification"]) == (True, 1, None)


def test_a_forced_reclassification_that_ends_in_review_removes_the_old_saga_file(
    service, anaf, cfg, openrouter
):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))
    service.sync(VALID_CUI)  # classified by Jev at 0.95
    assert saga_file(cfg).exists()
    openrouter.answer_for("piese", "628", confidence=0.2)

    result = service.classify("3001", force=True)

    assert result["invoice"]["classification_status"] == "review"
    assert result["invoice"]["saga_xml_path"] is None
    assert not saga_file(cfg).exists()


# --- review ----------------------------------------------------------------------------


def test_review_lists_what_a_person_must_decide_with_jevs_suggestion(service, in_review):
    result = service.review()

    assert (result["ok"], result["count"], result["min_confidence"]) == (True, 1, 0.8)
    assert result["accounts"] == BOOK.accounts
    (entry,) = result["invoices"]
    assert (entry["id"], entry["suggested_cont"], entry["confidence"]) == ("3001", "628", 0.41)
    assert entry["jev_probabilities"] == {"628": 0.41}
    assert entry["supplier_name"] == "Furnizor SRL"


def test_review_leaves_out_classified_invoices_and_other_companies(service, anaf, in_review):
    anaf.add("3002", xml=rich_invoice_xml(lines=FUEL, number="A2"))
    service.sync(VALID_CUI)

    assert [entry["id"] for entry in service.review()["invoices"]] == ["3001"]
    assert service.review(cui=OTHER_VALID_CUI)["count"] == 0
    assert service.review(cui=f"RO{VALID_CUI}")["count"] == 1


def test_accepting_jevs_suggestion_classifies_and_writes_the_file(service, cfg, in_review):
    result = service.set_cont("3001", accept=True)

    invoice = result["invoice"]
    assert (invoice["classification_status"], invoice["cont"], invoice["classification_method"]) == (
        "classified", "628", "jev_accepted"
    )
    assert (invoice["suggested_cont"], invoice["confidence"]) == ("628", 0.41)  # kept for later analysis
    assert conts_in(saga_file(cfg)) == ["628"]
    assert service.review()["count"] == 0


def test_a_person_can_set_another_account_including_an_analytic_one(service, cfg, in_review):
    result = service.set_cont("3001", cont=" 371.01 ")

    invoice = result["invoice"]
    assert (invoice["cont"], invoice["classification_method"], invoice["suggested_cont"]) == (
        "371.01", "human", "628"
    )
    assert conts_in(saga_file(cfg)) == ["371.01"]


def test_a_person_can_correct_an_invoice_that_is_already_classified(service, anaf, cfg):
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))
    service.sync(VALID_CUI)

    service.set_cont("3001", cont="3022")

    assert conts_in(saga_file(cfg)) == ["3022"]
    assert saved(cfg)["classification_method"] == "human"


@pytest.mark.parametrize("arguments", [
    {},                                # neither
    {"accept": True, "cont": "628"},   # both
    {"cont": "abc"},
    {"cont": "62"},
    {"cont": "628; DROP"},
    {"cont": ""},
])
def test_set_cont_needs_exactly_one_sensible_instruction(service, in_review, arguments):
    assert error_code(lambda: service.set_cont("3001", **arguments)) == "invalid_input"


def test_accepting_when_jev_suggested_nothing_is_invalid(service, anaf, openrouter):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))
    openrouter.answer_for("piese", "altul", confidence=0.9)
    service.sync(VALID_CUI)

    assert error_code(lambda: service.set_cont("3001", accept=True)) == "invalid_input"


def test_set_cont_refuses_an_old_invoice_unless_forced(service, cfg, old_invoice):
    assert error_code(lambda: service.set_cont("3001", cont="628")) == "not_classifiable"
    assert service.set_cont("3001", cont="628", force=True)["invoice"]["cont"] == "628"


def test_set_cont_on_an_unknown_message_is_not_found(service):
    assert error_code(lambda: service.set_cont("nope", cont="628")) == "not_found"


# --- the confidence level ----------------------------------------------------------------


def test_the_confidence_level_starts_at_eighty_percent(service):
    settings = service.classification_settings()

    assert settings == {
        "ok": True, "min_confidence": 0.8, "model": "typesafe/jev-1.14", "jev_configured": True,
        "accounts": BOOK.accounts, "jev_instructions": BOOK.instructions,
    }


def test_the_confidence_level_can_be_changed_and_is_kept_in_the_database(service, cfg, anaf):
    assert service.set_min_confidence(0.9)["min_confidence"] == 0.9

    again = Service(cfg, http=anaf.client(), now=lambda: NOW)
    assert again.classification_settings()["min_confidence"] == 0.9


def test_a_raised_level_sends_a_formerly_good_answer_to_review(service, anaf, openrouter):
    service.set_min_confidence(0.99)
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))
    openrouter.answer_for("piese", "628", confidence=0.95)

    (entry,) = service.sync(VALID_CUI)["new"]

    assert (entry["classification_status"], entry["confidence_threshold"]) == ("review", 0.99)


def test_an_answer_exactly_at_the_level_is_accepted(service, anaf, openrouter):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))
    openrouter.answer_for("piese", "628", confidence=0.8)

    assert service.sync(VALID_CUI)["new"][0]["classification_status"] == "classified"


@pytest.mark.parametrize("value", [1.5, -0.1, float("nan"), "abc", None, True])
def test_a_confidence_level_outside_zero_to_one_is_invalid(service, value):
    assert error_code(lambda: service.set_min_confidence(value)) == "invalid_input"


# --- costs -------------------------------------------------------------------------------


def test_costs_add_up_what_jev_was_paid(service, anaf, openrouter):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS, number="A1"))
    anaf.add("3002", xml=rich_invoice_xml(lines=PARTS, number="A2"))
    anaf.add("3003", xml=rich_invoice_xml(lines=FUEL, number="A3"))  # rules: free
    service.sync(VALID_CUI)

    costs = service.costs()

    assert (costs["ok"], costs["calls"], costs["failed_calls"], costs["invoices"]) == (True, 2, 0, 2)
    assert costs["input_tokens"] == 800
    assert costs["cost_usd"] == pytest.approx(0.00004)
    assert costs["average_cost_per_invoice_usd"] == pytest.approx(0.00002)
    assert (costs["group"], [period["period"] for period in costs["by_period"]]) == ("month", ["2026-11"])


def test_costs_before_any_call_are_zero(service):
    costs = service.costs()

    assert (costs["calls"], costs["cost_usd"], costs["average_cost_per_invoice_usd"]) == (0, 0, None)


def test_costs_can_be_narrowed_by_date_and_company(service, anaf):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))
    service.sync(VALID_CUI)

    assert service.costs(since="2026-11-12")["calls"] == 0
    assert service.costs(until="2026-11-10")["calls"] == 0
    assert service.costs(since="2026-11-11", until="2026-11-11", group="day")["by_period"][0]["period"] == "2026-11-11"
    assert error_code(lambda: service.costs(group="decade")) == "invalid_input"
    assert error_code(lambda: service.costs(until="mâine")) == "invalid_input"
    assert service.costs(since="2026-11-01", cui=f"RO{VALID_CUI}")["calls"] == 1
    assert service.costs(cui=OTHER_VALID_CUI)["calls"] == 0
    assert error_code(lambda: service.costs(since="yesterday")) == "invalid_input"


# --- listing -----------------------------------------------------------------------------


def test_invoices_can_be_listed_by_classification(service, anaf, in_review):
    anaf.add("3002", xml=rich_invoice_xml(lines=FUEL, number="A2"))
    service.sync(VALID_CUI)

    assert [e["id"] for e in service.invoices(classification="review")["invoices"]] == ["3001"]
    assert [e["id"] for e in service.invoices(classification="classified")["invoices"]] == ["3002"]
    assert service.invoices(classification="pending")["count"] == 0
    assert error_code(lambda: service.invoices(classification="done")) == "invalid_input"


def test_single_invoice_shows_its_classification_with_a_full_path(service, anaf, cfg):
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))
    service.sync(VALID_CUI)

    invoice = service.invoice("3001")["invoice"]

    assert (invoice["classification_status"], invoice["cont"]) == ("classified", "6022")
    assert invoice["saga_xml_path"] == str(saga_file(cfg))


# --- rules and accounts kept in the database ---------------------------------------------


def rule(**fields):
    return {"name": "regula", "cont": "6022", "keywords": ["motorina"], **fields}


def test_a_fresh_database_classifies_with_the_example_rules(tmp_path, anaf):
    path = tmp_path / "config.toml"
    path.write_text(
        '[anaf]\nclient_id = "c"\nclient_secret = "s"\n'
        f"token_file = '{tmp_path / 'private' / 'tokens.json'}'\n", encoding="utf-8",
    )
    fresh = Service(load_config(path), http=anaf.client(), now=lambda: NOW)
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))

    assert fresh.sync(VALID_CUI)["new"][0]["cont"] == "6022"


def test_rules_overview_lists_accounts_rules_and_the_question(service):
    overview = service.rules_overview()

    assert (overview["ok"], overview["accounts"]) == (True, BOOK.accounts)
    assert overview["jev_instructions"] == BOOK.instructions
    (only,) = overview["rules"]
    assert (only["name"], only["cont"], only["keywords"], only["client_cui"], only["enabled"]) == (
        "combustibil", "6022", ["motorina"], None, True
    )


def test_a_rule_added_on_screen_decides_the_next_invoice(service, anaf, openrouter):
    service.save_rule(name="piese", cont="3024", keywords=["piese de schimb"])
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))

    (entry,) = service.sync(VALID_CUI)["new"]

    assert (entry["cont"], entry["classification_method"]) == ("3024", "rules")
    assert openrouter.requests == []


def test_a_clients_own_rule_is_checked_before_the_shared_ones(service, anaf):
    service.save_rule(name="combustibil pentru revanzare", cont="371", keywords=["motorina"],
                      client_cui=f"RO{VALID_CUI}")
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))

    assert service.sync(VALID_CUI)["new"][0]["cont"] == "371"
    assert service.sync(OTHER_VALID_CUI)["new"] == []  # nothing new, but:
    anaf.add("3002", xml=rich_invoice_xml(lines=FUEL, number="A2"))
    assert service.sync(OTHER_VALID_CUI)["new"][0]["cont"] == "6022"  # the shared rule


def test_a_rule_that_is_switched_off_is_ignored(service, anaf):
    (existing,) = service.rules_overview()["rules"]
    service.save_rule(rule_id=existing["id"], **rule(enabled=False))
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))

    assert service.sync(VALID_CUI)["new"][0]["classification_method"] == "jev"


def test_a_rule_can_be_changed_moved_and_deleted(service):
    first = service.rules_overview()["rules"][0]["id"]
    second = service.save_rule(**rule(name="a doua", cont="626"))["rules"][-1]["id"]

    service.save_rule(rule_id=second, **rule(name="redenumita", cont="628"))
    order = [each["name"] for each in service.move_rule(second, up=True)["rules"]]
    left = [each["id"] for each in service.delete_rule(first)["rules"]]

    assert order == ["redenumita", "combustibil"]
    assert left == [second]


@pytest.mark.parametrize("fields, code", [
    (rule(name="  "), "invalid_input"),
    (rule(cont="abc"), "invalid_input"),
    (rule(keywords=[]), "invalid_input"),          # no condition at all
    (rule(keywords="motorina"), "invalid_input"),  # a list is expected
    (rule(client_cui="12345678"), "invalid_cui"),  # wrong check digit
])
def test_a_rule_that_makes_no_sense_is_refused(service, fields, code):
    assert error_code(lambda: service.save_rule(**fields)) == code


def test_changing_or_deleting_an_unknown_rule_is_not_found(service):
    assert error_code(lambda: service.save_rule(rule_id=999, **rule())) == "not_found"
    assert error_code(lambda: service.delete_rule(999)) == "not_found"
    assert error_code(lambda: service.move_rule(999, up=True)) == "not_found"


def test_an_account_can_be_added_described_and_removed(service):
    added = service.save_account(" 302 ", "Materiale consumabile.")
    removed = service.delete_account("302")

    assert added["accounts"]["302"] == "Materiale consumabile."
    assert "302" not in removed["accounts"]
    assert error_code(lambda: service.save_account("30", "prea scurt")) == "invalid_input"
    assert error_code(lambda: service.delete_account("999")) == "not_found"


def test_jev_is_offered_the_accounts_and_question_from_the_database(service, anaf, openrouter):
    service.save_account("302", "Materiale consumabile.")
    service.set_jev_instructions("Alege contul potrivit.")
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))

    service.sync(VALID_CUI)

    question = openrouter.requests[0]["questions"]["cont"]
    assert question["instructions"] == "Alege contul potrivit."
    assert "302" in question["criteria"]


def test_an_empty_question_for_jev_is_refused(service):
    assert error_code(lambda: service.set_jev_instructions("   ")) == "invalid_input"


def test_without_any_account_jev_is_not_asked(service, anaf, openrouter):
    for cont in BOOK.accounts:
        service.delete_account(cont)
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))

    (entry,) = service.sync(VALID_CUI)["new"]

    assert entry["classification_status"] == "review"
    assert openrouter.requests == []


# --- found by the independent review -----------------------------------------------------


def test_an_invoice_jev_rejects_goes_to_review_and_does_not_hold_up_the_others(
    service, anaf, cfg, openrouter
):
    anaf.add("3001", xml=rich_invoice_xml(lines=[line("Ceva ciudat", "10.00")], number="A1"))
    anaf.add("3002", xml=rich_invoice_xml(lines=PARTS, number="A2"))
    openrouter.fail_for["ciudat"] = 400

    first, second = service.sync(VALID_CUI)["new"]

    assert (first["classification_status"], second["classification_status"]) == ("review", "classified")
    assert "HTTP 400" in first["classification_reason"]
    assert first["suggested_cont"] is None
    assert len(openrouter.requests) == 2
    assert service.sync(VALID_CUI)["classification"]["pending"] == 0  # nothing left to retry


def test_an_answer_that_makes_no_sense_sends_that_invoice_to_review_only(service, anaf, openrouter):
    anaf.add("3001", xml=rich_invoice_xml(lines=[line("Ceva ciudat", "10.00")], number="A1"))
    anaf.add("3002", xml=rich_invoice_xml(lines=PARTS, number="A2"))
    openrouter.answer_for("ciudat", "9999")  # not one of the accounts offered

    first, second = service.sync(VALID_CUI)["new"]

    assert (first["classification_status"], second["classification_status"]) == ("review", "classified")
    assert "9999" in first["classification_reason"]


def test_a_confidence_that_is_not_between_zero_and_one_is_not_trusted(service, anaf, openrouter):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))
    openrouter.answer_for("piese", "628", confidence=95)

    (entry,) = service.sync(VALID_CUI)["new"]

    assert (entry["classification_status"], entry["cont"]) == ("review", None)


@pytest.mark.parametrize("failure", ["unreachable", 401, 402, 404, 429, 503])
def test_a_failure_of_the_service_as_a_whole_still_stops_the_run(service, anaf, openrouter, failure):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS, number="A1"))
    anaf.add("3002", xml=rich_invoice_xml(lines=PARTS, number="A2"))
    openrouter.fail_with = [failure, failure]

    statuses = [entry["classification_status"] for entry in service.sync(VALID_CUI)["new"]]

    assert statuses == ["pending", "pending"]
    assert len(openrouter.requests) <= 2  # the second invoice was never sent


def test_two_invoices_whose_numbers_differ_only_in_punctuation_get_separate_files(service, anaf, cfg):
    service.set_saga_output(per="invoice")
    anaf.add("3001", xml=rich_invoice_xml(lines=[line("Motorina", "100.00")], number="AB 12"))
    anaf.add("3002", xml=rich_invoice_xml(lines=[line("Motorina", "999.00")], number="AB/12"))

    first, second = service.sync(VALID_CUI)["new"]

    assert first["saga_xml_path"] != second["saga_xml_path"]
    values = {
        ElementTree.parse(entry["saga_xml_path"]).getroot().findtext(".//Valoare")
        for entry in (first, second)
    }
    assert values == {"100.00", "999.00"}


def test_file_names_that_differ_only_in_letter_case_are_kept_apart(service, anaf):
    service.set_saga_output(per="invoice")
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL, number="ab12"))
    anaf.add("3002", xml=rich_invoice_xml(lines=FUEL, number="AB12"))

    first, second = service.sync(VALID_CUI)["new"]

    assert first["saga_xml_path"].lower() != second["saga_xml_path"].lower()


def test_the_same_invoice_sent_again_under_a_new_anaf_id_waits_for_a_person(service, anaf, cfg):
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))
    service.sync(VALID_CUI)
    anaf.add("3002", xml=rich_invoice_xml(lines=FUEL))  # same supplier, number and date

    (again,) = service.sync(VALID_CUI)["new"]

    assert (again["classification_status"], again["possible_duplicate_of"]) == ("review", "3001")
    assert "3001" in again["classification_reason"]
    assert conts_in(saga_file(cfg)) == ["6022"]  # the first one's file is untouched


def test_deciding_a_repeated_invoice_never_touches_the_first_ones_file(service, anaf, cfg):
    service.set_saga_output(per="invoice")
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))
    service.sync(VALID_CUI)
    anaf.add("3002", xml=rich_invoice_xml(lines=FUEL))
    service.sync(VALID_CUI)

    decided = service.set_cont("3002", cont="626")["invoice"]

    assert decided["saga_xml_path"] != str(saga_file(cfg))
    assert conts_in(decided["saga_xml_path"]) == ["626"]
    assert conts_in(saga_file(cfg)) == ["6022"]
    assert saved(cfg, "3001")["cont"] == "6022"


def test_the_same_number_on_another_date_is_a_different_invoice(service, anaf):
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))
    service.sync(VALID_CUI)
    next_year = rich_invoice_xml(lines=FUEL).replace(b"2026-11-09", b"2027-01-15")
    anaf.add("3002", xml=next_year)

    (entry,) = service.sync(VALID_CUI)["new"]

    assert entry["classification_status"] == "classified"


def test_no_file_is_left_for_saga_when_the_decision_could_not_be_recorded(
    service, anaf, cfg, monkeypatch
):
    import sqlite3

    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))
    real = Store.set_classification

    def fail_on_classified(self, message_id, **fields):
        if fields.get("classification_status") == "classified":
            raise sqlite3.OperationalError("disk I/O error")
        real(self, message_id, **fields)

    monkeypatch.setattr(Store, "set_classification", fail_on_classified)

    (entry,) = service.sync(VALID_CUI)["new"]

    assert entry["classification_status"] == "pending"
    assert not saga_file(cfg).exists()


def test_an_earlier_file_is_put_back_when_a_correction_could_not_be_recorded(
    service, anaf, cfg, monkeypatch
):
    import sqlite3

    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))
    service.sync(VALID_CUI)

    def always_fail(self, message_id, **fields):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(Store, "set_classification", always_fail)

    with pytest.raises(sqlite3.OperationalError):
        service.set_cont("3001", cont="3022")

    assert conts_in(saga_file(cfg)) == ["6022", ] * len(conts_in(saga_file(cfg)))
    assert saved(cfg)["cont"] == "6022"


def test_a_file_that_could_not_be_put_in_place_leaves_no_half_written_copy(
    service, anaf, cfg, monkeypatch
):
    import os

    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))
    real_replace = os.replace

    def refuse_saga(source, target):
        if "SAGA Import" in str(target):
            raise PermissionError("the file is open in another program")
        real_replace(source, target)

    monkeypatch.setattr(os, "replace", refuse_saga)

    service.sync(VALID_CUI)

    assert list(cfg.saga_dir.rglob("*")) == [cfg.saga_dir / VALID_CUI]  # the folder, and nothing in it


def test_an_invoice_already_marked_uploaded_is_not_reclassified(service, anaf, cfg):
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))
    service.sync(VALID_CUI)
    service.mark_uploaded(["3001"])

    assert error_code(lambda: service.set_cont("3001", cont="3022")) == "not_classifiable"
    assert error_code(lambda: service.classify("3001", force=True)) == "not_classifiable"
    assert not saga_file(cfg).exists()  # imported: it waits in no file

    service.mark_uploaded(["3001"], undo=True)
    assert service.set_cont("3001", cont="3022")["invoice"]["cont"] == "3022"
    assert conts_in(saga_file(cfg)) == ["3022"]


def test_when_the_list_of_accounts_leaves_no_room_for_the_invoice_it_goes_to_review(cfg, anaf, openrouter):
    huge = Rulebook(
        accounts={str(6000 + n): "O descriere foarte lunga a contului. " * 5 for n in range(200)},
        rules=(), instructions="Alege contul.",
    )
    set_rulebook(cfg.db_path, huge)
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))

    (entry,) = Service(cfg, http=anaf.client(), now=lambda: NOW).sync(VALID_CUI)["new"]

    assert entry["classification_status"] == "review"
    assert openrouter.requests == []


def test_the_openrouter_key_is_never_written_to_the_database_or_the_log(
    service, anaf, cfg, openrouter, caplog
):
    import sqlite3

    for message_id in ("3001", "3002", "3003"):
        anaf.add(message_id, xml=rich_invoice_xml(lines=PARTS, number=f"N{message_id}"))
    openrouter.fail_with = [401, 503, "unreachable"]

    with caplog.at_level("DEBUG"):
        service.sync(VALID_CUI)
        service.sync(VALID_CUI)

    database = "\n".join(sqlite3.connect(cfg.db_path).iterdump())
    assert len(calls(cfg)) >= 3
    assert "or-test-key" not in database
    assert "or-test-key" not in caplog.text


def test_a_waiting_invoice_booked_by_hand_in_the_meantime_is_left_alone(service, anaf, cfg, openrouter):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))
    openrouter.fail_with = [402]
    service.sync(VALID_CUI)  # stays pending
    service.mark_uploaded(["3001"])

    result = service.sync(VALID_CUI)

    assert result["classification"]["classified"] == 0
    assert not cfg.saga_dir.exists()
    assert len(openrouter.requests) == 1  # not asked again


def test_review_leaves_out_invoices_already_booked_by_hand(service, in_review):
    service.mark_uploaded(["3001"])

    assert service.review()["count"] == 0


# --- what the screen shows about one invoice, and about Jev's work ---------------------------


def test_invoice_view_gathers_everything_the_screen_shows(service, anaf, cfg, in_review):
    service.save_client(VALID_CUI, "Alfa Construct SRL")

    view = service.invoice_view("3001")

    assert (view["ok"], view["invoice"]["id"], view["client_name"]) == (True, "3001", "Alfa Construct SRL")
    assert view["xml"].startswith("<?xml") and "Piese de schimb" in view["xml"]
    assert view["saga_xml"] is None  # in review: no file yet
    document = view["document"]
    assert (document["supplier"]["name"], document["customer"]["cui"]) == ("Furnizor SRL", "12345674")
    assert document["lines"] == [{
        "number": 1, "description": "Piese de schimb", "seller_code": None, "barcode": None,
        "commodity_codes": [], "unit": "H87", "unit_name": "BUC", "quantity": "1",
        "unit_price": "900.00", "value": "900.00", "vat_percent": "19", "vat_category": "S",
    }]
    assert (document["total_without_vat"], document["total_vat"], document["total_payable"]) == (
        "900.00", "171.00", "1071.00"
    )
    assert view["jev"]["probabilities"] == {"628": 0.41}
    assert view["jev"]["cost_usd"] == 0.00002


def test_an_invoice_with_an_earlier_balance_is_listed_at_what_it_is_worth(service, anaf, cfg):
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL, prepaid="-3123.88"))
    (saved,) = service.sync(VALID_CUI)["new"]

    (listed,) = service.invoices(cui=VALID_CUI)["invoices"]
    view = service.invoice_view("3001")

    assert (saved["total_with_vat"], saved["total_payable"]) == ("535.50", "3659.38")
    assert (listed["total_with_vat"], listed["total_payable"]) == ("535.50", "3659.38")
    assert view["invoice"]["total_with_vat"] == "535.50"
    document = view["document"]
    assert (document["total_with_vat"], document["total_prepaid"], document["total_rounding"]) == (
        "535.50", "-3123.88", None
    )
    assert document["total_payable"] == "3659.38"  # still what is left to pay, as other programs read it


def test_an_earlier_balance_never_reaches_the_file_for_saga(service, anaf, cfg):
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL, prepaid="-3123.88"))
    service.sync(VALID_CUI)

    view = service.invoice_view("3001")
    on_disk = Path(view["invoice"]["saga_xml_path"]).read_text(encoding="utf-8")

    for written in (view["saga_xml"], on_disk):
        assert "<Valoare>450.00</Valoare>" in written and "<TVA>85.50</TVA>" in written
        assert "3123.88" not in written and "3659.38" not in written


def test_a_message_that_is_no_invoice_is_worth_nothing(service, anaf, cfg):
    anaf.add("3001", tip="ERORI FACTURA", xml=b"<header><Error errorMessage='x'/></header>")
    service.sync(VALID_CUI)

    assert service.invoice("3001")["invoice"]["total_with_vat"] is None


def test_invoice_view_includes_the_saga_file_once_it_exists(service, anaf, cfg):
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))
    service.sync(VALID_CUI)

    view = service.invoice_view("3001")

    assert "<Cont>6022</Cont>" in view["saga_xml"]
    assert view["jev"] is None  # decided by a rule: Jev was never asked
    assert view["client_name"] is None  # not in the client list


def test_invoice_view_of_a_message_that_is_not_an_invoice_has_no_document(service, anaf):
    anaf.add("3001", tip="ERORI FACTURA", xml=ANAF_ERROR_NOTICE.encode())
    service.sync(VALID_CUI)

    view = service.invoice_view("3001")

    assert (view["document"], view["saga_xml"]) == (None, None)
    assert "errorMessage" in view["xml"]
    assert error_code(lambda: service.invoice_view("nope")) == "not_found"


def test_an_invoices_part_for_saga_is_shown_from_what_is_stored_not_from_the_file(service, anaf, cfg):
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))
    service.sync(VALID_CUI)
    saga_file(cfg).unlink()  # deleted by hand

    assert "<Cont>6022</Cont>" in service.invoice_view("3001")["saga_xml"]


def test_jev_calls_are_listed_newest_first_with_the_invoice_they_were_about(service, anaf, openrouter):
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS, number="A1"))
    anaf.add("3002", xml=rich_invoice_xml(lines=[line("Ceva rar", "10.00")], number="A2"))
    openrouter.answer_for("rar", "628", confidence=0.3)
    service.sync(VALID_CUI)

    result = service.jev_calls()

    assert (result["ok"], result["count"]) == (True, 2)
    newest, oldest = result["calls"]
    assert (newest["message_id"], newest["invoice_number"], newest["choice"], newest["confidence"]) == (
        "3002", "A2", "628", 0.3
    )
    assert (newest["classification_status"], newest["client_name"]) == ("review", "Alfa Construct SRL")
    assert (oldest["message_id"], oldest["supplier_name"], oldest["cost_usd"], oldest["error"]) == (
        "3001", "Furnizor SRL", 0.00002, None
    )


def test_jev_calls_can_be_narrowed_and_limited(service, anaf):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS, number="A1"))
    anaf.add("3002", xml=rich_invoice_xml(lines=PARTS, number="A2"))
    service.sync(VALID_CUI)

    assert service.jev_calls(limit=1)["count"] == 1
    assert service.jev_calls(since="2026-11-12")["count"] == 0
    assert service.jev_calls(until="2026-11-11", cui=VALID_CUI)["count"] == 2
    assert service.jev_calls(cui=OTHER_VALID_CUI)["count"] == 0


def test_a_failed_call_is_listed_with_its_error_and_no_answer(service, anaf, openrouter):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))
    openrouter.fail_with = [402]
    service.sync(VALID_CUI)

    (call,) = service.jev_calls()["calls"]

    assert (call["choice"], call["confidence"]) == (None, None)
    assert "credit" in call["error"]


# --- found by the review of the screen -------------------------------------------------------


def test_a_supplier_in_a_rule_may_be_typed_with_ro_and_spaces(service, anaf, openrouter):
    service.save_rule(name="materiale", cont="302", supplier_cuis=[" ro 87654321 "])
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))  # from supplier RO87654321

    (entry,) = service.sync(VALID_CUI)["new"]

    assert (entry["cont"], entry["classification_method"]) == ("302", "rules")
    assert service.rules_overview()["rules"][-1]["supplier_cuis"] == ["87654321"]


def test_a_foreign_supplier_in_a_rule_is_kept_as_an_id_not_refused(service):
    service.save_rule(name="import", cont="371", supplier_cuis=["de 123456789"])

    assert service.rules_overview()["rules"][-1]["supplier_cuis"] == ["DE123456789"]


def test_the_folder_of_an_invoice_is_opened_where_its_file_really_is(service, anaf, cfg, tmp_path, monkeypatch):
    revealed = []
    monkeypatch.setattr(service_module, "_reveal", revealed.append)
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))
    service.sync(VALID_CUI)
    service.set_saga_output(folder=str(tmp_path / "folderul nou"))  # what is waiting moves there

    result = service.open_saga_folder(message_id="3001")

    assert revealed == [tmp_path / "folderul nou" / VALID_CUI]
    assert result["folder"] == str(tmp_path / "folderul nou" / VALID_CUI)
    assert error_code(lambda: service.open_saga_folder(message_id="nope")) == "not_found"


def test_opening_the_folder_of_an_invoice_without_a_file_is_refused(service, in_review, monkeypatch):
    monkeypatch.setattr(service_module, "_reveal", lambda folder: None)

    assert error_code(lambda: service.open_saga_folder(message_id="3001")) == "not_found"


def test_a_chosen_folder_with_romanian_letters_comes_back_intact(monkeypatch):
    import subprocess

    chosen = "C:/Contabilitate/Clienți și țări"

    def fake_run(command, **options):
        assert options.get("text") is not True  # bytes, so no code page can mangle the path
        return subprocess.CompletedProcess(command, 0, stdout=chosen.encode("utf-8"), stderr=b"")

    monkeypatch.setattr(service_module.subprocess, "run", fake_run)

    assert service_module._ask_for_folder("C:/", "Folderul pentru SAGA") == str(service_module.Path(chosen))
