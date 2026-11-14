"""Classifying a trial invoice the way a real one is, and saving nothing but Jev's cost."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from efactura import journal
from efactura.api import create_app
from efactura.config import load_config
from efactura.errors import EfacturaError
from efactura.rules import Rule, Rulebook
from efactura.service import RULE_TEST, Service
from efactura.store import Store

from helpers import VALID_CUI, FakeAnaf, FakeOpenRouter, set_rulebook

NOW = datetime(2026, 11, 14, 9, 30, tzinfo=timezone(timedelta(hours=2)))
KEY = {"X-API-Key": "local-key"}
CIMENT = [{"description": "Ciment Portland 40 kg", "quantity": "20", "unit_price": "28.50"}]
MOTORINA = [{"description": "Motorina Euro 5", "quantity": "40", "unit_price": "7.20"}]
CONSULTANTA = [{"description": "Consultanta de specialitate", "quantity": "1", "unit_price": "900"}]


def settings(tmp_path, key='api_key = "or-test-key"'):
    path = tmp_path / "config.toml"
    path.write_text(
        f"[anaf]\nclient_id = \"id\"\nclient_secret = \"secret\"\ntoken_file = '{tmp_path / 'tokens.json'}'\n"
        f'[api]\nkey = "local-key"\n[openrouter]\n{key}\n', encoding="utf-8")
    return load_config(path)


@pytest.fixture
def cfg(tmp_path):
    cfg = settings(tmp_path)
    set_rulebook(cfg.db_path, Rulebook(
        accounts={"302": "Materiale consumabile", "6022": "Combustibil", "612": "Chirii", "628": "Alte servicii"},
        rules=(Rule("combustibil", "6022", keywords=("motorina",)),),
        instructions="Alege contul facturii.",
    ))
    return cfg


@pytest.fixture
def openrouter():
    answers = FakeOpenRouter()
    answers.answer_for("ciment", "302", confidence=0.93)
    answers.answer_for("consultanta", "628", confidence=0.61)
    return answers


@pytest.fixture
def desk(cfg, openrouter):
    anaf = FakeAnaf()
    anaf.openrouter = openrouter
    return Service(cfg, http=anaf.client(), now=lambda: NOW)


def test_a_rule_that_fits_decides_and_jev_is_not_asked(desk, openrouter):
    result = desk.test_rules(lines=MOTORINA, supplier_name="Rompetrol", supplier_cui="1860712")

    assert (result["decided_by"], result["cont"], result["account_description"]) == ("rule", "6022", "Combustibil")
    assert result["rule"] == {"name": "combustibil", "line": 1} and result["deciding_line"] == "Motorina Euro 5"
    assert result["jev"] is None and result["suggestion"] is None and openrouter.requests == []


def test_with_no_rule_fitting_jev_is_asked_and_its_account_stands(desk, openrouter):
    result = desk.test_rules(lines=CIMENT, supplier_name="Dedeman SRL", supplier_cui="2816464")

    assert (result["decided_by"], result["cont"], result["why_not"]) == ("jev", "302", None)
    asked = result["jev"]
    assert (asked["choice"], asked["confidence"], asked["threshold"], asked["refused"], asked["error"]) == ("302", 0.93, 0.8, False, None)
    assert asked["cost_usd"] == pytest.approx(0.00002) and len(openrouter.requests) == 1
    assert result["suggestion"]["cont"] == "302" and "ciment" in result["suggestion"]["words"]
    assert result["suggestion"]["supplier_name"] == "Dedeman SRL"


def test_jev_not_sure_enough_leaves_it_to_a_person(desk):
    result = desk.test_rules(lines=CONSULTANTA)

    assert (result["decided_by"], result["cont"], result["why_not"]) == ("nobody", None, "below_threshold")
    assert (result["jev"]["choice"], result["jev"]["confidence"]) == ("628", 0.61)
    assert result["suggestion"]["cont"] == "628"


def test_asking_jev_directly_skips_the_rules(desk, openrouter):
    result = desk.test_rules(lines=MOTORINA, ask="jev_only")

    assert (result["decided_by"], result["cont"], result["rule"]) == ("jev", "628", None)
    assert len(openrouter.requests) == 1
    assert result["suggestion"] is None  # a rule of the rulebook already fits this invoice


def test_what_a_saved_invoice_carries_reaches_jev(desk, openrouter):
    carried = [{"description": "Ciment Portland", "quantity": "20", "unit_price": "28.50", "unit": "KGM", "vat_percent": "9"}]

    desk.test_rules(lines=carried, currency="EUR", credit_note=True)

    asked = openrouter.requests[-1]["state"]  # `requests` holds the bodies the stand-in was sent
    assert asked["factura"]["moneda"] == "EUR" and asked["linii"][0]["um"] == "KGM"
    assert str(asked["linii"][0]["cota_tva"]).startswith("9")


def test_the_codes_of_a_line_let_the_rules_decide_as_they_did_for_the_real_invoice(desk, openrouter):
    desk.save_rule(name="cod articol", cont="302", item_codes=["ART-77"])
    desk.save_rule(name="servicii it", cont="628", commodity_prefixes=["7226"])
    plain = {"description": "Diverse", "quantity": "1", "unit_price": "10"}

    by_code = desk.test_rules(lines=[{**plain, "seller_code": "ART-77"}])
    by_prefix = desk.test_rules(lines=[{**plain, "commodity_codes": ["72260000"]}])

    assert (by_code["decided_by"], by_code["rule"]["name"]) == ("rule", "cod articol")
    assert (by_prefix["decided_by"], by_prefix["rule"]["name"]) == ("rule", "servicii it")
    assert openrouter.requests == []  # a rule decided, so Jev was neither asked nor paid


def test_a_value_carried_with_a_line_is_its_value_and_decides_which_line_counts(cfg, desk, openrouter):
    # A line discount: 10 × 100 would be 1000, but the invoice says 400, less than the fuel line.
    lines = [
        {"description": "Ciment Portland", "quantity": "10", "unit_price": "100", "value": "400.00"},
        {"description": "Motorina Euro 5", "quantity": "1", "unit_price": "600", "value": "600.00"},
    ]
    api = TestClient(create_app(cfg, service_factory=lambda cfg: desk))

    desk.test_rules(lines=lines, ask="jev_only")
    reply = api.post("/rules/test", headers=KEY, json={"lines": lines}).json()  # the route closes the service

    assert (reply["decided_by"], reply["deciding_line"], reply["rule"]["line"]) == ("rule", "Motorina Euro 5", 2)
    asked = openrouter.requests[-1]["state"]
    assert [line["valoare_fara_tva"] for line in asked["linii"]] == ["400.00", "600.00"]
    assert asked["linia_cu_valoarea_cea_mai_mare"] == 2


def test_a_rule_for_one_client_applies_only_when_that_client_is_chosen(desk):
    desk.save_client(VALID_CUI, "Alfa Construct SRL")
    desk.save_rule(name="chirie", cont="612", keywords=["chirie"], client_cui=VALID_CUI)
    rent = [{"description": "Chirie birou noiembrie", "quantity": "1", "unit_price": "2000"}]

    assert desk.test_rules(lines=rent, client_cui=VALID_CUI)["decided_by"] == "rule"
    assert desk.test_rules(lines=rent)["decided_by"] == "jev"  # the general rules only


def test_nothing_is_saved_but_the_cost(desk, cfg):
    desk.test_rules(lines=CIMENT, client_cui=VALID_CUI)

    assert desk.invoices()["invoices"] == [] and desk.rule_suggestions()["count"] == 0
    assert not cfg.saga_dir.exists() or not any(cfg.saga_dir.rglob("*.xml"))
    for costs in (desk.costs(since="2026-01-01"), desk.costs(since="2026-01-01", cui=VALID_CUI)):
        assert (costs["calls"], costs["invoices"]) == (1, 0) and costs["cost_usd"] == pytest.approx(0.00002)
    (call,) = desk.jev_calls()["calls"]
    assert (call["message_id"], call["cui"], call["choice"]) == (RULE_TEST, VALID_CUI, "302")


def test_a_trial_is_in_the_total_but_not_in_the_average_per_invoice(desk, cfg):
    store = Store(cfg.db_path)
    for message_id, cost in (("3001", 0.5), (RULE_TEST, 0.25)):
        store.add_jev_call(
            message_id=message_id, cui=VALID_CUI, called_at=NOW.isoformat(), model="m", request_json="{}",
            response_json=None, http_status=200, input_tokens=1, output_tokens=1, cost_usd=cost, duration_ms=5, error=None,
        )
    store.close()

    costs = desk.costs(since="2026-01-01")

    assert (costs["calls"], costs["invoices"]) == (2, 1) and costs["cost_usd"] == pytest.approx(0.75)
    assert costs["average_cost_per_invoice_usd"] == pytest.approx(0.5)


@pytest.mark.parametrize("change, why", [
    ({"lines": []}, "no_lines"),
    ({"lines": [{"description": "  ", "quantity": "1", "unit_price": "1"}]}, "no_lines"),
])
def test_an_invoice_with_nothing_on_it_is_not_sent_anywhere(desk, openrouter, change, why):
    result = desk.test_rules(**change)

    assert (result["decided_by"], result["why_not"], result["jev"]) == ("nobody", why, None) and openrouter.requests == []


def test_without_a_key_or_accounts_jev_cannot_be_asked(tmp_path, openrouter):
    no_key = Service(settings(tmp_path, key=""), http=FakeAnaf().client(), now=lambda: NOW)
    set_rulebook(no_key.cfg.db_path, Rulebook(accounts={"302": "Materiale"}, rules=(), instructions="."))
    assert no_key.test_rules(lines=CIMENT)["why_not"] == "no_key"

    (tmp_path / "second").mkdir()
    no_accounts = Service(settings(tmp_path / "second"), http=FakeAnaf().client(), now=lambda: NOW)
    set_rulebook(no_accounts.cfg.db_path, Rulebook(accounts={}, rules=(), instructions="."))
    assert no_accounts.test_rules(lines=CIMENT)["why_not"] == "no_accounts"


def test_a_jev_that_fails_is_reported_at_once_not_tried_again(desk, openrouter):
    openrouter.fail_with = ["unreachable", "unreachable"]

    result = desk.test_rules(lines=CIMENT)

    assert (result["decided_by"], result["why_not"]) == ("nobody", "jev_failed")
    assert result["jev"]["error"] and len(openrouter.fail_with) == 1  # one attempt used, one left


def test_numbers_as_people_type_them(desk):
    typed = [{"description": "Ciment", "quantity": " 20 ", "unit_price": "28,50"}]
    assert desk.test_rules(lines=typed)["decided_by"] == "jev"

    for bad in (
        [{"description": "Ciment", "quantity": "abc", "unit_price": "1"}],
        [{"description": "Ciment", "quantity": "", "unit_price": "1"}],
        [{"description": "x" * 501, "quantity": "1", "unit_price": "1"}],
        CIMENT * 51,
    ):
        with pytest.raises(EfacturaError) as refused:
            desk.test_rules(lines=bad)
        assert refused.value.code == "invalid_input"
    with pytest.raises(EfacturaError):
        desk.test_rules(lines=CIMENT, ask="something else")


def test_the_route_and_the_journal(cfg, desk):
    api = TestClient(create_app(cfg, service_factory=lambda cfg: desk))

    reply = api.post("/rules/test", headers=KEY, json={"lines": MOTORINA, "client_cui": None})

    assert reply.status_code == 200 and reply.json()["decided_by"] == "rule"
    tested = [line for line in journal.events(cfg.db_path)["events"] if line["event"] == "rule.tested"]
    assert tested[0]["data"]["decided_by"] == "rule" and tested[0]["data"]["asked_jev"] is False
