"""Serving the page: the /api prefix, who is trusted without a key, the built files."""

import json

import pytest
from fastapi.testclient import TestClient

from efactura import background, cli
from efactura.api import create_app
from efactura.config import load_config

KEY = {"X-API-Key": "local-key"}
OWN_PAGE = {"Sec-Fetch-Site": "same-origin", "Host": "127.0.0.1:8765"}


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[api]\nkey = "local-key"\n', encoding="utf-8")
    return path


@pytest.fixture
def cfg(config_path):
    return load_config(config_path)


@pytest.fixture
def built_page(tmp_path):
    folder = tmp_path / "ui"
    (folder / "assets").mkdir(parents=True)
    (folder / "index.html").write_text("<!doctype html><title>e-Factura pentru SAGA</title>")
    (folder / "assets" / "app.js").write_text("console.log('ok')")
    return folder


@pytest.fixture
def api(cfg, built_page):
    return TestClient(create_app(cfg, ui_dir=built_page))


# --- the same routes under /api ------------------------------------------------------------


def test_every_route_is_also_served_under_api(api):
    assert api.get("/clients", headers=KEY).json() == api.get("/api/clients", headers=KEY).json()
    assert api.get("/api/health").json()["ok"] is True
    assert api.get("/api/no-such-route", headers=KEY).status_code == 404


def test_the_documentation_lists_each_route_once(api):
    paths = api.get("/openapi.json").json()["paths"]

    assert "/clients" in paths
    assert not [path for path in paths if path.startswith("/api/")]


# --- who is trusted without the key ---------------------------------------------------------


def test_the_programs_own_page_needs_no_key(api):
    assert api.get("/api/clients", headers=OWN_PAGE).status_code == 200


@pytest.mark.parametrize("headers", [
    {},                                                               # another program
    {"Sec-Fetch-Site": "cross-site", "Host": "127.0.0.1:8765"},       # a page from another site
    {"Sec-Fetch-Site": "same-site", "Host": "127.0.0.1:8765"},
    {"Sec-Fetch-Site": "none", "Host": "127.0.0.1:8765"},             # typed into the address bar
    {"Sec-Fetch-Site": "same-origin", "Host": "evil.example:8765"},   # another name pointed at this PC
    {"Sec-Fetch-Site": "same-origin", "Host": "127.0.0.1:9999"},
])
def test_anything_else_still_needs_the_key(api, headers):
    reply = api.get("/api/clients", headers=headers)

    assert (reply.status_code, reply.json()["error"]["code"]) == (401, "unauthorized")


def test_the_page_is_trusted_under_api_only(api):
    assert api.get("/clients", headers=OWN_PAGE).status_code == 401


def test_the_page_may_also_be_opened_as_localhost_and_on_another_port(cfg, built_page):
    api = TestClient(create_app(cfg, ui_dir=built_page, port=9001))

    assert api.get("/api/clients", headers={**OWN_PAGE, "Host": "localhost:9001"}).status_code == 200
    assert api.get("/api/clients", headers=OWN_PAGE).status_code == 401  # 8765 is not this server


def test_the_page_may_be_opened_under_its_own_name(api):
    as_named = api.get("/api/clients", headers={**OWN_PAGE, "Host": "autosaga.localhost:8765"})
    another_name = api.get("/api/clients", headers={**OWN_PAGE, "Host": "other.localhost:8765"})
    without_the_port = api.get("/api/clients", headers={**OWN_PAGE, "Host": "autosaga.localhost"})

    assert (as_named.status_code, another_name.status_code, without_the_port.status_code) == (200, 401, 401)


def test_on_port_80_the_address_has_no_port(cfg, built_page):
    api = TestClient(create_app(cfg, ui_dir=built_page, port=80))

    for host in ("autosaga.localhost", "localhost", "127.0.0.1"):
        assert api.get("/api/clients", headers={**OWN_PAGE, "Host": host}).status_code == 200
    assert api.get("/api/clients", headers={**OWN_PAGE, "Host": "autosaga.localhost:8765"}).status_code == 401


def test_the_program_can_be_told_to_stop_but_only_with_the_key(cfg, built_page):
    app = create_app(cfg, ui_dir=built_page)
    stopped = []
    app.state.stop = lambda: stopped.append(True)  # what `efactura serve` puts there
    api = TestClient(app)

    without_the_key = api.post("/shutdown")
    from_the_page = api.post("/api/shutdown", headers=OWN_PAGE)
    stopped_so_far = list(stopped)
    with_the_key = api.post("/shutdown", headers=KEY)

    assert (without_the_key.status_code, from_the_page.status_code, stopped_so_far) == (401, 404, [])
    assert (with_the_key.json(), stopped) == ({"ok": True, "stopping": True}, [True])


def test_stopping_does_nothing_to_a_program_not_started_by_serve(api):
    assert api.post("/shutdown", headers=KEY).json() == {"ok": True, "stopping": False}


def test_the_key_still_works_under_api(api):
    assert api.get("/api/clients", headers=KEY).status_code == 200


# --- the built page ---------------------------------------------------------------------------


def test_the_page_and_its_files_are_served_without_a_key(api):
    page = api.get("/ui/")
    script = api.get("/ui/assets/app.js")

    assert (page.status_code, "e-Factura pentru SAGA" in page.text) == (200, True)
    assert (script.status_code, script.text) == (200, "console.log('ok')")


def test_the_address_without_a_path_leads_to_the_page(api):
    reply = api.get("/", follow_redirects=False)

    assert (reply.status_code, reply.headers["location"]) == (307, "/ui/")


def test_a_page_that_was_never_built_says_how_to_build_it(cfg, tmp_path):
    api = TestClient(create_app(cfg, ui_dir=tmp_path / "missing"))

    reply = api.get("/ui/")

    assert reply.status_code == 404
    assert "pnpm" in reply.json()["error"]["message"]


# --- the commands ------------------------------------------------------------------------------


@pytest.fixture
def run(config_path, monkeypatch, capsys):
    started = {}
    monkeypatch.setattr(cli, "run_server", lambda cfg, port, network=False: started.setdefault("server", port))
    monkeypatch.setattr(background, "probe", lambda port: None)  # nothing runs on the port yet
    monkeypatch.setattr(cli, "open_page_soon", lambda url: started.setdefault("opened", url))
    monkeypatch.setattr(cli, "run_dev", lambda cfg, port: started.setdefault("dev", port))

    def invoke(*argv):
        code = cli.main(["--config", str(config_path), *argv])
        return code, json.loads(capsys.readouterr().out), started

    return invoke


def test_serve_says_where_the_page_is(run):
    code, out, started = run("serve", "--port", "9001")

    assert (code, out["page"], started) == (0, "http://autosaga.localhost:9001/ui/", {"server": 9001})
    assert out["listening"] == "http://127.0.0.1:9001"


def test_serve_can_open_the_page_in_the_browser(run):
    _, _, started = run("serve", "--open")

    assert started == {"opened": "http://autosaga.localhost:8765/ui/", "server": 8765}


def test_dev_starts_the_api_and_the_page_together(run):
    code, out, started = run("dev")

    assert (code, started) == (0, {"dev": 8765})
    assert (out["ok"], out["page"]) == (True, "http://localhost:5173/ui/")


# --- found by the review of the screen -------------------------------------------------------


def test_the_page_cannot_be_shown_inside_another_sites_frame(api):
    for path in ("/ui/", "/api/health", "/health"):
        headers = api.get(path).headers
        assert headers["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in headers["content-security-policy"]


def test_no_page_on_this_address_loads_scripts_from_the_internet(api):
    # The interactive documentation pages pull their scripts from a CDN. On an address
    # whose page is trusted without a key, such a script could read every key.
    assert api.get("/docs", headers=KEY).status_code == 404
    assert api.get("/redoc", headers=KEY).status_code == 404
    assert api.get("/openapi.json").status_code == 200


def test_the_database_is_ready_before_the_first_request(cfg, built_page):
    from efactura.store import Store

    create_app(cfg, ui_dir=built_page)

    assert cfg.db_path.exists()
    store = Store(cfg.db_path)
    assert len(store.rules()) == 2
    store.close()
