"""Connecting to ANAF with the certificate Windows holds, without the browser."""

import subprocess
import threading
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from efactura import auth, certificate_login, journal
from efactura.api import create_app
from efactura.config import load_config
from efactura.errors import EfacturaError
from efactura.service import Service, configure_logging
from efactura.store import Store

from helpers import FakeAnaf

LOGIN = "https://logincert.anaf.ro/anaf-oauth2/v1/authorize?client_id=abc"
ENDED_ON = "https://localhost/callback?code=good-code"
REFUSED = "https://localhost/callback?error=access_denied"
NOW = datetime(2026, 11, 15, 9, 30, tzinfo=timezone(timedelta(hours=2)))
KEY = {"X-API-Key": "local-key"}


def test_the_address_anaf_ends_on_is_handed_back(monkeypatch):
    asked = []
    monkeypatch.setattr(certificate_login, "_run_helper", lambda url: asked.append(url) or {"location": ENDED_ON})

    assert certificate_login.ask_windows(LOGIN) == ENDED_ON
    assert asked == [LOGIN]


def test_the_address_is_handed_back_when_the_answer_also_carries_tries_and_opened(monkeypatch):
    monkeypatch.setattr(
        certificate_login, "_run_helper", lambda url: {"location": ENDED_ON, "tries": 1, "opened": True}
    )

    assert certificate_login.ask_windows(LOGIN) == ENDED_ON


@pytest.mark.parametrize("printed, code", [
    ({"cancelled": True}, "login_cancelled"),
    ({"error": "The remote server returned an error: (400) Bad Request."}, "anaf_error"),
    ({"location": ""}, "anaf_error"),
    ({"location": None}, "anaf_error"),
    ({}, "anaf_error"),
])
def test_what_the_helper_can_come_back_with(monkeypatch, printed, code):
    monkeypatch.setattr(certificate_login, "_run_helper", lambda url: printed)

    with pytest.raises(EfacturaError) as failed:
        certificate_login.ask_windows(LOGIN)

    assert failed.value.code == code


@pytest.mark.parametrize("said, mentions", [
    ('(400) Bad Request. | {"error":"invalid_client","error_description":"Invalid client_id abc"}', "Client ID"),
    ('(400) Bad Request. | {"error":"invalid_request","error_description":"Redirect-URI (https://x) does not match with client app configuration."}', "callback"),
])
def test_a_wrong_client_id_or_callback_is_a_settings_problem(journaled, monkeypatch, said, mentions):
    monkeypatch.setattr(certificate_login, "_run_helper", lambda url: {"error": said})

    with pytest.raises(EfacturaError) as failed:
        certificate_login.ask_windows(LOGIN)

    assert failed.value.code == "config_error"
    assert mentions.lower() in failed.value.message.lower()
    assert said in failed.value.message
    assert _asked(journaled)[0]["data"]["outcome"] == "failed"


@pytest.mark.parametrize("said", [
    "invalid_request without the other part", "Redirect-URI alone", "(500) Server Error.",
])
def test_any_other_helper_error_stays_an_anaf_error(monkeypatch, said):
    monkeypatch.setattr(certificate_login, "_run_helper", lambda url: {"error": said})

    with pytest.raises(EfacturaError) as failed:
        certificate_login.ask_windows(LOGIN)

    assert failed.value.code == "anaf_error"


def test_anafs_own_words_reach_whoever_helps(monkeypatch):
    monkeypatch.setattr(
        certificate_login, "_run_helper",
        lambda url: {"error": "(400) Bad Request. | Invalid client_id abc"},
    )

    with pytest.raises(EfacturaError) as failed:
        certificate_login.ask_windows(LOGIN)

    assert "Invalid client_id abc" in failed.value.message


def _printing(text: bytes):
    """Stands in for subprocess.run: prints `text` and remembers how the helper was started."""
    started = {}

    def run(command, **how):
        started["command"], started["how"] = command, how
        return subprocess.CompletedProcess(command, 0, stdout=text, stderr=b"")

    return run, started


def _helper_printing(monkeypatch, text: bytes) -> dict:
    run, _ = _printing(text)
    monkeypatch.setattr(certificate_login.subprocess, "run", run)
    monkeypatch.setattr(certificate_login, "_powershell", lambda: "powershell.exe")
    return certificate_login._run_helper(LOGIN)


def test_the_helper_gets_the_address_in_its_environment_never_on_the_command_line(monkeypatch):
    run, started = _printing(b'{"location":"https://localhost/callback?code=good-code"}\r\n')
    monkeypatch.setattr(certificate_login.subprocess, "run", run)
    monkeypatch.setattr(certificate_login, "_powershell", lambda: "powershell.exe")

    assert certificate_login._run_helper(LOGIN) == {"location": ENDED_ON}
    assert started["command"] == ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(certificate_login.HELPER)]
    assert started["how"]["env"]["AUTOSAGA_AUTHORIZE_URL"] == LOGIN
    assert started["how"]["timeout"] == certificate_login.TIMEOUT
    assert started["how"]["stdin"] == subprocess.DEVNULL
    assert started["how"]["capture_output"] is True
    assert LOGIN not in " ".join(started["command"])


def test_the_last_non_empty_line_is_the_one_read(monkeypatch):
    printed = b'Some warning\r\n{"error":"old"}\r\n{"location":"https://localhost/callback?code=good-code"}\r\n\r\n\r\n'

    assert _helper_printing(monkeypatch, printed) == {"location": ENDED_ON}


def test_an_ampersand_printed_as_a_json_escape_comes_back_as_an_ampersand(monkeypatch):
    # Windows PowerShell 5.1 prints "&" inside JSON as backslash, u, 0026.
    escape = chr(92) + "u0026"
    printed = ('{"location":"https://localhost/callback?state=1' + escape + 'code=good-code"}').encode()

    assert _helper_printing(monkeypatch, printed) == {"location": "https://localhost/callback?state=1&code=good-code"}


@pytest.mark.parametrize("printed", [b"", b"\r\n\r\n", b"not json at all", b"[]", b'"x"', b"12"])
def test_nothing_usable_printed_says_how_the_helper_ended(monkeypatch, printed):
    assert _helper_printing(monkeypatch, printed) == {"error": "The helper ended with code 0"}


def test_what_the_helper_said_on_standard_error_is_kept(monkeypatch):
    refused = b"\r\n  File C:\\x\\certificate_login.ps1 cannot be loaded because running scripts is disabled.\r\nmore\r\n"

    def run(command, **how):
        return subprocess.CompletedProcess(command, 1, stdout=b"", stderr=refused)

    monkeypatch.setattr(certificate_login.subprocess, "run", run)
    monkeypatch.setattr(certificate_login, "_powershell", lambda: "powershell.exe")

    said = certificate_login._run_helper(LOGIN)["error"]

    assert said.startswith("The helper ended with code 1: File C:")
    assert "running scripts is disabled." in said and "more" not in said


def test_a_long_line_on_standard_error_is_cut(monkeypatch):
    def run(command, **how):
        return subprocess.CompletedProcess(command, 1, stdout=b"", stderr=b"x" * 1000)

    monkeypatch.setattr(certificate_login.subprocess, "run", run)
    monkeypatch.setattr(certificate_login, "_powershell", lambda: "powershell.exe")

    said = certificate_login._run_helper(LOGIN)["error"]

    assert said == "The helper ended with code 1: " + "x" * 300


def test_output_that_is_not_utf8_raises_nothing(monkeypatch):
    assert "error" in _helper_printing(monkeypatch, b'\xff\xfe junk\r\n{"cancelled": true}\xff\r\n')
    assert _helper_printing(monkeypatch, b'\xff\r\n{"cancelled": true}\r\n') == {"cancelled": True}


def test_running_out_of_time_counts_as_cancelled(monkeypatch):
    def too_slow(command, **how):
        raise subprocess.TimeoutExpired(command, how["timeout"])

    monkeypatch.setattr(certificate_login.subprocess, "run", too_slow)
    monkeypatch.setattr(certificate_login, "_powershell", lambda: "powershell.exe")

    assert certificate_login._run_helper(LOGIN) == {"cancelled": True}


def test_powershell_that_cannot_be_started_is_an_error_with_words(monkeypatch):
    def missing(command, **how):
        raise OSError("The system cannot find the file specified")

    monkeypatch.setattr(certificate_login.subprocess, "run", missing)
    monkeypatch.setattr(certificate_login, "_powershell", lambda: "powershell.exe")

    answer = certificate_login._run_helper(LOGIN)

    assert "cannot find the file" in answer["error"]


# --- the journal line ----------------------------------------------------------------------------


@pytest.fixture
def journaled(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[anaf]\nclient_id = "my-client"\nclient_secret = "my-secret"\n'
        f"token_file = '{tmp_path / 'private' / 'tokens.json'}'\n"
        '[api]\nkey = "local-key"\n',
        encoding="utf-8",
    )
    cfg = load_config(path)
    Store(cfg.db_path).close()  # makes the database, and the journal's table with it
    configure_logging(cfg)
    return cfg


def _asked(cfg):
    return [line for line in journal.events(cfg.db_path, details=True)["events"] if line["event"] == "anaf.certificate_asked"]


@pytest.mark.parametrize("printed, outcome", [
    ({"location": ENDED_ON, "tries": 2, "opened": False}, "answered"),
    ({"location": REFUSED}, "answered"),
    ({"cancelled": True}, "cancelled"),
    ({"error": "Windows said no."}, "failed"),
    ({}, "failed"),
])
def test_each_call_leaves_one_journal_line(journaled, monkeypatch, printed, outcome):
    monkeypatch.setattr(certificate_login, "_run_helper", lambda url: printed)

    try:
        certificate_login.ask_windows(LOGIN)
    except EfacturaError:
        pass

    lines = _asked(journaled)
    assert len(lines) == 1
    assert lines[0]["data"]["outcome"] == outcome
    assert lines[0]["duration_ms"] is not None


def test_the_journal_line_holds_how_many_tries_and_whether_the_key_was_opened_first(journaled, monkeypatch):
    monkeypatch.setattr(
        certificate_login, "_run_helper", lambda url: {"location": ENDED_ON, "tries": 2, "opened": False}
    )

    certificate_login.ask_windows(LOGIN)

    data = _asked(journaled)[0]["data"]
    assert data["tries"] == 2 and data["opened_first"] is False


def test_the_journal_line_leaves_out_what_the_helper_did_not_print(journaled, monkeypatch):
    monkeypatch.setattr(certificate_login, "_run_helper", lambda url: {"cancelled": True})

    with pytest.raises(EfacturaError):
        certificate_login.ask_windows(LOGIN)

    assert set(_asked(journaled)[0]["data"]) == {"outcome"}


def test_the_journal_line_holds_neither_the_address_nor_the_code(journaled, monkeypatch):
    monkeypatch.setattr(certificate_login, "_run_helper", lambda url: {"location": ENDED_ON})

    certificate_login.ask_windows(LOGIN)

    line = str(_asked(journaled)[0])
    assert "good-code" not in line and "localhost" not in line and "client_id" not in line


# --- where it is offered -------------------------------------------------------------------------


@pytest.fixture
def cfg(journaled):
    return journaled


def test_it_is_not_offered_off_windows(cfg, monkeypatch):
    monkeypatch.setattr(certificate_login, "_powershell", lambda: "powershell.exe")

    assert certificate_login.available(cfg, system="posix") is False


def test_it_is_offered_on_windows_where_powershell_is_found(cfg, monkeypatch):
    monkeypatch.setattr(certificate_login, "_powershell", lambda: "C:/Windows/powershell.exe")
    assert certificate_login.available(cfg, system="nt") is True

    monkeypatch.setattr(certificate_login, "_powershell", lambda: None)
    assert certificate_login.available(cfg, system="nt") is False


def test_it_is_not_offered_in_the_demo(cfg, monkeypatch):
    from dataclasses import replace

    monkeypatch.setattr(certificate_login, "_powershell", lambda: "powershell.exe")

    assert certificate_login.available(replace(cfg, demo=True), system="nt") is False


def test_the_helper_file_is_beside_the_module_and_plain():
    assert certificate_login.HELPER.is_file()
    assert certificate_login.HELPER.name == "certificate_login.ps1"
    text = certificate_login.HELPER.read_bytes().decode("ascii")  # raises on anything else
    for word in ("Write-Host", "Start-Process", "Invoke-Expression"):
        assert word not in text


def test_the_sentence_in_windows_window_is_written_with_its_diacritics():
    # The file stays ASCII, so the letters are built from their code points.
    text = certificate_login.HELPER.read_text(encoding="ascii")

    assert "[char]0x021B" in text and "[char]0x00EE" in text
    assert "Alegeti" not in text


# --- the service and the route -------------------------------------------------------------------


@pytest.fixture
def anaf():
    return FakeAnaf()


@pytest.fixture
def service(cfg, anaf, monkeypatch):
    monkeypatch.setattr(certificate_login, "available", lambda cfg, system=None: True)
    return Service(cfg, http=anaf.client(), now=lambda: NOW)


def _windows_answers(monkeypatch, address=None, raises=None):
    asked = []

    def ask(url):
        asked.append(url)
        if raises:
            raise raises
        return address

    monkeypatch.setattr(certificate_login, "ask_windows", ask)
    return asked


def test_a_certificate_login_is_saved_like_a_pasted_address(service, cfg, monkeypatch):
    asked = _windows_answers(monkeypatch, ENDED_ON)

    done = service.login_with_certificate()

    assert done["ok"] is True and done["state"] == "valid"
    assert auth.load_tokens(cfg.token_file) is not None
    assert asked[0].startswith("https://logincert.anaf.ro/")


def test_a_refusal_is_login_refused_and_saves_nothing(service, cfg, monkeypatch):
    _windows_answers(monkeypatch, REFUSED)

    with pytest.raises(EfacturaError) as failed:
        service.login_with_certificate()

    assert failed.value.code == "login_refused"
    assert auth.load_tokens(cfg.token_file) is None


def test_no_certificate_chosen_saves_nothing(service, cfg, monkeypatch):
    _windows_answers(monkeypatch, raises=EfacturaError("login_cancelled", "No certificate was chosen."))

    with pytest.raises(EfacturaError) as failed:
        service.login_with_certificate()

    assert failed.value.code == "login_cancelled"
    assert auth.load_tokens(cfg.token_file) is None


def test_where_it_is_not_available_windows_is_not_asked(service, cfg, monkeypatch):
    monkeypatch.setattr(certificate_login, "available", lambda cfg, system=None: False)
    asked = _windows_answers(monkeypatch, ENDED_ON)

    with pytest.raises(EfacturaError) as failed:
        service.login_with_certificate()

    assert failed.value.code == "invalid_input"
    assert asked == []


@pytest.mark.parametrize("offered", [True, False])
def test_the_login_status_says_whether_the_certificate_way_is_offered(cfg, anaf, monkeypatch, offered):
    monkeypatch.setattr(certificate_login, "available", lambda cfg, system=None: offered)

    assert Service(cfg, http=anaf.client(), now=lambda: NOW).auth_status()["certificate_login"] is offered


@pytest.fixture
def api(cfg, anaf, monkeypatch):
    monkeypatch.setattr(certificate_login, "available", lambda cfg, system=None: True)
    return TestClient(create_app(cfg, service_factory=lambda c: Service(c, http=anaf.client(), now=lambda: NOW)))


def test_the_route_answers_with_the_login(api, monkeypatch):
    _windows_answers(monkeypatch, ENDED_ON)

    reply = api.post("/auth/login/certificate", headers=KEY)

    assert reply.status_code == 200 and reply.json()["state"] == "valid"


@pytest.mark.parametrize("address, raises, code", [
    (REFUSED, None, "login_refused"),
    (None, EfacturaError("login_cancelled", "No certificate was chosen."), "login_cancelled"),
])
def test_the_route_answers_409_when_the_login_did_not_happen(api, monkeypatch, address, raises, code):
    _windows_answers(monkeypatch, address, raises)

    reply = api.post("/auth/login/certificate", headers=KEY)

    assert reply.status_code == 409
    assert reply.json()["error"]["code"] == code


def test_the_route_needs_the_key(api):
    assert api.post("/auth/login/certificate").status_code == 401


def test_neither_the_address_nor_the_code_is_kept_anywhere(service, cfg, monkeypatch):
    _windows_answers(monkeypatch, ENDED_ON)

    service.login_with_certificate()

    import sqlite3

    with sqlite3.connect(cfg.db_path) as database:
        written = " ".join(" ".join(str(value) for value in row) for row in database.execute("SELECT * FROM events"))
    written += cfg.log_path.read_text(encoding="utf-8")
    assert "good-code" not in written
    assert "localhost/callback" not in written


def test_a_try_that_ends_on_an_address_with_no_code_is_anafs_fault(service, cfg, monkeypatch):
    _windows_answers(monkeypatch, "https://localhost/callback")

    with pytest.raises(EfacturaError) as failed:
        service.login_with_certificate()

    assert failed.value.code == "anaf_error"
    assert "no code" in failed.value.message
    assert auth.load_tokens(cfg.token_file) is None


def test_a_download_in_progress_refuses_the_try_before_windows_is_asked(service, monkeypatch):
    asked = _windows_answers(monkeypatch, ENDED_ON)

    with service._lock():
        with pytest.raises(EfacturaError) as failed:
            service.login_with_certificate()

    assert failed.value.code == "busy"
    assert asked == []


def test_the_programs_lock_is_free_while_windows_is_asked(service, monkeypatch):
    held = []

    def ask(url):
        with service._lock():  # raises busy if the wait held it
            held.append(True)
        return ENDED_ON

    monkeypatch.setattr(certificate_login, "ask_windows", ask)

    service.login_with_certificate()

    assert held == [True]


def test_a_failed_try_leaves_the_address_in_neither_the_journal_nor_the_log(api, cfg, monkeypatch):
    import sqlite3

    said = 'Cannot convert value "' + LOGIN + '" to type System.Uri.'
    monkeypatch.setattr(certificate_login, "_run_helper", lambda url: {"error": said})

    reply = api.post("/auth/login/certificate", headers=KEY)

    assert reply.status_code == 502
    with sqlite3.connect(cfg.db_path) as database:
        written = " ".join(" ".join(str(value) for value in row) for row in database.execute("SELECT * FROM events"))
    written += cfg.log_path.read_text(encoding="utf-8")
    assert LOGIN not in written and "logincert.anaf.ro/anaf-oauth2" not in written


# --- one helper at a time ------------------------------------------------------------------------


def _two_calls(service, monkeypatch, outcome):
    """Starts a first call that stops inside Windows' question, then a second one, and
    hands back what each came back with once the question is answered."""
    inside, answer, entered, results = threading.Event(), threading.Event(), [], {}

    def ask(url):
        entered.append(url)
        inside.set()
        assert answer.wait(5)
        return outcome()

    monkeypatch.setattr(certificate_login, "ask_windows", ask)

    def call(name):
        try:
            results[name] = service.login_with_certificate()
        except EfacturaError as error:
            results[name] = error

    first = threading.Thread(target=call, args=("first",))
    first.start()
    assert inside.wait(5)
    second = threading.Thread(target=call, args=("second",))
    second.start()
    # The second call is waiting on the first when it holds _running's future and no other
    # helper has been entered.
    return first, second, answer, entered, results


def _finish(first, second, answer):
    answer.set()
    first.join(5)
    second.join(5)
    assert not first.is_alive() and not second.is_alive()


def test_a_second_request_waits_for_the_first_and_gets_its_answer(service, monkeypatch):
    first, second, answer, entered, results = _two_calls(service, monkeypatch, lambda: ENDED_ON)
    try:
        assert len(entered) == 1
    finally:
        _finish(first, second, answer)

    assert len(entered) == 1
    assert results["first"]["state"] == "valid" and results["second"] == results["first"]
    assert certificate_login._running is None


def test_a_second_request_gets_the_same_error(service, monkeypatch):
    def refuse():
        raise EfacturaError("login_cancelled", "No certificate was chosen.")

    first, second, answer, entered, results = _two_calls(service, monkeypatch, refuse)
    _finish(first, second, answer)

    assert len(entered) == 1
    assert [results[name].code for name in ("first", "second")] == ["login_cancelled", "login_cancelled"]
    assert certificate_login._running is None


def test_after_a_run_has_ended_a_new_call_starts_a_new_one(service, monkeypatch):
    asked = _windows_answers(monkeypatch, ENDED_ON)

    service.login_with_certificate()
    service.login_with_certificate()

    assert len(asked) == 2 and certificate_login._running is None
