"""Copies of the database in a folder the person chose, and putting one back."""

import json
import os
import sqlite3
import zipfile
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from efactura import backup, background, cli, journal
from efactura.api import create_app
from efactura.config import load_config
from efactura.errors import EfacturaError
from efactura.store import Store

NOW = datetime(2026, 11, 14, 9, 0, tzinfo=timezone(timedelta(hours=2)))
HEALTHY = {"ok": True, "service": "efactura", "version": "0.3.0"}
KEY = {"X-API-Key": "local-key"}


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "program" / "config.toml"
    path.parent.mkdir()
    path.write_text('[api]\nkey = "local-key"\nport = 9001\n', encoding="utf-8")
    cfg = load_config(path)
    add_client(cfg, "12345674", "Alfa Construct SRL")
    journal.configure(cfg.db_path)
    return cfg


@pytest.fixture
def folder(tmp_path, cfg):
    """A backup folder that has been chosen."""
    chosen = tmp_path / "stick" / "Copii AutoSaga"
    backup.set_folder(cfg, str(chosen))
    return chosen


@pytest.fixture
def computer(monkeypatch):
    state = SimpleNamespace(answer=None, asked_to_stop=[], spawned=[])

    def spawn_command(config_path, output, *command):
        state.spawned.append((command, output))
        if command == ("serve",):
            state.answer = HEALTHY

    def ask_to_stop(port, key):
        state.asked_to_stop.append(port)
        state.answer = None

    monkeypatch.setattr(background, "probe", lambda port: state.answer)
    monkeypatch.setattr(background, "spawn_command", spawn_command)
    monkeypatch.setattr(background, "ask_to_stop", ask_to_stop)
    monkeypatch.setattr(background, "pause", lambda seconds: None)
    return state


def add_client(cfg, cui, name):
    store = Store(cfg.db_path)
    store.save_client(cui, name, NOW.isoformat())
    store.close()


def clients_in(db_path):
    with sqlite3.connect(db_path) as database:
        return sorted(row[0] for row in database.execute("SELECT name FROM clients"))


def clients_in_snapshot(path, tmp_path):
    with zipfile.ZipFile(path) as archive:
        archive.extract("efactura.db", tmp_path / "opened")
    return clients_in(tmp_path / "opened" / "efactura.db")


def names(folder):
    return sorted(path.name for path in folder.iterdir())


def journal_events(cfg):
    return [line["event"] for line in journal.events(cfg.db_path, oldest_first=True)["events"]]


# --- the folder ----------------------------------------------------------------------------------


def test_nothing_is_backed_up_until_a_folder_is_chosen(cfg):
    state = backup.status(cfg, NOW)
    with pytest.raises(EfacturaError) as refused:
        backup.snapshot(cfg, now=NOW)

    assert (state["folder"], state["snapshots"], state["next_due_at"]) == (None, [], None)
    assert refused.value.code == "backup_error"
    assert backup.run_if_due(cfg, NOW) is None


def test_the_chosen_folder_is_made_and_remembered(tmp_path, cfg):
    chosen = tmp_path / "stick" / "Copii AutoSaga"

    saved = backup.set_folder(cfg, f"  {chosen}  ")

    assert chosen.is_dir()
    assert (saved["folder"], saved["folder_found"], backup.status(cfg, NOW)["folder"]) == (str(chosen), True, str(chosen))
    assert "backup.folder_set" in journal_events(cfg)


def test_a_folder_that_cannot_be_used_is_refused(tmp_path, cfg):
    (tmp_path / "a-file").write_text("not a folder")

    for bad in ("", "   ", str(tmp_path / "a-file"), "relative/folder"):
        with pytest.raises(EfacturaError) as refused:
            backup.set_folder(cfg, bad)
        assert refused.value.code == "invalid_input"

    assert backup.status(cfg, NOW)["folder"] is None


# --- one snapshot --------------------------------------------------------------------------------


def test_a_snapshot_is_a_zip_holding_the_whole_database(folder, cfg, tmp_path):
    made = backup.snapshot(cfg, now=NOW)

    assert names(folder) == ["autosaga-20261114-090000-manual.zip"]  # and nothing half-written beside it
    assert (made["ok"], made["name"], made["kind"], made["removed"]) == (True, "autosaga-20261114-090000-manual.zip", "manual", [])
    assert clients_in_snapshot(folder / made["name"], tmp_path) == ["Alfa Construct SRL"]
    (listed,) = backup.status(cfg, NOW)["snapshots"]
    assert (listed["name"], listed["kind"], listed["at"]) == (made["name"], "manual", "2026-11-14T09:00:00")
    assert listed["size"] == (folder / made["name"]).stat().st_size > 0
    assert journal_events(cfg)[-1] == "backup.made"


def test_a_copy_that_does_not_check_out_is_never_kept(folder, cfg, monkeypatch):
    monkeypatch.setattr(backup, "_is_sound", lambda database: False)

    with pytest.raises(EfacturaError) as failed:
        backup.snapshot(cfg, now=NOW)

    assert failed.value.code == "backup_error"
    assert names(folder) == []


def test_only_the_newest_twenty_five_are_kept_and_nothing_else_is_touched(folder, cfg):
    (folder / "facturi-de-mana.zip").write_text("someone else's file")
    (folder / "notite.txt").write_text("notes")

    for day in range(27):
        made = backup.snapshot(cfg, kind="auto" if day % 2 else "manual", now=NOW + timedelta(days=day))

    kept = [name for name in names(folder) if name.startswith("autosaga-")]
    assert len(kept) == 25
    assert kept[0] == "autosaga-20261116-090000-manual.zip"  # the two oldest went
    assert made["removed"] == ["autosaga-20261115-090000-auto.zip"]
    assert {"facturi-de-mana.zip", "notite.txt"} <= set(names(folder))
    assert backup.status(cfg, NOW + timedelta(days=27))["count"] == 25


# --- every 24 hours ------------------------------------------------------------------------------


def test_a_copy_is_made_by_itself_once_twenty_four_hours_have_passed(folder, cfg):
    first = backup.run_if_due(cfg, NOW)
    too_soon = backup.run_if_due(cfg, NOW + timedelta(hours=23, minutes=59))
    due = backup.run_if_due(cfg, NOW + timedelta(hours=24))

    assert (first["kind"], too_soon, due["kind"]) == ("auto", None, "auto")
    assert names(folder) == ["autosaga-20261114-090000-auto.zip", "autosaga-20261115-090000-auto.zip"]


def test_a_copy_made_by_hand_also_counts_for_the_twenty_four_hours(folder, cfg):
    backup.snapshot(cfg, now=NOW)

    state = backup.status(cfg, NOW + timedelta(hours=1))

    assert backup.run_if_due(cfg, NOW + timedelta(hours=20)) is None
    assert (state["last_at"], state["next_due_at"]) == ("2026-11-14T09:00:00", "2026-11-15T09:00:00")
    assert (state["due_now"], backup.status(cfg, NOW + timedelta(hours=25))["due_now"]) == (False, True)


def test_a_missing_folder_is_reported_and_tried_again(folder, cfg):
    os.rename(folder, folder.with_name("unplugged"))

    missing = backup.run_if_due(cfg, NOW)  # must not raise: it runs in the background
    while_missing = backup.status(cfg, NOW)
    os.rename(folder.with_name("unplugged"), folder)
    back = backup.run_if_due(cfg, NOW + timedelta(minutes=15))

    assert missing is None
    assert (while_missing["folder_found"], while_missing["last_failure"]["at"]) == (False, NOW.isoformat())
    assert str(folder) in while_missing["last_failure"]["error"]
    assert back["kind"] == "auto" and backup.status(cfg, NOW + timedelta(minutes=16))["last_failure"] is None
    assert [event for event in journal_events(cfg) if event.startswith("backup.")][-2:] == ["backup.failed", "backup.made"]
    failed = [line for line in journal.events(cfg.db_path)["events"] if line["event"] == "backup.failed"]
    assert failed[0]["data"]["folder_found"] is False  # so the page can say why without guessing


# --- putting one back ----------------------------------------------------------------------------


@pytest.fixture
def saved(folder, cfg):
    """A snapshot with one client, then a second client added after it."""
    name = backup.snapshot(cfg, now=NOW)["name"]
    add_client(cfg, "14399840", "Brutăria Soarelui SRL")
    return name


def test_restore_puts_the_snapshot_back_and_keeps_a_copy_of_what_was_there(saved, folder, cfg, tmp_path, computer):
    later = NOW + timedelta(hours=3)

    result = backup.restore(cfg, saved, now=later)

    assert clients_in(cfg.db_path) == ["Alfa Construct SRL"]
    safety = "autosaga-20261114-120000-before-restore.zip"
    assert (result["ok"], result["restored"], result["kept_as"]) == (True, saved, safety)
    assert clients_in_snapshot(folder / safety, tmp_path) == ["Alfa Construct SRL", "Brutăria Soarelui SRL"]
    state = backup.status(cfg, later)
    assert state["folder"] == str(folder)  # backups go on after a restore
    assert state["last_restore"] == {"at": later.isoformat(), "ok": True, "name": saved, "error": None}


def test_a_running_program_is_stopped_for_the_restore_and_started_again(saved, cfg, computer):
    computer.answer = HEALTHY

    result = backup.restore(cfg, saved, now=NOW + timedelta(hours=3))

    assert computer.asked_to_stop == [9001]
    assert [command for command, _ in computer.spawned] == [("serve",)]
    assert result["restarted"] is True


def test_what_was_still_in_the_databases_journal_file_does_not_come_back(saved, cfg, computer):
    # SQLite would apply a leftover journal file to the restored database.
    for suffix in ("-wal", "-shm"):
        cfg.db_path.with_name(cfg.db_path.name + suffix).write_bytes(b"left over")

    backup.restore(cfg, saved, now=NOW + timedelta(hours=3))

    assert clients_in(cfg.db_path) == ["Alfa Construct SRL"]


@pytest.mark.parametrize("name", [
    "autosaga-20200101-000000-manual.zip",   # not there
    "../autosaga-20261114-090000-manual.zip",  # out of the folder
    "notite.txt",                              # not one of ours
])
def test_only_a_snapshot_from_the_folder_can_be_restored(saved, folder, cfg, computer, name):
    (folder / "notite.txt").write_text("notes")
    computer.answer = HEALTHY

    with pytest.raises(EfacturaError) as refused:
        backup.restore(cfg, name, now=NOW + timedelta(hours=3))

    assert refused.value.code == "backup_error"
    assert computer.asked_to_stop == []  # refused before the program was touched
    assert clients_in(cfg.db_path) == ["Alfa Construct SRL", "Brutăria Soarelui SRL"]


def test_a_file_that_is_not_a_database_is_refused(saved, folder, cfg, computer):
    fake = folder / "autosaga-20261113-090000-manual.zip"
    with zipfile.ZipFile(fake, "w") as archive:
        archive.writestr("efactura.db", "this is not a database")

    with pytest.raises(EfacturaError):
        backup.restore(cfg, fake.name, now=NOW + timedelta(hours=3))

    assert clients_in(cfg.db_path) == ["Alfa Construct SRL", "Brutăria Soarelui SRL"]


def test_a_restore_refused_at_the_start_is_still_recorded_for_the_page(saved, folder, cfg, computer):
    # The page starts the restore as a process of its own and waits to read how it ended.
    fake = folder / "autosaga-20261113-090000-manual.zip"
    with zipfile.ZipFile(fake, "w") as archive:
        archive.writestr("efactura.db", "this is not a database")
    later = NOW + timedelta(hours=3)

    with pytest.raises(EfacturaError):
        backup.restore(cfg, fake.name, now=later)

    record = backup.status(cfg, later)["last_restore"]
    assert (record["at"], record["ok"], record["name"]) == (later.isoformat(), False, fake.name)
    assert "does not hold a database" in record["error"]
    assert journal_events(cfg)[-1] == "restore.failed"


def test_a_program_that_will_not_stop_is_recorded_and_nothing_is_replaced(saved, cfg, computer, monkeypatch):
    def will_not_stop(cfg):
        raise EfacturaError("config_error", "The program did not stop in time.")

    monkeypatch.setattr(background, "stop", will_not_stop)
    later = NOW + timedelta(hours=3)

    with pytest.raises(EfacturaError) as failed:
        backup.restore(cfg, saved, now=later)

    assert failed.value.code == "backup_error"
    record = backup.status(cfg, later)["last_restore"]
    assert (record["ok"], record["name"]) == (False, saved) and "did not stop" in record["error"]
    assert clients_in(cfg.db_path) == ["Alfa Construct SRL", "Brutăria Soarelui SRL"]


def test_a_restore_is_not_called_failed_because_the_program_did_not_start_again(saved, cfg, computer, monkeypatch):
    computer.answer = HEALTHY

    def will_not_start(cfg, config_path, network=False):
        raise EfacturaError("config_error", "Port 9001 on this computer is used by another program.")

    monkeypatch.setattr(background, "start", will_not_start)
    later = NOW + timedelta(hours=3)

    result = backup.restore(cfg, saved, now=later)

    assert (result["ok"], result["restarted"]) == (True, False)
    assert clients_in(cfg.db_path) == ["Alfa Construct SRL"]  # the database is the restored one, and the record says so
    assert backup.status(cfg, later)["last_restore"]["ok"] is True
    assert journal_events(cfg)[-2:] == ["restore.finished", "restore.not_restarted"]


def test_a_restore_that_cannot_replace_the_file_leaves_the_database_alone(saved, cfg, computer, monkeypatch):
    computer.answer = HEALTHY

    def held_open(source, target):
        raise PermissionError("The process cannot access the file because it is being used by another process")

    monkeypatch.setattr(backup.os, "replace", held_open)
    later = NOW + timedelta(hours=3)

    with pytest.raises(EfacturaError) as failed:
        backup.restore(cfg, saved, now=later)

    assert failed.value.code == "backup_error"
    assert clients_in(cfg.db_path) == ["Alfa Construct SRL", "Brutăria Soarelui SRL"]
    assert computer.answer == HEALTHY  # the program runs again, on the database it had
    record = backup.status(cfg, later)["last_restore"]
    assert (record["ok"], record["name"]) == (False, saved) and "being used" in record["error"]
    assert not list(cfg.data_dir.glob("*.restoring"))


# --- when the database itself is damaged -----------------------------------------------------------


def damage_the_clients(db_path):
    """One page of the clients table overwritten, as a failing disk leaves it. The program
    still opens the file; reading the clients fails."""
    store = Store(db_path)
    for number in range(400):
        store.save_client(str(20000000 + number), f"Client {number} SRL " + "x" * 80, NOW.isoformat())
    store.close()
    raw = db_path.read_bytes()
    page_size = int.from_bytes(raw[16:18], "big")
    page = raw.index(b"Client 399 SRL") // page_size
    with open(db_path, "r+b") as file:
        file.seek(page * page_size)
        file.write(b"\xff" * page_size)


def test_a_damaged_database_can_be_replaced_by_a_good_snapshot(saved, folder, cfg, computer):
    damage_the_clients(cfg.db_path)
    with pytest.raises(sqlite3.DatabaseError):
        clients_in(cfg.db_path)
    later = NOW + timedelta(hours=3)

    result = backup.restore(cfg, saved, now=later)  # the one thing a backup is for

    assert clients_in(cfg.db_path) == ["Alfa Construct SRL"]
    # No sound copy of the damaged one could be made, so the file itself was kept.
    aside = cfg.db_path.with_name("efactura.db.replaced-20261114-120000")
    assert (result["kept_as"], aside.is_file()) == (aside.name, True)
    assert backup.status(cfg, later)["last_restore"]["ok"] is True
    assert journal_events(cfg)[-2:] == ["restore.kept_aside", "restore.finished"]


def test_a_file_that_is_no_longer_a_database_is_replaced_from_the_whole_path(saved, folder, cfg, computer):
    cfg.db_path.write_bytes(b"\0" * 8192)  # what a crash during a write can leave
    later = NOW + timedelta(hours=3)

    with pytest.raises(EfacturaError) as by_name:  # the folder was written in the database that is gone
        backup.restore(cfg, saved, now=later)
    backup.restore(cfg, str(folder / saved), now=later)

    assert "whole path" in by_name.value.message
    assert clients_in(cfg.db_path) == ["Alfa Construct SRL"]
    assert backup.status(cfg, later)["folder"] == str(folder)  # backups go on to the folder the file came from


def test_a_whole_path_must_still_be_a_copy_this_program_made(saved, folder, cfg, computer):
    other = folder / "notite.zip"
    other.write_bytes((folder / saved).read_bytes())

    with pytest.raises(EfacturaError):
        backup.restore(cfg, str(other), now=NOW + timedelta(hours=3))
    with pytest.raises(EfacturaError):  # the page can only name a file in the folder
        backup.start_restore_in_background(cfg, str(folder / saved))

    assert clients_in(cfg.db_path) == ["Alfa Construct SRL", "Brutăria Soarelui SRL"]


def test_with_the_folder_gone_the_old_database_is_kept_beside_the_new_one(saved, folder, cfg, computer, monkeypatch):
    real_snapshot = backup.snapshot

    def stick_pulled(cfg, kind="manual", now=None, never_remove=None):
        os.rename(folder, folder.with_name("unplugged"))  # after the chosen copy was read
        return real_snapshot(cfg, kind, now, never_remove)

    monkeypatch.setattr(backup, "snapshot", stick_pulled)

    result = backup.restore(cfg, saved, now=NOW + timedelta(hours=3))

    assert clients_in(cfg.db_path) == ["Alfa Construct SRL"]
    assert clients_in(cfg.db_path.with_name(result["kept_as"])) == ["Alfa Construct SRL", "Brutăria Soarelui SRL"]


# --- whatever goes wrong, the program runs again ----------------------------------------------------


def test_the_program_is_started_again_whatever_goes_wrong_in_between(saved, cfg, computer, monkeypatch):
    computer.answer = HEALTHY

    def a_bug(cfg, staged):
        raise RuntimeError("something nobody expected")

    monkeypatch.setattr(backup, "_swap", a_bug)
    later = NOW + timedelta(hours=3)

    with pytest.raises(EfacturaError) as failed:
        backup.restore(cfg, saved, now=later)

    assert computer.answer == HEALTHY
    assert "left as it was" in failed.value.message and "RuntimeError" in failed.value.message
    assert clients_in(cfg.db_path) == ["Alfa Construct SRL", "Brutăria Soarelui SRL"]
    assert backup.status(cfg, later)["last_restore"]["ok"] is False


def test_an_old_copy_that_cannot_be_deleted_does_not_fail_the_restore(saved, folder, cfg, computer, monkeypatch):
    computer.answer = HEALTHY
    for day in range(24, 0, -1):  # with `saved` the folder is full: the next copy makes the oldest go
        backup.snapshot(cfg, kind="auto", now=NOW - timedelta(days=day))
    real_unlink = type(folder).unlink

    def held_open(self, missing_ok=False):  # Windows: the oldest zip is open in another program
        if self.name.endswith("-auto.zip"):
            raise PermissionError(13, "The process cannot access the file because it is being used by another process")
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(type(folder), "unlink", held_open)

    result = backup.restore(cfg, saved, now=NOW + timedelta(hours=3))

    assert (result["ok"], computer.answer) == (True, HEALTHY)
    assert clients_in(cfg.db_path) == ["Alfa Construct SRL"]


def test_a_program_that_cannot_even_be_started_does_not_undo_what_was_restored(saved, cfg, computer, monkeypatch):
    computer.answer = HEALTHY

    def cannot_be_spawned(cfg, config_path, network=False):
        raise OSError(8, "Not enough memory resources are available to process this command")

    monkeypatch.setattr(background, "start", cannot_be_spawned)
    later = NOW + timedelta(hours=3)

    result = backup.restore(cfg, saved, now=later)

    assert (result["ok"], result["restarted"]) == (True, False)
    assert clients_in(cfg.db_path) == ["Alfa Construct SRL"]
    assert backup.status(cfg, later)["last_restore"]["ok"] is True


def test_a_file_held_for_a_moment_is_tried_again(saved, cfg, computer, monkeypatch):
    real_replace, refusals = os.replace, []

    def held_twice(source, target):  # the stopped program has not quite let go of the file
        if len(refusals) < 2:
            refusals.append(target)
            raise PermissionError(13, "The process cannot access the file because it is being used by another process")
        return real_replace(source, target)

    monkeypatch.setattr(backup.os, "replace", held_twice)

    backup.restore(cfg, saved, now=NOW + timedelta(hours=3))

    assert len(refusals) == 2 and clients_in(cfg.db_path) == ["Alfa Construct SRL"]


def test_a_restore_is_refused_while_invoices_are_being_downloaded(saved, cfg, computer):
    from efactura.service import _FileLock

    computer.answer = HEALTHY
    later = NOW + timedelta(hours=3)

    with _FileLock(cfg.lock_path):  # what a download holds
        with pytest.raises(EfacturaError) as from_the_page:
            backup.start_restore_in_background(cfg, saved)
        with pytest.raises(EfacturaError):
            backup.restore(cfg, saved, now=later)

    assert from_the_page.value.code == "busy"
    assert computer.asked_to_stop == [] and computer.spawned == []  # refused before the program was touched
    assert "downloaded" in backup.status(cfg, later)["last_restore"]["error"]
    assert clients_in(cfg.db_path) == ["Alfa Construct SRL", "Brutăria Soarelui SRL"]


def test_a_copy_that_went_missing_after_the_click_is_recorded_for_the_page(saved, folder, cfg, computer):
    backup.start_restore_in_background(cfg, saved)  # the page checked the name
    (folder / saved).unlink()  # then the stick was pulled
    later = NOW + timedelta(hours=3)

    with pytest.raises(EfacturaError):
        backup.restore(cfg, saved, now=later)  # what the process it started runs

    assert backup.status(cfg, later)["last_restore"]["ok"] is False


def test_a_restore_does_not_bring_back_a_failure_that_was_already_over(folder, cfg, computer):
    os.rename(folder, folder.with_name("unplugged"))
    backup.run_if_due(cfg, NOW)  # fails: the stick is not in
    os.rename(folder.with_name("unplugged"), folder)
    good = backup.run_if_due(cfg, NOW + timedelta(minutes=15))["name"]  # made while the failure was still noted

    backup.restore(cfg, good, now=NOW + timedelta(hours=3))

    assert backup.status(cfg, NOW + timedelta(hours=3))["last_failure"] is None


# --- a clock that was wrong, and files that are not what they seem -----------------------------------


@pytest.fixture
def clock_was_ahead(folder, cfg):
    """The PC's clock was a year ahead for a while (25 copies), then it was corrected."""
    for number in range(25):
        backup.snapshot(cfg, kind="auto", now=NOW + timedelta(days=365, hours=number))
    return folder


def test_a_copy_made_now_is_kept_though_every_other_is_named_later(clock_was_ahead, cfg):
    made = backup.snapshot(cfg, kind="manual", now=NOW)

    kept = names(clock_was_ahead)
    assert made["name"] in kept and len(kept) == 25
    assert made["removed"] == ["autosaga-20271114-090000-auto.zip"]  # of those from the future, the earliest goes


def test_the_daily_copy_goes_on_when_the_newest_file_is_from_the_future(clock_was_ahead, cfg):
    made = [backup.run_if_due(cfg, NOW + timedelta(hours=6 * quarter)) for quarter in range(12)]  # three days

    assert [bool(each) for each in made] == [True, False, False, False] * 3
    state = backup.status(cfg, NOW + timedelta(days=3))
    assert (state["last_at"], state["count"]) == ("2026-11-16T09:00:00", 25)


def test_the_copy_made_before_a_restore_is_kept_too(clock_was_ahead, cfg, computer):
    computer.answer = HEALTHY
    chosen = backup.snapshots(clock_was_ahead)[0]["name"]

    result = backup.restore(cfg, chosen, now=NOW)

    assert (clock_was_ahead / result["kept_as"]).is_file() and computer.answer == HEALTHY


def test_a_half_written_file_left_by_a_crash_is_cleared_away(folder, cfg):
    left = folder / "autosaga-20261101-090000-auto.zip.partial"  # the PC was switched off mid-copy
    left.write_bytes(b"half a zip")
    fresh = folder / "autosaga-20261114-085930-manual.zip.partial"  # another copy, being written right now
    fresh.write_bytes(b"half a zip")

    backup.snapshot(cfg, kind="auto", now=NOW)

    assert (left.exists(), fresh.exists()) == (False, True)


def test_a_file_named_like_a_copy_but_with_no_real_date_is_left_out(folder, cfg):
    (folder / "autosaga-20261340-250000-manual.zip").write_bytes(b"renamed by hand")

    state = backup.status(cfg, NOW)  # what the screen reads
    background.keep_house(cfg, NOW)  # what the background job runs

    assert state["count"] == 0
    assert [each["kind"] for each in backup.snapshots(folder)] == ["auto"]


# --- from the page, the terminal and the background job -------------------------------------------


def test_backups_over_the_api(tmp_path, cfg, computer, monkeypatch):
    api = TestClient(create_app(cfg))
    chosen = tmp_path / "stick" / "Copii"

    set_folder = api.put("/backups/folder", headers=KEY, json={"folder": str(chosen)})
    made = api.post("/api/backups", headers={"Sec-Fetch-Site": "same-origin", "Host": "127.0.0.1:9001"})
    listed = api.get("/backups", headers=KEY).json()
    restore = api.post("/backups/restore", headers=KEY, json={"name": made.json()["name"]})
    unknown = api.post("/backups/restore", headers=KEY, json={"name": "autosaga-20200101-000000-manual.zip"})

    assert (set_folder.status_code, set_folder.json()["folder"]) == (200, str(chosen))
    assert (made.status_code, made.json()["kind"], listed["count"], listed["max"]) == (200, "manual", 1, 25)
    assert (restore.status_code, restore.json()) == (200, {"ok": True, "started": True})
    assert computer.spawned == [(("restore", made.json()["name"]), cfg.data_dir / "restore.log")]
    assert (unknown.status_code, unknown.json()["error"]["code"]) == (409, "backup_error")
    assert api.put("/backups/folder", headers=KEY, json={"folder": ""}).status_code == 400
    assert api.get("/backups").status_code == 401


def test_backup_and_restore_from_the_terminal(folder, cfg, computer, capsys):
    config = str(cfg.path)

    made_code = cli.main(["--config", config, "backup"])
    made = json.loads(capsys.readouterr().out)
    add_client(cfg, "14399840", "Brutăria Soarelui SRL")
    restored_code = cli.main(["--config", config, "restore", made["name"]])
    restored = json.loads(capsys.readouterr().out)

    assert (made_code, made["kind"], restored_code, restored["restored"]) == (0, "manual", 0, made["name"])
    assert clients_in(cfg.db_path) == ["Alfa Construct SRL"]


def test_the_background_job_makes_the_daily_copy_and_cleans_the_journal(folder, cfg):
    journal.record("sync", "sync.finished", "Old line.", now=NOW - timedelta(days=40))

    background.keep_house(cfg, NOW)
    background.keep_house(cfg, NOW + timedelta(minutes=15))

    assert names(folder) == ["autosaga-20261114-090000-auto.zip"]
    assert "Old line." not in [line["message"] for line in journal.events(cfg.db_path)["events"]]
