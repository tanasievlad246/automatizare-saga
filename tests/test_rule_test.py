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
    assert result["rule"] == {
        "name": "combustibil", "line": 1, "condition": "keyword", "found": "motorina", "prefix": None,
        "client_only": False, "also": [],
    }
    assert result["deciding_line"] == "Motorina Euro 5"
    assert result["jev"] is None and result["suggestion"] is None and openrouter.requests == []
    # One line is one account, as for any client: the answer is that line.
    assert result["per_line"] is False and [entry["line"] for entry in result["lines"]] == [1]


# --- line by line, as the program decides a client's invoices since 0.9.0 -------------

FOUR_LINES = [
    {"description": "Motorina Euro 5", "quantity": "100", "unit_price": "7,20"},  # 720, the largest
    {"description": "Ciment Portland 40 kg", "quantity": "20", "unit_price": "28,50"},  # 570
    {"description": "Consultanta tehnica", "quantity": "1", "unit_price": "400"},
    {"description": "Discount comercial", "quantity": "1", "unit_price": "-50"},
]


def test_without_a_client_each_line_is_decided_on_its_own_and_says_why(desk, openrouter):
    result = desk.test_rules(lines=FOUR_LINES, supplier_name="Dedeman SRL", supplier_cui="2816464")

    assert result["per_line"] is True
    by_line = {entry["line"]: entry for entry in result["lines"]}
    assert [(entry["decided_by"], entry["cont"]) for entry in result["lines"]] == [
        ("rule", "6022"), ("jev", "302"), ("nobody", None), ("follows", "6022"),
    ]
    assert (by_line[1]["rule"]["name"], by_line[1]["rule"]["found"]) == ("combustibil", "motorina")
    assert (by_line[1]["description"], by_line[1]["value"]) == ("Motorina Euro 5", "720.00")
    assert (by_line[2]["jev"]["choice"], by_line[2]["jev"]["confidence"], by_line[2]["account_description"]) == (
        "302", 0.93, "Materiale consumabile")
    assert (by_line[3]["why_not"], by_line[3]["jev"]["choice"]) == ("below_threshold", "628")
    assert (by_line[4]["follows"], by_line[4]["jev"], by_line[4]["account_description"]) == (1, None, "Combustibil")
    # Jev is asked about the two lines no rule decided, once each, with the question for one line.
    assert [request["state"]["linia"]["descriere"] for request in openrouter.requests] == [
        "Ciment Portland 40 kg", "Consultanta tehnica"]
    assert (result["waiting"], result["jev_calls"], result["cost_usd"]) == (1, 2, pytest.approx(0.00004))
    # The invoice as a whole, as the program keeps it: its largest line's, and an account only
    # once every line has one.
    assert (result["decided_by"], result["cont"], result["why_not"]) == ("nobody", None, "lines_left")
    assert result["accounts"]["302"] == "Materiale consumabile"


def test_a_client_with_one_account_per_invoice_is_tried_the_old_way(desk, openrouter):
    desk.save_client(VALID_CUI, "Alfa Construct SRL")
    desk.set_client_per_line(VALID_CUI, False)

    result = desk.test_rules(lines=FOUR_LINES, client_cui=VALID_CUI)

    assert result["per_line"] is False and (result["decided_by"], result["cont"]) == ("rule", "6022")
    assert [entry["line"] for entry in result["lines"]] == [1] and openrouter.requests == []


def test_a_client_switched_to_line_by_line_is_tried_line_by_line(desk):
    desk.save_client(VALID_CUI, "Alfa Construct SRL")

    assert desk.test_rules(lines=FOUR_LINES, client_cui=VALID_CUI)["per_line"] is True


def test_lines_that_say_the_same_thing_put_one_question_to_jev(desk, openrouter):
    twice = [CIMENT[0], {**CIMENT[0], "quantity": "3"}]

    result = desk.test_rules(lines=twice)

    assert len(openrouter.requests) == 1 and result["jev_calls"] == 1
    assert [(entry["cont"], entry["same_as"]) for entry in result["lines"]] == [("302", None), ("302", 1)]
    (call,) = desk.jev_calls()["calls"]
    assert call["message_id"] == RULE_TEST


def test_what_jev_was_sent_comes_back_with_its_answer(desk):
    result = desk.test_rules(lines=FOUR_LINES, supplier_name="Dedeman SRL", supplier_cui="2816464")

    sent = result["lines"][1]["jev"]["sent"]
    assert sent["question"].startswith("Pe ce cont contabil se înregistrează această linie")
    assert sent["state"]["furnizor"] == {"nume": "Dedeman SRL", "cui": "2816464"}
    assert (sent["state"]["linia"]["descriere"], sent["state"]["linia"]["valoare_fara_tva"]) == ("Ciment Portland 40 kg", "570.00")
    # The whole-invoice question, for a client with one account per invoice, comes back the same way.
    whole = desk.test_rules(lines=CIMENT)["jev"]["sent"]
    assert whole["question"] == "Alege contul facturii." and whole["state"]["linii"][0]["descriere"] == "Ciment Portland 40 kg"


def test_the_ways_jev_can_leave_a_line_without_an_account_can_be_told_apart(desk, openrouter):
    openrouter.answer_for("nimic", "altul", confidence=0.72, probabilities_extra={"628": 0.18})
    openrouter.answer_for("refuz", "", refusal=True)
    openrouter.answer_for("nesigur", "628", confidence=None)
    lines = [{"description": f"{word} de facturat", "quantity": "1", "unit_price": "10"} for word in ("nimic", "refuz", "nesigur")]

    none_fits, refused, unsure = desk.test_rules(lines=lines)["lines"]

    assert none_fits["why_not"] == "jev_declined" and none_fits["jev"]["choice"] is None
    assert none_fits["jev"]["probabilities"] == {"altul": 0.72, "628": 0.18}
    assert refused["jev"]["refused"] is True and refused["jev"]["probabilities"] == {}
    assert (unsure["jev"]["choice"], unsure["jev"]["confidence"], unsure["why_not"]) == ("628", None, "jev_declined")


def test_a_rule_says_which_condition_matched_and_what_else_would_have(desk):
    desk.save_client(VALID_CUI, "Alfa Construct SRL")
    desk.save_rule(name="Dedeman", cont="371", supplier_cuis=["2816464"])
    desk.save_rule(name="ciment", cont="302", item_codes=["10023"], client_cui=VALID_CUI)
    desk.save_rule(name="carburanti", cont="6022", commodity_prefixes=["2710"])
    lines = [
        {"description": "Ciment", "quantity": "1", "unit_price": "100", "seller_code": "10023"},
        {"description": "Aditiv", "quantity": "1", "unit_price": "50", "commodity_codes": ["27101943"]},
    ]

    first, second = desk.test_rules(lines=lines, client_cui=VALID_CUI, supplier_cui="2816464")["lines"]

    # The client's own rules are checked first.
    assert {key: first["rule"][key] for key in ("name", "condition", "found", "client_only", "also")} == {
        "name": "ciment", "condition": "seller_code", "found": "10023", "client_only": True, "also": ["Dedeman"]}
    assert (second["rule"]["name"], second["rule"]["condition"]) == ("Dedeman", "supplier_cui")
    assert second["rule"]["also"] == ["carburanti"]


def test_without_a_key_the_lines_a_rule_decides_still_get_their_account(tmp_path):
    no_key = Service(settings(tmp_path, key=""), http=FakeAnaf().client(), now=lambda: NOW)
    set_rulebook(no_key.cfg.db_path, Rulebook(
        accounts={"6022": "Combustibil"}, rules=(Rule("combustibil", "6022", keywords=("motorina",)),), instructions="."))

    fuel, cement, *_ = no_key.test_rules(lines=FOUR_LINES)["lines"]

    assert (fuel["decided_by"], fuel["cont"]) == ("rule", "6022")
    assert (cement["decided_by"], cement["why_not"], cement["jev"]) == ("nobody", "no_key", None)


def test_asking_jev_directly_skips_the_rules_on_every_line_but_a_discount_still_follows(desk, openrouter):
    result = desk.test_rules(lines=FOUR_LINES, ask="jev_only")

    assert [entry["decided_by"] for entry in result["lines"]] == ["jev", "jev", "nobody", "follows"]
    assert len(openrouter.requests) == 3 and result["lines"][3]["cont"] == "628"  # the default answer, on line 1


def test_a_line_jev_cannot_answer_is_told_and_the_others_keep_theirs(desk, openrouter):
    openrouter.fail_for = {"consultanta": 500}

    result = desk.test_rules(lines=FOUR_LINES)

    assert [entry["why_not"] for entry in result["lines"]] == [None, None, "jev_failed", None]
    assert result["lines"][2]["jev"]["http_status"] == 500 and result["lines"][1]["cont"] == "302"


THREE_ITEMS = [{"description": f"Articol {word}", "quantity": "1", "unit_price": "10"} for word in ("unu", "doi", "trei")]


@pytest.mark.parametrize("failure", [401, 402, 429, 503, "unreachable"])
def test_once_openrouter_fails_as_a_whole_the_lines_left_are_not_sent(desk, openrouter, failure):
    # As the program does: it stops at such a failure and the invoice waits to be tried again.
    openrouter.fail_with = [failure]

    result = desk.test_rules(lines=THREE_ITEMS)

    assert len(openrouter.requests) == 1 and result["jev_calls"] == 1
    assert [entry["why_not"] for entry in result["lines"]] == ["jev_failed", "not_asked", "not_asked"]
    assert [entry["jev"] is None for entry in result["lines"]] == [False, True, True]
    assert result["jev_stopped"] == {"line": 1, "http_status": None if failure == "unreachable" else failure,
                                     "error": result["lines"][0]["jev"]["error"]}


def test_a_failure_about_one_line_alone_does_not_stop_the_others(desk, openrouter):
    openrouter.fail_for = {"unu": 400}

    result = desk.test_rules(lines=THREE_ITEMS)

    assert [entry["why_not"] for entry in result["lines"]] == ["jev_failed", None, None]
    assert result["jev_calls"] == 3 and result["jev_stopped"] is None


def test_with_the_rules_skipped_the_reason_does_not_speak_of_rules(tmp_path):
    no_key = Service(settings(tmp_path, key=""), http=FakeAnaf().client(), now=lambda: NOW)
    set_rulebook(no_key.cfg.db_path, Rulebook(accounts={"302": "Materiale"}, rules=(), instructions="."))

    by_line = no_key.test_rules(lines=THREE_ITEMS, ask="jev_only")["lines"][0]["reason"]
    whole = no_key.test_rules(lines=CIMENT, ask="jev_only")["reason"]

    assert by_line.startswith("The rules were skipped, and OpenRouter is not set up")
    assert whole.startswith("The rules were skipped, and OpenRouter is not set up")


def test_the_rule_proposed_comes_from_a_line_jev_gave_an_account(desk):
    result = desk.test_rules(lines=FOUR_LINES, supplier_name="Dedeman SRL", supplier_cui="2816464")

    # Of the two lines Jev answered, the larger: "Ciment" (570), not "Consultanta" (400).
    assert (result["suggestion"]["cont"], result["suggestion"]["line"], result["suggestion"]["from_line"]) == (
        "302", "Ciment Portland 40 kg", 2)


def test_a_trial_line_by_line_is_one_line_in_the_journal(cfg, desk):
    desk.test_rules(lines=FOUR_LINES)

    (tested,) = [line for line in journal.events(cfg.db_path)["events"] if line["event"] == "rule.tested"]
    assert tested["data"]["asked_jev"] is True and tested["data"]["cost_usd"] == pytest.approx(0.00004)
    assert "4 lines" in tested["message"]


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
    desk.save_client(VALID_CUI, "Alfa Construct SRL")
    desk.set_client_per_line(VALID_CUI, False)  # one account per invoice: decided by its largest line

    desk.test_rules(lines=lines, ask="jev_only", client_cui=VALID_CUI)
    reply = api.post("/rules/test", headers=KEY, json={"lines": lines, "client_cui": VALID_CUI}).json()  # the route closes the service

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
    # The list for that client has it too, as "Costuri Jev" shows it under a client filter.
    (for_client,) = desk.jev_calls(cui=VALID_CUI)["calls"]
    assert (for_client["message_id"], for_client["cost_usd"]) == (RULE_TEST, pytest.approx(0.00002))


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


@pytest.mark.parametrize("failure, status", [(401, 401), (402, 402), (403, 403), (502, 502), ("unreachable", None)])
def test_a_failed_call_says_what_openrouter_answered(desk, openrouter, failure, status):
    # A refused key or an empty account is not helped by waiting; the screen tells them apart by this.
    openrouter.fail_with = [failure]

    result = desk.test_rules(lines=CIMENT)

    assert (result["why_not"], result["jev"]["http_status"]) == ("jev_failed", status)


def test_an_answered_call_carries_its_status_too(desk):
    assert desk.test_rules(lines=CIMENT)["jev"]["http_status"] == 200


def test_numbers_as_people_type_them(desk):
    typed = [{"description": "Ciment", "quantity": " 20 ", "unit_price": "28,50"}]
    assert desk.test_rules(lines=typed)["decided_by"] == "jev"

    for bad in (
        [{"description": "Ciment", "quantity": "abc", "unit_price": "1"}],
        [{"description": "x" * 501, "quantity": "1", "unit_price": "1"}],
        CIMENT * 51,
    ):
        with pytest.raises(EfacturaError) as refused:
            desk.test_rules(lines=bad)
        assert refused.value.code == "invalid_input"
    with pytest.raises(EfacturaError):
        desk.test_rules(lines=CIMENT, ask="something else")


def test_a_row_with_only_a_description_is_one_at_no_price_and_a_rule_on_a_word_decides_it(cfg, desk, openrouter):
    desk.save_rule(name="telefon", cont="628", keywords=["telefon"])

    by_rule = desk.test_rules(lines=[{"description": "abonament telefon", "quantity": "", "unit_price": ""}])
    desk.test_rules(lines=[{"description": "Ciment", "quantity": " ", "unit_price": ""}], ask="jev_only")
    asked = openrouter.requests[-1]["state"]["linii"][0]
    # From another program, the numbers may be left out altogether.
    api = TestClient(create_app(cfg, service_factory=lambda cfg: desk))
    reply = api.post("/rules/test", headers=KEY, json={"lines": [{"description": "abonament telefon"}]})

    assert (by_rule["decided_by"], by_rule["rule"]["name"]) == ("rule", "telefon")
    assert (asked["cantitate"], asked["valoare_fara_tva"]) == ("1", "0")
    assert reply.status_code == 200 and reply.json()["decided_by"] == "rule"


@pytest.mark.parametrize("typed, read", [
    ("12 000", "12000"),
    ("12\u00a0000", "12000"),  # the space a copied number often carries
    ("1.234,50", "1234.50"),
    ("28,50", "28.50"),
    ("28.50", "28.50"),
    (" 20 ", "20"),
])
def test_numbers_are_read_as_romanians_write_them(desk, openrouter, typed, read):
    desk.test_rules(lines=[{"description": "Ciment", "quantity": typed, "unit_price": typed}], ask="jev_only")

    (asked,) = openrouter.requests[-1]["state"]["linii"]
    assert asked["cantitate"] == read


@pytest.mark.parametrize("quantity, price", [
    ("abc", "1"),
    ("1,234,50", "1"),
    ("NaN", "1"),
    ("1e999999", "28,50"),  # too large to compute with: once a 500 with decimal.Overflow
    ("2", "1e999999"),
    ("1e-999999", "1"),  # a million digits to write out
])
def test_a_number_that_cannot_be_read_or_computed_with_is_bad_input(cfg, desk, quantity, price):
    api = TestClient(create_app(cfg, service_factory=lambda cfg: desk))

    reply = api.post("/rules/test", headers=KEY, json={"lines": [{"description": "Ciment", "quantity": quantity, "unit_price": price}]})

    assert (reply.status_code, reply.json()["error"]["code"]) == (400, "invalid_input")


def test_a_negative_quantity_is_accepted_as_a_return(cfg, desk):
    api = TestClient(create_app(cfg, service_factory=lambda cfg: desk))

    reply = api.post("/rules/test", headers=KEY, json={"lines": [{"description": "Retur motorina", "quantity": "-10", "unit_price": "7,20"}]})

    assert reply.status_code == 200 and (reply.json()["decided_by"], reply.json()["deciding_line"]) == ("rule", "Retur motorina")


def test_the_route_and_the_journal(cfg, desk):
    api = TestClient(create_app(cfg, service_factory=lambda cfg: desk))

    reply = api.post("/rules/test", headers=KEY, json={"lines": MOTORINA, "client_cui": None})

    assert reply.status_code == 200 and reply.json()["decided_by"] == "rule"
    tested = [line for line in journal.events(cfg.db_path)["events"] if line["event"] == "rule.tested"]
    assert tested[0]["data"]["decided_by"] == "rule" and tested[0]["data"]["asked_jev"] is False
