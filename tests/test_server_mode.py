"""Server mode: the program served to every computer on the office network, without a login.

Started apart from the local mode (`serve --network`). The page is trusted from any computer,
never from another website; windows open only for a browser on the computer that runs it.
"""

import json
import os

import pytest
from fastapi.testclient import TestClient

from efactura import api as api_module
from efactura import background, cli
from efactura.api import create_app
from efactura.config import load_config
from efactura.errors import EfacturaError

KEY = {"X-API-Key": "local-key"}
PLAIN = {"Host": "192.168.1.50:8765"}  # plain http on the office network: no Sec-Fetch-Site
FROM_THE_PAGE = {**PLAIN, "X-AutoSaga-Page": "1"}  # the page sends its header with every call
A_CHANGE = FROM_THE_PAGE
ANOTHER_PC = ("192.168.1.20", 50000)
THIS_PC = ("127.0.0.1", 50000)


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[api]\nkey = "local-key"\n'
        "[server]\n"
        'names = ["birou-nas", "Birou-NAS.local"]\n'
        "saga_folder_windows = '\\\\192.168.1.50\\AutoSaga-SAGA'\n"
        'saga_folder_mac = "/Volumes/AutoSaga-SAGA"\n',
        encoding="utf-8",
    )
    return path


@pytest.fixture
def cfg(config_path):
    return load_config(config_path)


@pytest.fixture
def built_page(tmp_path):
    folder = tmp_path / "ui"
    folder.mkdir()
    (folder / "index.html").write_text("<!doctype html><title>AutoSaga</title>")
    return folder


class Windows:
    """Stands in for the program's own work where it would open a window on this computer."""

    def __init__(self, cfg):
        self.opened = []

    def choose_folder(self, purpose="saga"):
        return {"ok": True, "folder": "/ales"}

    def open_folder(self, folder):
        return {"ok": True, "opened": folder}

    def open_saga_folder(self, cui, invoice_id):
        return {"ok": True}

    def open_saga_archive(self, import_id):
        return {"ok": True}

    def login_with_certificate(self):
        return {"ok": True, "logged_in": True}

    def auth_status(self):
        return {"ok": True, "logged_in": False, "certificate_login": True}

    def health(self):
        return {"ok": True, "service": "efactura", "version": "0"}

    def close(self):
        pass


@pytest.fixture
def server(cfg, built_page, monkeypatch):
    """The app in server mode, asked from another computer unless told otherwise."""
    monkeypatch.setattr(api_module.socket, "gethostname", lambda: "Contabil-PC")

    def make(client=ANOTHER_PC, service_factory=None, port=8765):
        app = create_app(cfg, ui_dir=built_page, port=port, network=True, service_factory=service_factory)
        return TestClient(app, client=client)

    return make


# --- the settings --------------------------------------------------------------------------------


def test_the_server_section_is_read(cfg):
    assert cfg.server_names == ("birou-nas", "birou-nas.local")
    assert (cfg.saga_folder_windows, cfg.saga_folder_mac) == ("\\\\192.168.1.50\\AutoSaga-SAGA", "/Volumes/AutoSaga-SAGA")


def test_without_a_server_section_nothing_is_set(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[api]\nkey = "k"\n', encoding="utf-8")

    cfg = load_config(path)

    assert (cfg.server_names, cfg.saga_folder_windows, cfg.saga_folder_mac) == ((), None, None)


@pytest.mark.parametrize("names", ['"birou-nas"', "[1, 2]"])
def test_names_must_be_a_list_of_text(tmp_path, names):
    path = tmp_path / "config.toml"
    path.write_text(f'[api]\nkey = "k"\n[server]\nnames = {names}\n', encoding="utf-8")

    with pytest.raises(EfacturaError) as raised:
        load_config(path)

    assert raised.value.code == "config_error"


# --- who is let in ---------------------------------------------------------------------------------


def test_the_page_is_trusted_from_another_computer(server):
    assert server().get("/api/clients", headers=FROM_THE_PAGE).status_code == 200


@pytest.mark.parametrize("host", [
    "192.168.1.50:8765", "10.0.0.7:8765", "[fe80::1]:8765", "localhost:8765", "autosaga.localhost:8765",
    "birou-nas:8765", "BIROU-NAS.local:8765", "contabil-pc:8765", "Contabil-PC.local:8765",
    "192.168.1.50:8080",  # the container's port published under another one
    "192.168.1.50",  # behind a proxy on port 80
])
def test_the_page_may_be_opened_under_any_address_or_a_known_name(server, host):
    assert server().get("/api/clients", headers={**FROM_THE_PAGE, "Host": host}).status_code == 200


@pytest.mark.parametrize("headers", [
    {"Host": "evil.example:8765"},  # a name of another site pointed at this computer
    {"Host": "192.168.1.50.evil.example:8765"},
    {"Host": ""},
    {**FROM_THE_PAGE, "Sec-Fetch-Site": "cross-site"},  # another site, over https
    {**FROM_THE_PAGE, "Sec-Fetch-Site": "same-site"},
    {**FROM_THE_PAGE, "Origin": "http://evil.example"},
    {**FROM_THE_PAGE, "Origin": "null"},
])
def test_another_website_is_never_let_in(server, headers):
    reply = server().get("/api/clients", headers=headers)

    assert (reply.status_code, reply.json()["error"]["code"]) == (401, "unauthorized")


def test_a_plain_request_from_another_site_reads_nothing_and_starts_nothing(server):
    # Over plain http nothing tells another site's <img> or link from the page, so the page's
    # own header is asked of reads too: one of them (/api/anaf/messages) asks ANAF.
    for path in ("/api/clients", "/api/anaf/messages?cui=12345674&days=60", "/api/update?check=true"):
        reply = server().get(path, headers=PLAIN)
        assert (reply.status_code, reply.json()["error"]["code"]) == (401, "unauthorized"), path


def test_the_two_downloads_the_browser_follows_by_itself_need_no_header(server):
    # Links, which carry no header of their own: what they give is saved, never read by a site.
    assert server().get("/api/events/export", headers=PLAIN).status_code == 200
    assert server().get("/api/saga-archive/1/files/F.xml", headers=PLAIN).status_code != 401
    assert server().post("/api/events/export", headers=PLAIN).status_code == 401


def test_a_file_waiting_for_saga_is_not_one_of_them(server):
    # The page fetches it with its header and saves it itself, so no link to it goes without.
    plain = server().get("/api/saga-files/12345674/files/F.xml", headers=PLAIN)
    from_the_page = server().get("/api/saga-files/12345674/files/F.xml", headers=FROM_THE_PAGE)

    assert (plain.status_code, plain.json()["error"]["code"]) == (401, "unauthorized")
    assert from_the_page.status_code != 401


def test_a_change_must_come_from_the_page_itself(server):
    # A form on another site can post here, but it cannot add a header of its own.
    plain = server().put("/api/clients/12345674/enabled", headers=PLAIN, json={"enabled": False})
    from_the_page = server().put("/api/clients/12345674/enabled", headers=A_CHANGE, json={"enabled": False})

    assert plain.status_code == 401
    assert from_the_page.status_code != 401


def test_a_change_from_the_same_origin_is_let_in(server):
    headers = {**A_CHANGE, "Origin": "http://192.168.1.50:8765"}

    assert server().put("/api/clients/12345674/enabled", headers=headers, json={"enabled": False}).status_code != 401


def test_other_programs_still_need_the_key(server):
    assert server().get("/clients", headers=FROM_THE_PAGE).status_code == 401
    assert server().get("/clients", headers={**KEY, **FROM_THE_PAGE}).status_code == 200


def test_the_local_mode_is_unchanged(cfg, built_page):
    local = TestClient(create_app(cfg, ui_dir=built_page), client=ANOTHER_PC)

    assert local.get("/api/clients", headers=FROM_THE_PAGE).status_code == 401


def test_the_health_answer_names_the_mode(server, cfg, built_page):
    local = TestClient(create_app(cfg, ui_dir=built_page))

    assert server().get("/health").json()["mode"] == "network"
    assert local.get("/health").json()["mode"] == "local"


# --- windows open only on the computer that runs the program ------------------------------------


WINDOW_ROUTES = [
    ("post", "/api/settings/choose-folder", None),
    ("post", "/api/folders/open", {"invoice_id": "1"}),
    ("post", "/api/saga-archive/1/open", None),
    ("post", "/api/backups/open-folder", None),
    ("post", "/api/auth/login/certificate", None),
]


@pytest.mark.parametrize(("method", "path", "body"), WINDOW_ROUTES)
def test_no_window_is_opened_for_another_computer(server, method, path, body):
    reply = getattr(server(service_factory=Windows), method)(path, headers=A_CHANGE, json=body)

    assert (reply.status_code, reply.json()["error"]["code"]) == (409, "not_on_this_computer")


@pytest.mark.parametrize(("method", "path", "body"), WINDOW_ROUTES)
def test_a_browser_on_this_computer_still_gets_its_windows(server, method, path, body):
    reply = getattr(server(client=THIS_PC, service_factory=Windows), method)(
        path, headers={**A_CHANGE, "Host": "localhost:8765"}, json=body,
    )

    assert reply.json().get("error", {}).get("code") != "not_on_this_computer"


def test_the_certificate_login_is_not_offered_to_another_computer(server):
    elsewhere = server(service_factory=Windows).get("/api/auth/status", headers=FROM_THE_PAGE).json()
    here = server(client=THIS_PC, service_factory=Windows).get(
        "/api/auth/status", headers={**FROM_THE_PAGE, "Host": "localhost:8765"},
    ).json()

    assert (elsewhere["certificate_login"], here["certificate_login"]) == (False, True)


def test_the_page_is_told_where_it_is(server, cfg):
    elsewhere = server().get("/api/where", headers=FROM_THE_PAGE).json()
    here = server(client=THIS_PC).get("/api/where", headers={**FROM_THE_PAGE, "Host": "localhost:8765"}).json()

    assert elsewhere == {
        "ok": True,
        "mode": "network",
        "on_this_computer": False,
        "saga_folder": str(cfg.saga_dir),
        "saga_folder_windows": "\\\\192.168.1.50\\AutoSaga-SAGA",
        "saga_folder_mac": "/Volumes/AutoSaga-SAGA",
    }
    assert here["on_this_computer"] is True


def test_in_local_mode_the_page_is_always_on_this_computer(cfg, built_page):
    local = TestClient(create_app(cfg, ui_dir=built_page))

    where = local.get("/api/where", headers={"Sec-Fetch-Site": "same-origin", "Host": "127.0.0.1:8765"}).json()

    assert (where["mode"], where["on_this_computer"]) == ("local", True)


# --- starting it ---------------------------------------------------------------------------------


@pytest.fixture
def run(config_path, monkeypatch, capsys):
    started = {}

    def run_server(cfg, port, network=False):
        started.update(server=port, network=network)

    monkeypatch.setattr(cli, "run_server", run_server)
    monkeypatch.setattr(cli, "open_page_soon", lambda url: started.setdefault("opened", url))
    monkeypatch.setattr(background, "probe", lambda port: None)  # nothing runs yet

    def invoke(*argv):
        code = cli.main(["--config", str(config_path), *argv])
        return code, json.loads(capsys.readouterr().out), started

    return invoke


def test_serve_network_starts_the_server_mode(run):
    code, out, started = run("serve", "--network", "--port", "9001")

    assert (code, started) == (0, {"server": 9001, "network": True})
    assert (out["mode"], out["listening"]) == ("network", "http://0.0.0.0:9001")
    assert out["page"] == "http://autosaga.localhost:9001/ui/"  # on this computer itself


def test_serve_alone_is_still_the_local_mode(run):
    code, out, started = run("serve")

    assert (code, started, out["mode"]) == (0, {"server": 8765, "network": False}, "local")
    assert out["listening"] == "http://127.0.0.1:8765"


@pytest.mark.parametrize(("running", "named"), [("local", "local"), ("network", "server")])
def test_either_mode_is_refused_while_the_program_already_runs(run, monkeypatch, running, named):
    monkeypatch.setattr(background, "probe", lambda port: {"service": "efactura", "mode": running})

    for argv in (["serve"], ["serve", "--network"]):
        code, out, started = run(*argv)
        assert (code, out["error"]["code"], started) == (1, "config_error", {})
        assert named in out["error"]["message"]


def test_the_program_is_started_in_the_background_in_its_mode(cfg, config_path, monkeypatch):
    spawned = []
    answers = iter([None, {"service": "efactura", "mode": "network"}])
    monkeypatch.setattr(background, "probe", lambda port: next(answers))
    monkeypatch.setattr(background, "spawn_server", lambda path, output, network=False: spawned.append(network))

    background.start(cfg, config_path, network=True)

    assert spawned == [True]


def test_stopping_says_which_mode_was_stopped(cfg, monkeypatch):
    answers = iter([{"service": "efactura", "mode": "network"}, None])
    monkeypatch.setattr(background, "probe", lambda port: next(answers))
    monkeypatch.setattr(background, "ask_to_stop", lambda port, key: None)

    assert background.stop(cfg) == {"ok": True, "stopped": True, "network": True}


# --- a database brought over from a Windows PC -----------------------------------------------------

# A full path on the other kind of system: what a database moved between them remembers.
FOREIGN = "/volume1/AutoSaga-SAGA" if os.name == "nt" else "C:\\Users\\contabil\\SAGA Import"


def test_a_saved_saga_folder_from_another_system_is_left_aside(cfg):
    from efactura.service import Service
    from efactura.store import Store

    store = Store(cfg.db_path)
    store.set_setting("saga_dir", FOREIGN)
    store.close()

    service = Service(cfg)
    try:
        assert service.app_settings()["saga_folder"] == str(cfg.saga_dir)
    finally:
        service.close()


def test_a_saved_backup_folder_from_another_system_is_asked_for_again(cfg):
    from efactura import backup
    from efactura.store import Store

    store = Store(cfg.db_path)
    store.set_setting("backup_folder", FOREIGN)
    store.close()

    assert backup.status(cfg)["folder"] is None
    assert backup.run_if_due(cfg) is None  # no copy is written into a folder named after the other system


# --- updates in a container ------------------------------------------------------------------------


def test_in_a_container_the_page_is_told_to_update_on_the_nas(cfg, monkeypatch, tmp_path):
    from efactura import update

    monkeypatch.setenv("EFACTURA_IN_CONTAINER", "1")

    status = update.status(cfg, project=tmp_path)

    assert (status["can_update"], status["why_not_kind"]) == (False, "container")
    with pytest.raises(EfacturaError) as refused:
        update.update(cfg, project=tmp_path)
    assert "README-NAS.md" in refused.value.message


def test_behind_a_proxy_the_origin_may_be_any_name_the_program_knows(server):
    # DSM's reverse proxy may hand the request on as localhost while the browser says where
    # the page is: http://birou-nas, a name listed under [server] names.
    behind = {"Host": "localhost:8765", "X-AutoSaga-Page": "1"}

    known = server().put("/api/clients/12345674/enabled", headers={**behind, "Origin": "http://birou-nas"}, json={"enabled": False})
    unknown = server().put("/api/clients/12345674/enabled", headers={**behind, "Origin": "http://evil.example"}, json={"enabled": False})

    assert (known.status_code != 401, unknown.status_code) == (True, 401)
