"""When the program downloads by itself: the rules, with a clock moved by hand."""

from dataclasses import replace
from datetime import date, datetime, timedelta

import pytest

from efactura import schedule
from efactura.errors import EfacturaError
from efactura.schedule import Period, Schedule
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


def test_no_retry_is_promised_after_the_schedule_is_saved_again():
    saved_again = replace(WEEKDAYS_AT_8, saved_at="2026-11-16T08:05:00")
    for last in (ran(at(0, 8), "unreachable", ended=at(0, 8, 0, 30)), ran(at(0, 8), "running")):
        assert schedule.retry_at(saved_again, last, at(0, 8, 6)) is None
        assert schedule.due(saved_again, last, at(0, 8, 16)) is None


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


def test_a_stored_run_record_with_a_zoned_moment_counts_as_unreadable(store):
    for field in ("slot", "started_at", "finished_at"):
        record = ran(at(0, 8))
        record[field] = "2026-11-16T08:00:00+02:00"
        schedule.record_run(store, record)

        assert schedule.last_run(store) is None

    assert schedule.due(WEEKDAYS_AT_8, schedule.last_run(store), at(0, 8, 20)) == (at(0, 8), 1)


# --- the period: which invoices each run asks for ---------------------------------------------

TODAY = date(2026, 11, 16)
NOVEMBER = {"start": "2026-11-01", "end": "2026-11-30"}


def test_a_schedule_that_never_chose_a_period_asks_for_the_last_seven_days(store):
    assert Schedule().period == Period(days=7)
    # A schedule saved before the period existed.
    store.set_setting(schedule.SETTING, '{"enabled": true, "days": [0], "times": ["08:00"], "saved_at": null}')
    assert schedule.read(store) == Schedule(True, (0,), ("08:00",), None, Period(days=7))


@pytest.mark.parametrize(
    "asked, kept",
    [
        ({"days": 3}, Period(days=3)),
        ({"days": 60}, Period(days=60)),
        (NOVEMBER, Period(days=None, start="2026-11-01", end="2026-11-30")),
        ({"start": "2026-11-16", "end": "2026-11-16"}, Period(days=None, start="2026-11-16", end="2026-11-16")),
    ],
)
def test_a_saved_period_is_read_back(store, asked, kept):
    saved = schedule.save(store, schedule.checked(True, [0], ["08:00"], asked, TODAY), at(0, 7))

    assert saved.period == kept
    assert schedule.read(store).period == kept
    assert kept.as_dict() == asked


@pytest.mark.parametrize(
    "period",
    [
        {}, "7", [7], 7,                                                    # neither days nor two dates
        {"days": 0}, {"days": 61}, {"days": True}, {"days": "7"}, {"days": 7.0},
        {"days": 7, "start": "2026-11-01"}, {"days": 7, **NOVEMBER},       # both ways at once
        {"start": "2026-11-01"}, {"end": "2026-11-30"},                     # one date only
        {"start": "2026-11-10", "end": "2026-11-01"},                      # the first day after the last
        {"start": "01.11.2026", "end": "2026-11-30"}, {"start": "2026-11-01", "end": "2026-11-31"},
        {"start": 20261101, "end": "2026-11-30"}, {"start": None, "end": "2026-11-30"},
        {"start": "20261101", "end": "2026-11-30"},                        # only YYYY-MM-DD is a date here
    ],
)
def test_a_period_that_makes_no_sense_is_refused(period):
    with pytest.raises(EfacturaError) as refused:
        schedule.checked(False, [0], ["08:00"], period)
    assert refused.value.code == "invalid_input"


@pytest.mark.parametrize(
    "period",
    [
        {"start": "2026-11-17", "end": "2026-11-30"},  # begins tomorrow
        {"start": "2026-08-01", "end": "2026-09-16"},  # ended 61 days ago: ANAF has nothing left of it
    ],
)
def test_a_period_anaf_cannot_be_asked_for_is_refused_only_while_the_schedule_is_on(period):
    with pytest.raises(EfacturaError) as refused:
        schedule.checked(True, [0], ["08:00"], period, TODAY)
    assert refused.value.code == "invalid_input"

    assert schedule.checked(False, [0], ["08:00"], period, TODAY).period.as_dict() == period


@pytest.mark.parametrize(
    "period",
    [
        {"start": "2026-08-01", "end": "2026-09-17"},  # its last day is the sixtieth back
        {"start": "2026-08-01", "end": "2027-01-31"},  # began long ago, still running
        {"start": "2026-11-16", "end": "2026-12-31"},  # begins today
    ],
)
def test_a_period_with_a_day_anaf_still_has_is_accepted(period):
    assert schedule.checked(True, [0], ["08:00"], period, TODAY).period.as_dict() == period


def test_a_stored_period_that_went_stale_is_still_read(store):
    stale = {"start": "2026-01-01", "end": "2026-01-31"}
    schedule.save(store, schedule.checked(False, [0], ["08:00"], stale), at(0, 7))
    store.set_setting(schedule.SETTING, store.get_setting(schedule.SETTING).replace("false", "true"))

    read = schedule.read(store)

    assert read.enabled is True
    assert read.period.as_dict() == stale


def test_a_run_asks_for_the_last_days_as_a_minimum_that_reaches_back_to_the_last_complete_run():
    assert schedule.asked_for(Period(days=3), TODAY) == {"days": 3, "cover_gap": True}


@pytest.mark.parametrize(
    "period, asked",
    [
        (NOVEMBER, {"start": "2026-11-01", "end": "2026-11-16"}),                       # up to today, not beyond
        ({"start": "2026-11-01", "end": "2026-11-10"}, {"start": "2026-11-01", "end": "2026-11-10"}),
        ({"start": "2026-08-01", "end": "2026-12-31"}, {"start": "2026-09-17", "end": "2026-11-16"}),  # 60 days back
        ({"start": "2026-08-01", "end": "2026-09-17"}, {"start": "2026-09-17", "end": "2026-09-17"}),
    ],
)
def test_a_run_asks_for_the_chosen_days_that_have_come_and_that_anaf_still_keeps(period, asked):
    assert schedule.asked_for(schedule.checked(False, [0], ["08:00"], period).period, TODAY) == asked


@pytest.mark.parametrize(
    "period",
    [
        {"start": "2026-08-01", "end": "2026-09-16"},  # ended more than 60 days ago
        {"start": "2026-11-17", "end": "2026-11-30"},  # not begun (the clock was moved back)
    ],
)
def test_a_period_with_no_day_left_to_ask_for_is_refused_at_the_run(period):
    with pytest.raises(EfacturaError) as refused:
        schedule.asked_for(schedule.checked(False, [0], ["08:00"], period).period, TODAY)
    assert refused.value.code == "invalid_input"
