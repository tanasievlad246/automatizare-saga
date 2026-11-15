"""The program runs the schedule: run_if_due, the status the page reads, and the journal."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from efactura import auth, journal, schedule
from efactura.auth import Tokens
from efactura.config import load_config
from efactura.errors import INVALID_INPUT, EfacturaError
from efactura.service import Service
from efactura.store import Store

from helpers import OTHER_VALID_CUI, VALID_CUI, FakeAnaf

TOKENS_CLOCK = datetime(2026, 11, 11, 9, 30, tzinfo=timezone(timedelta(hours=2)))
THIRD_CUI = "10000008"
MONDAY_8 = datetime(2026, 11, 16, 8, 0, 20).astimezone()


def at(hour, minute, second=0):
    return datetime(2026, 11, 16, hour, minute, second).astimezone()


def make_cfg(tmp_path, logged_in=True):
    path = tmp_path / "config.toml"
    path.write_text(
        '[anaf]\nclient_id = "c"\nclient_secret = "s"\n'
        f"token_file = '{tmp_path / 'private' / 'tokens.json'}'\n", encoding="utf-8",
    )
    cfg = load_config(path)
    if logged_in:
        auth.save_tokens(
            cfg.token_file,
            Tokens(
                "access-secret-1", "refresh-1", MONDAY_8 + timedelta(days=30),
                MONDAY_8 + timedelta(days=300), TOKENS_CLOCK,
            ),
        )
    return cfg


@pytest.fixture
def cfg(tmp_path):
    return make_cfg(tmp_path)


@pytest.fixture(autouse=True)
def nothing_held():
    schedule._held = None
    yield
    schedule._held = None


@pytest.fixture
def anaf():
    return FakeAnaf()


@pytest.fixture
def make_service(anaf):
    return lambda cfg: Service(cfg, http=anaf.client(), now=lambda: MONDAY_8)


def switch_on(cfg, days=(0, 1, 2, 3, 4), times=("08:00",)):
    store = Store(cfg.db_path)
    try:
        schedule.save(store, schedule.checked(True, list(days), list(times)), datetime(2026, 11, 13, 17))
    finally:
        store.close()


def stored_last_run(cfg):
    store = Store(cfg.db_path)
    try:
        return schedule.last_run(store)
    finally:
        store.close()


def with_clients(cfg, make_service, *clients):
    service = make_service(cfg)
    for cui, name in clients:
        service.save_client(cui, name)
    return service


def test_nothing_runs_while_the_schedule_is_off(cfg, make_service):
    with_clients(cfg, make_service, (VALID_CUI, "Alfa"))

    assert schedule.run_if_due(cfg, MONDAY_8, make_service) is None
    assert schedule.status(cfg, MONDAY_8)["last_run"] is None


def test_a_moment_that_has_come_downloads_for_every_client_that_is_on(cfg, anaf, make_service):
    service = with_clients(cfg, make_service, (VALID_CUI, "Alfa"), (OTHER_VALID_CUI, "Beta"), (THIRD_CUI, "Gama"))
    service.set_client_enabled(THIRD_CUI, False)
    anaf.add("3001", cui=VALID_CUI)
    anaf.add("3002", cui=OTHER_VALID_CUI)
    switch_on(cfg)

    record = schedule.run_if_due(cfg, MONDAY_8, make_service)

    assert record["slot"] == "2026-11-16T08:00:00"
    assert record["attempt"] == 1
    assert record["status"] == "ok"
    assert record["clients"] == 2
    assert record["new"] == 2
    assert record["error"] is None
    assert record["started_at"] == record["finished_at"] == "2026-11-16T08:00:20"
    shown = schedule.status(cfg, MONDAY_8)
    assert shown["running"] is None
    assert shown["next_at"] == "2026-11-17T08:00:00"
    assert shown["last_run"]["status"] == "ok"
    assert shown["last_run"]["retry_at"] is None
    assert (shown["clients_on"], shown["clients_off"]) == (2, 1)


def test_the_same_moment_is_not_run_twice(cfg, make_service):
    with_clients(cfg, make_service, (VALID_CUI, "Alfa"))
    switch_on(cfg)

    first = schedule.run_if_due(cfg, MONDAY_8, make_service)
    second = schedule.run_if_due(cfg, MONDAY_8, make_service)

    assert first is not None
    assert second is None


def test_without_a_login_the_run_is_recorded_as_failed(tmp_path):
    cfg = make_cfg(tmp_path, logged_in=False)
    make_service = lambda cfg: Service(cfg, http=FakeAnaf().client(), now=lambda: MONDAY_8)
    with_clients(cfg, make_service, (VALID_CUI, "Alfa"))
    switch_on(cfg)

    record = schedule.run_if_due(cfg, MONDAY_8, make_service)

    assert record["status"] == "failed"
    assert record["error"]["code"] == "login_needed"
    assert schedule.status(cfg, MONDAY_8)["last_run"]["retry_at"] is None


def test_anaf_out_of_reach_is_tried_again_a_quarter_of_an_hour_later(cfg):
    def refuse(request):
        raise httpx.ConnectError("connection reset", request=request)

    make_service = lambda cfg: Service(cfg, http=httpx.Client(transport=httpx.MockTransport(refuse)), now=lambda: MONDAY_8)
    with_clients(cfg, make_service, (VALID_CUI, "Alfa"))
    switch_on(cfg)

    first = schedule.run_if_due(cfg, MONDAY_8, make_service)

    assert first["status"] == "unreachable"
    assert schedule.status(cfg, MONDAY_8)["last_run"]["retry_at"] == "2026-11-16T08:15:20"
    assert schedule.run_if_due(cfg, at(8, 10), make_service) is None
    assert schedule.run_if_due(cfg, at(8, 15, 20), make_service)["attempt"] == 2


def test_a_run_in_which_anaf_refused_every_client_is_recorded_as_failed(cfg, anaf, make_service, monkeypatch):
    with_clients(cfg, make_service, (VALID_CUI, "Alfa"), (OTHER_VALID_CUI, "Beta"), (THIRD_CUI, "Gama"))
    switch_on(cfg)

    def refuse(self, cui, *a, **k):
        raise EfacturaError("anaf_error", "ANAF said no")

    monkeypatch.setattr(Service, "sync", refuse)

    record = schedule.run_if_due(cfg, MONDAY_8, make_service)

    assert record["status"] == "failed"
    assert record["error"]["code"] == "anaf_error"
    assert schedule.status(cfg, MONDAY_8)["last_run"]["retry_at"] is None
    last = journal.events(cfg.db_path, trace=record["trace"])["events"][0]
    assert (last["event"], last["level"]) == ("sync.auto_finished", "error")
    assert last["data"]["error"] == "anaf_error"


def test_the_page_can_see_a_run_in_progress(cfg):
    seen = []

    class Slow:
        def sync_all(self, progress=None):
            progress(1, 3)
            seen.append(schedule.status(cfg, MONDAY_8)["running"])
            return {"ok": True, "status": "ok", "clients": 3, "failed_clients": 0, "new": 0,
                    "review": 0, "stopped_by": None, "results": []}

        def close(self):
            pass

    switch_on(cfg)

    schedule.run_if_due(cfg, MONDAY_8, lambda cfg: Slow())

    assert seen == [{"started_at": "2026-11-16T08:00:20", "done": 1, "total": 3}]
    assert schedule.status(cfg, MONDAY_8)["running"] is None


def test_a_service_that_breaks_ends_the_run_as_failed(cfg):
    closed = []

    class Broken:
        def sync_all(self, progress=None):
            progress(0, 2)
            raise RuntimeError("boom")

        def close(self):
            closed.append(True)

    switch_on(cfg)

    record = schedule.run_if_due(cfg, MONDAY_8, lambda cfg: Broken())

    assert record["status"] == "failed"
    assert record["error"]["code"] == "internal_error"
    assert "boom" in record["error"]["message"]
    assert closed == [True]
    assert schedule.status(cfg, MONDAY_8)["running"] is None
    assert stored_last_run(cfg)["status"] == "failed"


def test_a_service_that_cannot_be_made_ends_the_run_as_failed(cfg):
    def refuse(cfg):
        raise RuntimeError("no service")

    switch_on(cfg)

    record = schedule.run_if_due(cfg, MONDAY_8, refuse)

    assert (record["status"], record["error"]["code"]) == ("failed", "internal_error")
    assert schedule.status(cfg, MONDAY_8)["running"] is None


def test_a_record_left_running_by_a_dead_program_shows_as_interrupted(cfg, make_service):
    with_clients(cfg, make_service, (VALID_CUI, "Alfa"))
    switch_on(cfg)
    store = Store(cfg.db_path)
    schedule.record_run(store, {
        "slot": "2026-11-16T08:00:00", "attempt": 1, "started_at": "2026-11-16T08:00:00",
        "finished_at": None, "status": "running", "clients": 0, "failed_clients": 0,
        "new": 0, "review": 0, "error": None, "trace": "abc",
    })
    store.close()

    shown = schedule.status(cfg, at(8, 5))["last_run"]

    assert shown["status"] == "interrupted"
    assert shown["retry_at"] == "2026-11-16T08:15:00"
    assert schedule.run_if_due(cfg, at(8, 15), make_service)["attempt"] == 2


def test_saving_the_schedule_again_cancels_the_retry_the_status_promised(cfg):
    def refuse(request):
        raise httpx.ConnectError("connection reset", request=request)

    make_service = lambda cfg: Service(cfg, http=httpx.Client(transport=httpx.MockTransport(refuse)), now=lambda: MONDAY_8)
    service = with_clients(cfg, make_service, (VALID_CUI, "Alfa"))
    switch_on(cfg)
    assert schedule.run_if_due(cfg, MONDAY_8, make_service)["status"] == "unreachable"

    later = Service(cfg, now=lambda: at(8, 5))
    later.set_schedule(True, [0, 1, 2, 3, 4], ["08:00"])

    assert schedule.status(cfg, at(8, 6))["last_run"]["retry_at"] is None


def test_saving_the_schedule_stamps_the_services_clock(cfg):
    service = Service(cfg, now=lambda: at(8, 5))

    service.set_schedule(True, [0], ["08:00"])

    store = Store(cfg.db_path)
    try:
        assert schedule.read(store).saved_at == "2026-11-16T08:05:00"
    finally:
        store.close()
    assert schedule.run_if_due(cfg, at(8, 6), lambda cfg: Service(cfg, now=lambda: at(8, 6))) is None


def test_run_if_due_never_raises(tmp_path):
    cfg = make_cfg(tmp_path)
    cfg.db_path.mkdir(parents=True)

    assert schedule.run_if_due(cfg, MONDAY_8) is None


def test_a_run_is_one_story_in_the_journal(cfg, anaf, make_service):
    with_clients(cfg, make_service, (VALID_CUI, "Alfa"))
    anaf.add("3001", cui=VALID_CUI)
    switch_on(cfg)

    record = schedule.run_if_due(cfg, MONDAY_8, make_service)

    story = journal.events(cfg.db_path, trace=record["trace"], oldest_first=True)["events"]
    names = [line["event"] for line in story]
    for wanted in ("sync.auto_started", "sync.started", "sync.finished", "sync.auto_finished"):
        assert wanted in names
    assert names[0] == "sync.auto_started" and names[-1] == "sync.auto_finished"
    finished = story[-1]
    assert finished["data"]["status"] == "ok"
    assert finished["data"]["new"] == 1
    assert finished["level"] == "info"
    assert finished["data"].get("error") is None  # the journal leaves out empty values
    assert finished["data"]["slot"] == "2026-11-16T08:00:00"


def test_a_run_that_fails_is_written_as_an_error(cfg):
    class Broken:
        def sync_all(self, progress=None):
            raise RuntimeError("boom")

        def close(self):
            pass

    switch_on(cfg)

    record = schedule.run_if_due(cfg, MONDAY_8, lambda cfg: Broken())

    last = journal.events(cfg.db_path, trace=record["trace"])["events"][0]
    assert (last["event"], last["level"]) == ("sync.auto_finished", "error")
    assert last["data"]["error"] == "internal_error"


def test_a_run_leaves_no_token_in_the_journal(cfg, anaf, make_service):
    with_clients(cfg, make_service, (VALID_CUI, "Alfa"))
    anaf.add("3001", cui=VALID_CUI)
    switch_on(cfg)

    schedule.run_if_due(cfg, MONDAY_8, make_service)

    with sqlite3.connect(cfg.db_path) as database:
        text = " ".join(" ".join(str(value) for value in row) for row in database.execute("SELECT * FROM events"))
    assert "sync.auto_finished" in text
    assert "access-secret-1" not in text


def test_saving_the_schedule_is_written_in_the_journal(cfg, make_service):
    service = make_service(cfg)

    shown = service.set_schedule(True, [1, 0], ["08:00"])

    assert shown["enabled"] is True
    assert shown["days"] == [0, 1]
    assert shown["next_at"] is not None
    saved = [line for line in journal.events(cfg.db_path, area="settings")["events"] if line["event"] == "schedule.saved"]
    assert saved[0]["data"] == {"enabled": True, "days": [0, 1], "times": ["08:00"]}
    assert service.schedule() == shown


def test_a_schedule_that_makes_no_sense_is_not_saved(cfg, make_service):
    service = make_service(cfg)
    service.set_schedule(True, [2], ["09:30"])

    with pytest.raises(EfacturaError) as raised:
        service.set_schedule(True, [], ["08:00"])

    assert raised.value.code == INVALID_INPUT
    shown = service.schedule()
    assert (shown["enabled"], shown["days"], shown["times"]) == (True, [2], ["09:30"])


class _Empty:
    def sync_all(self, progress=None):
        return {"ok": True, "status": "ok", "clients": 0, "failed_clients": 0, "new": 0,
                "review": 0, "stopped_by": None, "results": []}

    def close(self):
        pass


def test_a_failed_write_of_the_final_record_does_not_hide_the_run(cfg, monkeypatch):
    real, calls = schedule.record_run, []

    def second_fails(store, record):
        calls.append(record["status"])
        if len(calls) == 2:
            raise sqlite3.OperationalError("database is locked")
        real(store, record)

    monkeypatch.setattr(schedule, "record_run", second_fails)
    switch_on(cfg)

    record = schedule.run_if_due(cfg, MONDAY_8, lambda cfg: _Empty())

    assert record["status"] == "ok"
    story = journal.events(cfg.db_path, trace=record["trace"])["events"]
    finished = [line for line in story if line["event"] == "sync.auto_finished"]
    assert finished and finished[0]["data"]["status"] == "ok"
    assert any("could not be saved" in line["message"] for line in story)
    assert schedule.status(cfg, MONDAY_8)["running"] is None


def fail_the_final_write(monkeypatch):
    real, calls = schedule.record_run, []

    def second_fails(store, record):
        calls.append(record["status"])
        if len(calls) == 2:
            raise sqlite3.OperationalError("database is locked")
        real(store, record)

    monkeypatch.setattr(schedule, "record_run", second_fails)
    return real


def test_a_run_whose_record_could_not_be_saved_is_shown_as_it_ended(cfg, monkeypatch):
    fail_the_final_write(monkeypatch)
    switch_on(cfg)
    schedule.run_if_due(cfg, MONDAY_8, lambda cfg: _Empty())

    last = schedule.status(cfg, MONDAY_8)["last_run"]

    assert last["status"] == "ok"
    assert last["finished_at"] is not None
    assert last["retry_at"] is None


def test_a_run_whose_record_could_not_be_saved_is_not_made_again(cfg, monkeypatch):
    real = fail_the_final_write(monkeypatch)
    switch_on(cfg)
    schedule.run_if_due(cfg, MONDAY_8, lambda cfg: _Empty())
    monkeypatch.setattr(schedule, "record_run", real)

    again = schedule.run_if_due(cfg, MONDAY_8 + timedelta(minutes=16), lambda cfg: _Empty())

    assert again is None
    store = Store(cfg.db_path)
    try:
        assert schedule.last_run(store)["status"] == "ok"
    finally:
        store.close()


def test_a_held_record_gives_way_to_a_later_stored_one(cfg, monkeypatch):
    fail_the_final_write(monkeypatch)
    switch_on(cfg)
    schedule.run_if_due(cfg, MONDAY_8, lambda cfg: _Empty())
    later = {"slot": "2026-11-17T08:00:00", "attempt": 1, "started_at": "2026-11-17T08:00:20",
             "finished_at": "2026-11-17T08:01:00", "status": "ok", "clients": 0, "failed_clients": 0,
             "new": 0, "review": 0, "error": None, "trace": None}
    store = Store(cfg.db_path)
    try:
        store.set_setting(schedule.LAST_RUN, json.dumps(later))
    finally:
        store.close()

    assert schedule.status(cfg, at(9, 0))["last_run"]["slot"] == "2026-11-17T08:00:00"


def test_a_run_that_ends_between_the_two_reads_is_not_shown_as_interrupted(cfg, monkeypatch):
    running = {"slot": "2026-11-16T08:00:00", "attempt": 1, "started_at": "2026-11-16T08:00:20",
               "finished_at": None, "status": "running"}
    answers = [running, {**running, "status": "ok", "finished_at": "2026-11-16T08:01:00"}]
    monkeypatch.setattr(schedule, "last_run", lambda store: answers.pop(0) if len(answers) > 1 else answers[0])
    switch_on(cfg)

    assert schedule.status(cfg, MONDAY_8)["last_run"]["status"] == "ok"


def test_the_end_of_a_run_reads_the_clock_again(cfg, monkeypatch):
    first, later = datetime(2026, 11, 16, 8, 0, 20), datetime(2026, 11, 16, 8, 3, 0)
    seen = []

    def clock(now=None):
        seen.append(now)
        return first if len(seen) == 1 else later

    monkeypatch.setattr(schedule, "local_clock", clock)
    switch_on(cfg)

    record = schedule.run_if_due(cfg, None, lambda cfg: _Empty())

    assert (record["started_at"], record["finished_at"]) == ("2026-11-16T08:00:20", "2026-11-16T08:03:00")
