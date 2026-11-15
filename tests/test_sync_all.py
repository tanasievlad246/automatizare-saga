"""sync_all: one download for every client that is switched on."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from efactura import auth
from efactura.auth import Tokens
from efactura.config import load_config
from efactura.errors import ANAF_ERROR, ANAF_LIMIT_REACHED, EfacturaError
from efactura.service import BUSY_PAUSE, BUSY_TRIES, Service
from efactura.store import Store

from helpers import OTHER_VALID_CUI, VALID_CUI, FakeAnaf

NOW = datetime(2026, 11, 11, 9, 30, tzinfo=timezone(timedelta(hours=2)))


def make_cfg(tmp_path, logged_in):
    path = tmp_path / "config.toml"
    path.write_text(
        '[anaf]\nclient_id = "c"\nclient_secret = "s"\n'
        f"token_file = '{tmp_path / 'private' / 'tokens.json'}'\n", encoding="utf-8",
    )
    cfg = load_config(path)
    if logged_in:
        auth.save_tokens(
            cfg.token_file,
            Tokens("access-1", "refresh-1", NOW + timedelta(days=30), NOW + timedelta(days=300), NOW),
        )
    return cfg


@pytest.fixture
def cfg(tmp_path):
    return make_cfg(tmp_path, True)


@pytest.fixture
def anaf():
    return FakeAnaf()


@pytest.fixture
def service(cfg, anaf):
    service = Service(cfg, http=anaf.client(), now=lambda: NOW)
    service.save_client(OTHER_VALID_CUI, "Beta")
    service.save_client(VALID_CUI, "Alfa")
    return service


def sync_with(monkeypatch, behaviour):
    """Replace Service.sync: behaviour(real, self, cui) answers or raises."""
    real = Service.sync
    monkeypatch.setattr(Service, "sync", lambda self, cui, *a, **k: behaviour(real, self, cui))


def switch_off(service, cui):
    service.set_client_enabled(cui, False)


def test_every_client_that_is_on_is_downloaded_in_the_order_of_the_list(service, anaf):
    anaf.add("3001", cui=VALID_CUI)
    anaf.add("3002", cui=OTHER_VALID_CUI)

    answer = service.sync_all()

    assert answer["status"] == "ok"
    assert answer["clients"] == 2
    assert answer["failed_clients"] == 0
    assert answer["new"] == 2
    assert answer["stopped_by"] is None
    assert [r["name"] for r in answer["results"]] == ["Alfa", "Beta"]
    assert all(r["ok"] for r in answer["results"])


def test_a_client_that_is_off_is_left_out(service, cfg, anaf):
    anaf.add("3001", cui=VALID_CUI)
    switch_off(service, OTHER_VALID_CUI)

    answer = service.sync_all()

    assert answer["clients"] == 1
    assert [r["cui"] for r in answer["results"]] == [VALID_CUI]
    store = Store(cfg.db_path)
    assert [r for r in store.runs() if r["cui"] == OTHER_VALID_CUI] == []
    store.close()


def test_with_no_client_on_the_run_is_fine_and_empty(cfg, anaf):
    service = Service(cfg, http=anaf.client(), now=lambda: NOW)

    assert service.sync_all() == {
        "ok": True, "status": "ok", "clients": 0, "failed_clients": 0,
        "new": 0, "review": 0, "stopped_by": None, "results": [],
    }


def test_one_client_failing_does_not_stop_the_others(service, anaf, monkeypatch):
    anaf.add("3001", cui=OTHER_VALID_CUI)

    def behaviour(real, self, cui):
        if cui == VALID_CUI:
            raise EfacturaError("anaf_error", "ANAF said no")
        return real(self, cui)

    sync_with(monkeypatch, behaviour)

    answer = service.sync_all()

    assert answer["status"] == "partial"
    assert answer["failed_clients"] == 1
    assert answer["results"][0]["error"]["code"] == "anaf_error"
    assert answer["results"][1]["ok"]


def test_without_a_login_the_run_stops_at_the_first_client(tmp_path, anaf):
    service = Service(make_cfg(tmp_path, False), http=anaf.client(), now=lambda: NOW)
    service.save_client(OTHER_VALID_CUI, "Beta")
    service.save_client(VALID_CUI, "Alfa")

    answer = service.sync_all()

    assert answer["status"] == "failed"
    assert answer["stopped_by"] == "login_needed"
    assert len(answer["results"]) == 1


def test_anafs_daily_limit_stops_the_run(service, monkeypatch):
    def limit(real, self, cui):
        raise EfacturaError(ANAF_LIMIT_REACHED, "x")

    sync_with(monkeypatch, limit)

    answer = service.sync_all()

    assert answer["status"] == "failed"
    assert answer["stopped_by"] == "anaf_limit_reached"
    assert len(answer["results"]) == 1


def test_anaf_out_of_reach_stops_the_run_as_unreachable(cfg, monkeypatch):
    def refuse(request):
        raise httpx.ConnectError("connection reset", request=request)

    service = Service(cfg, http=httpx.Client(transport=httpx.MockTransport(refuse)), now=lambda: NOW)
    service.save_client(OTHER_VALID_CUI, "Beta")
    service.save_client(VALID_CUI, "Alfa")

    answer = service.sync_all()

    assert answer["status"] == "unreachable"
    assert answer["stopped_by"] == "network_error"
    assert len(answer["results"]) == 1


def test_a_bug_while_downloading_one_client_counts_as_its_failure(service, anaf, monkeypatch):
    anaf.add("3001", cui=OTHER_VALID_CUI)

    def behaviour(real, self, cui):
        if cui == VALID_CUI:
            raise RuntimeError("boom")
        return real(self, cui)

    sync_with(monkeypatch, behaviour)

    answer = service.sync_all()

    assert answer["results"][0]["error"]["code"] == "internal_error"
    assert answer["results"][1]["ok"]
    assert answer["status"] == "partial"


def test_a_run_waits_for_a_download_made_by_hand(service, anaf, monkeypatch):
    anaf.add("3001", cui=VALID_CUI)
    switch_off(service, OTHER_VALID_CUI)
    held = service._lock()
    held.__enter__()
    pauses = []

    def pause(seconds):
        pauses.append(seconds)
        if len(pauses) == 3:
            held.__exit__(None, None, None)

    monkeypatch.setattr("efactura.service._pause", pause)

    answer = service.sync_all()

    assert answer["status"] == "ok"
    assert answer["new"] == 1
    assert pauses == [BUSY_PAUSE] * 3


def test_a_client_whose_turn_never_comes_is_its_failure(service, monkeypatch):
    switch_off(service, OTHER_VALID_CUI)
    pauses = []
    monkeypatch.setattr("efactura.service._pause", pauses.append)

    with service._lock():
        answer = service.sync_all()

    assert answer["results"][0]["error"]["code"] == "busy"
    assert len(pauses) == BUSY_TRIES - 1
    assert answer["status"] == "failed"  # its only client failed


def test_the_lock_is_free_between_two_clients(service, anaf, monkeypatch):
    anaf.add("3001", cui=VALID_CUI)
    anaf.add("3002", cui=OTHER_VALID_CUI)

    def behaviour(real, self, cui):
        with self._lock():  # raises busy when sync_all still held it
            pass
        return real(self, cui)

    sync_with(monkeypatch, behaviour)

    assert service.sync_all()["status"] == "ok"


def test_a_client_switched_off_during_the_run_is_skipped(service, anaf):
    anaf.add("3001", cui=VALID_CUI)
    anaf.add("3002", cui=OTHER_VALID_CUI)

    def progress(position, total):
        if (position, total) == (1, 2):
            switch_off(service, OTHER_VALID_CUI)

    answer = service.sync_all(progress)

    assert [r["cui"] for r in answer["results"]] == [VALID_CUI]
    assert answer["clients"] == 2
    assert answer["status"] == "ok"


def test_progress_is_told_before_each_client_and_at_the_end(service, anaf, monkeypatch):
    calls = []
    service.sync_all(lambda position, total: calls.append((position, total)))
    assert calls == [(0, 2), (1, 2), (2, 2)]

    def limit(real, self, cui):
        raise EfacturaError(ANAF_LIMIT_REACHED, "x")

    sync_with(monkeypatch, limit)
    calls.clear()
    service.sync_all(lambda position, total: calls.append((position, total)))
    assert calls == [(0, 2), (2, 2)]


def test_messages_left_behind_make_the_run_partial(service, anaf):
    anaf.add("3001", cui=VALID_CUI)
    anaf.download_errors["3001"] = "Nu se poate descarca"
    switch_off(service, OTHER_VALID_CUI)

    answer = service.sync_all()

    assert answer["results"][0]["failed_count"] == 1
    assert answer["status"] == "partial"
    assert answer["failed_clients"] == 0


def test_a_run_in_which_no_client_succeeded_is_failed(service, cfg, monkeypatch):
    service.save_client("10000008", "Gama")

    def refuse(real, self, cui):
        raise EfacturaError(ANAF_ERROR, "x")

    sync_with(monkeypatch, refuse)

    answer = service.sync_all()

    assert answer["status"] == "failed"
    assert answer["failed_clients"] == 3
    assert answer["stopped_by"] is None
    assert len(answer["results"]) == 3


def test_a_client_removed_during_the_run_is_skipped(service, cfg, anaf):
    anaf.add("3001", cui=VALID_CUI)
    anaf.add("3002", cui=OTHER_VALID_CUI)

    def progress(position, total):
        if (position, total) == (1, 2):
            service.remove_client(OTHER_VALID_CUI)

    answer = service.sync_all(progress)

    assert [r["cui"] for r in answer["results"]] == [VALID_CUI]
    assert answer["status"] == "ok"
    store = Store(cfg.db_path)
    try:
        assert {row["cui"] for row in store.runs()} == {VALID_CUI}
    finally:
        store.close()


# --- the period ------------------------------------------------------------------------------

def _asked_of_anaf(anaf):
    """For each list request: the client, and the first and last moment asked for, on NOW's clock."""
    moment = lambda millis: datetime.fromtimestamp(int(millis) / 1000, tz=NOW.tzinfo)  # noqa: E731
    return [(str(r["cif"]), moment(r["startTime"]), moment(r["endTime"])) for r in anaf.list_requests]


def test_chosen_dates_are_asked_of_anaf_for_every_client(service, anaf):
    answer = service.sync_all(start="2026-11-03", end="2026-11-05")

    first = datetime(2026, 11, 3, tzinfo=NOW.tzinfo)
    after_last = datetime(2026, 11, 6, tzinfo=NOW.tzinfo)
    assert answer["status"] == "ok"
    assert _asked_of_anaf(anaf) == [(VALID_CUI, first, after_last), (OTHER_VALID_CUI, first, after_last)]


def test_a_number_of_days_is_asked_of_anaf_for_every_client(service, anaf):
    service.sync_all(days=2)

    asked = _asked_of_anaf(anaf)
    assert [cui for cui, _, _ in asked] == [VALID_CUI, OTHER_VALID_CUI]
    assert all(last - first == timedelta(days=2) for _, first, last in asked)


def test_dates_that_make_no_sense_end_the_run_as_failed(service):
    answer = service.sync_all(start="2026-11-09", end="2026-11-03")

    assert answer["status"] == "failed"
    assert {r["error"]["code"] for r in answer["results"]} == {"invalid_input"}


def test_a_minimum_of_days_reaches_back_to_the_last_complete_run(cfg, anaf):
    ten_days_ago = Service(cfg, http=anaf.client(), now=lambda: NOW - timedelta(days=10))
    ten_days_ago.save_client(VALID_CUI, "Alfa")
    assert ten_days_ago.sync_all()["status"] == "ok"
    service = Service(cfg, http=anaf.client(), now=lambda: NOW)

    anaf.list_requests.clear()
    service.sync_all(days=3, cover_gap=True)
    (_, first, last), = _asked_of_anaf(anaf)
    assert last - first >= timedelta(days=10)

    anaf.list_requests.clear()
    service.sync_all(days=3)
    (_, first, last), = _asked_of_anaf(anaf)
    assert last - first == timedelta(days=3)


def test_a_run_that_passes_midnight_keeps_its_first_day_within_what_anaf_keeps(cfg, anaf):
    before, after = (datetime(2026, 11, day, *time, tzinfo=NOW.tzinfo) for day, time in ((11, (23, 59, 30)), (12, (0, 0, 30))))
    clock = {"now": before}
    service = Service(cfg, http=anaf.client(), now=lambda: clock["now"])
    service.save_client(OTHER_VALID_CUI, "Beta")
    service.save_client(VALID_CUI, "Alfa")

    def midnight_passes_before_the_second_client(position, total):
        if position == 1:
            clock["now"] = after

    # 12 September is the sixtieth day back on the 11th, and one day too old on the 12th.
    answer = service.sync_all(midnight_passes_before_the_second_client, start="2026-09-12", end="2026-11-11")

    assert [(r["name"], r["ok"]) for r in answer["results"]] == [("Alfa", True), ("Beta", True)]
    # Each was asked from as far back as ANAF reaches at its own moment.
    as_far_back = timedelta(days=60) - timedelta(minutes=5)
    assert [first for _, first, _ in _asked_of_anaf(anaf)] == [before - as_far_back, after - as_far_back]
