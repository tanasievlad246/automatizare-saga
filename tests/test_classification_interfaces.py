"""The classification commands and routes: each pair must answer the same way."""

import io
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from efactura import auth, cli, service as service_module
from efactura.api import create_app
from efactura.auth import Tokens
from efactura.config import load_config
from efactura.rules import Rule, Rulebook
from efactura.service import Service

from helpers import VALID_CUI, FakeAnaf, FakeOpenRouter, line, rich_invoice_xml, set_rulebook

NOW = datetime(2026, 11, 11, 9, 30, tzinfo=timezone(timedelta(hours=2)))
KEY = {"X-API-Key": "local-key"}
BOOK = Rulebook(
    accounts={"6022": "Combustibil.", "628": "Alte servicii."},
    rules=(Rule("combustibil", "6022", keywords=("motorina",)),),
    instructions="Alege contul facturii.",
)
FUEL = [line("Motorina", "450.00")]
PARTS = [line("Piese de schimb", "900.00")]


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[anaf]\nclient_id = "my-client"\nclient_secret = "my-secret"\n'
        f"token_file = '{tmp_path / 'private' / 'tokens.json'}'\n"
        '[api]\nkey = "local-key"\n[openrouter]\napi_key = "or-test-key"\n',
        encoding="utf-8",
    )
    return path


@pytest.fixture
def cfg(config_path):
    cfg = load_config(config_path)
    set_rulebook(cfg.db_path, BOOK)
    auth.save_tokens(
        cfg.token_file,
        Tokens("access-1", "refresh-1", NOW + timedelta(days=30), NOW + timedelta(days=300), NOW),
    )
    return cfg


@pytest.fixture
def openrouter():
    return FakeOpenRouter()


@pytest.fixture
def anaf(openrouter):
    fake = FakeAnaf()
    fake.openrouter = openrouter
    return fake


@pytest.fixture
def make_service(anaf, monkeypatch):
    monkeypatch.setattr(service_module, "_pause", lambda seconds: None)
    return lambda cfg: Service(cfg, http=anaf.client(), now=lambda: NOW)


@pytest.fixture
def run(config_path, cfg, make_service, monkeypatch, capsys):
    monkeypatch.setattr(cli, "build_service", make_service)

    def invoke(*argv):
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        code = cli.main(["--config", str(config_path), *argv])
        return code, json.loads(capsys.readouterr().out)

    return invoke


@pytest.fixture
def api(cfg, make_service):
    return TestClient(create_app(cfg, service_factory=make_service))


@pytest.fixture
def in_review(anaf, openrouter, cfg, make_service):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))
    openrouter.answer_for("piese", "628", confidence=0.41)
    make_service(cfg).sync(VALID_CUI)


@pytest.fixture
def old_invoice(anaf, cfg, make_service):
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))
    make_service(cfg).sync(VALID_CUI, classify=False)


# --- sync --------------------------------------------------------------------------------


def test_sync_command_classifies_and_reports_it(run, anaf):
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))

    code, out = run("sync", VALID_CUI)

    assert code == 0
    assert out["new"][0]["cont"] == "6022"
    assert out["classification"]["classified"] == 1
    assert out["saga_folder"].endswith(VALID_CUI)


def test_sync_command_can_save_without_classifying(run, anaf):
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))

    code, out = run("sync", VALID_CUI, "--no-classify")

    assert (code, out["classification"], out["new"][0]["classification_status"]) == (0, None, None)


def test_sync_route_classifies_by_default_and_can_be_told_not_to(api, anaf):
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL, number="A1"))
    first = api.post("/sync", headers=KEY, json={"cui": VALID_CUI, "classify": False}).json()
    anaf.add("3002", xml=rich_invoice_xml(lines=FUEL, number="A2"))
    second = api.post("/sync", headers=KEY, json={"cui": VALID_CUI}).json()

    assert first["classification"] is None
    assert second["classification"]["classified"] == 1
    assert [entry["id"] for entry in second["new"]] == ["3002"]


# --- classify by id ----------------------------------------------------------------------


def test_classify_command_and_route_answer_alike(run, api, old_invoice):
    code, from_command = run("classify", "3001", "--force")
    from_route = api.post("/invoices/3001/classify", headers=KEY, json={"force": True})

    assert code == 0 and from_route.status_code == 200
    assert from_command == from_route.json()
    assert from_command["invoice"]["cont"] == "6022"


def test_classify_route_needs_no_body(api, in_review, openrouter):
    openrouter.answer_for("piese", "628", confidence=0.99)

    reply = api.post("/invoices/3001/classify", headers=KEY)

    assert reply.status_code == 200
    assert reply.json()["invoice"]["classification_status"] == "classified"


def test_an_old_invoice_is_refused_the_same_way_by_command_and_route(run, api, old_invoice):
    code, from_command = run("classify", "3001")
    from_route = api.post("/invoices/3001/classify", headers=KEY)

    assert (code, from_route.status_code) == (1, 409)
    assert from_command == from_route.json()
    assert from_command["error"]["code"] == "not_classifiable"


def test_a_jev_failure_is_reported_as_a_gateway_error(run, api, in_review, openrouter):
    openrouter.fail_with = [402, 402]

    code, from_command = run("classify", "3001")
    from_route = api.post("/invoices/3001/classify", headers=KEY)

    assert (code, from_route.status_code) == (1, 502)
    assert from_command["error"]["code"] == from_route.json()["error"]["code"] == "jev_error"


def test_classifying_an_unknown_id_is_not_found(run, api, cfg):
    code, out = run("classify", "nope")

    assert (code, out["error"]["code"]) == (1, "not_found")
    assert api.post("/invoices/nope/classify", headers=KEY).status_code == 404


# --- review ------------------------------------------------------------------------------


def test_review_command_and_route_answer_alike(run, api, in_review):
    code, from_command = run("review")
    from_route = api.get("/review", headers=KEY)

    assert code == 0 and from_route.status_code == 200
    assert from_command == from_route.json()
    assert [entry["id"] for entry in from_command["invoices"]] == ["3001"]
    assert from_command["invoices"][0]["suggested_cont"] == "628"


def test_review_can_be_narrowed_to_a_company(run, api, in_review):
    _, from_command = run("review", "--cui", "14399840")
    from_route = api.get("/review", headers=KEY, params={"cui": "14399840"}).json()

    assert from_command["count"] == from_route["count"] == 0


def test_accepting_the_suggestion_by_command(run, in_review):
    code, out = run("set-cont", "3001", "--accept")

    assert code == 0
    assert (out["invoice"]["cont"], out["invoice"]["classification_method"]) == ("628", "jev_accepted")


def test_accepting_the_suggestion_by_route(api, in_review):
    reply = api.post("/invoices/3001/cont", headers=KEY, json={"accept": True})

    assert reply.status_code == 200
    assert reply.json()["invoice"]["classification_method"] == "jev_accepted"


def test_setting_an_account_by_command(run, in_review):
    code, out = run("set-cont", "3001", "--cont", "371.01")

    assert code == 0
    assert (out["invoice"]["cont"], out["invoice"]["classification_method"]) == ("371.01", "human")


def test_setting_an_account_by_route_accepts_text_or_a_number(api, in_review):
    as_number = api.post("/invoices/3001/cont", headers=KEY, json={"cont": 6022})
    as_text = api.post("/invoices/3001/cont", headers=KEY, json={"cont": "371.01"})

    assert as_number.json()["invoice"]["cont"] == "6022"
    assert as_text.json()["invoice"]["cont"] == "371.01"


def test_set_cont_without_a_decision_is_invalid_input(run, api, in_review):
    code, out = run("set-cont", "3001")
    both = run("set-cont", "3001", "--accept", "--cont", "628")
    from_route = api.post("/invoices/3001/cont", headers=KEY, json={})

    assert (code, out["error"]["code"]) == (1, "invalid_input")
    assert (both[0], both[1]["error"]["code"]) == (1, "invalid_input")
    assert (from_route.status_code, from_route.json()["error"]["code"]) == (400, "invalid_input")


def test_set_cont_on_an_old_invoice_needs_force(run, api, old_invoice):
    refused = api.post("/invoices/3001/cont", headers=KEY, json={"cont": "628"})
    code, out = run("set-cont", "3001", "--cont", "628", "--force")

    assert (refused.status_code, refused.json()["error"]["code"]) == (409, "not_classifiable")
    assert (code, out["invoice"]["cont"]) == (0, "628")


# --- the confidence level ----------------------------------------------------------------


def test_confidence_command_shows_and_changes_the_level(run):
    _, before = run("confidence")
    code, after = run("confidence", "0.9")
    _, shown_again = run("confidence")

    assert (before["min_confidence"], after["min_confidence"], shown_again["min_confidence"]) == (
        0.8, 0.9, 0.9
    )
    assert code == 0 and after["jev_configured"] is True


def test_confidence_routes_show_and_change_the_level(api, run):
    before = api.get("/classification/settings", headers=KEY)
    changed = api.put("/classification/settings", headers=KEY, json={"min_confidence": 0.65})
    _, from_command = run("confidence")

    assert before.json()["min_confidence"] == 0.8
    assert (changed.status_code, changed.json()["min_confidence"]) == (200, 0.65)
    assert from_command == api.get("/classification/settings", headers=KEY).json()


def test_a_confidence_level_out_of_range_is_invalid_input(run, api):
    code, out = run("confidence", "1.5")
    not_a_number = run("confidence", "high")
    from_route = api.put("/classification/settings", headers=KEY, json={"min_confidence": 2})
    wrong_type = api.put("/classification/settings", headers=KEY, json={"min_confidence": "high"})

    assert (code, out["error"]["code"]) == (1, "invalid_input")
    assert not_a_number[1]["error"]["code"] == "invalid_input"
    assert (from_route.status_code, wrong_type.status_code) == (400, 400)


# --- costs -------------------------------------------------------------------------------


def test_costs_command_and_route_answer_alike(run, api, in_review):
    code, from_command = run("costs")
    from_route = api.get("/classification/costs", headers=KEY)

    assert code == 0 and from_route.status_code == 200
    assert from_command == from_route.json()
    assert (from_command["calls"], from_command["cost_usd"]) == (1, 0.00002)


def test_costs_can_be_narrowed(run, api, in_review):
    _, from_command = run("costs", "--since", "2026-11-12", "--cui", VALID_CUI)
    from_route = api.get(
        "/classification/costs", headers=KEY, params={"since": "2026-11-12", "cui": VALID_CUI}
    ).json()

    assert from_command == from_route
    assert from_command["calls"] == 0


# --- listing -----------------------------------------------------------------------------


def test_invoices_can_be_filtered_by_classification(run, api, in_review):
    code, from_command = run("invoices", "--classification", "review")
    from_route = api.get("/invoices", headers=KEY, params={"classification": "review"})
    none = api.get("/invoices", headers=KEY, params={"classification": "classified"}).json()

    assert code == 0 and from_command == from_route.json()
    assert (from_command["count"], none["count"]) == (1, 0)


def test_an_unknown_classification_filter_is_invalid_input(run, api, cfg):
    code, out = run("invoices", "--classification", "done")
    from_route = api.get("/invoices", headers=KEY, params={"classification": "done"})

    assert (code, out["error"]["code"]) == (1, "invalid_input")
    assert from_route.status_code == 400


# --- the key -----------------------------------------------------------------------------


@pytest.mark.parametrize("method, path", [
    ("post", "/invoices/3001/classify"),
    ("get", "/review"),
    ("post", "/invoices/3001/cont"),
    ("get", "/classification/settings"),
    ("put", "/classification/settings"),
    ("get", "/classification/costs"),
])
def test_every_classification_route_needs_the_key(api, method, path):
    reply = getattr(api, method)(path)

    assert (reply.status_code, reply.json()["error"]["code"]) == (401, "unauthorized")
