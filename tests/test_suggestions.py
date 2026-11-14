"""What a proposed rule would look for: words of the deciding line, or the supplier."""

import unicodedata

import pytest

from efactura.rules import Rule, Subject
from efactura.suggestions import Proposal, propose, ticked_words, words_of

# --- the words offered -------------------------------------------------------------


def test_the_words_offered_are_the_words_of_the_line_in_order():
    assert words_of("Ciment Portland 42,5R, saci 40 kg") == ("ciment", "portland", "saci")


def test_numbers_units_and_link_words_are_not_offered():
    assert words_of("Motorină Euro 5 - 60 litri pentru luna octombrie 2026") == ("motorină",)


def test_document_words_are_not_offered():
    assert words_of("Servicii conform contract nr. 15 din 01.02.2026") == ("servicii",)


def test_a_word_is_offered_once_however_it_is_written():
    assert words_of("Hârtie A4, HARTIE A3") == ("hârtie",)


def test_at_most_six_words_are_offered():
    offered = words_of("Șurub cap hexagonal zincat filet metric complet oțel")

    assert offered == ("șurub", "cap", "hexagonal", "zincat", "filet", "metric")


def test_a_line_without_words_offers_none():
    assert words_of("12345 / 2026") == ()
    assert words_of("") == ()


def test_a_word_stuck_to_digits_or_an_underscore_is_not_offered():
    # A keyword has to stand as a word of its own: "office" would not find "Office365".
    assert words_of("Office365 Business") == ("business",)
    assert words_of("PVC110 teava") == ("teava",)
    assert words_of("Transport_marfa intern") == ("intern",)


def test_a_letter_written_as_letter_plus_accent_stays_in_its_word():
    taken_apart = unicodedata.normalize("NFD", "Piața centrală")

    assert words_of(taken_apart) == ("piața", "centrală")


@pytest.mark.parametrize("description", [
    "Office365 Business", "PVC110 teava", "Transport_marfa", "CEM42 saci", "iPhone15 Pro",
    unicodedata.normalize("NFD", "Piața centrală"), "Windows™ licență", "Preț/buc. hârtie",
    "Ciment Portland 42,5R, saci 40 kg",
])
def test_every_word_offered_is_one_a_rule_finds_on_that_very_line(description):
    for word in words_of(description):
        assert Rule("r", "628", keywords=(word,)).matches(Subject(None, description)), word


# --- the words ticked to begin with --------------------------------------------------


def test_the_first_word_is_ticked():
    assert ticked_words(("ciment", "portland", "saci")) == ("ciment",)


def test_a_general_word_is_passed_over():
    assert ticked_words(("servicii", "contabilitate")) == ("contabilitate",)
    assert ticked_words(("Abonament", "internet")) == ("internet",)
    assert ticked_words(("prestări", "servicii", "transport", "marfă")) == ("transport",)


def test_nothing_is_ticked_when_every_word_is_general():
    assert ticked_words(("servicii", "diverse")) == ()
    assert ticked_words(()) == ()


# --- the proposal --------------------------------------------------------------------


def test_a_proposal_looks_for_the_first_telling_word():
    proposal = propose(Subject("87654321", "Ciment Portland 40 kg"), "302")

    assert proposal == Proposal("302", keywords=("ciment",))


def test_a_line_that_says_nothing_telling_is_proposed_by_supplier():
    proposal = propose(Subject("87654321", "Servicii conform contract"), "628")

    assert proposal == Proposal("628", supplier_cuis=("87654321",))


def test_nothing_is_proposed_without_a_telling_word_or_a_supplier():
    assert propose(Subject(None, "Servicii diverse"), "628") is None


def test_the_same_word_written_differently_is_one_proposal():
    with_marks = propose(Subject("1", "Motorină Euro 5"), "6022")
    without = propose(Subject("2", "MOTORINA"), "6022")

    assert with_marks.key == without.key
    assert with_marks.key != propose(Subject("1", "Motorină"), "628").key
