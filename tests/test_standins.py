import httpx

import helpers
from efactura import jev, standins


def test_the_tests_and_the_program_share_one_set_of_stand_ins():
    for name in ("FakeAnaf", "FakeOpenRouter", "rich_invoice_xml", "line", "adjustment", "invoice_xml", "make_zip"):
        assert getattr(helpers, name) is getattr(standins, name)


def test_the_jev_stand_in_can_be_told_to_accept_any_key():
    openrouter = standins.FakeOpenRouter()
    openrouter.valid_keys = None
    request = {"model": "m", "state": {"linii": [{"descriere": "ciment"}]}, "questions": {}}
    with openrouter.client() as http:
        assert jev.ask(http, "any key at all", request).ok
