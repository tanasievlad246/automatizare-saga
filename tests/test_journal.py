"""The journal: what the program did, line by line, and which lines belong to one operation."""

import asyncio
import logging
import socket
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from efactura import auth, jev, journal, service as service_module
from efactura.api import create_app
from efactura.auth import Tokens
from efactura.config import load_config
from efactura.rules import Rule, Rulebook
from efactura.service import Service, configure_logging
from efactura.store import Store

from helpers import VALID_CUI, FakeAnaf, FakeOpenRouter, line, rich_invoice_xml, set_rulebook

NOW = datetime(2026, 11, 14, 9, 30, tzinfo=timezone(timedelta(hours=2)))
KEY = {"X-API-Key": "local-key"}
# Everything in these tests that must never reach the journal.
SECRETS = ("my-secret", "or-test-key", "local-key", "access-1", "refresh-1", "good-code")


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
    return cfg


def rows(cfg, **wanted):
    return journal.events(cfg.db_path, **wanted)["events"]


def everything_written(cfg):
    with sqlite3.connect(cfg.db_path) as database:
        return " ".join(" ".join(str(value) for value in row) for row in database.execute("SELECT * FROM events"))


# --- writing -----------------------------------------------------------------------------------


def test_a_line_is_kept_with_its_details(cfg):
    journal.record("rules", "rule.added", "Rule added.", name="ciment", cont="302", now=NOW)

    (line_,) = rows(cfg)

    assert (line_["area"], line_["event"], line_["message"], line_["level"]) == ("rules", "rule.added", "Rule added.", "info")
    assert (line_["data"], line_["at"], line_["trace"]) == ({"name": "ciment", "cont": "302"}, NOW.isoformat(), None)


def test_writing_can_never_break_the_work(tmp_path, cfg):
    journal.configure(tmp_path / "missing" / "nowhere.db")
    journal.record("rules", "rule.added", "Rule added.")  # no table, no folder: must not raise
    journal.configure(None)
    journal.record("rules", "rule.added", "Rule added.")  # not set up at all

    journal.configure(cfg.db_path)
    assert rows(cfg) == []


def test_anything_that_looks_like_a_key_is_hidden(cfg):
    journal.record("settings", "settings.secret_changed", "A key was changed.", name="openrouter_api_key",
                   api_key="sk-live", client_secret="s3cret", access_token="tok-9f1", password="pw-77")

    (line_,) = rows(cfg)

    assert line_["data"]["name"] == "openrouter_api_key"
    assert {line_["data"][name] for name in ("api_key", "client_secret", "access_token", "password")} == {"[hidden]"}
    assert not any(secret in everything_written(cfg) for secret in ("sk-live", "s3cret", "tok-9f1", "pw-77"))


def test_lines_of_one_operation_share_a_trace(cfg):
    with journal.trace() as first:
        journal.record("sync", "sync.started", "Started.")
        with journal.trace() as inner:  # a step inside the same operation
            journal.record("anaf", "anaf.call", "Called.", level="detail")
    with journal.trace() as second:
        journal.record("sync", "sync.started", "Started again.")
    journal.record("program", "program.started", "Outside any operation.")

    assert inner == first and second != first and len(first) >= 8
    assert [line_["event"] for line_ in rows(cfg, trace=first, oldest_first=True)] == ["sync.started", "anaf.call"]
    assert [line_["trace"] for line_ in rows(cfg, details=True, oldest_first=True)] == [first, first, second, None]


def test_the_programs_ordinary_log_lines_land_in_the_journal_too(cfg):
    log = logging.getLogger("efactura.service")
    log.warning("Message %s repeats invoice %s", "3002", "FV-1")
    try:
        raise ValueError("boom")
    except ValueError:
        log.exception("Could not classify message %s", "3003")

    warning, error = rows(cfg, oldest_first=True)

    assert (warning["level"], warning["message"], warning["event"]) == ("warning", "Message 3002 repeats invoice FV-1", None)
    assert (error["level"], error["message"]) == ("error", "Could not classify message 3003")
    assert "ValueError: boom" in error["data"]["traceback"]


# --- reading -----------------------------------------------------------------------------------


@pytest.fixture
def filled(cfg):
    journal.record("sync", "sync.finished", "Sync finished for 12345674.", now=NOW - timedelta(days=2), cui="12345674")
    journal.record("page", "page.request", "GET /api/clients", level="detail", now=NOW - timedelta(hours=3))
    journal.record("jev", "jev.failed", "Jev did not answer.", level="warning", now=NOW - timedelta(hours=2))
    journal.record("backup", "backup.failed", "Folder E:\\\\Copii was not found.", level="error", now=NOW - timedelta(hours=1))
    journal.record("rules", "rule.added", "Rule added.", now=NOW, name="ciment")
    return cfg


def test_the_newest_line_comes_first_and_details_are_left_out_unless_asked(filled):
    shown = rows(filled)
    with_details = rows(filled, details=True)

    assert [line_["event"] for line_ in shown] == ["rule.added", "backup.failed", "jev.failed", "sync.finished"]
    assert [line_["event"] for line_ in with_details][2:4] == ["jev.failed", "page.request"]


def test_lines_can_be_narrowed_to_problems_an_area_a_period_or_a_word(filled):
    assert [line_["event"] for line_ in rows(filled, problems_only=True)] == ["backup.failed", "jev.failed"]
    assert [line_["event"] for line_ in rows(filled, area="rules")] == ["rule.added"]
    assert [line_["event"] for line_ in rows(filled, since=(NOW - timedelta(hours=4)).isoformat())] == [
        "rule.added", "backup.failed", "jev.failed",
    ]
    assert [line_["event"] for line_ in rows(filled, text="copii")] == ["backup.failed"]  # the message
    assert [line_["event"] for line_ in rows(filled, text="CIMENT")] == ["rule.added"]  # the details


def test_older_lines_are_read_a_page_at_a_time(filled):
    first = journal.events(filled.db_path, limit=3)
    rest = journal.events(filled.db_path, limit=3, before=first["events"][-1]["id"])

    assert (len(first["events"]), first["has_more"]) == (3, True)
    assert ([line_["event"] for line_ in rest["events"]], rest["has_more"]) == (["sync.finished"], False)


def test_the_journal_can_be_saved_as_text(filled):
    text = journal.as_text(journal.events(filled.db_path, details=True)["events"])

    assert text.splitlines()[0].startswith(f"{NOW.isoformat()}  INFO     rules")
    assert "Rule added.  name=ciment" in text
    assert len(text.splitlines()) == 5


def test_lines_older_than_thirty_days_are_removed(cfg):
    journal.record("sync", "sync.finished", "Old.", now=NOW - timedelta(days=31))
    journal.record("sync", "sync.finished", "Kept.", now=NOW - timedelta(days=29))

    removed = journal.prune(cfg.db_path, NOW)

    assert removed == 1
    assert [line_["message"] for line_ in rows(cfg)] == ["Kept."]


def test_no_more_than_the_limit_is_kept(cfg, monkeypatch):
    monkeypatch.setattr(journal, "KEEP_LINES", 3)
    for number in range(5):
        journal.record("sync", "sync.finished", f"Line {number}.", now=NOW + timedelta(seconds=number))

    journal.prune(cfg.db_path, NOW + timedelta(minutes=1))

    assert [line_["message"] for line_ in rows(cfg)] == ["Line 4.", "Line 3.", "Line 2."]


# --- what the program itself writes ---------------------------------------------------------------


@pytest.fixture
def downloaded(cfg, monkeypatch):
    """One download: an invoice a rule decides and one Jev decides."""
    monkeypatch.setattr(service_module, "_pause", lambda seconds: None)
    openrouter = FakeOpenRouter()
    openrouter.answer_for("ciment", "302", confidence=0.93)
    anaf = FakeAnaf()
    anaf.openrouter = openrouter
    anaf.add("3001", xml=rich_invoice_xml(lines=[line("Motorina Euro 5", "450.00")], number="FV-1"))
    anaf.add("3002", xml=rich_invoice_xml(lines=[line("Ciment Portland", "840.00")], number="FV-2"))
    with journal.trace() as trace:
        Service(cfg, http=anaf.client(), now=lambda: NOW).sync(VALID_CUI)
    return cfg, trace


def test_the_end_of_a_download_says_how_many_invoices_were_received_and_how_many_issued(cfg):
    anaf = FakeAnaf()
    anaf.add("3001", tip="FACTURA TRIMISA")
    anaf.add("3002", tip="FACTURA TRIMISA")
    anaf.add("3003", xml=rich_invoice_xml(lines=[line("Motorina Euro 5", "450.00")], number="FV-1"))
    with journal.trace() as trace:
        Service(cfg, http=anaf.client(), now=lambda: NOW).sync(VALID_CUI)

    finished = rows(cfg, trace=trace, oldest_first=True)[-1]

    assert finished["event"] == "sync.finished"
    assert (finished["data"]["new"], finished["data"]["received"], finished["data"]["issued"]) == (3, 1, 2)


def test_a_download_leaves_its_whole_story_under_one_trace(downloaded):
    cfg, trace = downloaded

    story = rows(cfg, trace=trace, details=True, oldest_first=True)
    events = [line_["event"] for line_ in story]

    assert events[0] == "sync.started" and events[-1] == "sync.finished"
    assert events.count("anaf.call") == 3  # the list, and one download per message
    assert [e for e in events if e and e.startswith("account.")] == ["account.by_rule", "account.by_jev"]
    assert "jev.answered" in events
    finished = story[-1]
    assert (finished["data"]["cui"], finished["data"]["new"], finished["data"]["failed"]) == (VALID_CUI, 2, 0)
    assert finished["duration_ms"] is not None
    by_jev = next(line_ for line_ in story if line_["event"] == "account.by_jev")
    assert (by_jev["data"]["cont"], by_jev["data"]["confidence"], by_jev["data"]["invoice_number"]) == ("302", 0.93, "FV-2")


def test_no_key_or_token_ever_reaches_the_journal(downloaded, monkeypatch):
    cfg, _ = downloaded
    service = Service(cfg, now=lambda: NOW)
    service.set_secret("openrouter_api_key", "or-test-key-2")
    service.save_rule(name="ciment", cont="302", keywords=["ciment"])
    api = TestClient(create_app(cfg))
    api.put("/secrets/anaf_client_secret", headers=KEY, json={"value": "my-secret-2"})
    api.get("/secrets", headers=KEY)

    written = everything_written(cfg)

    assert [secret for secret in (*SECRETS, "or-test-key-2", "my-secret-2") if secret in written] == []
    assert "settings.secret_changed" in written and "openrouter_api_key" in written


def test_each_request_from_the_page_is_a_detail_with_its_own_trace(cfg):
    api = TestClient(create_app(cfg))

    first = api.get("/clients", headers=KEY)
    second = api.post("/clients", headers=KEY, json={"cui": VALID_CUI, "name": "Alfa Construct SRL"})
    api.get("/events", headers=KEY)
    api.get("/health")

    requests = rows(cfg, area="page", details=True, oldest_first=True)
    assert [(line_["data"]["method"], line_["data"]["path"], line_["data"]["status"]) for line_ in requests] == [
        ("GET", "/clients", 200), ("POST", "/clients", 200),
    ]
    assert first.headers["X-Trace-Id"] == requests[0]["trace"] != second.headers["X-Trace-Id"]
    saved = rows(cfg, trace=second.headers["X-Trace-Id"], details=True, oldest_first=True)
    assert [line_["event"] for line_ in saved] == ["client.saved", "page.request"]
    assert "Alfa Construct SRL" not in requests[1]["message"]  # the body of a request is never written


def test_a_request_is_its_own_operation_though_the_program_was_started_inside_one(cfg):
    # `efactura serve` runs the server inside the trace of its own command, and every task the
    # server makes starts with a copy of that. A request must not join it.
    async def two_requests():
        served = httpx.ASGITransport(app=create_app(cfg))
        async with httpx.AsyncClient(transport=served, base_url="http://testserver", headers=KEY) as page:
            return [(await page.get("/clients")).headers["X-Trace-Id"] for _ in range(2)]

    with journal.trace() as command:
        journal.record("program", "program.started", "The program started.")
        first, second = asyncio.run(two_requests())

    assert len({command, first, second}) == 3
    assert [line_["event"] for line_ in rows(cfg, trace=command)] == ["program.started"]
    assert [line_["event"] for line_ in rows(cfg, trace=first)] == ["page.request"]


def test_a_request_that_crashes_is_filed_under_itself_with_what_went_wrong(cfg):
    def crashing(cfg):
        raise RuntimeError("boom")

    async def one_request():
        served = httpx.ASGITransport(app=create_app(cfg, service_factory=crashing), raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=served, base_url="http://testserver", headers=KEY) as page:
            return await page.get("/clients")

    with journal.trace() as command:
        reply = asyncio.run(one_request())

    assert (reply.status_code, reply.json()["error"]["code"]) == (500, "internal_error")
    its_own = reply.headers["X-Trace-Id"]
    assert its_own != command
    story = rows(cfg, trace=its_own, oldest_first=True)
    assert [(line_["level"], line_["event"]) for line_ in story] == [("error", None), ("error", "page.request")]
    assert "RuntimeError: boom" in story[0]["data"]["traceback"] and story[1]["data"]["status"] == 500


def test_requests_do_not_wait_in_a_row_for_each_others_journal_line(cfg, monkeypatch):
    monkeypatch.setattr(journal, "WRITE_TIMEOUT", 0.4)  # how long a line waits for a busy database
    app = create_app(cfg)

    async def three_at_once():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as page:
            began = time.monotonic()
            await asyncio.gather(*(page.get("/no-such-route") for _ in range(3)))
            return time.monotonic() - began

    writer = sqlite3.connect(cfg.db_path)
    writer.execute("BEGIN IMMEDIATE")  # something else is writing
    try:
        took = asyncio.run(three_at_once())
    finally:
        writer.rollback()
        writer.close()

    assert took < 0.9  # one wait, not three one after the other


def test_a_key_does_not_reach_the_journal_through_the_text_of_an_error(cfg, monkeypatch):
    # A key with a line break in it (from config.toml) is refused by the HTTP library, whose
    # message is the header itself.
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    monkeypatch.setattr(jev, "DECISIONS_URL", f"http://127.0.0.1:{listener.getsockname()[1]}/decisions")
    try:
        with httpx.Client(trust_env=False) as http:
            call = jev.ask(http, "sk-or-v1-first-half\nsecond-half", {"model": "x"})
    finally:
        listener.close()

    assert call.error and "first-half" not in call.error


def test_a_key_with_a_line_break_cannot_be_saved(cfg):
    api = TestClient(create_app(cfg))

    refused = api.put("/secrets/openrouter_api_key", headers=KEY, json={"value": "sk-or-v1-first\nsecond"})

    assert (refused.status_code, refused.json()["error"]["code"]) == (400, "invalid_input")
    assert "first" not in everything_written(cfg)


def test_housekeeping_is_an_operation_of_its_own(cfg):
    with journal.trace() as command:
        with journal.trace(fresh=True) as job:
            journal.record("backup", "backup.made", "Backup made.")
        journal.record("program", "program.stopped", "The program stopped.")

    assert job != command
    assert [line_["trace"] for line_ in rows(cfg, oldest_first=True)] == [job, command]


def test_the_saved_journal_is_whole_and_leaves_the_details_out_when_asked(cfg, monkeypatch):
    monkeypatch.setattr(journal, "MOST_AT_ONCE", 3)  # what the screen may read in one go
    for number in range(5):
        journal.record("rules", "rule.added", f"Rule {number} added.")
    journal.record("page", "page.request", "GET /clients answered 200.", level="detail")
    api = TestClient(create_app(cfg))

    everything = api.get("/events/export", headers=KEY).text
    as_on_screen = api.get("/events/export?details=false", headers=KEY).text

    assert everything.count("Rule ") == 5 and "GET /clients" in everything
    assert as_on_screen.count("Rule ") == 5 and "GET /clients" not in as_on_screen


def test_the_journal_is_read_and_saved_over_the_api(cfg):
    journal.record("rules", "rule.added", "Rule added.", name="ciment")
    api = TestClient(create_app(cfg))

    listed = api.get("/events?area=rules", headers=KEY).json()
    saved = api.get("/api/events/export", headers={"Sec-Fetch-Site": "same-origin", "Host": "127.0.0.1:8765"})

    assert (listed["ok"], [line_["event"] for line_ in listed["events"]], listed["has_more"]) == (True, ["rule.added"], False)
    assert saved.status_code == 200 and "Rule added.  name=ciment" in saved.text
    assert "attachment" in saved.headers["content-disposition"]
    assert api.get("/events").status_code == 401
