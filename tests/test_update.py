"""Updating an installed copy to the newest release, keeping its settings and its data.

The repositories here are real ones in temporary folders: a "remote" with tagged releases
and the clone the installer would have made from it.
"""

import json
import os
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from efactura import backup, background, cli, update
from efactura.api import create_app
from efactura.config import load_config
from efactura.errors import EfacturaError
from efactura.store import Store

NOW = datetime(2026, 11, 14, 10, 0, tzinfo=timezone(timedelta(hours=2)))
HEALTHY = {"ok": True, "service": "efactura", "version": "0.1.0"}
KEY = {"X-API-Key": "local-key"}


def git(folder, *arguments):
    done = subprocess.run(["git", "-C", str(folder), *arguments], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


@pytest.fixture(autouse=True)
def only_these_repositories(monkeypatch):
    """Git reads no settings or hooks from the person running the tests."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for name, value in (("NAME", "Tests"), ("EMAIL", "tests@example.invalid")):
        monkeypatch.setenv(f"GIT_AUTHOR_{name}", value)
        monkeypatch.setenv(f"GIT_COMMITTER_{name}", value)


@pytest.fixture
def computer(monkeypatch):
    """What answers on the program's port, and what was done about it."""
    state = SimpleNamespace(answer=None, asked_to_stop=[], spawned=[], synced=[], sync_fails=0)

    def spawn_command(config_path, output, *command):
        state.spawned.append((command, output))
        if command == ("serve",):
            state.answer = HEALTHY

    def ask_to_stop(port, key):
        state.asked_to_stop.append(port)
        state.answer = None

    def sync_dependencies(project):
        state.synced.append(git(project, "describe", "--tags", "--always"))
        if state.sync_fails:
            state.sync_fails -= 1
            raise EfacturaError("update_error", "uv sync failed (exit code 2).")

    monkeypatch.setattr(background, "probe", lambda port: state.answer)
    monkeypatch.setattr(background, "spawn_command", spawn_command)
    monkeypatch.setattr(background, "ask_to_stop", ask_to_stop)
    monkeypatch.setattr(background, "pause", lambda seconds: None)
    monkeypatch.setattr(update, "sync_dependencies", sync_dependencies)
    return state


@pytest.fixture
def installed(tmp_path, computer):
    """Release v0.1.0 as the installer leaves it: cloned, with settings and a database."""
    remote = tmp_path / "remote"
    remote.mkdir()
    git(remote, "init", "-q", "-b", "main")
    (remote / ".gitignore").write_text("config.toml\ndata/\n", encoding="utf-8")
    (remote / "program.txt").write_text("release 0.1.0\n", encoding="utf-8")
    git(remote, "add", "-A")
    git(remote, "commit", "-q", "-m", "release 0.1.0")
    git(remote, "tag", "v0.1.0")

    project = tmp_path / "AutoSaga"
    git(tmp_path, "clone", "-q", str(remote), str(project))
    git(project, "-c", "advice.detachedHead=false", "checkout", "-q", "--detach", "v0.1.0")
    (project / "config.toml").write_text('[api]\nkey = "local-key"\nport = 9001\n', encoding="utf-8")
    cfg = load_config(project / "config.toml")
    store = Store(cfg.db_path)
    store.save_client("12345674", "Alfa Construct SRL", NOW.isoformat())
    store.close()

    def release(version, **files):
        for name, text in {"program.txt": f"release {version}\n", **files}.items():
            (remote / name).parent.mkdir(parents=True, exist_ok=True)
            (remote / name).write_text(text, encoding="utf-8")
        git(remote, "add", "-A", "--force")
        git(remote, "commit", "-q", "-m", f"release {version}")
        git(remote, "tag", f"v{version}")

    return SimpleNamespace(project=project, remote=remote, cfg=cfg, release=release)


def clients_in(db_path):
    with sqlite3.connect(db_path) as database:
        return [row[0] for row in database.execute("SELECT name FROM clients")]


def held(installed):
    return git(installed.project, "describe", "--tags")


# --- is there a newer release? -----------------------------------------------------------------


def test_a_newer_release_is_reported(installed):
    installed.release("0.2.0")

    found = update.status(installed.cfg, check=True, project=installed.project, now=NOW)

    assert (found["ok"], found["version"], found["installed_release"]) == (True, "v0.1.0", "v0.1.0")
    assert (found["latest_release"], found["update_available"], found["can_update"]) == ("v0.2.0", True, True)
    assert (found["checked_at"], found["check_error"], found["last_update"]) == (NOW.isoformat(), None, None)


def test_the_newest_release_installed_means_nothing_to_do(installed):
    found = update.status(installed.cfg, check=True, project=installed.project, now=NOW)

    assert (found["latest_release"], found["update_available"]) == ("v0.1.0", False)


def test_the_highest_version_is_the_latest_not_the_last_in_the_alphabet(installed):
    installed.release("0.9.0")
    installed.release("0.10.0")

    assert update.status(installed.cfg, check=True, project=installed.project, now=NOW)["latest_release"] == "v0.10.0"


def test_the_answer_is_remembered_for_twelve_hours(installed):
    installed.release("0.2.0")
    update.status(installed.cfg, check=True, project=installed.project, now=NOW)
    git(installed.project, "remote", "set-url", "origin", str(installed.remote.parent / "gone"))

    soon = update.status(installed.cfg, project=installed.project, now=NOW + timedelta(hours=11))
    later = update.status(installed.cfg, project=installed.project, now=NOW + timedelta(hours=13))
    after = update.status(installed.cfg, project=installed.project, now=NOW + timedelta(hours=14))

    assert (soon["latest_release"], soon["check_error"], soon["checked_at"]) == ("v0.2.0", None, NOW.isoformat())
    assert later["latest_release"] == "v0.2.0" and "Reading the releases" in later["check_error"]
    assert after["check_error"] is None  # a failed look is not repeated on every page either


def test_a_development_copy_cannot_be_updated(installed):
    git(installed.project, "checkout", "-q", "main")
    installed.release("0.2.0")

    found = update.status(installed.cfg, check=True, project=installed.project, now=NOW)
    with pytest.raises(EfacturaError) as refused:
        update.update(installed.cfg, project=installed.project, now=NOW)

    assert (found["can_update"], found["update_available"], found["latest_release"]) == (False, False, "v0.2.0")
    assert "main" in found["why_not"]
    assert refused.value.code == "update_error"
    assert held(installed) == "v0.1.0"


def test_a_folder_that_is_not_a_clone_cannot_be_updated(tmp_path):
    (tmp_path / "config.toml").write_text('[api]\nkey = "local-key"\n', encoding="utf-8")

    found = update.status(load_config(tmp_path / "config.toml"), check=True, project=tmp_path, now=NOW)

    assert (found["can_update"], found["installed_release"], found["update_available"]) == (False, None, False)


# --- updating --------------------------------------------------------------------------------


def test_update_moves_to_the_newest_release_and_keeps_settings_and_data(installed, computer):
    installed.release("0.2.0", **{"src/new_module.py": "print('new')\n"})
    settings_before = (installed.project / "config.toml").read_bytes()

    result = update.update(installed.cfg, project=installed.project, now=NOW)

    assert (result["ok"], result["updated"], result["from"], result["to"]) == (True, True, "v0.1.0", "v0.2.0")
    assert held(installed) == "v0.2.0"
    assert (installed.project / "src" / "new_module.py").exists()
    assert computer.synced == ["v0.2.0"]
    assert (installed.project / "config.toml").read_bytes() == settings_before
    assert clients_in(installed.cfg.db_path) == ["Alfa Construct SRL"]


def test_the_database_is_copied_before_anything_changes(installed):
    installed.release("0.2.0")

    result = update.update(installed.cfg, project=installed.project, now=NOW)

    backups = sorted((installed.cfg.data_dir / "backups").iterdir())
    assert [path.name for path in backups] == ["efactura-v0.1.0-20261114-100000.db"]
    assert result["backup"] == str(backups[0])
    assert clients_in(backups[0]) == ["Alfa Construct SRL"]


def test_only_the_last_three_copies_are_kept(installed):
    for number in range(2, 7):
        installed.release(f"0.{number}.0")
        update.update(installed.cfg, project=installed.project, now=NOW + timedelta(days=number))

    kept = sorted(path.name for path in (installed.cfg.data_dir / "backups").iterdir())

    assert kept == [
        "efactura-v0.3.0-20261118-100000.db",
        "efactura-v0.4.0-20261119-100000.db",
        "efactura-v0.5.0-20261120-100000.db",
    ]


def test_nothing_happens_when_the_newest_release_is_installed(installed, computer):
    computer.answer = HEALTHY

    result = update.update(installed.cfg, project=installed.project, now=NOW)

    assert result == {"ok": True, "updated": False, "version": "v0.1.0"}
    assert (computer.synced, computer.asked_to_stop) == ([], [])
    assert not (installed.cfg.data_dir / "backups").exists()


def test_a_running_program_is_stopped_for_the_update_and_started_again(installed, computer):
    installed.release("0.2.0")
    computer.answer = HEALTHY

    result = update.update(installed.cfg, project=installed.project, now=NOW)

    assert computer.asked_to_stop == [9001]
    assert [command for command, _ in computer.spawned] == [("serve",)]
    assert (result["restarted"], computer.answer) == (True, HEALTHY)


def test_a_program_that_was_not_running_is_not_started(installed, computer):
    installed.release("0.2.0")

    result = update.update(installed.cfg, project=installed.project, now=NOW)

    assert (result["restarted"], computer.spawned) == (False, [])


def test_a_failed_update_goes_back_to_the_release_that_worked(installed, computer):
    installed.release("0.2.0")
    computer.answer = HEALTHY
    computer.sync_fails = 1

    with pytest.raises(EfacturaError) as failed:
        update.update(installed.cfg, project=installed.project, now=NOW)

    assert failed.value.code == "update_error" and "uv sync failed" in failed.value.message
    assert held(installed) == "v0.1.0"
    assert computer.synced == ["v0.2.0", "v0.1.0"]  # the old release's dependencies were put back
    assert computer.answer == HEALTHY  # and the program runs again
    assert clients_in(installed.cfg.db_path) == ["Alfa Construct SRL"]
    record = update.status(installed.cfg, project=installed.project, now=NOW)["last_update"]
    assert (record["ok"], record["from"], record["to"]) == (False, "v0.1.0", "v0.2.0")
    assert "uv sync failed" in record["error"]


def test_a_successful_update_is_recorded_for_the_page(installed):
    installed.release("0.2.0")

    update.update(installed.cfg, project=installed.project, now=NOW)

    found = update.status(installed.cfg, project=installed.project, now=NOW)
    assert found["last_update"] == {"at": NOW.isoformat(), "ok": True, "from": "v0.1.0", "to": "v0.2.0", "error": None}
    assert (found["version"], found["update_available"]) == ("v0.2.0", False)


def test_an_update_that_fails_before_anything_is_stopped_is_recorded_too(installed):
    # The page waits for this record. Without it the update window would wait for ever.
    git(installed.project, "remote", "set-url", "origin", str(installed.remote.parent / "gone"))

    with pytest.raises(EfacturaError):
        update.update(installed.cfg, project=installed.project, now=NOW)

    record = update.status(installed.cfg, project=installed.project, now=NOW)["last_update"]
    assert (record["at"], record["ok"], record["from"], record["to"]) == (NOW.isoformat(), False, "v0.1.0", None)
    assert "Reading the releases" in record["error"]


def test_finding_nothing_newer_is_recorded_as_done(installed):
    update.update(installed.cfg, project=installed.project, now=NOW)

    record = update.status(installed.cfg, project=installed.project, now=NOW)["last_update"]
    assert record == {"at": NOW.isoformat(), "ok": True, "from": "v0.1.0", "to": "v0.1.0", "error": None}


@pytest.mark.parametrize("smuggled", ["config.toml", "data/efactura.db"])
def test_a_release_that_would_replace_settings_or_data_is_refused(installed, computer, smuggled):
    # Git overwrites ignored files without a word, so this has to be checked by hand.
    installed.release("0.2.0", **{smuggled: "from the release"})
    computer.answer = HEALTHY

    with pytest.raises(EfacturaError) as refused:
        update.update(installed.cfg, project=installed.project, now=NOW)

    assert refused.value.code == "update_error" and smuggled in refused.value.message
    assert held(installed) == "v0.1.0"
    assert update.status(installed.cfg, project=installed.project, now=NOW)["last_update"]["ok"] is False
    assert computer.asked_to_stop == []  # the program was never stopped
    assert clients_in(installed.cfg.db_path) == ["Alfa Construct SRL"]  # still the PC's own database
    assert (installed.project / "config.toml").read_text(encoding="utf-8").startswith("[api]")


def test_two_updates_cannot_run_at_once(installed, monkeypatch):
    installed.release("0.2.0")

    def a_second_update_in_the_middle(project):
        with pytest.raises(EfacturaError) as busy:
            update.update(installed.cfg, project=installed.project, now=NOW)
        assert busy.value.code == "busy"

    monkeypatch.setattr(update, "sync_dependencies", a_second_update_in_the_middle)

    assert update.update(installed.cfg, project=installed.project, now=NOW)["updated"] is True


# --- from the page and from the terminal ---------------------------------------------------------


def test_the_page_starts_the_update_as_a_process_of_its_own(installed, computer, monkeypatch):
    monkeypatch.setattr(update, "PROJECT", installed.project)
    installed.release("0.2.0")
    api = TestClient(create_app(installed.cfg))

    status = api.get("/update?check=true", headers=KEY).json()
    started = api.post("/api/update", headers={"Sec-Fetch-Site": "same-origin", "Host": "127.0.0.1:9001"})

    assert (status["update_available"], status["latest_release"]) == (True, "v0.2.0")
    assert (started.status_code, started.json()) == (200, {"ok": True, "started": True})
    assert computer.spawned == [(("update",), installed.cfg.data_dir / "update.log")]
    assert held(installed) == "v0.1.0"  # the request itself changes nothing


def test_the_page_cannot_update_a_development_copy(installed, computer, monkeypatch):
    monkeypatch.setattr(update, "PROJECT", installed.project)
    git(installed.project, "checkout", "-q", "main")
    api = TestClient(create_app(installed.cfg))

    refused = api.post("/update", headers=KEY)

    assert (refused.status_code, refused.json()["error"]["code"], computer.spawned) == (409, "update_error", [])
    assert api.post("/update").status_code == 401


def test_the_update_command_checks_or_updates(installed, monkeypatch, capsys):
    monkeypatch.setattr(update, "PROJECT", installed.project)
    installed.release("0.2.0")
    config = str(installed.project / "config.toml")

    checked = cli.main(["--config", config, "update", "--check"])
    found = json.loads(capsys.readouterr().out)
    updated = cli.main(["--config", config, "update"])
    result = json.loads(capsys.readouterr().out)

    assert (checked, found["update_available"], held(installed)) == (0, True, "v0.2.0")
    assert (updated, result["updated"], result["to"]) == (0, True, "v0.2.0")


def test_the_program_is_started_again_when_the_copy_before_an_update_cannot_be_made(installed, computer, monkeypatch):
    installed.release("0.2.0")
    computer.answer = HEALTHY

    def disk_full(source, target):
        raise sqlite3.OperationalError("database or disk is full")

    monkeypatch.setattr(backup, "copy_database", disk_full)

    with pytest.raises(EfacturaError) as failed:
        update.update(installed.cfg, project=installed.project, now=NOW)

    assert failed.value.code == "update_error" and "disk is full" in failed.value.message
    assert computer.answer == HEALTHY  # stopped for the update, and running again
    record = update.status(installed.cfg, project=installed.project, now=NOW)["last_update"]
    assert record["ok"] is False and "disk is full" in record["error"]  # the page is told how it ended


def test_an_update_is_not_called_failed_because_the_program_did_not_start_again(installed, computer, monkeypatch):
    installed.release("0.2.0")
    computer.answer = HEALTHY

    def will_not_start(cfg, config_path):
        raise EfacturaError("config_error", "Port 9001 on this computer is used by another program.")

    monkeypatch.setattr(background, "start", will_not_start)

    result = update.update(installed.cfg, project=installed.project, now=NOW)

    assert (result["updated"], result["restarted"], held(installed)) == (True, False, "v0.2.0")
    assert update.status(installed.cfg, project=installed.project, now=NOW)["last_update"]["ok"] is True


def test_a_development_copy_can_still_look_for_the_newest_release(installed):
    installed.release("0.2.0")
    git(installed.project, "checkout", "-q", "-b", "work")

    found = update.status(installed.cfg, check=True, project=installed.project, now=NOW)

    assert (found["can_update"], found["update_available"]) == (False, False)
    assert (found["latest_release"], found["why_not_kind"], found["check_error"]) == ("v0.2.0", "development", None)


def test_a_development_copy_that_cannot_reach_the_remote_says_so(installed):
    git(installed.project, "checkout", "-q", "-b", "work")
    git(installed.project, "remote", "set-url", "origin", str(installed.remote.parent / "gone"))

    found = update.status(installed.cfg, check=True, project=installed.project, now=NOW)

    assert found["why_not_kind"] == "development" and found["check_error"]


def test_a_folder_that_is_not_a_clone_says_so(tmp_path):
    (tmp_path / "config.toml").write_text('[api]\nkey = "k"\n', encoding="utf-8")

    found = update.status(load_config(tmp_path / "config.toml"), check=True, project=tmp_path, now=NOW)

    assert (found["why_not_kind"], found["latest_release"], found["check_error"]) == ("not_a_clone", None, None)


def test_an_installed_copy_has_no_reason_not_to_update(installed):
    assert update.status(installed.cfg, project=installed.project, now=NOW)["why_not_kind"] is None
