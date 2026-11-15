# Automatic Download and Client Switch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The program downloads invoices by itself on chosen days and times for every client that is switched on, and each client has an on/off switch that keeps it out of every download.

**Architecture:** A column on `clients` and two JSON rows in `settings` hold the state. A new module `schedule.py` holds the rules (when a run is due) and runs one through `Service.sync_all`, which loops over the existing `Service.sync`. A second background thread in the running program looks every 30 seconds. The page gets a switch on each client row and a new screen, "Descărcare automată".

**Tech Stack:** Python 3.11+, FastAPI, SQLite, pytest (`uv run pytest -q`). React 19, TypeScript, Tailwind 4, shadcn/ui on `radix-ui`, TanStack Query 5, vitest (`pnpm --dir frontend test`).

**Spec:** `docs/superpowers/specs/2026-11-15-automatic-download-design.md`. The screens: https://claude.ai/artifact/VSxb2ocdWVd9UtMUcuWukH (private; every sentence on screen is written out below, and this plan is the authority for them).

## Global Constraints

- Text on screen is Romanian, formal ("dumneavoastră"), with diacritics, exactly as written in this plan. Identifiers, comments, error messages and journal messages are English.
- A failure is `EfacturaError(code, message)`. A `Service` method returns `{"ok": True, ...}`. `api.py` and `cli.py` stay thin: they call `Service` and nothing else.
- The journal and the log never hold a key, a token, a login address or a request body.
- Everything that contacts ANAF or Jev goes through `Service`, so demo settings reach only the stand-ins.
- Every moment of the schedule is the PC's own clock, without a time zone, as `YYYY-MM-DDTHH:MM:SS`. Day 0 is Monday.
- No new dependency, Python or npm. The version stays 0.5.0.
- Tests first: write the test, watch it fail, then the code. Page tests cover plain functions only (there is no component test library).
- Before a task is called done: `uv run pytest -q`, `pnpm --dir frontend test`, `pnpm --dir frontend exec tsc -b --noEmit`, `pnpm --dir frontend lint` (exactly 3 known `only-export-components` warnings). Tasks that change the page also run `pnpm --dir frontend build` and commit `src/efactura/ui/`.
- Tests start no server, no PowerShell, and contact neither ANAF nor OpenRouter.
- Commit on the branch `automatic-download`; each message ends with `Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>`. Never push.

## Review Focus

Each line has its test in the task named.

1. The PC is shut down in the middle of a run (it happens daily): the record stays `running`. It must show as interrupted, be tried again, and stop being tried after 4 attempts. (Task 2: `test_a_run_that_was_cut_off_is_tried_again`; Task 4: `test_a_record_left_running_by_a_dead_program_shows_as_interrupted`.)
2. The schedule is switched on, or its time changed, after today's moment: nothing must start at once. (Task 2: `test_saving_never_starts_a_run_for_a_moment_already_past`.)
3. Someone is downloading by hand when the moment arrives: the run must wait for the lock, not fail every client. (Task 3: `test_a_run_waits_for_a_download_made_by_hand`.)
4. A client is switched off or removed while a run is in progress: it is skipped, and the run finishes. (Task 3: `test_a_client_switched_off_during_the_run_is_skipped`.)
5. A settings row that cannot be read (a backup restored from another version, an edit by hand): the schedule reads as off instead of failing every 30 seconds. (Task 2: `test_a_stored_schedule_that_cannot_be_read_is_off`.)

## File Structure

| File | Responsibility |
|---|---|
| `src/efactura/store.py` | the `enabled` column and three small client queries |
| `src/efactura/errors.py`, `api.py` | code `client_off` (409); three routes |
| `src/efactura/schedule.py` (new) | the schedule: validation, storage, when a run is due, running one, the status the page shows |
| `src/efactura/service.py` | `set_client_enabled`, the refusal in `sync`, `sync_all`, `schedule`, `set_schedule` |
| `src/efactura/cli.py` | the thread that looks every 30 seconds; command `sync-all` |
| `frontend/src/components/ui/switch.tsx` (new) | the switch |
| `frontend/src/clients/` | the switch on a row, the count line, the notice during a run |
| `frontend/src/schedule/` (new) | the screen, its form, its state card, its sentences, the shared query |

---

### Task 1: A client can be switched off (program)

**Files:**
- Modify: `src/efactura/store.py`, `src/efactura/errors.py`, `src/efactura/service.py`, `src/efactura/api.py`, `README.md`
- Test: `tests/test_store.py`, `tests/test_clients.py`, `tests/test_ui_api.py`

**Interfaces:**
- Produces:
  - `Store.clients()` rows gain `"enabled": bool`
  - `Store.set_client_enabled(cui: str, enabled: bool) -> None` (raises `not_found` for a CUI not in the list)
  - `Store.client_enabled(cui: str) -> bool | None` (`None`: not in the list)
  - `Store.clients_switched_on() -> list[dict]` (`{"cui", "name"}`, in the order of `clients()`; one cheap query, no join)
  - `Store.client_switch_counts() -> tuple[int, int]` (on, off)
  - `errors.CLIENT_OFF = "client_off"`, HTTP 409
  - `Service.set_client_enabled(cui: str, enabled: bool) -> dict` (what `Service.clients()` returns)
  - `PUT /clients/{cui}/enabled`, body `{"enabled": bool}`
  - journal: area `clients`, event `client.switched`, data `cui`, `client` (the name), `enabled`

- [ ] **Step 1: Write the failing tests**

`tests/test_store.py`:

```python
def test_a_database_from_before_the_switch_gets_every_client_switched_on(tmp_path):
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE clients (cui TEXT PRIMARY KEY, name TEXT NOT NULL, added_at TEXT NOT NULL)")
    old.execute("INSERT INTO clients VALUES ('12345674', 'Alfa', '2026-11-01T09:00:00')")
    old.commit()
    old.close()

    store = Store(path)

    assert [c["enabled"] for c in store.clients()] == [True]
    assert store.client_switch_counts() == (1, 0)
```

`tests/test_clients.py` (its `service`, `anaf`, `cfg` fixtures and `error_code`):

```python
def test_a_new_client_is_switched_on(service):
    service.save_client(VALID_CUI, "Alfa")

    assert service.clients()["clients"][0]["enabled"] is True


def test_a_client_can_be_switched_off_and_on_again(service):
    service.save_client(VALID_CUI, "Alfa")

    off = service.set_client_enabled(f"RO{VALID_CUI}", False)
    on = service.set_client_enabled(VALID_CUI, True)

    assert [c["enabled"] for c in off["clients"]] == [False]
    assert [c["enabled"] for c in on["clients"]] == [True]


def test_switching_a_client_that_is_not_in_the_list_is_not_found(service):
    assert error_code(lambda: service.set_client_enabled(VALID_CUI, False)) == "not_found"


def test_renaming_or_importing_a_client_leaves_its_switch_alone(service):
    service.save_client(VALID_CUI, "Alfa")
    service.set_client_enabled(VALID_CUI, False)

    service.save_client(VALID_CUI, "Alfa Nou")
    service.import_clients("clienti.csv", f"CUI,Denumire\n{VALID_CUI},Alfa Trei\n".encode())

    assert service.clients()["clients"][0]["enabled"] is False


def test_a_client_that_is_switched_off_is_not_downloaded(service, anaf, cfg):
    service.save_client(VALID_CUI, "Alfa")
    service.set_client_enabled(VALID_CUI, False)
    anaf.add("3001", xml=rich_invoice_xml(number="A1"))

    assert error_code(lambda: service.sync(VALID_CUI)) == "client_off"
    store = Store(cfg.db_path)
    assert store.runs() == []  # refused before anything was started
    store.close()


def test_a_cui_that_is_not_in_the_client_list_is_downloaded_as_before(service, anaf):
    anaf.add("3001", xml=rich_invoice_xml(number="A1"))

    assert service.sync(VALID_CUI)["new_count"] == 1


def test_the_clients_that_are_on_are_listed_by_name(service, cfg):
    service.save_client(OTHER_VALID_CUI, "Beta")
    service.save_client(VALID_CUI, "Alfa")
    service.set_client_enabled(OTHER_VALID_CUI, False)

    store = Store(cfg.db_path)
    assert store.clients_switched_on() == [{"cui": VALID_CUI, "name": "Alfa"}]
    assert store.client_switch_counts() == (1, 1)
    assert (store.client_enabled(VALID_CUI), store.client_enabled(OTHER_VALID_CUI), store.client_enabled("99")) == (True, False, None)
    store.close()
```

Also in `tests/test_clients.py`: `test_switching_a_client_is_written_in_the_journal` (after switching off, the journal has one `client.switched` line whose data is `{"cui": VALID_CUI, "client": "Alfa", "enabled": False}`; read the journal the way `tests/test_journal.py` does).

`tests/test_ui_api.py` (its client fixture and the style of its other tests): `test_a_client_is_switched_off_through_the_api` (`PUT /clients/{cui}/enabled` with `{"enabled": false}` answers 200 with the list, that client `enabled: false`), `test_downloading_a_client_that_is_off_answers_409` (`POST /sync` for it: 409, code `client_off`), `test_switching_an_unknown_client_answers_404`.

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_store.py tests/test_clients.py tests/test_ui_api.py -q`
Expected: the new tests fail (`KeyError: 'enabled'`, `AttributeError: set_client_enabled`, 404/405 for the route).

- [ ] **Step 3: Write the code**

- `store.py`: `enabled INTEGER NOT NULL DEFAULT 1` in the `clients` table of `SCHEMA`; in `_migrate`, add the column to a `clients` table that lacks it (same transaction, same pattern as the `messages` columns). `clients()` selects `c.enabled` and returns it as `bool`. `save_client` must keep leaving `enabled` out of its upsert. Add the four methods in Interfaces.
- `errors.py`: `CLIENT_OFF`. `api.py`: `CLIENT_OFF: 409` in `HTTP_STATUS`; the route, written like `DELETE /clients/{cui}`, with a `ClientSwitchRequest(BaseModel)` holding `enabled: bool`.
- `service.py`: `set_client_enabled` normalises the CUI, sets the flag, writes the journal line (`"Client {cui} switched on."` / `"… switched off."`) and returns `self.clients()`. In `sync`, straight after `normalize_cui` and before the lock: if `store.client_enabled(cui) is False`, raise `EfacturaError(CLIENT_OFF, "This client is switched off. Switch it on in the client list to download its invoices.")`.
- `README.md`: the route in the route list, `client_off` in the table of error codes, and one paragraph where clients are described: a client that is off keeps its invoices and is left out of every download until it is switched on; a CUI that is not in the list is not affected.

- [ ] **Step 4: Run everything**

Run: `uv run pytest -q`
Expected: all pass (921 before this task, plus the new ones).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "A client can be switched off: it keeps its invoices and is left out of every download"
```

---

### Task 2: The schedule's rules

**Files:**
- Create: `src/efactura/schedule.py`
- Test: `tests/test_schedule.py`

**Interfaces:**
- Consumes: `Store.get_setting`, `Store.set_setting`; `EfacturaError`, `INVALID_INPUT`.
- Produces (all in `efactura.schedule`):

```python
SETTING = "auto_sync"            # in the settings table: when to download by itself
LAST_RUN = "auto_sync_last_run"  # how the last automatic download went
RETRY_AFTER = timedelta(minutes=15)
MAX_ATTEMPTS = 4
MAX_TIMES = 4
CUT_OFF = ("running", "interrupted")  # a record whose run never wrote its end

@dataclass(frozen=True)
class Schedule:
    enabled: bool = False
    days: tuple[int, ...] = (0, 1, 2, 3, 4)   # 0 is Monday
    times: tuple[str, ...] = ("08:00",)
    saved_at: str | None = None               # the PC's clock, to the second

def checked(enabled, days, times) -> Schedule          # sorted, or invalid_input; saved_at None
def read(store: Store) -> Schedule                      # Schedule() when nothing readable is stored
def save(store: Store, schedule: Schedule, clock: datetime) -> Schedule   # stamps saved_at
def last_run(store: Store) -> dict | None               # None when nothing readable is stored
def record_run(store: Store, record: dict) -> None
def local_clock(now: datetime | None = None) -> datetime   # naive, the PC's zone, microsecond 0
def latest_slot(schedule: Schedule, clock: datetime) -> datetime | None
def next_slot(schedule: Schedule, clock: datetime) -> datetime | None
def retry_at(schedule: Schedule, last: dict | None, clock: datetime) -> datetime | None
def due(schedule: Schedule, last: dict | None, clock: datetime) -> tuple[datetime, int] | None
```

`latest_slot` and `next_slot` are calendar only: they ignore `enabled`. `local_clock(now)` converts an aware `now` to the PC's zone (`now.astimezone()`) before dropping the zone; with `None` it reads the clock.

- [ ] **Step 1: Write the failing tests** (`tests/test_schedule.py`)

```python
"""When the program downloads by itself: the rules, with a clock moved by hand."""

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from efactura import schedule
from efactura.errors import EfacturaError
from efactura.schedule import Schedule
from efactura.store import Store

MONDAY = datetime(2026, 11, 16)  # a Monday
# Monday to Friday at 08:00, saved the Friday before, in the evening.
WEEKDAYS_AT_8 = Schedule(True, (0, 1, 2, 3, 4), ("08:00",), "2026-11-13T17:00:00")
TWICE_A_DAY = replace(WEEKDAYS_AT_8, times=("08:00", "14:00"))


def at(day, hour, minute=0, second=0):
    """A moment counted from that Monday: at(1, 8) is Tuesday 08:00, at(-3, 8) the Friday before."""
    return MONDAY + timedelta(days=day, hours=hour, minutes=minute, seconds=second)


def ran(slot, status="ok", attempt=1, ended=None):
    cut_off = status == "running"
    return {
        "slot": slot.isoformat(), "attempt": attempt, "status": status,
        "started_at": slot.isoformat(), "finished_at": None if cut_off else (ended or slot).isoformat(),
    }


@pytest.fixture
def store(tmp_path):
    store = Store(tmp_path / "efactura.db")
    yield store
    store.close()


# --- what is stored --------------------------------------------------------------------------

def test_a_database_that_never_saved_a_schedule_has_it_off(store):
    assert schedule.read(store) == Schedule(False, (0, 1, 2, 3, 4), ("08:00",), None)


def test_a_saved_schedule_is_read_back_sorted_and_stamped(store):
    saved = schedule.save(store, schedule.checked(True, [4, 0], ["14:00", "08:00"]), at(0, 7))

    assert saved == Schedule(True, (0, 4), ("08:00", "14:00"), "2026-11-16T07:00:00")
    assert schedule.read(store) == saved


def test_a_stored_schedule_that_cannot_be_read_is_off(store):
    store.set_setting(schedule.SETTING, "{not json")
    assert schedule.read(store) == Schedule()
    store.set_setting(schedule.SETTING, '{"enabled": true, "days": "all", "times": 8}')
    assert schedule.read(store) == Schedule()


def test_a_stored_last_run_that_cannot_be_read_counts_as_none(store):
    store.set_setting(schedule.LAST_RUN, "[1, 2")
    assert schedule.last_run(store) is None


def test_the_last_run_is_read_back_as_recorded(store):
    schedule.record_run(store, ran(at(0, 8)))
    assert schedule.last_run(store) == ran(at(0, 8))


@pytest.mark.parametrize(
    "enabled, days, times",
    [
        (True, [], ["08:00"]),                                            # on, with no day
        (False, [7], ["08:00"]), (False, [-1], ["08:00"]),                 # not a day
        (False, [0, 0], ["08:00"]), (False, [True], ["08:00"]), (False, "0", ["08:00"]),
        (False, [0], []),                                                 # no time
        (False, [0], ["08:00", "09:00", "10:00", "11:00", "12:00"]),       # five times
        (False, [0], ["8:00"]), (False, [0], ["24:00"]), (False, [0], ["08:60"]),
        (False, [0], ["08:00:00"]), (False, [0], [800]), (False, [0], ["08:00", "08:00"]),
        ("yes", [0], ["08:00"]),
    ],
)
def test_a_schedule_that_makes_no_sense_is_refused(enabled, days, times):
    with pytest.raises(EfacturaError) as refused:
        schedule.checked(enabled, days, times)
    assert refused.value.code == "invalid_input"


def test_a_schedule_that_is_off_may_have_no_day():
    assert schedule.checked(False, [], ["08:00"]) == Schedule(False, (), ("08:00",), None)


# --- the calendar ----------------------------------------------------------------------------

def test_the_latest_moment_is_the_last_one_not_after_the_clock():
    assert schedule.latest_slot(WEEKDAYS_AT_8, at(0, 8)) == at(0, 8)          # on the dot
    assert schedule.latest_slot(WEEKDAYS_AT_8, at(0, 8, 0, 20)) == at(0, 8)
    assert schedule.latest_slot(WEEKDAYS_AT_8, at(0, 7, 59)) == at(-3, 8)     # the Friday before
    assert schedule.latest_slot(WEEKDAYS_AT_8, at(-1, 12)) == at(-3, 8)       # asked on Sunday
    assert schedule.latest_slot(TWICE_A_DAY, at(0, 15)) == at(0, 14)
    assert schedule.latest_slot(replace(WEEKDAYS_AT_8, days=()), at(0, 9)) is None


def test_the_next_moment_is_the_first_one_after_the_clock():
    assert schedule.next_slot(WEEKDAYS_AT_8, at(0, 7, 59)) == at(0, 8)
    assert schedule.next_slot(WEEKDAYS_AT_8, at(0, 8)) == at(1, 8)            # strictly after
    assert schedule.next_slot(WEEKDAYS_AT_8, at(4, 9)) == at(7, 8)            # Friday -> Monday
    assert schedule.next_slot(TWICE_A_DAY, at(0, 9)) == at(0, 14)
    assert schedule.next_slot(replace(WEEKDAYS_AT_8, days=(0,)), at(0, 8, 0, 1)) == at(7, 8)
    assert schedule.next_slot(replace(WEEKDAYS_AT_8, days=()), at(0, 9)) is None


def test_the_clock_is_the_pcs_own_without_a_zone_to_the_second():
    aware = datetime(2026, 11, 16, 8, 0, 20, 123456).astimezone()
    assert schedule.local_clock(aware) == datetime(2026, 11, 16, 8, 0, 20)
    assert schedule.local_clock().tzinfo is None


# --- when a run is due -----------------------------------------------------------------------

def test_a_moment_that_has_come_is_due_once():
    assert schedule.due(WEEKDAYS_AT_8, None, at(0, 8, 0, 20)) == (at(0, 8), 1)
    assert schedule.due(WEEKDAYS_AT_8, ran(at(0, 8)), at(0, 8, 1)) is None
    assert schedule.due(WEEKDAYS_AT_8, ran(at(0, 8)), at(1, 8, 0, 10)) == (at(1, 8), 1)


def test_nothing_is_due_while_the_schedule_is_off():
    assert schedule.due(replace(WEEKDAYS_AT_8, enabled=False), None, at(0, 9)) is None


def test_saving_never_starts_a_run_for_a_moment_already_past():
    assert schedule.due(WEEKDAYS_AT_8, None, at(0, 7, 59)) is None            # Friday's 08:00 was before the save
    just_saved = replace(WEEKDAYS_AT_8, saved_at="2026-11-16T08:05:00")
    assert schedule.due(just_saved, None, at(0, 9)) is None
    assert schedule.due(just_saved, None, at(1, 8)) == (at(1, 8), 1)


def test_moments_missed_while_the_pc_was_off_are_made_up_once():
    assert schedule.due(WEEKDAYS_AT_8, None, at(2, 10)) == (at(2, 8), 1)      # Wednesday: only the latest
    assert schedule.due(WEEKDAYS_AT_8, ran(at(2, 8)), at(2, 10, 1)) is None


def test_a_run_that_could_not_reach_anaf_is_tried_again_after_a_quarter_of_an_hour():
    unreachable = ran(at(0, 8), "unreachable", ended=at(0, 8, 0, 30))

    assert schedule.retry_at(WEEKDAYS_AT_8, unreachable, at(0, 8, 5)) == at(0, 8, 15, 30)
    assert schedule.due(WEEKDAYS_AT_8, unreachable, at(0, 8, 15)) is None
    assert schedule.due(WEEKDAYS_AT_8, unreachable, at(0, 8, 15, 30)) == (at(0, 8), 2)


def test_the_fourth_attempt_is_the_last():
    gave_up = ran(at(0, 8), "unreachable", attempt=4, ended=at(0, 8, 46))

    assert schedule.retry_at(WEEKDAYS_AT_8, gave_up, at(0, 9)) is None
    assert schedule.due(WEEKDAYS_AT_8, gave_up, at(0, 12)) is None


def test_a_run_that_was_cut_off_is_tried_again():
    for status in ("running", "interrupted"):
        cut_off = ran(at(0, 8), status) | {"finished_at": None}
        assert schedule.due(WEEKDAYS_AT_8, cut_off, at(0, 8, 14)) is None
        assert schedule.due(WEEKDAYS_AT_8, cut_off, at(0, 8, 15)) == (at(0, 8), 2)
    assert schedule.due(WEEKDAYS_AT_8, ran(at(0, 8), "running", attempt=4), at(0, 12)) is None


def test_a_run_that_failed_or_was_not_complete_is_not_tried_again():
    for status in ("failed", "partial"):
        assert schedule.retry_at(WEEKDAYS_AT_8, ran(at(0, 8), status), at(0, 9)) is None
        assert schedule.due(WEEKDAYS_AT_8, ran(at(0, 8), status), at(0, 9)) is None


def test_the_next_moment_drops_the_attempts_owed_to_the_one_before():
    unreachable = ran(at(0, 8), "unreachable", ended=at(0, 13, 55))

    assert schedule.retry_at(TWICE_A_DAY, unreachable, at(0, 14, 0, 5)) is None
    assert schedule.due(TWICE_A_DAY, unreachable, at(0, 14, 0, 5)) == (at(0, 14), 1)


def test_nothing_is_tried_again_once_the_schedule_is_off():
    unreachable = ran(at(0, 8), "unreachable", ended=at(0, 8, 0, 30))
    assert schedule.retry_at(replace(WEEKDAYS_AT_8, enabled=False), unreachable, at(0, 8, 5)) is None


def test_a_clock_moved_back_does_not_run_a_moment_again():
    assert schedule.due(WEEKDAYS_AT_8, ran(at(1, 8)), at(0, 9)) is None       # Tuesday's is recorded; it is Monday
```

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_schedule.py -q`
Expected: collection error, `No module named 'efactura.schedule'`.

- [ ] **Step 3: Write `src/efactura/schedule.py`**

The signatures and constants in Interfaces. What the tests do not decide by themselves:

- `checked`: `enabled` must be a `bool`; `days` a list or tuple of `int` that are not `bool`, each 0–6, no repeats; `times` a list or tuple of 1 to `MAX_TIMES` strings matching `HH:MM` with hour 00–23 and minute 00–59, no repeats; `enabled` needs at least one day. Each refusal is `EfacturaError(INVALID_INPUT, …)` saying which rule was broken.
- `read` returns `Schedule()` when the row is missing, is not JSON, or does not pass `checked`.
- `latest_slot` looks at the clock's day and the seven days before it; `next_slot` at the clock's day and the seven after.
- `retry_at(schedule, last, clock)`: `None` unless the schedule is on, `last["slot"]` is `latest_slot(schedule, clock)`, `last["status"]` is `"unreachable"` or in `CUT_OFF`, and `last["attempt"] < MAX_ATTEMPTS`; then `(finished_at or started_at) + RETRY_AFTER`.
- `due`: `None` when the schedule is off, has no latest slot, or that slot is not after `saved_at` (a schedule with `saved_at` `None` has no such bound). With no record, or a record for an earlier slot: `(slot, 1)`. With a record for a later slot: `None`. With a record for this slot: `(slot, attempt + 1)` when `retry_at` is not `None` and not after the clock, else `None`.

- [ ] **Step 4: Run everything**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "The schedule's rules: what is stored, the calendar, and when a run is due"
```

---

### Task 3: One run for every client that is on

**Files:**
- Modify: `src/efactura/service.py`, `src/efactura/cli.py`, `README.md`
- Test: `tests/test_sync_all.py` (new), `tests/test_cli.py`

**Interfaces:**
- Consumes: `Store.clients_switched_on()`, `Store.client_enabled(cui)`, `CLIENT_OFF` (Task 1); `Service.sync(cui)`.
- Produces:
  - `Service.sync_all(progress: Callable[[int, int], None] | None = None) -> dict`
  - in `service.py`: `BUSY_PAUSE = 5.0` (seconds), `BUSY_TRIES = 12`, `STOPS_THE_RUN = {LOGIN_NEEDED: "failed", ANAF_LIMIT_REACHED: "failed", CONFIG_ERROR: "failed", NETWORK_ERROR: "unreachable"}`
  - the answer: `{"ok": True, "status": "ok" | "partial" | "failed" | "unreachable", "clients": int, "failed_clients": int, "new": int, "review": int, "stopped_by": str | None, "results": [...]}`. `clients` is how many were on when the run began. Each result is `{"cui", "name", "ok": True, "new_count", "failed_count", "review"}` or `{"cui", "name", "ok": False, "error": {"code", "message"}}`.
  - command `efactura sync-all`

What `sync_all` does, for each client that is on, in order:
1. `progress(position, total)` if given (and `progress(total, total)` once after the last client, also when the run was stopped).
2. Skip it, with no result, unless `store.client_enabled(cui) is True` now (it was switched off or removed since the run began).
3. Call `self.sync(cui)`. On `busy`, call `_pause(BUSY_PAUSE)` and try again, at most `BUSY_TRIES` times in all; the last `busy` is that client's failure.
4. `client_off` from `sync`: skip, no result. An `EfacturaError` whose code is in `STOPS_THE_RUN`: note the failure, set `stopped_by`, stop. Any other `EfacturaError`: note the failure, go on. Any other exception: `log.exception`, note the failure as `internal_error` with `repr(exc)`, go on.

`status`: `STOPS_THE_RUN[stopped_by]` when stopped; else `"partial"` when a client failed or any result has `failed_count > 0`; else `"ok"`. `new` and `review` are the sums over the results that are `ok` (`review` from `result["classification"]`, 0 when that is `None`).

- [ ] **Step 1: Write the failing tests** (`tests/test_sync_all.py`)

Use the fixtures of `tests/test_clients.py` (a `cfg` with a saved login, `FakeAnaf`, `Service(cfg, http=anaf.client(), now=lambda: NOW)`). Read `tests/helpers.py` and `efactura/standins.py` for what `FakeAnaf` can do: how to give each CUI its own messages, how to make one CUI's list fail with an ANAF error, and how to make ANAF unreachable (the tests of `sync` in `tests/test_service.py` do each of these). Tests, by name, with what each asserts:

- `test_every_client_that_is_on_is_downloaded_in_the_order_of_the_list`: clients "Beta" (`OTHER_VALID_CUI`) and "Alfa" (`VALID_CUI`), one new invoice for each. `status == "ok"`, `clients == 2`, `failed_clients == 0`, `new == 2`, `stopped_by is None`, `[r["name"] for r in results] == ["Alfa", "Beta"]`, every result `ok`.
- `test_a_client_that_is_off_is_left_out`: "Beta" off. `clients == 1`, `[r["cui"] for r in results] == [VALID_CUI]`; Beta has no `sync_runs` row.
- `test_with_no_client_on_the_run_is_fine_and_empty`: `{"ok": True, "status": "ok", "clients": 0, "failed_clients": 0, "new": 0, "review": 0, "stopped_by": None, "results": []}`.
- `test_one_client_failing_does_not_stop_the_others`: ANAF answers an error for Alfa's list only. `status == "partial"`, `failed_clients == 1`, `results[0]["error"]["code"] == "anaf_error"`, Beta downloaded (`results[1]["ok"]`).
- `test_without_a_login_the_run_stops_at_the_first_client`: no saved login. `status == "failed"`, `stopped_by == "login_needed"`, `len(results) == 1`.
- `test_anafs_daily_limit_stops_the_run`: `monkeypatch` `Service.sync` to raise `EfacturaError(ANAF_LIMIT_REACHED, "x")`. `status == "failed"`, `stopped_by == "anaf_limit_reached"`, `len(results) == 1`.
- `test_anaf_out_of_reach_stops_the_run_as_unreachable`: `status == "unreachable"`, `stopped_by == "network_error"`, `len(results) == 1`.
- `test_a_bug_while_downloading_one_client_counts_as_its_failure`: `Service.sync` patched to raise `RuntimeError("boom")` for Alfa and to work for Beta. `results[0]["error"]["code"] == "internal_error"`, `results[1]["ok"]`, `status == "partial"`.
- `test_a_run_waits_for_a_download_made_by_hand`: take the program's lock (`service._lock()`), patch `efactura.service._pause` with a function that counts its calls and lets go of the lock on the third. The run then downloads the client: `status == "ok"`, pauses counted `== 3`, each called with `BUSY_PAUSE`.
- `test_a_client_whose_turn_never_comes_is_its_failure`: lock held throughout, `_pause` patched to count. That client's `error.code == "busy"`, pauses counted `== BUSY_TRIES - 1`, `status == "partial"`.
- `test_the_lock_is_free_between_two_clients`: in a patched `Service.sync` that calls the real one, take and let go of `service._lock()` before each call; it never raises.
- `test_a_client_switched_off_during_the_run_is_skipped`: a `progress` callback that switches Beta off when called with `(1, 2)`. `[r["cui"] for r in results] == [VALID_CUI]`, `clients == 2`, `status == "ok"`.
- `test_progress_is_told_before_each_client_and_at_the_end`: calls are `[(0, 2), (1, 2), (2, 2)]`; when stopped at the first client, `[(0, 2), (2, 2)]`.
- `test_messages_left_behind_make_the_run_partial`: one client whose download returns `failed_count == 1` (a message that cannot be downloaded): `status == "partial"`, `failed_clients == 0`.

`tests/test_cli.py`, in the style of its `sync` test: `test_sync_all_downloads_for_every_client_that_is_on` (the command prints the answer of `Service.sync_all` as JSON and exits 0).

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_sync_all.py tests/test_cli.py -q`
Expected: `AttributeError: 'Service' object has no attribute 'sync_all'`; the CLI test fails on an unknown command.

- [ ] **Step 3: Write the code**

`sync_all` beside `sync` in `service.py`, as described above; it takes no lock of its own (each `sync` takes it). `cli.py`: the `sync-all` parser (no arguments; help: `"fetch and save for every client that is switched on"`) and its `_dispatch` case. `README.md`: the command, with one sentence: it does once, now, what the schedule does, and leaves no record of an automatic run.

- [ ] **Step 4: Run everything**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "sync_all: one download for every client that is on, and the sync-all command"
```

---

### Task 4: The program runs the schedule

**Files:**
- Modify: `src/efactura/schedule.py`, `src/efactura/service.py`, `src/efactura/cli.py`, `src/efactura/api.py`, `README.md`
- Test: `tests/test_schedule_runs.py` (new), `tests/test_ui_api.py`, `tests/test_cli.py`, the test that covers `api._worth_a_line`

**Interfaces:**
- Consumes: everything Task 2 produces; `Service.sync_all(progress)` (Task 3); `Store.client_switch_counts()` (Task 1); `journal.trace(fresh=True)`, `journal.record`.
- Produces:
  - `schedule.run_if_due(cfg: Config, now: datetime | None = None, make_service: Callable[[Config], Service] | None = None) -> dict | None`: the record of the run it made, or `None`. Never raises.
  - `schedule.status(cfg: Config, now: datetime | None = None) -> dict`
  - `Service.schedule() -> dict` (is `schedule.status(self.cfg, self._now())`)
  - `Service.set_schedule(enabled, days, times) -> dict` (validates, saves, journals, returns the status)
  - `GET /sync/schedule`, `PUT /sync/schedule` with `{"enabled": bool, "days": [int], "times": [str]}`
  - in `cli.py`: `FIRST_SCHEDULE_LOOK = 30`, `SCHEDULE_LOOK_EVERY = 30`, `_download_on_schedule_until(cfg, stopped)`
  - journal: `schedule.saved` (area `settings`; data `enabled`, `days`, `times`), `sync.auto_started` (area `sync`; data `slot`, `attempt`), `sync.auto_finished` (area `sync`; data `slot`, `attempt`, `status`, `clients`, `failed_clients`, `new`, `review`, `error` (the code or `None`), `duration_ms`; level `info` for `ok`, `warning` for `partial`, `error` for `failed` and `unreachable`)

The status:

```python
{
    "ok": True, "enabled": bool, "days": [int], "times": [str],
    "next_at": str | None,       # next_slot, None while off
    "running": {"started_at": str, "done": int, "total": int} | None,
    "last_run": {...} | None,    # the record, plus "retry_at": str | None
    "clients_on": int, "clients_off": int,
}
```

The record of a run: `{"slot", "attempt", "started_at", "finished_at", "status", "clients", "failed_clients", "new", "review", "error", "trace"}`. It is written twice: when the run starts (`status: "running"`, `finished_at: None`, counts 0, `error: None`) and when it ends (`status` and the counts from `sync_all`; `error` is the `{"code", "message"}` of the failure that stopped the run, else `None`). In `status()`, a record that says `running` while no run is in progress in this process is shown as `"interrupted"`. `retry_at` is `schedule.retry_at(...)` as text, and `None` while a run is in progress.

The run in progress is kept in memory, in `schedule.py`, behind a `threading.Lock`: `{"started_at", "done", "total"}`, updated by the `progress` callback given to `sync_all`, cleared in a `finally`.

`run_if_due`: read the schedule and the last run, ask `due`, and when a run is due: one `journal.trace(fresh=True)`; write the starting record; journal `sync.auto_started`; `service = (make_service or Service)(cfg)`; `service.sync_all(progress=…)`; `service.close()`; write the final record; journal `sync.auto_finished`. An exception from `make_service` or `sync_all` ends the run as `failed` with `error` `{"code": "internal_error", "message": repr(exc)}`. Anything else that goes wrong is logged and answered with `None`.

- [ ] **Step 1: Write the failing tests**

`tests/test_schedule_runs.py`: fixtures as in `tests/test_clients.py`; a `now` that is aware and falls on Monday 2026-11-16 08:00:20 in the PC's zone (`datetime(2026, 11, 16, 8, 0, 20).astimezone()`); the schedule saved through `schedule.save(store, schedule.checked(True, [0, 1, 2, 3, 4], ["08:00"]), datetime(2026, 11, 13, 17))`; `make_service=lambda cfg: Service(cfg, http=anaf.client(), now=lambda: now)`. Tests:

- `test_nothing_runs_while_the_schedule_is_off`: `run_if_due` is `None`; `status()["last_run"] is None`.
- `test_a_moment_that_has_come_downloads_for_every_client_that_is_on`: two clients, one off, one new invoice. The record: `slot == "2026-11-16T08:00:00"`, `attempt == 1`, `status == "ok"`, `clients == 1`, `new == 1`, `error is None`, `started_at == finished_at == "2026-11-16T08:00:20"`. `status()`: `running is None`, `next_at == "2026-11-17T08:00:00"`, `last_run["status"] == "ok"`, `last_run["retry_at"] is None`, `(clients_on, clients_off) == (1, 1)`.
- `test_the_same_moment_is_not_run_twice`: the second `run_if_due` with the same `now` is `None`.
- `test_without_a_login_the_run_is_recorded_as_failed`: `status == "failed"`, `error["code"] == "login_needed"`, `retry_at is None`.
- `test_anaf_out_of_reach_is_tried_again_a_quarter_of_an_hour_later`: first run `unreachable`, `status()["last_run"]["retry_at"] == "2026-11-16T08:15:20"`; `run_if_due` at 08:10 is `None`; at 08:15:20 it runs with `attempt == 2`.
- `test_the_page_can_see_a_run_in_progress`: `make_service` returns an object whose `sync_all(progress)` calls `progress(1, 3)`, appends `schedule.status(cfg, now)["running"]` to a list and returns an empty ok answer, and whose `close()` does nothing. Seen: `{"started_at": "2026-11-16T08:00:20", "done": 1, "total": 3}`. After the run `status()["running"] is None`.
- `test_a_service_that_breaks_ends_the_run_as_failed`: `sync_all` raises `RuntimeError("boom")`. `run_if_due` does not raise; record `status == "failed"`, `error["code"] == "internal_error"`; `status()["running"] is None`.
- `test_a_record_left_running_by_a_dead_program_shows_as_interrupted`: write a `running` record for 08:00 by hand; `status(cfg, 08:05)`: `last_run["status"] == "interrupted"`, `retry_at == "2026-11-16T08:15:00"`; `run_if_due` at 08:15 runs `attempt == 2`.
- `test_run_if_due_never_raises`: `cfg` pointing at a database path that is a directory: `None`, no exception.
- `test_a_run_is_one_story_in_the_journal`: the lines `sync.auto_started`, the client's `sync.started` and `sync.finished`, and `sync.auto_finished` all carry the same trace, and it equals the record's `trace`; the `auto_finished` data has `status == "ok"`, `new == 1`.
- `test_a_run_leaves_no_token_in_the_journal`: after a run, no row of the `events` table contains the saved access token.
- `test_saving_the_schedule_is_written_in_the_journal`: `service.set_schedule(True, [0, 1], ["08:00"])` returns the status (`enabled`, `days == [0, 1]`, `next_at` set), journal `schedule.saved` with that data.
- `test_a_schedule_that_makes_no_sense_is_not_saved`: `set_schedule(True, [], ["08:00"])` is `invalid_input`; the stored schedule is unchanged.

`tests/test_ui_api.py`: `test_the_schedule_is_off_to_begin_with` (`GET /sync/schedule`: `enabled false`, `days [0,1,2,3,4]`, `times ["08:00"]`, `next_at null`, `running null`, `last_run null`), `test_the_schedule_is_saved_through_the_api` (`PUT`, then `GET` gives it back), `test_a_bad_schedule_answers_400` (`times: ["25:00"]`), `test_reading_the_schedule_is_not_written_in_the_journal` (after one `GET` and one `PUT`, the journal's `page.request` lines for `/sync/schedule` are the `PUT` only).

`tests/test_cli.py`, modelled on the test of `_keep_house_until`: `test_the_schedule_is_looked_at_until_the_program_stops` (with `schedule.run_if_due` patched to count and the two waits patched to 0.01 s, the thread calls it more than once and ends when `stopped` is set) and `test_one_bad_look_at_the_schedule_is_not_the_last` (the first call raises; a later call is still made). `run_server` starts both threads (assert it the way the existing test asserts the housekeeping thread, if it does).

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/test_schedule_runs.py tests/test_ui_api.py tests/test_cli.py -q`
Expected: `AttributeError: module 'efactura.schedule' has no attribute 'run_if_due'`, 404 for the routes.

- [ ] **Step 3: Write the code**

- `schedule.py`: `run_if_due`, `status`, the in-memory progress. Import `Service` inside the function (it imports this module's neighbours).
- `service.py`: `schedule()`, `set_schedule()` (journal message `"Automatic download switched on: days …, at …."` / `"Automatic download switched off."`).
- `cli.py`: `_download_on_schedule_until`, written like `_keep_house_until`, and started beside it in `run_server`.
- `api.py`: the two routes with a `ScheduleRequest(BaseModel)`; `_worth_a_line` learns the method and leaves out `GET` on `/sync/schedule` (the `PUT` is still written).
- `README.md`: a section "Automatic download" for a person (what it does; that the program must be running; a missed moment is made up once; what stops a run; the three more attempts; that it spends on Jev as a download by hand does); the two routes; the two settings rows; under "Not yet confirmed": on Windows, the thread under the window-less start and a run made up after sleep.

- [ ] **Step 4: Run everything**

Run: `uv run pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "The program downloads on the schedule: run_if_due, its status, the thread and the routes"
```

---

### Task 5: The page: a switch on each client

**Files:**
- Create: `frontend/src/components/ui/switch.tsx`, `frontend/src/clients/switchedOff.ts`, `frontend/src/clients/switchedOff.test.ts`
- Modify: `frontend/src/clients/ClientRow.tsx`, `ClientsPage.tsx`, `SyncDialog.tsx`, `frontend/src/api.ts`, `types.ts`, `errorMessages.ts`, `frontend/src/journal/eventTexts.ts`, `eventTexts.test.ts`, the built page in `src/efactura/ui/`

**Interfaces:**
- Consumes: `PUT /clients/{cui}/enabled`; `enabled` on each client; journal `client.switched`; code `client_off` (Task 1).
- Produces:
  - `Client.enabled: boolean` in `types.ts`; `api.setClientEnabled(cui: string, enabled: boolean)`
  - `switchedOn(clients: Client[]): Client[]`
  - `switchedOffLine(on: number, off: number): string | null` (Task 6 uses it too)
  - `<Switch>` in `components/ui/switch.tsx`
  - `ClientRow` takes a new prop `blocked: boolean` (Task 6 passes `true` during an automatic download; this task passes `false`)

- [ ] **Step 1: Write the failing tests**

`frontend/src/clients/switchedOff.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import type { Client } from '../types'
import { switchedOffLine, switchedOn } from './switchedOff'

const client = (name: string, enabled: boolean) => ({ name, enabled }) as Client

describe('switchedOn', () => {
  it('keeps the clients that are on, in their order', () => {
    const list = [client('Alfa', true), client('Beta', false), client('Gama', true)]
    expect(switchedOn(list).map((c) => c.name)).toEqual(['Alfa', 'Gama'])
  })
})

describe('switchedOffLine', () => {
  it('says nothing while every client is on', () => {
    expect(switchedOffLine(4, 0)).toBeNull()
    expect(switchedOffLine(0, 0)).toBeNull()
  })
  it('counts the clients that are downloaded and those that are off', () => {
    expect(switchedOffLine(3, 1)).toBe('Se descarcă 3 din cei 4 clienți. Un client este oprit.')
    expect(switchedOffLine(1, 2)).toBe('Se descarcă 1 din cei 3 clienți. 2 clienți sunt opriți.')
    expect(switchedOffLine(5, 20)).toBe('Se descarcă 5 din cei 25 de clienți. 20 de clienți sunt opriți.')
  })
  it('says so when every client is off', () => {
    expect(switchedOffLine(0, 2)).toBe('Toți clienții sunt opriți. Porniți cel puțin unul ca să descărcați facturi.')
  })
})
```

`eventTexts.test.ts`, in the style of its other cases: `client.switched` with `{ client: 'Alfa SRL', cui: '12345674', enabled: false }` reads `Clientul Alfa SRL a fost oprit: facturile lui nu se mai descarcă.`; with `enabled: true`: `Clientul Alfa SRL a fost pornit: facturile lui se descarcă din nou.`

- [ ] **Step 2: Run them and see them fail**

Run: `pnpm --dir frontend test`
Expected: the new file fails to import `./switchedOff`; the two journal cases fall back to the English line.

- [ ] **Step 3: Write the code**

- `switch.tsx`: shadcn's Switch written like `checkbox.tsx` in the same folder (`import { Switch as SwitchPrimitive } from "radix-ui"`, `cn`, `data-slot`). Track 52 × 30 px, fully rounded; thumb 24 px, white. On: the green of the page's "done" colour; off: a grey that is clearly not the green. Focus ring as on the checkbox.
- `ClientRow`: the switch is the first thing in the group on the right, with the visible word "Pornit" or "Oprit" beside it (fixed width, so the row does not jump). Its accessible name: `` `${client.name}: facturile se descarcă` `` when on, `` `${client.name}: facturile nu se descarcă` `` when off. Flipping it calls `api.setClientEnabled`, then refreshes the queries `['clients']` and `['schedule']`; a failure goes to `showError`; the switch cannot be flipped while its request is on the way. A client that is off: dashed border, muted background, name in the muted colour, the badges ("facturi noi", "de verificat", "Nimic nou") replaced by the line `Oprit: facturile lui nu se descarcă până îl porniți.` in semibold muted text, and "Descarcă facturile" disabled. "Vezi facturile" and the bin stay as they are. "Descarcă facturile" is also disabled while `blocked`.
- `ClientsPage`: the button for all downloads `switchedOn(clients)` and is disabled when that is empty. Under the row of buttons, when `switchedOffLine(on, off)` is not null, that line in muted text. Passes `blocked={false}` to each row.
- `SyncDialog`: new prop `someAreOff: boolean`. With more than one client and `someAreOff`, the line under the title is `` `Pentru cei ${countOf(clients.length, 'un client', 'clienți')} porniți` ``; otherwise as today.
- `errorMessages.ts`: `client_off: 'Clientul este oprit. Porniți-l din lista de clienți ca să îi descărcați facturile.'`
- `eventTexts.ts`: the `client.switched` sentence (`who(data)` gives the name).

- [ ] **Step 4: Run everything and build the page**

Run: `pnpm --dir frontend test && pnpm --dir frontend exec tsc -b --noEmit && pnpm --dir frontend lint && pnpm --dir frontend build && uv run pytest -q`
Expected: tests pass, no type error, 3 known lint warnings, the build writes `src/efactura/ui/`.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "The page: a switch on each client, and a client that is off is left out of the download for all"
```

---

### Task 6: The page: "Descărcare automată"

**Files:**
- Create: `frontend/src/schedule/SchedulePage.tsx`, `ScheduleForm.tsx`, `ScheduleStateCard.tsx`, `scheduleTexts.ts`, `scheduleTexts.test.ts`, `useSchedule.ts`
- Modify: `frontend/src/App.tsx`, `frontend/src/layout/AppShell.tsx`, `frontend/src/clients/ClientsPage.tsx`, `frontend/src/api.ts`, `types.ts`, `format.ts`, `format.test.ts`, `errorMessages.ts`, `frontend/src/journal/eventTexts.ts`, `eventTexts.test.ts`, the built page

**Interfaces:**
- Consumes: `GET`/`PUT /sync/schedule` and the status of Task 4; the journal events of Task 4; `switchedOffLine`, `ClientRow`'s `blocked` (Task 5).
- Produces, in `types.ts`:

```ts
export type ScheduleRun = {
  slot: string; attempt: number; started_at: string; finished_at: string | null
  status: 'ok' | 'partial' | 'failed' | 'unreachable' | 'interrupted' | 'running'
  clients: number; failed_clients: number; new: number; review: number
  error: { code: string; message: string } | null
  retry_at: string | null
}
export type ScheduleStatus = {
  enabled: boolean; days: number[]; times: string[]; next_at: string | null
  running: { started_at: string; done: number; total: number } | null
  last_run: ScheduleRun | null
  clients_on: number; clients_off: number
}
```

- `api.schedule(): Promise<ScheduleStatus>`, `api.saveSchedule(schedule: { enabled: boolean; days: number[]; times: string[] }): Promise<ScheduleStatus>`
- `format.ts`: `formatNext(iso: string, now = new Date()): string`
- `errorMessages.ts`: `messageForCode(code: string): string` (the sentence `errorMessage` gives for that code; the general sentence for an unknown one)
- `scheduleTexts.ts`:

```ts
export const DAY_NAMES = ['Luni', 'Marți', 'Miercuri', 'Joi', 'Vineri', 'Sâmbătă', 'Duminică']
export const MOST_TIMES = 4
export function describeWhen(days: number[], times: string[]): string
export function formProblem(enabled: boolean, days: number[], times: string[]): string | null
export type StateCard = { tone: 'done' | 'plain' | 'fresh' | 'attention'; title: string; text: string; journal: boolean; clients: boolean }
export function stateCard(status: ScheduleStatus, now?: Date): StateCard
export function menuNote(status: ScheduleStatus | undefined): { text: string; tone: 'fresh' | 'attention' } | null
export function pollEvery(status: ScheduleStatus | undefined): number | false
```

- [ ] **Step 1: Write the failing tests**

`format.test.ts` (in its style): with `now = new Date(2026, 10, 15, 9, 0)` (Sunday): `formatNext('2026-11-15T14:00:00', now)` is `azi, la 14:00`; `'2026-11-16T08:00:00'` is `mâine, la 08:00`; `'2026-11-18T08:00:00'` is `miercuri, 18.11.2026, la 08:00`.

`scheduleTexts.test.ts`, with `const NOW = new Date(2026, 10, 16, 9, 0)` (Monday) and a helper `status(over)` that spreads over `{ enabled: true, days: [0, 1, 2, 3, 4], times: ['08:00'], next_at: '2026-11-17T08:00:00', running: null, last_run: null, clients_on: 3, clients_off: 0 }`, and `run(over)` over `{ slot: '2026-11-16T08:00:00', attempt: 1, started_at: '2026-11-16T08:00:20', finished_at: '2026-11-16T08:01:05', status: 'ok', clients: 3, failed_clients: 0, new: 7, review: 2, error: null, retry_at: null }`:

| Case | Expected |
|---|---|
| `describeWhen([0,1,2,3,4], ['08:00'])` | `de luni până vineri, la 08:00` |
| `describeWhen([0,1,2,3,4,5,6], ['08:00', '14:00'])` | `în fiecare zi, la 08:00 și 14:00` |
| `describeWhen([0,2,4], ['08:00', '12:00', '16:00'])` | `luni, miercuri și vineri, la 08:00, 12:00 și 16:00` |
| `describeWhen([5], ['09:30'])` | `sâmbătă, la 09:30` |
| `formProblem(true, [], ['08:00'])` | `Alegeți cel puțin o zi.` |
| `formProblem(false, [], ['08:00'])` | `null` |
| `formProblem(true, [0], ['08:00', '08:00'])` | `Aceeași oră apare de două ori.` |
| `formProblem(true, [0], ['08:00', ''])` | `Completați ora.` |
| `formProblem(true, [0], ['08:00'])` | `null` |
| `stateCard(status({ last_run: run({}) }), NOW)` | tone `done`; title `Următoarea descărcare: mâine, la 08:00`; text `Ultima: azi, 08:00 · 3 clienți · 7 facturi noi · 2 de verificat.`; `journal: true`, `clients: false` |
| `stateCard(status({}), NOW)` | tone `done`; same title; text `Nu a fost făcută încă nicio descărcare automată.`; `journal: false` |
| last run with `new: 0, review: 0, clients: 1` | text `Ultima: azi, 08:00 · un client · nimic nou.` |
| `status({ enabled: false, next_at: null, last_run: run({ status: 'failed' }) })` | tone `plain`; title `Descărcarea automată este oprită`; text `Facturile se descarcă doar când apăsați dumneavoastră „Descarcă facturile”, pe pagina Clienți.` |
| `status({ running: { started_at: '2026-11-16T08:00:20', done: 2, total: 3 }, last_run: run({ status: 'running' }) })` | tone `fresh`; title `Se descarcă acum: 2 din 3 clienți`; text `A început azi, 08:00. Pagina se schimbă singură când se termină.` |
| running with `total: 0` | title `Se descarcă acum` |
| `status({ clients_on: 0, clients_off: 2 })` | tone `attention`; title `Niciun client nu este pornit`; text `Descărcarea automată nu are ce descărca. Porniți clienții din lista de clienți.`; `clients: true` |
| last run `{ status: 'failed', error: { code: 'login_needed', message: 'x' } }` | tone `attention`; title `Descărcarea de azi, 08:00 nu a reușit`; text is `messageForCode('login_needed')`, a space, then `Următoarea descărcare: mâine, la 08:00.` |
| last run `{ status: 'unreachable', retry_at: '2026-11-16T08:15:20' }` | tone `attention`; title `Descărcarea de azi, 08:00 nu a ajuns la ANAF`; text `Verificați conexiunea la internet. Programul mai încearcă azi, la 08:15 (încercarea 2 din 4).` |
| last run `{ status: 'unreachable', attempt: 4, retry_at: null }` | text `Verificați conexiunea la internet. Programul a încercat de 4 ori. Următoarea descărcare: mâine, la 08:00.` |
| last run `{ status: 'unreachable', attempt: 1, retry_at: null }` | text `Verificați conexiunea la internet. Programul a încercat o dată. Următoarea descărcare: mâine, la 08:00.` |
| last run `{ status: 'interrupted', retry_at: '2026-11-16T08:15:20' }` | title `Descărcarea de azi, 08:00 a fost întreruptă`; text `Programul sau calculatorul a fost oprit în timpul ei. Programul o reia azi, la 08:15.` |
| last run `{ status: 'interrupted', attempt: 4, retry_at: null }` | text `Programul sau calculatorul a fost oprit în timpul ei. Următoarea descărcare: mâine, la 08:00.` |
| last run `{ status: 'partial', failed_clients: 1 }` | tone `attention`; title `Ultima descărcare, azi, 08:00, nu a fost completă`; text `3 clienți · 7 facturi noi · 2 de verificat. Pentru un client descărcarea nu a reușit; se reia la următoarea descărcare.`; `journal: true` |
| last run `{ status: 'partial', failed_clients: 0 }` | text `3 clienți · 7 facturi noi · 2 de verificat. Unele facturi nu s-au putut descărca; se reiau la următoarea descărcare.` |
| `menuNote(undefined)`, `menuNote(status({ last_run: run({}) }))` | `null` |
| `menuNote` while running | `{ text: 'Se descarcă acum', tone: 'fresh' }` |
| `menuNote` with last run `failed`, `unreachable` or `interrupted` | `{ text: 'Ultima nu a reușit', tone: 'attention' }` |
| `menuNote(status({ enabled: false, last_run: run({ status: 'failed' }) }))` | `null` |
| `pollEvery(undefined)`, `pollEvery(status({ enabled: false }))` | `false` |
| `pollEvery(status({}))` | `30000` |
| `pollEvery` while running (also with the schedule off) | `3000` |

Which state wins, first match: running; off; no client on; then by the last run's status (`failed`, `unreachable`, `interrupted`, `partial`); otherwise fine.

`eventTexts.test.ts`:

| Event and data | Sentence |
|---|---|
| `schedule.saved`, `{ enabled: true, days: [0,1,2,3,4], times: ['08:00', '14:00'] }` | `Descărcarea automată a fost pornită: de luni până vineri, la 08:00 și 14:00.` |
| `schedule.saved`, `{ enabled: false, … }` | `Descărcarea automată a fost oprită.` |
| `sync.auto_started`, `{ attempt: 1 }` | `Descărcarea automată a început.` |
| `sync.auto_started`, `{ attempt: 2 }` | `Descărcarea automată a început. Este încercarea 2 din 4.` |
| `sync.auto_finished`, `{ status: 'ok', new: 7, review: 2 }` | `Descărcarea automată s-a terminat: 7 facturi noi, 2 de verificat.` |
| `sync.auto_finished`, `{ status: 'ok', new: 0, review: 0 }` | `Descărcarea automată s-a terminat: nimic nou.` |
| `sync.auto_finished`, `{ status: 'partial', new: 1, review: 0 }` | `Descărcarea automată s-a terminat: o factură nouă. Nu a fost completă; se reia la următoarea descărcare.` |
| `sync.auto_finished`, `{ status: 'failed', error: 'login_needed' }` | `Descărcarea automată nu a reușit: trebuie să vă conectați din nou la ANAF.` |
| `sync.auto_finished`, `{ status: 'failed', error: 'internal_error' }` | `Descărcarea automată nu a reușit.` |
| `sync.auto_finished`, `{ status: 'unreachable', attempt: 1 }` | `Descărcarea automată nu a ajuns la ANAF. Programul mai încearcă peste un sfert de oră.` |
| `sync.auto_finished`, `{ status: 'unreachable', attempt: 4 }` | `Descărcarea automată nu a ajuns la ANAF. A fost ultima încercare pentru această oră.` |

- [ ] **Step 2: Run them and see them fail**

Run: `pnpm --dir frontend test`
Expected: `scheduleTexts.test.ts` cannot import `./scheduleTexts`; `formatNext` is not exported; the journal cases fall back to English.

- [ ] **Step 3: Write the code**

- `useSchedule.ts`: `useSchedule()` is `useQuery({ queryKey: ['schedule'], queryFn: api.schedule, refetchOnWindowFocus: true, refetchInterval: (query) => pollEvery(query.state.data) })`. `useRefreshWhenAutomaticDownloadEnds()`: when `running` goes from set to null, invalidate `['clients']`, `['invoices']`, `['proposed-rules']`, `['auth']`.
- `AppShell.tsx`: the entry `{ to: '/descarcare-automata', label: 'Descărcare automată', icon: CalendarClock }` directly after "Clienți"; under its label the `menuNote` text, drawn like the "reguli propuse" note under "Reguli de clasificare" (`fresh`: the primary blue; `attention`: the attention foreground colour). Call `useRefreshWhenAutomaticDownloadEnds()` here, so it works on every screen.
- `App.tsx`: route `descarcare-automata`.
- `SchedulePage.tsx`: `PageTitle` "Descărcare automată" with the lead `Programul descarcă singur facturile de la ANAF, pentru toți clienții porniți, în zilele și la orele alese. Fiecare factură nouă își primește contul din reguli sau de la Jev, la fel ca atunci când descărcați dumneavoastră.` Then the state card, the form, and the card "Bine de știut" with four points:
  1. `Programul trebuie să fie pornit; el pornește singur odată cu Windows. Dacă la ora aleasă calculatorul era oprit, descărcarea se face imediat ce îl porniți.`
  2. `switchedOffLine(clients_on, clients_off)`, or `Se descarcă toți clienții din listă.` when it is null; then the link `Vezi clienții` to `/`.
  3. `Dacă ANAF nu poate fi contactat, de exemplu fără internet, programul mai încearcă de trei ori, din sfert în sfert de oră.`
  4. `Jev costă la fel ca la descărcarea făcută de dumneavoastră. Costurile sunt pe pagina „Costuri Jev”.`
  While the status loads: `Se încarcă…` as on the other screens; a failure to load: the `Notice` with `errorMessage`.
- `ScheduleStateCard.tsx`: draws `stateCard(status)`: the title in bold 19 px, the text under it, then the link `Vezi în jurnal` (to `/jurnal`) when `journal`, and `Vezi clienții` (to `/`) when `clients`. Tones: `done`, `fresh` and `attention` as the `Notice` colours; `plain` is a white card with a border. `role="status"`.
- `ScheduleForm.tsx`: a card headed `Când să descarce`. `PillTabs` labelled `Descărcare automată` with `Oprită` and `Pornită`. Heading `În ce zile?`: seven toggle buttons from `DAY_NAMES` in a group labelled `Zilele`, `aria-pressed`, a chosen day drawn in the "fresh" colours with a check mark before its name. Heading `La ce oră?`: one `<Input type="time">` per time (accessible name `` `Ora ${n}` ``); when there is more than one, each has a button with the accessible name `` `Scoate ora ${time}` ``; while there are fewer than `MOST_TIMES`, the link-button `Adaugă încă o oră` adds the first of `12:00`, `16:00`, `10:00`, `18:00` not already there; under them `Cel mult patru ore pe zi.` Then the button `Salvează` (large) and beside it `Ce schimbați aici se aplică după ce apăsați „Salvează”.`, or `formProblem(...)` in the attention colour when there is one. `Salvează` is disabled while there is a problem, while nothing differs from what is saved, and while saving. The form starts from the saved schedule and changes nothing until saved. Saving: `api.saveSchedule` with the days and times sorted; on success put the answer in the `['schedule']` query and toast `Descărcarea automată a fost salvată.`; a failure goes to `showError`.
- `ClientsPage.tsx`: reads `useSchedule()`. While `running` is set: under the buttons a `Notice` in the `fresh` tone with `` `Programul descarcă acum facturile, singur: ${done} din ${countOf(total, 'un client', 'clienți')}.` `` in semibold and under it `Butoanele de descărcare revin când se termină. Lista se actualizează singură.`; the button for all is disabled and every row gets `blocked`.
- `format.ts`: `formatNext`. `errorMessages.ts`: `messageForCode`. `eventTexts.ts`: the sentences in the table.

- [ ] **Step 4: Run everything and build the page**

Run: `pnpm --dir frontend test && pnpm --dir frontend exec tsc -b --noEmit && pnpm --dir frontend lint && pnpm --dir frontend build && uv run pytest -q`
Expected: tests pass, no type error, 3 known lint warnings, the build writes `src/efactura/ui/`.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "The page: Descărcare automată, with its state, its form and the notice on the client list"
```

---

## After the reviews (2026-11-15)

Built as planned, in the order 1, 2, 3, 5, 4, 6, each task reviewed on its own, then the whole branch. What ended differently from the text above:

- **A run in which no client succeeded is `failed`**, with the first client's error, and is not retried before the next moment (Task 3 said `partial`). ANAF answering 5xx to every client was otherwise shown as "not complete" and nobody was told.
- **`retry_at` has the same bound on `saved_at` as `due`**: saving the schedule again drops the attempts still owed to a moment before the save.
- **The page shows when a run was made** (`started_at`), not the moment it was scheduled for; titles use `formatFromWhen` ("de azi, 08:40", "din 13.11.2026, 08:00").
- **The schedule form is never remounted.** It keeps a draft and the saved schedule it follows; three plain functions decide what it does when the saved schedule changes (`sameSchedule`, `onSavedChange`, `ownSaveArrival`). With unsaved edits it keeps them and says "Descărcarea automată a fost schimbată din altă parte cât timp lucrați aici." with "Arată ce este salvat".
- **`formProblem` checks the times whatever the switch says** (only "Alegeți cel puțin o zi." depends on it), since the program refuses an empty or repeated time for a schedule that is off too.
- **The lists refresh after any run that ended**, not only one the page watched (`runEnded`).
- **With one client** the running card and the notice drop the count (`runningLine`): no "0 din un client".
- **A client's own invoices page** disables "Descarcă facturile" for a client that is off and during an automatic download, each with its sentence.
- **The switch** is not disabled while its request is on the way (it kept losing keyboard focus); a second flip is ignored meanwhile.
- **Hardening of the runner**: a final record that cannot be saved is journalled as `sync.record_unsaved` and the run's real outcome is still journalled; `status` reads the record a second time before calling a run interrupted; a stored record or `saved_at` that carries a time zone counts as unreadable.
- **Two more journal sentences**: a run stopped by ANAF's daily limit, and one refused by ANAF for every client.

Tests at the end: `uv run pytest -q` 1016 passed; `pnpm --dir frontend test` 133 passed. Checked in a browser against made-up data: the switch (mouse and keyboard), a schedule saved from the page running by itself at its minute, the running state on the client list and in the menu, a run failing for lack of a login and one refused by ANAF, the form's notice, the invoices page of a client that is off. Not checked: anything on Windows.

## After the owner's follow-up (2026-11-15)

The owner asked for the small things that had been left, and for the author line to move from the foot of the menu to a footer of the whole page. Built in one round, reviewed, and looked at in a browser.

- **The author line is a footer of every screen** (`frontend/src/layout/PageFooter.tsx`, on the canvas as "Subsolul paginii"): one muted line, "© 2026 … · e-mail", at the bottom of the window on a short screen and after the content on a long one. The foot of the menu ends with the version and "Caută o versiune nouă".
- **A run whose record could not be saved** is shown as it ended and is not made again: the record is kept in memory and saved at the next look (`schedule.py`).
- **"Vezi în jurnal" opens that run's own lines**: the journal screen reads the operation it shows from the address (`#/jurnal?operatiune=…`), so the browser's Back button works there too.
- **"azi" and "mâine" follow the clock** on the schedule card (`useNow`).
- **Keyboard**: "Salvează" keeps the focus after a save (it is marked unavailable instead of disabled); after a time is removed the focus goes to "Adaugă încă o oră"; the remove button of an empty time is named by its position.
- **Small**: the running state's icon turns; the switch's off colour is a design token; a code named like an inherited property is not taken for a known error code.

Tests at the end: `uv run pytest -q` 1019 passed; `pnpm --dir frontend test` 137 passed.
