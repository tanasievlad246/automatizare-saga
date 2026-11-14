import io
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from efactura import auth, cli
from efactura.api import create_app
from efactura.auth import Tokens
from efactura.config import load_config
from efactura.service import Service

from helpers import VALID_CUI, FakeAnaf, invoice_xml

NOW = datetime(2026, 11, 11, 9, 30, tzinfo=timezone(timedelta(hours=2)))
KEY = {"X-API-Key": "local-key"}


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[anaf]\nclient_id = "my-client"\nclient_secret = "my-secret"\n'
        f"token_file = '{tmp_path / 'private' / 'tokens.json'}'\n"
        '[api]\nkey = "local-key"\n',
        encoding="utf-8",
    )
    return path


@pytest.fixture
def cfg(config_path):
    return load_config(config_path)


@pytest.fixture
def anaf():
    return FakeAnaf()


@pytest.fixture
def make_service(anaf):
    return lambda cfg: Service(cfg, http=anaf.client(), now=lambda: NOW)


@pytest.fixture
def api(cfg, make_service):
    return TestClient(create_app(cfg, service_factory=make_service))


@pytest.fixture
def logged_in(cfg):
    auth.save_tokens(
        cfg.token_file,
        Tokens("access-1", "refresh-1", NOW + timedelta(days=30), NOW + timedelta(days=300), NOW),
    )


# --- the key -----------------------------------------------------------------


def test_health_answers_without_a_key(api):
    reply = api.get("/health")

    assert reply.status_code == 200
    assert reply.json()["ok"] is True


@pytest.mark.parametrize(
    "method, path",
    [
        ("GET", "/auth/status"),
        ("POST", "/auth/login/start"),
        ("POST", "/auth/login/finish"),
        ("GET", f"/anaf/messages?cui={VALID_CUI}"),
        ("POST", "/sync"),
        ("GET", "/invoices"),
        ("GET", "/invoices/3001"),
        ("POST", "/invoices/3001/uploaded"),
        ("DELETE", "/invoices/3001/uploaded"),
    ],
)
def test_every_other_route_refuses_a_request_without_the_key(api, anaf, method, path):
    reply = api.request(method, path)

    assert reply.status_code == 401
    assert reply.json() == {
        "ok": False,
        "error": {"code": "unauthorized", "message": "Missing or wrong X-API-Key header."},
    }
    assert anaf.list_requests == [] and anaf.token_requests == []


def test_a_wrong_key_is_refused(api):
    assert api.get("/auth/status", headers={"X-API-Key": "guess"}).status_code == 401


def test_app_cannot_be_created_without_a_configured_key(tmp_path, make_service):
    keyless = tmp_path / "keyless.toml"
    keyless.write_text("", encoding="utf-8")

    with pytest.raises(Exception) as info:
        create_app(load_config(keyless), service_factory=make_service)

    assert getattr(info.value, "code", None) == "config_error"


# --- routes ------------------------------------------------------------------


def test_auth_status(api):
    reply = api.get("/auth/status", headers=KEY)

    assert reply.status_code == 200
    assert reply.json()["state"] == "needs_login"


def test_login_start_then_finish(api):
    started = api.post("/auth/login/start", headers=KEY)
    finished = api.post(
        "/auth/login/finish",
        headers=KEY,
        json={"address": "https://localhost/callback?code=good-code"},
    )

    assert started.json()["authorize_url"].startswith("https://logincert.anaf.ro/")
    assert finished.status_code == 200
    assert finished.json()["state"] == "valid"
    assert api.get("/auth/status", headers=KEY).json()["state"] == "valid"


def test_sync_saves_and_returns_new_messages(api, anaf, logged_in):
    anaf.add("3001")

    reply = api.post("/sync", headers=KEY, json={"cui": VALID_CUI})

    assert reply.status_code == 200
    body = reply.json()
    assert (body["new_count"], body["window_days"]) == (1, 7)
    assert body["new"][0]["id"] == "3001"


def test_sync_accepts_days(api, logged_in):
    reply = api.post("/sync", headers=KEY, json={"cui": VALID_CUI, "days": 30})

    assert reply.json()["window_days"] == 30


def test_sync_accepts_the_cui_as_a_json_number(api, logged_in):
    reply = api.post("/sync", headers=KEY, json={"cui": int(VALID_CUI)})

    assert reply.status_code == 200
    assert reply.json()["cui"] == VALID_CUI


def test_the_list_of_routes_is_readable_without_the_key(api):
    routes = api.get("/openapi.json").json()["paths"]
    assert {"/sync", "/invoices", "/auth/status"} <= set(routes)


def test_anaf_messages_previews(api, anaf, logged_in):
    anaf.add("3001")

    reply = api.get("/anaf/messages", headers=KEY, params={"cui": VALID_CUI, "days": 3})

    assert reply.status_code == 200
    assert reply.json()["window_days"] == 3
    assert reply.json()["messages"][0]["is_new"] is True
    assert anaf.downloads == []


def test_invoices_filters(api, anaf, logged_in):
    anaf.add("3001")
    anaf.add("3002", tip="FACTURA TRIMISA")
    api.post("/sync", headers=KEY, json={"cui": VALID_CUI})
    api.post("/invoices/3001/uploaded", headers=KEY)

    pending = api.get("/invoices", headers=KEY, params={"pending": "true"})
    sent = api.get(
        "/invoices", headers=KEY, params={"type": "trimisa", "cui": VALID_CUI, "since": "2026-11-11"}
    )

    assert [i["id"] for i in pending.json()["invoices"]] == ["3002"]
    assert [i["id"] for i in sent.json()["invoices"]] == ["3002"]


def test_single_invoice_with_xml_on_request(api, anaf, logged_in):
    anaf.add("3001")
    api.post("/sync", headers=KEY, json={"cui": VALID_CUI})

    plain = api.get("/invoices/3001", headers=KEY).json()["invoice"]
    full = api.get("/invoices/3001", headers=KEY, params={"xml": "true"}).json()["invoice"]

    assert "invoice_xml" not in plain
    assert "<cbc:ID>FV-3001</cbc:ID>" in full["invoice_xml"]


def test_flag_can_be_set_and_cleared(api, anaf, logged_in):
    anaf.add("3001")
    api.post("/sync", headers=KEY, json={"cui": VALID_CUI})

    marked = api.post("/invoices/3001/uploaded", headers=KEY)
    cleared = api.delete("/invoices/3001/uploaded", headers=KEY)

    assert marked.json() == {
        "ok": True,
        "uploaded_to_accounting": True,
        "uploaded_at": NOW.isoformat(),
        "updated": ["3001"],
    }
    assert cleared.json()["uploaded_to_accounting"] is False
    assert api.get("/invoices/3001", headers=KEY).json()["invoice"]["uploaded_to_accounting"] is False


# --- failures keep the same JSON shape ---------------------------------------


def test_login_needed_is_409(api):
    reply = api.post("/sync", headers=KEY, json={"cui": VALID_CUI})

    assert reply.status_code == 409
    assert reply.json()["error"]["code"] == "login_needed"


def test_expired_login_code_is_409(api):
    reply = api.post(
        "/auth/login/finish", headers=KEY, json={"address": "https://localhost/callback?code=stale"}
    )

    assert reply.status_code == 409
    assert reply.json()["error"]["code"] == "login_code_expired"


def test_invalid_cui_is_400(api, logged_in):
    reply = api.post("/sync", headers=KEY, json={"cui": "12345678"})

    assert reply.status_code == 400
    assert reply.json()["error"]["code"] == "invalid_cui"


@pytest.mark.parametrize(
    "send",
    [
        lambda api: api.post("/sync", headers=KEY, json={}),
        lambda api: api.post("/sync", headers=KEY, json={"cui": VALID_CUI, "days": "many"}),
        lambda api: api.post("/sync", headers=KEY, content=b"not json"),
        lambda api: api.get("/anaf/messages", headers=KEY),
        lambda api: api.get("/invoices", headers=KEY, params={"type": "received"}),
        lambda api: api.post("/auth/login/finish", headers=KEY, json={}),
    ],
)
def test_malformed_requests_are_400_invalid_input(api, logged_in, send):
    reply = send(api)

    assert reply.status_code == 400
    body = reply.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "invalid_input"
    assert isinstance(body["error"]["message"], str)


def test_unknown_invoice_is_404(api):
    reply = api.get("/invoices/9999", headers=KEY)

    assert reply.status_code == 404
    assert reply.json()["error"]["code"] == "not_found"


def test_unknown_route_is_404_in_the_same_shape(api):
    reply = api.get("/nope", headers=KEY)

    assert reply.status_code == 404
    assert reply.json()["ok"] is False
    assert reply.json()["error"]["code"] == "not_found"


def test_anaf_refusal_is_502(api, anaf, logged_in):
    anaf.list_error = f"Nu aveti drept in SPV pentru CIF={VALID_CUI}"

    reply = api.post("/sync", headers=KEY, json={"cui": VALID_CUI})

    assert reply.status_code == 502
    assert reply.json()["error"]["code"] == "no_spv_rights"


def test_unexpected_failure_is_500_in_the_same_shape(cfg, make_service, monkeypatch):
    def explode(self):
        raise RuntimeError("boom")

    monkeypatch.setattr(Service, "auth_status", explode)
    api = TestClient(create_app(cfg, service_factory=make_service), raise_server_exceptions=False)

    reply = api.get("/auth/status", headers=KEY)

    assert reply.status_code == 500
    assert reply.json() == {
        "ok": False,
        "error": {"code": "internal_error", "message": "RuntimeError: boom"},
    }


def test_reply_is_plain_ascii(api, anaf, logged_in):
    anaf.add("3001", xml=invoice_xml(supplier_name="Țăran Ștefan SRL"))

    reply = api.post("/sync", headers=KEY, json={"cui": VALID_CUI})

    assert reply.content.isascii()
    assert reply.json()["new"][0]["supplier_name"] == "Țăran Ștefan SRL"


# --- commands and routes agree ------------------------------------------------


def command_output(monkeypatch, capsys, config_path, make_service, *argv):
    monkeypatch.setattr(cli, "build_service", make_service)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    capsys.readouterr()
    cli.main(["--config", str(config_path), *argv])
    return json.loads(capsys.readouterr().out)


def test_each_route_returns_what_its_command_prints(
    api, anaf, logged_in, config_path, make_service, monkeypatch, capsys
):
    anaf.add("3001")
    anaf.add("3002", tip="ERORI FACTURA")
    api.post("/sync", headers=KEY, json={"cui": VALID_CUI})

    def command(*argv):
        return command_output(monkeypatch, capsys, config_path, make_service, *argv)

    pairs = [
        (api.get("/auth/status", headers=KEY), command("auth-status")),
        (api.post("/auth/login/start", headers=KEY), command("login-start")),
        (api.get("/anaf/messages", headers=KEY, params={"cui": VALID_CUI}), command("list", VALID_CUI)),
        (api.post("/sync", headers=KEY, json={"cui": VALID_CUI}), command("sync", VALID_CUI)),
        (api.get("/invoices", headers=KEY, params={"pending": "true"}), command("invoices", "--pending")),
        (api.get("/invoices/3001", headers=KEY, params={"xml": "true"}), command("invoice", "3001", "--xml")),
        (api.post("/invoices/3001/uploaded", headers=KEY), command("mark-uploaded", "3001")),
        (api.delete("/invoices/3001/uploaded", headers=KEY), command("mark-uploaded", "3001", "--undo")),
        (api.get("/invoices/9999", headers=KEY), command("invoice", "9999")),
    ]

    for reply, printed in pairs:
        assert reply.json() == printed
