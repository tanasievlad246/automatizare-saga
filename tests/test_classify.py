import json
from decimal import Decimal

import pytest

from efactura import classify
from efactura.classify import (
    NONE_OF_THESE, decide_by_rules, deciding_line, jev_request, read_jev_answer, subject_of,
)
from efactura.errors import EfacturaError
from efactura.invoice import parse_invoice
from efactura.rules import Rule, Rulebook, Subject, any_of

from helpers import line, rich_invoice_xml

BOOK = Rulebook(
    accounts={
        "6022": "Combustibil pentru vehicule.",
        "626": "Telefonie si internet.",
        "371": "Marfuri pentru revanzare.",
    },
    rules=(
        Rule("combustibil", "6022", keywords=("motorina", "benzina")),
        Rule("telecom", "626", keywords=("abonament telefon*",)),
        Rule("papetarie", "3028", item_codes=("TN-2420",), commodity_prefixes=("3019",)),
        Rule("chirie", "612", supplier_cuis=("11112222",)),
    ),
    instructions="Alege contul pe care se inregistreaza factura.",
)


def invoice_of(*lines, **kwargs):
    return parse_invoice(rich_invoice_xml(lines=list(lines), **kwargs))


# --- which line decides ----------------------------------------------------------


def test_the_line_with_the_largest_value_decides():
    invoice = invoice_of(line("Transport", "40.00"), line("Motorina", "450.00"), line("Ulei", "90.00"))

    assert deciding_line(invoice).description == "Motorina"


def test_a_large_negative_line_outweighs_a_small_positive_one():
    invoice = invoice_of(line("Corectie", "-500.00"), line("Taxa", "20.00"))

    assert deciding_line(invoice).description == "Corectie"


def test_of_two_equal_lines_the_first_decides():
    invoice = invoice_of(line("Prima", "100.00"), line("A doua", "100.00"))

    assert deciding_line(invoice).description == "Prima"


def test_an_invoice_without_lines_has_no_deciding_line():
    assert deciding_line(invoice_of()) is None


# --- what a rule reads -------------------------------------------------------------


def test_the_subject_is_the_supplier_and_the_deciding_line():
    invoice = invoice_of(
        line("Transport", "40.00"),
        line("Toner negru", "450.00", seller_code="TN-2420", barcode="5941234567890", commodity="30125110"),
        supplier_cui="RO11112222",
    )

    assert subject_of(invoice) == Subject(
        supplier_cui="11112222", description="Toner negru", seller_code="TN-2420",
        barcode="5941234567890", commodity_codes=("30125110",),
    )


def test_an_invoice_without_lines_has_no_subject():
    assert subject_of(invoice_of()) is None


def test_a_rule_is_matched_against_a_subject_alone():
    assert BOOK.rule_for(Subject("87654321", "Motorină Euro 5")).name == "combustibil"
    assert BOOK.rule_for(Subject("11112222", "Altceva")).name == "chirie"
    assert BOOK.rule_for(Subject("87654321", "Hartie", commodity_codes=("30197630",))).name == "papetarie"
    assert BOOK.rule_for(Subject("87654321", "Toner", barcode="TN-2420")).name == "papetarie"
    assert BOOK.rule_for(Subject(None, "Altceva")) is None


def test_a_subject_stored_by_another_version_is_still_read():
    assert Subject.from_json('{"supplier_cui": "1", "description": "X", "added_later": 5}') == Subject("1", "X")
    assert Subject.from_json('{"description": "X"}') == Subject(None, "X")


def test_rules_taken_together_match_whatever_one_of_them_matches():
    together = any_of(BOOK.rules)

    assert together.matches(Subject("87654321", "Benzină fără plumb"))
    assert together.matches(Subject("87654321", "Abonament telefonie"))
    assert together.matches(Subject("11112222", "Altceva"))
    assert together.matches(Subject("87654321", "Toner", seller_code="TN-2420"))
    assert together.matches(Subject("87654321", "Hartie", commodity_codes=("30197630",)))
    assert not together.matches(Subject("87654321", "Altceva"))
    assert not any_of(()).matches(Subject("87654321", "Motorina"))


def test_a_keyword_that_starts_another_does_not_hide_it():
    rule = Rule("r", "628", keywords=("gaz", "gaze naturale", "transport*"))

    assert rule.matches(Subject(None, "Gaze naturale"))
    assert rule.matches(Subject(None, "Transportul gaz"))
    assert not rule.matches(Subject(None, "Gazon"))


@pytest.mark.parametrize("subject, said", [
    (Subject("11112222", "Altceva"), ("supplier_cui", "11112222", None)),
    (Subject("87654321", "Cartus", seller_code="TN-2420"), ("seller_code", "TN-2420", None)),
    (Subject("87654321", "Cartus", barcode="TN-2420"), ("barcode", "TN-2420", None)),
    (Subject("87654321", "Hartie", commodity_codes=("12", "30197630")), ("commodity_code", "30197630", "3019")),
    (Subject("87654321", "MOTORINĂ Euro 5"), ("keyword", "motorina", None)),
    (Subject("87654321", "Abonament telefonie"), ("keyword", "abonament telefon*", None)),
])
def test_a_rule_says_which_of_its_conditions_the_line_meets(subject, said):
    rule = BOOK.rule_for(subject)

    found = rule.match(subject)

    assert (found.condition, found.found, found.prefix) == said


def test_a_rule_says_why_exactly_when_it_matches():
    rule = Rule("r", "628", keywords=("gaz", "transport*"), item_codes=("A-1",), commodity_prefixes=("09",), supplier_cuis=("1",))
    for subject in (
        Subject("1", "x"), Subject("2", "Gaze naturale"), Subject("2", "gaz"), Subject("2", "Transportul"),
        Subject("2", "x", seller_code="A-1"), Subject("2", "x", commodity_codes=("0913",)), Subject("2", "Gazon"),
    ):
        assert (rule.match(subject) is not None) == rule.matches(subject)


def test_of_the_supplier_and_a_keyword_the_supplier_is_named_as_the_matching_checks_it_first():
    rule = Rule("r", "628", keywords=("motorina",), supplier_cuis=("1",))

    assert rule.match(Subject("1", "Motorina")).condition == "supplier_cui"


def test_every_rule_that_fits_a_line_is_listed_in_the_order_they_are_checked():
    book = Rulebook(
        accounts={}, instructions="",
        rules=(Rule("a", "111", keywords=("toner",)), Rule("x", "333", keywords=("hartie",)), Rule("b", "222", item_codes=("T-1",))),
    )

    assert [rule.name for rule in book.rules_for(Subject(None, "Toner negru", seller_code="T-1"))] == ["a", "b"]
    assert book.rules_for(Subject(None, "Altceva")) == []
    assert book.rules_for(Subject(None, "Toner"))[0] == book.rule_for(Subject(None, "Toner"))


def test_a_rule_knows_whether_it_is_for_one_client_and_compares_as_before():
    own = Rule("chirie", "612", keywords=("chirie",), client_cui="12345674")

    assert own.client_cui == "12345674" and Rule("chirie", "612", keywords=("chirie",)).client_cui is None
    assert own == Rule("chirie", "612", keywords=("chirie",))


def test_a_subject_survives_being_stored_as_text():
    subject = Subject("11112222", "Motorină Euro 5", "M-1", None, ("09134200", "2710"))

    assert Subject.from_json(subject.to_json()) == subject
    assert "Motorină" in subject.to_json()


# --- rules -------------------------------------------------------------------------


def test_a_keyword_on_the_deciding_line_gives_the_account():
    invoice = invoice_of(line("Spalare auto", "40.00"), line("MOTORINĂ Euro 5", "450.00"))

    decision = decide_by_rules(invoice, BOOK)

    assert (decision.cont, decision.rule, decision.line) == ("6022", "combustibil", 2)


def test_a_match_only_on_a_smaller_line_decides_nothing():
    invoice = invoice_of(line("Motorina", "40.00"), line("Piese de schimb", "900.00"))

    assert decide_by_rules(invoice, BOOK) is None


def test_keywords_match_whole_words_only():
    invoice = invoice_of(line("Motorinaxyz aditiv", "100.00"))

    assert decide_by_rules(invoice, BOOK) is None


def test_a_keyword_ending_in_a_star_matches_the_start_of_a_word():
    invoice = invoice_of(line("Abonament telefonie mobila", "100.00"))

    assert decide_by_rules(invoice, BOOK).cont == "626"


def test_the_first_matching_rule_wins():
    book = Rulebook(
        accounts={}, instructions="",
        rules=(Rule("a", "111", keywords=("toner",)), Rule("b", "222", keywords=("toner",))),
    )

    assert decide_by_rules(invoice_of(line("Toner negru", "10.00")), book).rule == "a"


def test_the_suppliers_article_code_gives_the_account():
    invoice = invoice_of(line("Cartus", "200.00", seller_code="TN-2420"))

    assert decide_by_rules(invoice, BOOK).cont == "3028"


def test_a_classification_code_prefix_gives_the_account():
    invoice = invoice_of(line("Hartie A4", "200.00", commodity="30197630"))

    assert decide_by_rules(invoice, BOOK).cont == "3028"


def test_a_supplier_rule_covers_every_line_of_that_supplier():
    invoice = invoice_of(line("Factura lunara", "2000.00"), supplier_cui="RO11112222")

    assert decide_by_rules(invoice, BOOK).cont == "612"


# --- the question for Jev ------------------------------------------------------------


def test_request_offers_every_account_plus_none_of_these():
    request = jev_request(invoice_of(line("Piese", "900.00")), BOOK, "typesafe/jev-1.14")

    question = request["questions"]["cont"]
    assert request["model"] == "typesafe/jev-1.14"
    assert question["type"] == "choice"
    assert question["instructions"] == BOOK.instructions
    assert set(question["criteria"]) == {"6022", "626", "371", NONE_OF_THESE}
    assert question["criteria"]["6022"] == "Combustibil pentru vehicule."


def test_request_describes_the_supplier_and_the_lines():
    invoice = invoice_of(
        line("Piese de schimb", "900.00", quantity="3", unit="H87", seller_code="P-1", commodity="34300000"),
        line("Manopera", "100.00", percent="9"),
    )

    state = jev_request(invoice, BOOK, "m")["state"]

    assert state["furnizor"] == {"nume": "Furnizor SRL", "cui": "87654321"}
    assert state["factura"]["moneda"] == "RON"
    assert state["linia_cu_valoarea_cea_mai_mare"] == 1
    first, second = state["linii"]
    assert first == {
        "nr": 1, "descriere": "Piese de schimb", "cod_furnizor": "P-1",
        "coduri_clasificare": ["34300000"], "um": "H87", "cantitate": "3",
        "valoare_fara_tva": "900.00", "cota_tva": "19",
    }
    assert (second["nr"], second["descriere"]) == (2, "Manopera")


def test_request_leaves_out_the_buyer_and_every_address_and_account():
    text = json.dumps(jev_request(invoice_of(line("Piese", "900.00")), BOOK, "m"))

    for private in ("Client SRL", "12345674", "Fabricii", "Unirii", "RO49AAAA", "office@", "0211234567"):
        assert private not in text


def test_a_very_long_invoice_is_cut_to_its_largest_lines():
    many = [line(f"Articol numarul {n} cu o descriere destul de lunga", f"{n}.00") for n in range(1, 1201)]

    request = jev_request(invoice_of(*many), BOOK, "m")

    state = request["state"]
    assert len(json.dumps(request).encode()) <= classify.MAX_REQUEST_BYTES
    assert state["linii_omise"] == 1200 - len(state["linii"]) > 0
    assert 1200 in {item["nr"] for item in state["linii"]}  # the largest stays
    assert [item["nr"] for item in state["linii"]] == sorted(item["nr"] for item in state["linii"])


# --- reading Jev's answer --------------------------------------------------------------


def answer(**cont):
    return {"answers": {"cont": cont}, "usage": {"input_tokens": 400, "output_tokens": 10, "cost": 0.00002}}


def test_reads_the_chosen_account_with_confidence_and_probabilities():
    result = read_jev_answer(
        answer(type="choice", choice="371", confidence=0.91,
               probabilities={"371": 0.93, "6022": 0.02, "626": 0.01, NONE_OF_THESE: 0.04}),
        BOOK,
    )

    assert (result.choice, result.confidence, result.refused) == ("371", 0.91, False)
    assert result.probabilities["371"] == 0.93


def test_none_of_these_is_reported_as_no_account():
    result = read_jev_answer(answer(type="choice", choice=NONE_OF_THESE, confidence=0.8), BOOK)

    assert (result.choice, result.confidence) == (None, 0.8)


def test_missing_confidence_stays_unknown():
    assert read_jev_answer(answer(type="choice", choice="371"), BOOK).confidence is None


def test_a_refusal_is_reported():
    result = read_jev_answer(answer(type="refusal"), BOOK)

    assert (result.choice, result.refused) == (None, True)


@pytest.mark.parametrize("body", [
    {},
    {"answers": {}},
    {"answers": {"cont": {"type": "choice", "choice": "9999"}}},
    {"answers": {"cont": {"type": "score", "score": 1}}},
    {"answers": {"cont": {"type": "choice", "choice": "371", "confidence": "high"}}},
    {"answers": {"cont": {"type": "choice", "choice": ["628"], "confidence": 0.9}}},  # a list, not an account
    {"answers": {"cont": {"type": "choice", "choice": {"cont": "628"}}}},
    {"answers": {"cont": {"type": "choice", "choice": "371", "confidence": 95}}},
    {"answers": {"cont": {"type": "choice", "choice": "371", "confidence": -0.2}}},
    {"answers": {"cont": {"type": "choice", "choice": "371", "confidence": float("nan")}}},
    "not an object",
])
def test_an_answer_that_does_not_make_sense_is_an_error(body):
    with pytest.raises(EfacturaError) as info:
        read_jev_answer(body, BOOK)

    assert info.value.code == "jev_error"


# --- a rule written carelessly must not match the wrong invoices -------------------------


def book_of(*rules_):
    return Rulebook(accounts={}, instructions="", rules=tuple(rules_))


def test_a_single_keyword_written_without_a_tuple_is_one_keyword_not_its_letters():
    book = book_of(Rule("combustibil", "6022", keywords="motorina"))

    assert decide_by_rules(invoice_of(line("Motorina", "10.00")), book).cont == "6022"
    assert decide_by_rules(invoice_of(line("Cablu 10 m", "10.00")), book) is None


def test_a_single_supplier_written_without_a_tuple_is_matched_whole():
    book = book_of(Rule("chirie", "612", supplier_cuis="11112222"))

    assert decide_by_rules(invoice_of(line("X", "10.00"), supplier_cui="RO1111"), book) is None
    assert decide_by_rules(invoice_of(line("X", "10.00"), supplier_cui="RO11112222"), book).cont == "612"


def test_rule_conditions_may_be_written_as_lists():
    book = book_of(Rule("papetarie", "3028", commodity_prefixes=["3019"], item_codes=["TN-1"]))

    assert decide_by_rules(invoice_of(line("Hartie", "10.00", commodity="30197630")), book).cont == "3028"
    assert decide_by_rules(invoice_of(line("Toner", "10.00", seller_code="TN-1")), book).cont == "3028"


def test_an_empty_keyword_matches_nothing():
    book = book_of(Rule("gol", "628", keywords=("", "  ", "*")))

    assert decide_by_rules(invoice_of(line("Orice", "10.00")), book) is None


# --- line by line ----------------------------------------------------------------


def test_each_line_is_read_by_the_rules_on_its_own():
    invoice = invoice_of(
        line("Motorina Euro 5", "450.00"), line("Abonament telefonie mobila", "200.00"), line("Spalare auto", "50.00"),
    )

    found = classify.rules_by_line(invoice, BOOK)

    assert {number: rule.cont for number, rule in found.items()} == {1: "6022", 2: "626"}


def test_a_line_brings_its_own_codes_to_the_rules():
    invoice = invoice_of(line("Servicii", "500.00"), line("Toner", "80.00", seller_code="TN-2420"))

    assert {number: rule.name for number, rule in classify.rules_by_line(invoice, BOOK).items()} == {2: "papetarie"}


def test_a_rule_on_the_supplier_gives_every_line_its_account():
    invoice = invoice_of(line("Chirie birou", "1000.00"), line("Utilitati", "120.00"), supplier_cui="RO11112222")

    assert {number: rule.cont for number, rule in classify.rules_by_line(invoice, BOOK).items()} == {1: "612", 2: "612"}


def test_a_discount_and_a_free_line_follow_the_largest_line():
    invoice = invoice_of(
        line("Ciment", "840.00"), line("Discount", "-40.00"), line("Paleti", "0.00"), line("Transport", "60.00"),
    )

    assert [classify.follows_largest(invoice, item) for item in invoice.lines] == [False, True, True, False]


def test_on_an_invoice_with_negative_amounts_the_positive_line_follows():
    invoice = invoice_of(line("Storno ciment", "-840.00"), line("Storno discount", "40.00"))

    assert [classify.follows_largest(invoice, item) for item in invoice.lines] == [False, True]


def test_lines_with_the_same_text_are_one_question():
    invoice = invoice_of(
        line("Ciment 40 kg", "840.00"), line("CIMENT  40 kg", "280.00"),
        line("Ciment 40 kg", "100.00", seller_code="C2"), line("Nisip", "90.00"),
    )

    keys = [classify.same_question(item) for item in invoice.lines]

    assert keys[0] == keys[1]
    assert len({keys[0], keys[2], keys[3]}) == 3


def test_the_request_about_one_line_names_that_line_and_the_supplier_only():
    invoice = invoice_of(
        line("Motorina Euro 5", "450.00"),
        line("Ciment Portland", "840.00", quantity="30", unit="KGM", price="28.00", commodity="44111200"),
    )

    request = classify.jev_line_request(invoice, invoice.lines[1], BOOK, "typesafe/jev-1.14")

    assert request["model"] == "typesafe/jev-1.14"
    assert request["state"]["furnizor"] == {"nume": "Furnizor SRL", "cui": "87654321"}
    assert request["state"]["linia"] == {
        "nr": 2, "descriere": "Ciment Portland", "coduri_clasificare": ["44111200"], "um": "KGM",
        "cantitate": "30", "valoare_fara_tva": "840.00", "cota_tva": "19",
    }
    sent = json.dumps(request, ensure_ascii=False)
    assert "linii" not in request["state"] and "Motorina" not in sent  # the other lines stay here
    assert "Client SRL" not in sent and "12345674" not in sent  # nor does the buyer
    question = request["questions"][classify.QUESTION]
    assert question["instructions"] == classify.DEFAULT_JEV_LINE_INSTRUCTIONS
    assert set(question["criteria"]) == {"6022", "626", "371", NONE_OF_THESE}


def test_the_question_about_one_line_is_the_one_set_for_lines():
    book = Rulebook(accounts=BOOK.accounts, rules=(), instructions="Contul facturii?", line_instructions="Contul liniei?")
    invoice = invoice_of(line("Ciment", "840.00"))

    request = classify.jev_line_request(invoice, invoice.lines[0], book, "m")

    assert request["questions"][classify.QUESTION]["instructions"] == "Contul liniei?"
    assert "Contul facturii?" not in json.dumps(request)


def test_the_answer_about_one_line_is_read_like_the_answer_about_an_invoice():
    body = {"answers": {classify.QUESTION: {"type": "choice", "choice": "6022", "confidence": 0.9}}}

    assert read_jev_answer(body, BOOK).choice == "6022"
