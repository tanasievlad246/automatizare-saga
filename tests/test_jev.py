import httpx
import pytest

from efactura import jev

from helpers import FakeOpenRouter

REQUEST = {
    "model": "typesafe/jev-1.14",
    "state": {"linii": [{"nr": 1, "descriere": "Piese de schimb"}]},
    "questions": {"cont": {"type": "choice", "criteria": {"628": "Servicii", "altul": "Niciunul"}}},
}


@pytest.fixture
def openrouter():
    return FakeOpenRouter()


def ask(openrouter, key="or-test-key"):
    return jev.ask(openrouter.client(), key, REQUEST)


def test_sends_the_request_to_the_decisions_endpoint_with_the_key():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"answers": {}, "usage": {"input_tokens": 1, "output_tokens": 0}})

    jev.ask(httpx.Client(transport=httpx.MockTransport(handler)), "or-test-key", REQUEST)

    (request,) = seen
    assert (request.method, str(request.url)) == ("POST", "https://openrouter.ai/api/alpha/decisions")
    assert request.headers["authorization"] == "Bearer or-test-key"
    assert request.headers["content-type"] == "application/json"


def test_a_good_reply_is_returned_with_tokens_and_cost(openrouter):
    call = ask(openrouter)

    assert call.ok and call.error is None
    assert call.status == 200
    assert call.response["answers"]["cont"]["choice"] == "628"
    assert (call.input_tokens, call.output_tokens, call.cost_usd) == (400, 12, 0.00002)
    assert call.model == "typesafe/jev-1.14-20261001"
    assert call.duration_ms >= 0


def test_the_record_keeps_the_request_but_never_the_key(openrouter):
    call = ask(openrouter)

    assert call.request == REQUEST
    assert "or-test-key" not in repr(call)


def test_a_reply_without_a_cost_is_kept_with_the_cost_unknown():
    def handler(request):
        return httpx.Response(200, json={"answers": {}, "usage": {"input_tokens": 9, "output_tokens": 0}})

    call = jev.ask(httpx.Client(transport=httpx.MockTransport(handler)), "k", REQUEST)

    assert call.ok and (call.input_tokens, call.cost_usd) == (9, None)


@pytest.mark.parametrize("status, expected, transient", [
    (401, "API key", False),
    (402, "credit", False),
    (429, "Rate limit", True),
    (503, "HTTP 503", True),
    (400, "HTTP 400", False),
])
def test_a_refused_request_is_reported_not_raised(openrouter, status, expected, transient):
    openrouter.fail_with = [status]

    call = ask(openrouter)

    assert not call.ok
    assert call.status == status
    assert expected in call.error
    assert call.transient is transient
    assert call.response["error"]["code"] == status


def test_an_unreachable_service_is_reported_as_transient(openrouter):
    openrouter.fail_with = ["unreachable"]

    call = ask(openrouter)

    assert not call.ok and call.status is None and call.transient
    assert "reach" in call.error


def test_a_reply_that_is_not_json_is_reported_with_its_text():
    def handler(request):
        return httpx.Response(200, text="<html>gateway</html>")

    call = jev.ask(httpx.Client(transport=httpx.MockTransport(handler)), "k", REQUEST)

    assert not call.ok
    assert call.response == {"unreadable": "<html>gateway</html>"}
