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


def test_a_stored_saved_at_that_carries_a_zone_counts_as_unreadable(store):
    store.set_setting(
        schedule.SETTING,
        '{"enabled": true, "days": [0], "times": ["08:00"], "saved_at": "2026-11-13T17:00:00+02:00"}',
    )
    assert schedule.read(store) == Schedule()
