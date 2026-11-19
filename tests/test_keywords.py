"""A rule's keywords: whole words, or, with a * at the start, the end or both, any letters there."""

import pytest

from efactura.rules import Rule, Subject, any_of


def matches(keyword: str, text: str) -> bool:
    return Rule("r", "302", keywords=(keyword,)).matches(Subject(None, text))


@pytest.mark.parametrize("keyword, text, expected", [
    # Ends with: the word itself, or any word ending in it.
    ("*cartus", "Toner tonercartus negru", True),
    ("*cartus", "Cartus toner", True),
    ("*cartus", "Cartuse toner", False),
    ("*transport", "Autotransport marfa", True),
    # Contains: anywhere in a word.
    ("*cartus*", "Tonercartusul HP", True),
    ("*cartus*", "Cartușe compatibile", True),
    ("*cartus*", "Cartella", False),
    # Starts with, as before.
    ("transport*", "Transportul marfii", True),
    ("transport*", "Autotransport", False),
    # Without a star, a whole word only, as before.
    ("toner", "Tonerul negru", False),
    ("toner", "Toner negru", True),
    # Case and diacritics are still ignored, on both sides.
    ("CARTUȘ*", "cartusele", True),
    ("*CARTUȘ*", "tonercartusul", True),
    # A phrase: the star belongs to the word it touches.
    ("*abonament telefon*", "Superabonament telefonie mobila", True),
    ("*abonament telefon*", "Abonament fix", False),
])
def test_a_star_stands_for_any_letters_where_it_is(keyword, text, expected):
    assert matches(keyword, text) is expected


def test_a_keyword_of_stars_alone_is_dropped_so_no_rule_matches_every_line():
    rule = Rule("r", "302", keywords=("*", "**", "* *", "*cartus"))

    assert rule.keywords == ("*cartus",)
    assert not Rule("r", "302", keywords=("*",)).matches(Subject(None, "Orice"))


def test_a_star_in_the_middle_is_a_plain_character():
    assert not matches("car*us", "Cartus")
    assert matches("car*us", "Cod car*us")


def test_the_rules_together_find_every_form_of_star():
    together = any_of((
        Rule("a", "302", keywords=("*cartus",)),
        Rule("b", "302", keywords=("transport*",)),
        Rule("c", "302", keywords=("*hartie*", "toner")),
    ))

    for text in ("Tonercartus", "Transporturi", "Superhartiei", "Toner"):
        assert together.matches(Subject(None, text)), text
    assert not together.matches(Subject(None, "Tonerul cartusei"))


@pytest.mark.parametrize("keyword, text, matched", [
    ("*cartus*", "Tonercartușul HP 85A", "Tonercartușul"),
    ("*cartus", "Toner tonercartus", "tonercartus"),
    ("transport*", "Transportul marfii", "Transportul"),
    ("motorina", "MOTORINĂ Euro 5", "MOTORINĂ"),
    ("abonament telefon*", "Abonament   telefonie mobila", "Abonament   telefonie"),
    ("cartus", "Ștampilă · Cartuș", "Cartuș"),
])
def test_the_rule_says_the_whole_words_it_found_as_the_line_writes_them(keyword, text, matched):
    found = Rule("r", "302", keywords=(keyword,)).match(Subject(None, text))

    assert (found.condition, found.found, found.matched) == ("keyword", keyword, matched)


def test_a_rule_says_why_exactly_when_it_matches_with_stars_too():
    rule = Rule("r", "302", keywords=("*cartus", "transport*", "*hartie*"))
    for text in ("Tonercartus", "Cartuse", "Transportul", "Autotransport", "Superhartiei", "Hartie", "Altceva"):
        subject = Subject(None, text)
        assert (rule.match(subject) is not None) == rule.matches(subject), text


def test_the_words_found_in_the_description_are_written_as_the_description_has_them():
    found = Rule("r", "302", keywords=("*cartus*",)).match(Subject(None, "Toner", details="Cartușe compatibile"))

    assert (found.matched, found.in_details) == ("Cartușe", True)


@pytest.mark.parametrize("text", [
    "Țeavă PPR 25 mm", "  MOTORINĂ Euro\t5  ", "İstanbul ﬁltru", "Cartuș · toner", "", "Ăîâșț ĂÎÂȘȚ",
])
def test_each_character_compared_has_its_place_in_the_line(text):
    from efactura.rules import _places, normalise

    places = _places(text)

    assert len(places) == len(normalise(text))
    assert all(0 <= place < len(text) for place in places)
    assert places == sorted(places)
