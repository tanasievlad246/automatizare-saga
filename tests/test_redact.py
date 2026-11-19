"""Hiding secrets before anything is written: by name, by shape and by value."""

import json

import pytest

from efactura import redact
from efactura.redact import HIDDEN


@pytest.fixture(autouse=True)
def nothing_remembered():
    redact.forget_all()
    yield
    redact.forget_all()


@pytest.mark.parametrize("name", [
    "Authorization", "authorization", "Proxy-Authorization", "Cookie", "Set-Cookie", "X-API-Key",
    "access_token", "refresh_token", "id_token", "client_secret", "api_key", "apiKey", "ApiKey",
    "accesstoken", "token", "secret", "password", "pin", "PIN", "session", "openrouter_api_key",
])
def test_names_that_hold_secrets_are_known(name):
    assert redact.secret_name(name)


@pytest.mark.parametrize("name", [
    "input_tokens", "output_tokens", "keywords", "cif", "pagina", "id", "content-type", "mesaje",
    "shipping", "mapping", "expires_in", "eroare", "code", "cont", "spin_off",
])
def test_ordinary_names_stay_readable(name):
    assert not redact.secret_name(name)


def test_a_bearer_or_basic_login_jwt_or_openrouter_key_is_hidden_wherever_it_stands():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.c2lnbmF0dXJlLWhlcmU"
    text = (
        f"sent Bearer abcdef123456 and Basic dXNlcjpwYXNzd29yZA== then {jwt} "
        "with sk-or-v1-0123456789abcdef and access_token=s3cr3tvalue&x=1, "
        '"refresh_token": "another-one", client_secret: third-one, PIN=4321'
    )

    cleaned = redact.clean(text)

    for leaked in ("abcdef123456", "dXNlcjpwYXNzd29yZA", jwt, "0123456789abcdef", "s3cr3tvalue",
                   "another-one", "third-one", "4321"):
        assert leaked not in cleaned
    assert "Bearer [hidden]" in cleaned and "x=1" in cleaned


def test_the_values_the_program_holds_are_hidden_whatever_surrounds_them():
    redact.remember("plain-looking-value-42", "short", None, "")

    cleaned = redact.clean("the server said: plain-looking-value-42 is wrong; short stays")

    assert cleaned == f"the server said: {HIDDEN} is wrong; short stays"  # too short to hide safely


def test_counts_of_tokens_and_ordinary_words_are_left_alone():
    text = '{"usage": {"input_tokens": 400, "output_tokens": 12}, "keywords": ["ciment"]}'

    assert redact.clean(text) == text


def test_headers_lose_the_value_of_every_secret_one():
    headers = [("Authorization", "Bearer abc"), ("Cookie", "a=b"), ("Accept", "*/*"), ("X-Api-Key", "k")]

    assert redact.headers(headers) == [
        ["Authorization", HIDDEN], ["Cookie", HIDDEN], ["Accept", "*/*"], ["X-Api-Key", HIDDEN],
    ]


def test_an_address_keeps_its_parameters_but_not_a_secret_one():
    address = "https://user:pass@api.example.test/rest/list?cif=12345674&token=abc123&code=one-time&pagina=1"

    cleaned = redact.url(address)

    assert cleaned == f"https://api.example.test/rest/list?cif=12345674&token={HIDDEN}&code={HIDDEN}&pagina=1"


def test_a_form_hides_the_login_code_and_every_token():
    form = "grant_type=authorization_code&code=good-code&redirect_uri=https%3A%2F%2Fx.test%2Fcb&refresh_token=r-1"

    assert redact.form(form) == (
        f"grant_type=authorization_code&code={HIDDEN}&redirect_uri=https://x.test/cb&refresh_token={HIDDEN}"
    )


def test_json_hides_by_key_at_any_depth_and_by_shape_in_any_value():
    body = {
        "access_token": "eyJx.eyJy.z", "nested": [{"api_key": "k-1", "note": "Bearer abcdefgh1234"}],
        "usage": {"input_tokens": 400}, "code": 402,
    }

    cleaned = json.loads(redact.json_text(json.dumps(body)))

    assert cleaned == {
        "access_token": HIDDEN, "nested": [{"api_key": HIDDEN, "note": "Bearer [hidden]"}],
        "usage": {"input_tokens": 400}, "code": 402,
    }


def test_text_that_is_not_json_is_cleaned_as_text():
    assert redact.json_text("not json, token=abcdef") == f"not json, token={HIDDEN}"
