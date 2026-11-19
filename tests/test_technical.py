"""The technical side of the journal: each HTTP exchange and the program's own debug records,
kept for whoever looks into how the program works, with every secret hidden."""

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from efactura import auth, background, journal, redact, service as service_module, technical
from efactura.api import create_app
from efactura.auth import Tokens
from efactura.config import load_config
from efactura.errors import ANAF_LIMIT_REACHED, EfacturaError
from efactura.rules import Rule, Rulebook
from efactura.service import Service, configure_logging

from helpers import VALID_CUI, FakeAnaf, FakeOpenRouter, line, rich_invoice_xml, set_rulebook

NOW = datetime(2026, 11, 14, 9, 30, tzinfo=timezone(timedelta(hours=2)))
KEY = {"X-API-Key": "local-key"}
log = logging.getLogger("efactura.service")


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[anaf]\nclient_id = "my-client"\nclient_secret = "my-secret"\n'
        f"token_file = '{tmp_path / 'private' / 'tokens.json'}'\n"
        '[api]\nkey = "local-key"\n[openrouter]\napi_key = "or-test-key"\n',
        encoding="utf-8",
    )
    cfg = load_config(path)
    set_rulebook(cfg.db_path, Rulebook(
        accounts={"302": "Materiale.", "6022": "Combustibil."},
        rules=(Rule("combustibil", "6022", keywords=("motorina",)),),
        instructions="Alege contul facturii.",
    ))
    auth.save_tokens(
        cfg.token_file,
        Tokens("access-1", "refresh-1", NOW + timedelta(days=30), NOW + timedelta(days=300), NOW),
    )
    configure_logging(cfg)
    yield cfg
    redact.forget_all()


def records(cfg, trace=None):
    """In the order they were written."""
    return technical.records(cfg.db_path, trace=trace, oldest_first=True)["records"]


def whole(cfg, record):
    return technical.record(cfg.db_path, record["id"])


def http_records(cfg, trace=None):
    return [r for r in records(cfg, trace) if r["kind"] == "http"]


def everything_stored(cfg) -> str:
    """Every row of every table, and the database's own files as bytes."""
    with sqlite3.connect(cfg.db_path) as database:
        dump = "\n".join(database.iterdump())
    raw = b"".join(
        path.read_bytes() for path in cfg.db_path.parent.glob(cfg.db_path.name + "*") if path.is_file()
    )
    return dump + raw.decode("latin-1")


def sync(cfg, anaf, openrouter=None, ends_with=None):
    """One download, in an operation of its own. `ends_with`: the error code it is expected to end with."""
    if openrouter is not None:
        anaf.openrouter = openrouter
    with journal.trace() as trace:
        service = Service(cfg, http=anaf.client(), now=lambda: NOW)
        if ends_with is None:
            service.sync(VALID_CUI)
        else:
            with pytest.raises(EfacturaError) as ended:
                service.sync(VALID_CUI)
            assert ended.value.code == ends_with
    return trace


# --- the calls to ANAF ------------------------------------------------------------------------------


def test_each_call_to_anaf_is_kept_with_its_address_code_duration_and_reply(cfg):
    anaf = FakeAnaf()
    anaf.add("3001")

    trace = sync(cfg, anaf)

    listed, downloaded = http_records(cfg, trace)
    assert (listed["method"], listed["status"], listed["service"], listed["level"]) == ("GET", 200, "anaf", "info")
    assert "listaMesajePaginatieFactura" in listed["url"] and f"cif={VALID_CUI}" in listed["url"]
    assert isinstance(listed["duration_ms"], int) and listed["trace"] == trace
    assert "body" not in listed  # the list is light: the payloads are read one record at a time
    full = whole(cfg, listed)
    assert dict(full["body"]["request"]["headers"])["authorization"] == redact.HIDDEN
    reply = full["body"]["response"]["body"]
    assert reply["format"] == "json" and json.loads(reply["text"])["mesaje"][0]["id"] == "3001"
    assert downloaded["url"].endswith("/descarcare?id=3001") and downloaded["status"] == 200


def test_a_zip_from_anaf_is_never_kept_only_its_type_and_size(cfg):
    anaf = FakeAnaf()
    anaf.add("3001", xml=rich_invoice_xml(lines=[line("Ciment unic 77", "840.00")], number="FV-UNIC-77"))

    trace = sync(cfg, anaf)

    downloaded = whole(cfg, http_records(cfg, trace)[1])
    size = len(anaf.zips["3001"])
    assert downloaded["body"]["response"]["body"] == {"binary": True, "type": "application/zip", "bytes": size}
    assert downloaded["received"] == {"type": "application/zip", "bytes": size}
    with sqlite3.connect(cfg.db_path) as database:
        kept = " ".join(str(row) for row in database.execute("SELECT * FROM technical WHERE kind = 'http'"))
    assert "FV-UNIC-77" not in kept and "Ciment unic" not in kept


def test_an_error_reply_from_anaf_is_kept_as_it_came(cfg):
    anaf = FakeAnaf()
    anaf.add("3001")
    anaf.throttled_downloads.add("3001")

    trace = sync(cfg, anaf, ends_with=ANAF_LIMIT_REACHED)

    throttled = next(r for r in http_records(cfg, trace) if r["url"].endswith("id=3001"))
    assert (throttled["status"], throttled["level"]) == (429, "warning")
    assert whole(cfg, throttled)["body"]["response"]["body"]["text"] == "Too Many Requests"


def test_an_eroare_in_an_ordinary_reply_is_kept_whole(cfg):
    anaf = FakeAnaf()
    anaf.add("3001")
    anaf.download_errors["3001"] = "Nu aveti drept de descarcare pentru acest mesaj"

    trace = sync(cfg, anaf)

    refused = whole(cfg, http_records(cfg, trace)[1])
    assert json.loads(refused["body"]["response"]["body"]["text"])["eroare"].startswith("Nu aveti drept")


def test_a_call_that_got_no_answer_is_kept_with_why(cfg):
    anaf = FakeAnaf()
    anaf.add("3001")
    anaf.unreachable_downloads.add("3001")

    trace = sync(cfg, anaf)

    lost = http_records(cfg, trace)[1]
    assert (lost["status"], lost["level"], lost["error"]) == (None, "error", "ConnectError: connection reset")
    assert dict(whole(cfg, lost)["body"]["request"]["headers"])["authorization"] == redact.HIDDEN


# --- the calls to Jev and the login -----------------------------------------------------------------


def test_what_was_asked_of_jev_and_what_it_answered_are_kept(cfg, monkeypatch):
    monkeypatch.setattr(service_module, "_pause", lambda seconds: None)
    openrouter = FakeOpenRouter()
    openrouter.answer_for("ciment", "302", confidence=0.93)
    anaf = FakeAnaf()
    anaf.add("3002", xml=rich_invoice_xml(lines=[line("Ciment Portland", "840.00")], number="FV-2"))

    trace = sync(cfg, anaf, openrouter)

    (asked,) = [r for r in http_records(cfg, trace) if r["service"] == "jev"]
    assert (asked["method"], asked["status"], asked["url"]) == ("POST", 200, "https://openrouter.ai/api/alpha/decisions")
    full = whole(cfg, asked)
    sent = json.loads(full["body"]["request"]["body"]["text"])
    assert "Ciment Portland" in json.dumps(sent, ensure_ascii=False)
    assert json.loads(full["body"]["response"]["body"]["text"])["usage"]["input_tokens"] == 400
    assert dict(full["body"]["request"]["headers"])["authorization"] == redact.HIDDEN
    assert "or-test-key" not in everything_stored(cfg)


def test_the_login_hides_its_code_the_client_secret_and_the_tokens_it_gets(cfg):
    anaf = FakeAnaf()
    service = Service(cfg, http=anaf.client(), now=lambda: NOW)

    with journal.trace() as trace:
        service.login_finish("https://localhost/callback?code=good-code")

    (exchange,) = http_records(cfg, trace)
    assert (exchange["method"], exchange["service"], exchange["status"]) == ("POST", "anaf_login", 200)
    full = whole(cfg, exchange)
    assert f"code={redact.HIDDEN}" in full["body"]["request"]["body"]["text"]
    assert dict(full["body"]["request"]["headers"])["authorization"] == redact.HIDDEN
    answer = json.loads(full["body"]["response"]["body"]["text"])
    assert (answer["access_token"], answer["refresh_token"], answer["expires_in"]) == (redact.HIDDEN, redact.HIDDEN, 7776000)
    stored = everything_stored(cfg)
    assert [secret for secret in ("good-code", "access-2", "refresh-2", "my-secret") if secret in stored] == []


def test_renewing_the_login_is_kept_without_the_refresh_token(cfg):
    auth.save_tokens(
        cfg.token_file,
        Tokens("access-1", "refresh-1", NOW - timedelta(minutes=1), NOW + timedelta(days=300), NOW - timedelta(days=90)),
    )
    anaf = FakeAnaf()
    anaf.add("3001")

    trace = sync(cfg, anaf)

    renewal = http_records(cfg, trace)[0]
    assert renewal["service"] == "anaf_login"
    assert f"refresh_token={redact.HIDDEN}" in whole(cfg, renewal)["body"]["request"]["body"]["text"]
    stored = everything_stored(cfg)
    assert [secret for secret in ("refresh-1", "refresh-2", "access-2") if secret in stored] == []


# --- the program's own records ------------------------------------------------------------------------


def test_the_programs_debug_records_are_kept_with_where_they_were_written(cfg):
    with journal.trace() as trace:
        log.debug("Window %s to %s", "2026-11-09", "2026-11-14")

    (kept,) = records(cfg, trace)
    assert (kept["kind"], kept["level"], kept["summary"]) == ("log", "debug", "Window 2026-11-09 to 2026-11-14")
    assert kept["logger"] == "efactura.service" and kept["where"].startswith("test_technical.py:")
    assert kept["function"] == "test_the_programs_debug_records_are_kept_with_where_they_were_written"


def test_debug_records_reach_neither_the_text_log_nor_the_ordinary_journal(cfg):
    log.debug("Only for the technical view")

    assert "Only for the technical view" not in cfg.log_path.read_text(encoding="utf-8")
    assert all("Only for" not in line_["message"] for line_ in journal.events(cfg.db_path, details=True)["events"])


def test_records_from_information_up_stay_journal_lines_and_are_not_kept_twice(cfg):
    with journal.trace() as trace:
        log.warning("Message %s failed", "3001")
        journal.record("rules", "rule.added", "Rule added.")

    assert records(cfg, trace) == []
    (warned,) = [line_ for line_ in journal.events(cfg.db_path, trace=trace)["events"] if line_["area"] == "program"]
    assert warned["data"]["logger"] == "efactura.service" and warned["data"]["where"].startswith("test_technical.py:")


def test_an_exception_in_a_debug_record_is_kept_with_its_traceback(cfg):
    try:
        raise ValueError("broken")
    except ValueError:
        log.debug("Could not read it", exc_info=True)

    (kept,) = records(cfg)
    assert kept["has_exception"] is True
    assert "ValueError: broken" in whole(cfg, kept)["body"]["exception"]


# --- what is kept and for how long ------------------------------------------------------------------


def test_a_long_reply_is_cut_and_says_how_long_it_was(cfg, monkeypatch):
    monkeypatch.setattr(technical, "BODY_LIMIT", 100)
    anaf = FakeAnaf()
    for number in range(20):
        anaf.add(str(4000 + number), with_zip=False)

    trace = sync(cfg, anaf)

    reply = whole(cfg, http_records(cfg, trace)[0])["body"]["response"]["body"]
    assert len(reply["text"]) == 100 and reply["cut"] is True and reply["bytes"] > 1000


def test_a_reply_too_large_to_look_at_is_not_kept(cfg, monkeypatch):
    monkeypatch.setattr(technical, "TOO_LARGE", 200)
    anaf = FakeAnaf()
    for number in range(5):
        anaf.add(str(4000 + number), with_zip=False)

    trace = sync(cfg, anaf)

    reply = whole(cfg, http_records(cfg, trace)[0])["body"]["response"]["body"]
    assert reply["too_large"] is True and "text" not in reply and reply["bytes"] > 200


def test_the_whole_stays_under_its_size_limit_the_oldest_going_first(cfg, monkeypatch):
    monkeypatch.setattr(technical, "TOTAL_BYTES", 2000)
    monkeypatch.setattr(technical, "TRIM_EVERY", 1)
    for number in range(60):
        log.debug("Record number %03d with some words to take room", number)

    with sqlite3.connect(cfg.db_path) as database:
        total, oldest = database.execute("SELECT SUM(size), MIN(summary) FROM technical").fetchone()
    assert total <= 2000
    assert records(cfg)[-1]["summary"].startswith("Record number 059")
    assert not oldest.startswith("Record number 000")


def test_records_older_than_seven_days_or_beyond_the_count_are_removed(cfg, monkeypatch):
    now = datetime.now().astimezone()  # the records below are written at the clock's time
    with sqlite3.connect(cfg.db_path) as database:
        database.execute(
            "INSERT INTO technical (at, trace, kind, level, summary, head, body, size) "
            "VALUES (?, NULL, 'log', 'debug', 'old', '{}', '{}', 3)",
            ((now - timedelta(days=8)).isoformat(),),
        )
    for number in range(4):
        log.debug("new %s", number)
    monkeypatch.setattr(technical, "KEEP_RECORDS", 3)

    removed = technical.prune(cfg.db_path, now)

    assert removed == 2
    assert [r["summary"] for r in records(cfg)] == ["new 1", "new 2", "new 3"]


def test_housekeeping_clears_the_technical_records_too(cfg):
    with sqlite3.connect(cfg.db_path) as database:
        database.execute(
            "INSERT INTO technical (at, trace, kind, level, summary, head, body, size) "
            "VALUES (?, NULL, 'log', 'debug', 'old', '{}', '{}', 3)",
            ((NOW - timedelta(days=8)).isoformat(),),
        )

    background.keep_house(cfg, NOW)

    assert records(cfg) == []


def test_keeping_a_record_can_never_break_the_work(cfg, monkeypatch):
    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(technical, "_insert", broken)
    anaf = FakeAnaf()
    anaf.add("3001")

    with journal.trace():
        result = Service(cfg, http=anaf.client(), now=lambda: NOW).sync(VALID_CUI)
    log.debug("still fine")

    assert result["new_count"] == 1


def test_a_client_is_watched_once_however_often_it_is_asked(cfg):
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="ok")))
    technical.watch(client)
    technical.watch(client)

    client.get("https://api.anaf.ro/prod/FCTEL/rest/health")

    assert len(http_records(cfg)) == 1


# --- over the API ----------------------------------------------------------------------------------------


def test_one_operations_records_are_read_over_the_api_lightly_and_one_of_them_whole(cfg):
    anaf = FakeAnaf()
    anaf.add("3001")
    trace = sync(cfg, anaf)
    api = TestClient(create_app(cfg))

    listed = api.get(f"/events/technical?trace={trace}", headers=KEY).json()
    calls = [r for r in listed["records"] if r["kind"] == "http"]
    the_list = next(r for r in calls if "listaMesaje" in r["url"])
    opened = api.get(f"/events/technical/{the_list['id']}", headers=KEY).json()

    assert listed["ok"] and listed["has_more"] is False and len(calls) == 2
    assert calls[0]["id"] > calls[1]["id"]  # newest first, as the journal
    assert "body" not in the_list and opened["record"]["body"]["response"]["body"]["format"] == "json"
    assert api.get("/events/technical/999999", headers=KEY).status_code == 404
    assert api.get(f"/events/technical?trace={trace}").status_code == 401
    assert api.get(f"/api/events/technical?trace={trace}", headers={
        "Sec-Fetch-Site": "same-origin", "Host": "127.0.0.1:8765",
    }).status_code == 200


def test_the_journal_says_how_many_requests_and_program_records_each_operation_has(cfg):
    anaf = FakeAnaf()
    anaf.add("3001")
    anaf.add("3002")
    anaf.throttled_downloads.add("3002")
    trace = sync(cfg, anaf, ends_with=ANAF_LIMIT_REACHED)
    with journal.trace(fresh=True) as quiet:
        journal.record("rules", "rule.added", "Rule added.")
    api = TestClient(create_app(cfg))

    plain = api.get("/events", headers=KEY).json()
    counted = api.get("/events?technical=true", headers=KEY).json()

    assert "technical" not in plain
    assert counted["technical"][trace]["http"] == 3 and counted["technical"][trace]["problems"] == 1
    assert counted["technical"][trace]["log"] >= 1
    assert quiet not in counted["technical"]


def test_the_saved_journal_holds_one_line_per_technical_record_only_when_asked(cfg):
    anaf = FakeAnaf()
    anaf.add("3001")
    trace = sync(cfg, anaf)
    api = TestClient(create_app(cfg))

    plain = api.get(f"/events/export?trace={trace}", headers=KEY).text
    technical_too = api.get(f"/events/export?trace={trace}&technical=true", headers=KEY).text

    assert "GET https://api.anaf.ro" not in plain
    lines = technical_too.splitlines()
    asked = next(number for number, text in enumerate(lines) if "GET https://api.anaf.ro" in text and "lista" in text)
    started = next(number for number, text in enumerate(lines) if "Download started" in text)
    finished = next(number for number, text in enumerate(lines) if "Download for" in text and "finished" in text)
    assert finished < asked < started  # newest first, as the rest of the file, each where it happened
    assert " 200 " in lines[asked]


# --- secrets ------------------------------------------------------------------------------------------------


FAKE = {
    "access": "FAKE-ACCESS-9f31c0d2a7",
    "refresh": "FAKE-REFRESH-5b80e1f4c3",
    "new_access": "FAKE-NEWACCESS-0a2b4c6d8e",
    "new_refresh": "FAKE-NEWREFRESH-1c3e5a7b9d",
    "code": "FAKE-CODE-77aa31bb52",
    "client_secret": "FAKE-CLIENTSECRET-4e5f6a7b",
    "openrouter": "sk-or-v1-FAKEOPENROUTER0123456789",
    "api_key": "FAKE-APIKEY-3c4d5e6f7a",
    "pin": "FAKE-PIN-8462",
    "url_token": "FAKE-URLTOKEN-6d7e8f9a0b",
    "cookie": "FAKE-COOKIE-2a3b4c5d6e",
    "body_secret": "FAKE-BODYSECRET-9e8d7c6b5a",
    "header": "FAKE-HEADER-1f2e3d4c5b",
}


@pytest.fixture
def secret_cfg(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        f'[anaf]\nclient_id = "my-client"\nclient_secret = "{FAKE["client_secret"]}"\n'
        f"token_file = '{tmp_path / 'private' / 'tokens.json'}'\n"
        f'[api]\nkey = "{FAKE["api_key"]}"\n[openrouter]\napi_key = "{FAKE["openrouter"]}"\n',
        encoding="utf-8",
    )
    cfg = load_config(path)
    set_rulebook(cfg.db_path, Rulebook(accounts={"302": "Materiale."}, rules=(), instructions="Alege contul."))
    configure_logging(cfg)
    yield cfg
    redact.forget_all()


def test_a_fake_secret_sent_through_every_path_never_reaches_the_database_or_the_api(secret_cfg, monkeypatch):
    cfg = secret_cfg
    monkeypatch.setattr(service_module, "_pause", lambda seconds: None)
    openrouter = FakeOpenRouter()
    openrouter.valid_keys = {FAKE["openrouter"]}
    anaf = FakeAnaf()
    anaf.valid_codes = {FAKE["code"]}
    anaf.valid_access = {FAKE["new_access"]}
    anaf.openrouter = openrouter
    anaf.add("3001", xml=rich_invoice_xml(lines=[line("Ciment Portland", "840.00")], number="FV-1"))
    anaf.add("3002")
    anaf.unreachable_downloads.add("3002")

    def login_service(request):
        """ANAF's login service, giving out the fake tokens, and refusing a second code with the
        code and the client secret quoted back, as a careless server might."""
        form = dict(httpx.QueryParams(request.content.decode()))
        if form.get("grant_type") == "authorization_code" and form.get("code") == FAKE["code"]:
            return httpx.Response(200, json={
                "access_token": FAKE["new_access"], "refresh_token": FAKE["new_refresh"],
                "token_type": "Bearer", "expires_in": 7776000,
            })
        return httpx.Response(400, text=f"bad code={form.get('code')} for client_secret={FAKE['client_secret']}")

    def answer(request):
        if request.url.host == "logincert.anaf.ro":
            return login_service(request)
        return anaf._handle(request)

    http = httpx.Client(transport=httpx.MockTransport(answer))
    service = Service(cfg, http=http, now=lambda: NOW)
    with journal.trace() as login_trace:
        # 1. the login: the code in the form, the client secret in the Basic header, the tokens in the reply
        service.login_finish(f"https://localhost/callback?code={FAKE['code']}")
        # 2. a second login, refused with the secrets quoted in the error body
        with pytest.raises(Exception):
            service.login_finish(f"https://localhost/callback?code={FAKE['code']}x")
    with journal.trace() as sync_trace:
        # 3. ANAF's calls with the access token in the header; one unanswered; Jev with its key
        service.sync(VALID_CUI)

    # 4. any address, header, cookie or body that carries a secret, and a reply quoting them back
    def echo(request):
        return httpx.Response(
            401,
            headers={"Set-Cookie": f"session={FAKE['cookie']}", "Content-Type": "application/json"},
            json={"you_sent": request.headers.get("authorization"), "client_secret": FAKE["body_secret"],
                  "note": f"refresh_token={FAKE['refresh']} and key {FAKE['openrouter']}"},
        )

    watched = technical.watch(httpx.Client(transport=httpx.MockTransport(echo)))
    with journal.trace() as echo_trace:
        watched.post(
            f"https://api.anaf.ro/prod/FCTEL/rest/x?cif=1&token={FAKE['url_token']}&key={FAKE['url_token']}",
            headers={"Authorization": f"Bearer {FAKE['new_access']}", "Cookie": f"sid={FAKE['cookie']}",
                     "X-Custom-Token": FAKE["header"]},
            json={"client_secret": FAKE["body_secret"], "deep": [{"refresh_token": FAKE["refresh"]}]},
        )

    # 5. the program's own records and journal lines that quote a secret
    with journal.trace() as log_trace:
        log.debug("Renewing with refresh token %s", FAKE["new_refresh"])
        log.debug("PIN: %s", FAKE["pin"])
        log.warning("ANAF refused access_token=%s", FAKE["new_access"])
        try:
            raise RuntimeError(f"Authorization: Bearer {FAKE['new_access']}")
        except RuntimeError:
            log.exception("Call failed")
            log.debug("Call failed again", exc_info=True)
        journal.record("anaf", None, f"Odd reply mentioning {FAKE['new_refresh']}", pin=FAKE["pin"],
                       detail=f"api_key={FAKE['openrouter']}")

    # 6. the page itself, sending the program's key
    api = TestClient(create_app(cfg))
    page = {"X-API-Key": FAKE["api_key"]}
    shown = [
        api.get("/events?details=true&technical=true&limit=1000", headers=page).text,
        api.get("/events/export?technical=true", headers=page).text,
    ]
    for trace in (login_trace, sync_trace, echo_trace, log_trace):
        listed = api.get(f"/events/technical?trace={trace}", headers=page)
        shown.append(listed.text)
        shown.extend(api.get(f"/events/technical/{r['id']}", headers=page).text for r in listed.json()["records"])
    shown.append(api.get("/events?details=true&limit=1000", headers=page).text)

    stored = everything_stored(cfg)
    assert [name for name, value in FAKE.items() if value in stored] == []
    assert [name for name, value in FAKE.items() if any(value in text for text in shown)] == []
    # and the paths were all taken
    assert len(http_records(cfg, login_trace)) == 2 and len(http_records(cfg, echo_trace)) == 1
    services = {r["service"] for r in http_records(cfg, sync_trace)}
    assert services == {"anaf", "jev"} and any(r["status"] is None for r in http_records(cfg, sync_trace))
    assert len(records(cfg, log_trace)) == 3
    assert redact.HIDDEN in stored
