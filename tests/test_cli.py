import io
import os
import json
from datetime import datetime, timedelta, timezone

import pytest

from efactura import auth, certificate_login, cli
from efactura.auth import Tokens
from efactura.config import load_config
from efactura.service import Service

from helpers import VALID_CUI, FakeAnaf, invoice_xml, line, rich_invoice_xml

NOW = datetime(2026, 11, 11, 9, 30, tzinfo=timezone(timedelta(hours=2)))


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[anaf]\nclient_id = "my-client"\nclient_secret = "my-secret"\n'
        f"token_file = '{tmp_path / 'private' / 'tokens.json'}'\n"
        '[api]\nkey = "local-key"\nport = 9001\n',
        encoding="utf-8",
    )
    return path


@pytest.fixture
def anaf():
    return FakeAnaf()


@pytest.fixture
def opened(monkeypatch):
    """Addresses the command tried to open in the browser."""
    addresses = []
    monkeypatch.setattr(cli, "open_browser", addresses.append)
    return addresses


@pytest.fixture
def run(config_path, anaf, opened, monkeypatch, capsys):
    monkeypatch.setattr(
        cli, "build_service", lambda cfg: Service(cfg, http=anaf.client(), now=lambda: NOW)
    )

    def invoke(*argv, stdin="", config=config_path):
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        code = cli.main(["--config", str(config), *argv])
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return invoke


@pytest.fixture
def logged_in(config_path):
    cfg = load_config(config_path)
    auth.save_tokens(
        cfg.token_file,
        Tokens("access-1", "refresh-1", NOW + timedelta(days=30), NOW + timedelta(days=300), NOW),
    )


# --- the output contract -----------------------------------------------------


def test_command_prints_exactly_one_json_document(run, monkeypatch):
    monkeypatch.setattr(certificate_login, "available", lambda cfg, system=None: False)  # any machine
    code, out, _ = run("auth-status")

    assert code == 0
    assert json.loads(out) == {
        "ok": True,
        "state": "needs_login",
        "access_expires_at": None,
        "refresh_expires_at": None,
        "access_days_left": None,
        "refresh_days_left": None,
        "certificate_login": False,
    }


def test_success_exits_zero(run, anaf, logged_in):
    anaf.add("3001")

    code, out, _ = run("sync", VALID_CUI)

    assert code == 0
    assert json.loads(out)["new_count"] == 1


def test_login_needed_exits_three_with_the_error_in_json(run):
    code, out, _ = run("sync", VALID_CUI)

    assert code == 3
    reply = json.loads(out)
    assert reply["ok"] is False
    assert reply["error"]["code"] == "login_needed"


def test_any_other_failure_exits_one(run, logged_in):
    code, out, _ = run("sync", "12345678")

    assert code == 1
    assert json.loads(out)["error"]["code"] == "invalid_cui"


@pytest.mark.parametrize(
    "argv",
    [("sync",), ("frobnicate",), ("sync", VALID_CUI, "--days", "many"), ("invoices", "--type", "x"), ()],
)
def test_bad_arguments_are_reported_as_json_too(run, argv):
    code, out, _ = run(*argv)

    assert code == 1
    assert json.loads(out)["error"]["code"] == "invalid_input"


def test_missing_settings_file_is_a_config_error(run, tmp_path):
    code, out, _ = run("auth-status", config=tmp_path / "absent.toml")

    assert code == 1
    assert json.loads(out)["error"]["code"] == "config_error"


def test_output_is_plain_ascii_so_romanian_names_survive_the_console(run, anaf, logged_in):
    anaf.add("3001", xml=invoice_xml(supplier_name="Țăran Ștefan SRL"))

    _, out, _ = run("sync", VALID_CUI)

    assert out.isascii()
    assert json.loads(out)["new"][0]["supplier_name"] == "Țăran Ștefan SRL"


def test_unexpected_failure_is_reported_as_json_not_a_traceback(run, monkeypatch):
    def explode(self):
        raise RuntimeError("boom")

    monkeypatch.setattr(Service, "auth_status", explode)

    code, out, err = run("auth-status")

    assert code == 1
    assert json.loads(out)["error"] == {"code": "internal_error", "message": "RuntimeError: boom"}
    assert "Traceback" not in err


def test_activity_is_logged_to_the_data_folder_not_the_output(run, anaf, logged_in, config_path):
    anaf.add("3001")

    _, out, _ = run("sync", VALID_CUI)

    log_text = load_config(config_path).log_path.read_text(encoding="utf-8")
    assert "Download for 12345674 finished: 1 listed, 1 new, 0 failed" in log_text
    json.loads(out)


# --- each command ------------------------------------------------------------


def test_list_previews_without_saving(run, anaf, logged_in):
    anaf.add("3001")

    code, out, _ = run("list", VALID_CUI, "--days", "3")

    reply = json.loads(out)
    assert code == 0
    assert reply["window_days"] == 3
    assert [(m["id"], m["is_new"]) for m in reply["messages"]] == [("3001", True)]
    assert anaf.downloads == []


def test_invoices_filters(run, anaf, logged_in):
    anaf.add("3001")
    anaf.add("3002", tip="FACTURA TRIMISA")
    run("sync", VALID_CUI)
    run("mark-uploaded", "3001")

    _, pending, _ = run("invoices", "--pending")
    _, sent, _ = run("invoices", "--type", "trimisa", "--cui", VALID_CUI, "--since", "2026-11-11")

    assert [i["id"] for i in json.loads(pending)["invoices"]] == ["3002"]
    assert [i["id"] for i in json.loads(sent)["invoices"]] == ["3002"]


def test_invoice_gives_xml_only_when_asked(run, anaf, logged_in):
    anaf.add("3001")
    run("sync", VALID_CUI)

    _, plain, _ = run("invoice", "3001")
    _, full, _ = run("invoice", "3001", "--xml")

    assert "invoice_xml" not in json.loads(plain)["invoice"]
    assert "<cbc:ID>FV-3001</cbc:ID>" in json.loads(full)["invoice"]["invoice_xml"]


def test_mark_uploaded_takes_several_ids_and_can_be_undone(run, anaf, logged_in):
    anaf.add("3001")
    anaf.add("3002")
    run("sync", VALID_CUI)

    code, marked, _ = run("mark-uploaded", "3001", "3002")
    _, undone, _ = run("mark-uploaded", "3001", "--undo")

    assert code == 0
    assert json.loads(marked)["updated"] == ["3001", "3002"]
    assert json.loads(marked)["uploaded_to_accounting"] is True
    assert json.loads(undone)["uploaded_to_accounting"] is False


def test_mark_uploaded_unknown_id_exits_one(run, logged_in):
    code, out, _ = run("mark-uploaded", "9999")

    assert code == 1
    assert json.loads(out)["error"]["code"] == "not_found"


def test_the_saga_import_commands_answer_in_json(run, config_path, logged_in):
    Service(load_config(config_path)).save_client(VALID_CUI, "Alfa Construct SRL")

    _, listed, _ = run("saga-files")
    _, one, _ = run("saga-files", VALID_CUI)
    code, confirmed, _ = run("saga-imported", VALID_CUI, "--version", "abc")
    _, archive, _ = run("saga-archive", VALID_CUI)
    unknown_code, unknown, _ = run("saga-imported", "18547290")

    assert json.loads(listed)["clients"] == [] and json.loads(one)["files"] == []
    assert code == 0 and json.loads(confirmed) == {"ok": True, "archive": None}
    assert json.loads(archive)["imports"] == []
    assert unknown_code == 1 and json.loads(unknown)["error"]["code"] == "not_found"


def test_classify_again_answers_for_one_client_or_for_all(run, config_path, logged_in):
    Service(load_config(config_path)).save_client(VALID_CUI, "Alfa Construct SRL")

    code, one, _ = run("classify-again", VALID_CUI, "--no-jev")
    _, every, _ = run("classify-again", "--all")
    neither_code, neither, _ = run("classify-again")

    assert code == 0
    assert {key: json.loads(one)[key] for key in ("cui", "total", "jev_asked")} == {
        "cui": VALID_CUI, "total": 0, "jev_asked": False,
    }
    assert json.loads(every)["clients"] == []  # nothing waits for an account
    assert neither_code == 1 and json.loads(neither)["error"]["code"] == "invalid_input"


def test_an_invoice_is_split_into_lines_and_one_line_decided_again(run, config_path, logged_in, anaf):
    service = Service(load_config(config_path))
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    service.set_client_per_line(VALID_CUI, False)
    anaf.add("3001", xml=rich_invoice_xml(lines=[line("Motorina", "450.00"), line("Spalare auto", "40.00")]))
    run("sync", VALID_CUI)

    split_code, split, _ = run("split", "3001")
    again_code, again, _ = run("classify", "3001", "--force", "--jev-only", "--line", "2")

    assert (split_code, again_code) == (0, 0)
    assert [entry["method"] for entry in json.loads(split)["invoice"]["line_accounts"]] == ["rules", "invoice"]
    second = json.loads(again)["invoice"]["line_accounts"][1]
    assert second["cont"] is None and second["reason"].startswith("The rules were skipped")  # no OpenRouter key here


# --- login -------------------------------------------------------------------


def test_login_start_returns_the_address_without_opening_a_browser(run, opened):
    code, out, _ = run("login-start")

    assert code == 0
    assert json.loads(out)["authorize_url"].startswith("https://logincert.anaf.ro/")
    assert opened == []


def test_login_start_can_open_the_browser(run, opened):
    _, out, _ = run("login-start", "--open")

    assert opened == [json.loads(out)["authorize_url"]]


def test_login_finish_saves_the_login(run):
    code, out, _ = run("login-finish", "https://localhost/callback?code=good-code")
    _, status, _ = run("auth-status")

    assert code == 0
    assert json.loads(out)["state"] == "valid"
    assert json.loads(status)["state"] == "valid"


def test_login_opens_the_browser_and_reads_the_pasted_address(run, opened):
    code, out, err = run("login", stdin="https://localhost/callback?code=good-code\n")

    assert code == 0
    assert json.loads(out)["state"] == "valid"
    assert len(opened) == 1
    assert "address bar" in err


def test_login_can_skip_opening_the_browser(run, opened):
    code, _, err = run("login", "--no-browser", stdin="https://localhost/callback?code=good-code\n")

    assert code == 0
    assert opened == []
    assert "https://logincert.anaf.ro/" in err


def test_login_asks_again_after_an_expired_code(run, opened):
    pasted = "https://localhost/callback?code=stale\nhttps://localhost/callback?code=good-code\n"

    code, out, err = run("login", stdin=pasted)

    assert code == 0
    assert json.loads(out)["state"] == "valid"
    assert len(opened) == 2
    assert "about a minute" in err


def test_bad_paste_does_not_reopen_the_browser_but_a_later_expired_code_does(run, opened):
    pasted = (
        "https://example.com/wrong-page\n"
        "https://localhost/callback?code=stale\n"
        "https://localhost/callback?code=good-code\n"
    )

    code, _, _ = run("login", stdin=pasted)

    assert code == 0
    assert len(opened) == 2


def test_login_gives_up_after_three_expired_codes(run):
    code, out, _ = run("login", stdin="https://localhost/callback?code=stale\n" * 5)

    assert code == 1
    assert json.loads(out)["error"]["code"] == "login_code_expired"


def test_login_with_nothing_pasted_is_invalid_input(run):
    code, out, _ = run("login", stdin="")

    assert code == 1
    assert json.loads(out)["error"]["code"] == "invalid_input"


# --- serve -------------------------------------------------------------------


def test_serve_starts_the_local_api_on_the_configured_port(run, monkeypatch):
    started = []
    monkeypatch.setattr(cli, "run_server", lambda cfg, port: started.append(port))

    code, out, _ = run("serve")

    assert code == 0
    assert started == [9001]
    assert json.loads(out)["listening"] == "http://127.0.0.1:9001"


def test_serve_port_can_be_overridden(run, monkeypatch):
    started = []
    monkeypatch.setattr(cli, "run_server", lambda cfg, port: started.append(port))

    run("serve", "--port", "9100")

    assert started == [9100]


def test_serve_refuses_to_start_without_an_api_key(run, tmp_path, monkeypatch):
    started = []
    monkeypatch.setattr(cli, "run_server", lambda cfg, port: started.append(port))
    keyless = tmp_path / "keyless.toml"
    keyless.write_text("", encoding="utf-8")

    code, out, _ = run("serve", config=keyless)

    assert code == 1
    assert json.loads(out)["error"]["code"] == "config_error"
    assert started == []


def test_one_bad_round_of_housekeeping_does_not_end_it_for_good(monkeypatch, tmp_path):
    import threading

    from efactura import background, cli

    stopped, rounds = threading.Event(), []

    def a_round(cfg):
        rounds.append(len(rounds))
        if len(rounds) == 1:
            raise RuntimeError("something nobody expected")
        stopped.set()

    monkeypatch.setattr(background, "keep_house", a_round)
    monkeypatch.setattr(cli, "FIRST_HOUSEKEEPING", 0)
    monkeypatch.setattr(cli, "HOUSEKEEPING_EVERY", 0)

    cli._keep_house_until(None, stopped)  # returns only because the second round was reached

    assert rounds == [0, 1]


def test_the_demo_command_builds_the_demo_once_and_starts_on_it(monkeypatch, tmp_path, capsys):
    from efactura import cli, demo

    monkeypatch.delenv("EFACTURA_CONFIG", raising=False)  # registered, so what the command sets is undone

    started = []
    monkeypatch.setattr(demo, "FOLDER", tmp_path / "demo")
    monkeypatch.setattr(cli, "run_dev", lambda cfg, port: started.append(("dev", cfg.demo, port)))
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/pnpm")

    assert cli.main(["demo", "--port", "9100"]) == 0
    kept = tmp_path / "demo" / "data" / "kept.txt"
    kept.write_text("x")
    cli.main(["demo", "--port", "9100"])
    still_there = kept.exists()
    cli.main(["demo", "--fresh", "--port", "9100"])

    assert os.environ["EFACTURA_CONFIG"] == str(tmp_path / "demo" / "config.toml")
    assert still_there and not kept.exists()
    assert started == [("dev", True, 9100)] * 3


def test_without_pnpm_the_demo_serves_the_built_page(monkeypatch, tmp_path, capsys):
    import json

    from efactura import cli, demo

    monkeypatch.delenv("EFACTURA_CONFIG", raising=False)  # registered, so what the command sets is undone

    started = []
    monkeypatch.setattr(demo, "FOLDER", tmp_path / "demo")
    monkeypatch.setattr(cli, "run_server", lambda cfg, port: started.append(("serve", cfg.demo, port)))
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)

    cli.main(["demo", "--port", "9100"])

    said = json.loads(capsys.readouterr().out)
    assert started == [("serve", True, 9100)] and "pnpm" in said["note"] and said["page"].endswith(":9100/ui/")


def test_a_demo_folder_left_by_an_earlier_version_is_built_again(monkeypatch, tmp_path):
    from efactura import cli, demo

    monkeypatch.delenv("EFACTURA_CONFIG", raising=False)  # registered, so what the command sets is undone

    old = tmp_path / "demo"
    (old / "data").mkdir(parents=True)
    (old / "config.toml").write_text('[api]\nkey = "k"\n', encoding="utf-8")  # says nothing of demo
    (old / "data" / "old.txt").write_text("x")
    started = []
    monkeypatch.setattr(demo, "FOLDER", old)
    monkeypatch.setattr(cli, "run_dev", lambda cfg, port: started.append((cfg.demo, port)))
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/pnpm")

    cli.main(["demo"])

    assert started == [(True, 8770)] and not (old / "data" / "old.txt").exists()


def test_sync_all_downloads_for_every_client_that_is_on(run, anaf, logged_in, config_path):
    cfg = load_config(config_path)
    Service(cfg, http=anaf.client(), now=lambda: NOW).save_client(VALID_CUI, "Alfa")
    anaf.add("3001")

    code, out, _ = run("sync-all")

    assert code == 0
    answer = json.loads(out)
    assert answer["status"] == "ok"
    assert answer["clients"] == 1
    assert answer["new"] == 1


def test_the_schedule_is_looked_at_until_the_program_stops(monkeypatch):
    import threading

    from efactura import cli, schedule

    stopped, looks = threading.Event(), []

    def look(cfg):
        looks.append(cfg)
        if len(looks) == 3:
            stopped.set()

    monkeypatch.setattr(schedule, "run_if_due", look)
    monkeypatch.setattr(cli, "FIRST_SCHEDULE_LOOK", 0.01)
    monkeypatch.setattr(cli, "SCHEDULE_LOOK_EVERY", 0.01)

    cli._download_on_schedule_until("cfg", stopped)

    assert looks == ["cfg"] * 3


def test_one_bad_look_at_the_schedule_is_not_the_last(monkeypatch):
    import threading

    from efactura import cli, schedule

    stopped, looks = threading.Event(), []

    def look(cfg):
        looks.append(len(looks))
        if len(looks) == 1:
            raise RuntimeError("something nobody expected")
        stopped.set()

    monkeypatch.setattr(schedule, "run_if_due", look)
    monkeypatch.setattr(cli, "FIRST_SCHEDULE_LOOK", 0)
    monkeypatch.setattr(cli, "SCHEDULE_LOOK_EVERY", 0)

    cli._download_on_schedule_until(None, stopped)

    assert looks == [0, 1]


def test_the_running_program_starts_its_background_threads(config_path, monkeypatch):
    import threading

    import uvicorn

    started = []

    class Recorder:
        def __init__(self, target, args=(), daemon=None):
            self.target = target

        def start(self):
            started.append(self.target)

    monkeypatch.setattr(uvicorn.Server, "run", lambda self: None)
    monkeypatch.setattr(threading, "Thread", Recorder)

    cli.run_server(load_config(config_path), 9001)

    assert started == [
        cli._bring_saga_files_up_to_date, cli._keep_house_until, cli._download_on_schedule_until
    ]


def test_at_its_start_the_program_brings_the_files_for_saga_up_to_date(config_path, monkeypatch):
    asked = []

    class Recorder:
        def __init__(self, cfg):
            asked.append(cfg)

        def write_saga_files(self):
            asked.append("written")

    monkeypatch.setattr(cli, "Service", Recorder)
    cfg = load_config(config_path)

    cli._bring_saga_files_up_to_date(cfg)

    assert asked == [cfg, "written"]


def test_a_failure_while_bringing_the_files_up_to_date_does_not_stop_the_start(config_path, monkeypatch, caplog):
    class Broken:
        def __init__(self, cfg):
            raise RuntimeError("the database is locked")

    monkeypatch.setattr(cli, "Service", Broken)

    cli._bring_saga_files_up_to_date(load_config(config_path))  # does not raise

    assert "files for SAGA" in caplog.text
