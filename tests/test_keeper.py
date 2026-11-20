"""`efactura keep-serving`: the program in a container, started again after a restore or a crash."""

import threading

import pytest

from efactura import backup, keeper
from efactura.config import load_config
from efactura.errors import BUSY, EfacturaError


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[api]\nkey = "k"\nport = 9001\n', encoding="utf-8")
    return load_config(path)


class Server:
    """A run of `serve --network` that ends when its turn says so."""

    def __init__(self, ends_after: float, code: int = 1):
        self.ends_after = ends_after
        self.code = code  # how it ended: 0 when it was stopped on purpose (a restore), else a failure
        self.terminated = False

    def wait(self):
        return self.code

    def poll(self):
        return self.code

    def terminate(self):
        self.terminated = True


@pytest.fixture
def computer(monkeypatch, cfg):
    """Stand-ins for the processes and the clock. Each run lasts as long as `runs` says; when
    they are used up, the keeper is told to stop."""
    state = type("State", (), {})()
    state.started, state.paused, state.now, state.restore_busy, state.answering = [], [], 0.0, 0, []
    state.runs = [100.0, 100.0]
    state.stop = threading.Event()
    state.servers = []
    state.during_the_pause = None  # what happens while the keeper waits to start again

    def spawn(config_path):
        state.started.append(config_path)
        turn = state.runs.pop(0) if state.runs else 0.0
        run = Server(*turn) if isinstance(turn, tuple) else Server(turn)
        state.servers.append(run)
        state.now += run.ends_after
        if not state.runs:
            state.stop.set()
        return run

    def pause(seconds, stop):
        state.paused.append(seconds)
        state.now += seconds
        if seconds == keeper.RESTART_PAUSE and state.during_the_pause:
            state.during_the_pause()
            state.during_the_pause = None

    def restore_running(cfg):
        if state.restore_busy:
            state.restore_busy -= 1
            return True
        return False

    monkeypatch.setattr(keeper, "spawn", spawn)
    monkeypatch.setattr(keeper, "pause", pause)
    monkeypatch.setattr(keeper, "clock", lambda: state.now)
    monkeypatch.setattr(keeper, "restore_running", restore_running)
    monkeypatch.setattr(keeper, "answering", lambda port: bool(state.answering and state.answering.pop(0)))
    return state


def test_the_program_is_started_again_each_time_it_stops(cfg, computer):
    computer.runs = [100.0, 100.0, 100.0]

    keeper.keep_serving(cfg, cfg.path, stop=computer.stop)

    assert computer.started == [cfg.path] * 3
    assert computer.paused == [keeper.RESTART_PAUSE] * 2


def test_it_waits_for_a_restore_to_finish_before_starting_again(cfg, computer):
    computer.restore_busy = 3

    keeper.keep_serving(cfg, cfg.path, stop=computer.stop)

    assert computer.paused == [keeper.LOOK_EVERY] * 3 + [keeper.RESTART_PAUSE]
    assert len(computer.started) == 2


def test_it_waits_while_another_copy_answers_on_the_port(cfg, computer):
    computer.answering = [True, True, False]

    keeper.keep_serving(cfg, cfg.path, stop=computer.stop)

    assert computer.paused == [keeper.LOOK_EVERY] * 2 + [keeper.RESTART_PAUSE]


def test_a_program_that_keeps_failing_at_once_is_tried_less_and_less_often(cfg, computer):
    computer.runs = [1.0] * 8

    keeper.keep_serving(cfg, cfg.path, stop=computer.stop)

    assert computer.paused == [4.0, 8.0, 16.0, 32.0, 60.0, 60.0, 60.0]


def test_a_long_run_resets_the_pause(cfg, computer):
    computer.runs = [1.0, 1.0, 100.0, 1.0]

    keeper.keep_serving(cfg, cfg.path, stop=computer.stop)

    assert computer.paused == [4.0, 8.0, keeper.RESTART_PAUSE]


def test_the_restore_lock_says_whether_a_restore_runs(cfg):
    assert keeper.restore_running(cfg) is False
    with backup.no_restore_running(cfg):
        assert keeper.restore_running(cfg) is True


def test_the_program_is_run_in_server_mode_and_knows_its_keeper(cfg, monkeypatch):
    seen = {}

    def popen(command, env):
        seen.update(command=command, keeper=env.get("EFACTURA_KEEPER"))
        return Server(0)

    monkeypatch.setattr(keeper.subprocess, "Popen", popen)

    keeper.spawn(cfg.path)

    assert seen["command"][-4:] == ["--config", str(cfg.path), "serve", "--network"]
    assert seen["keeper"] == "1"


def test_a_restore_under_the_keeper_does_not_start_the_program_itself(cfg, monkeypatch):
    from efactura import background

    monkeypatch.setenv("EFACTURA_KEEPER", "1")
    monkeypatch.setattr(background, "start", lambda *a, **k: pytest.fail("the keeper starts it"))

    assert background.start_again(cfg, {"ok": True, "stopped": True, "network": True}) is False


def test_without_the_keeper_it_starts_again_in_its_mode(cfg, monkeypatch):
    from efactura import background

    started = []
    monkeypatch.delenv("EFACTURA_KEEPER", raising=False)
    monkeypatch.setattr(background, "start", lambda cfg, path, network=False: started.append(network) or {"ok": True})

    assert background.start_again(cfg, {"ok": True, "stopped": True, "network": True}) is True
    assert background.start_again(cfg, {"ok": True, "stopped": True}) is True
    assert background.start_again(cfg, {"ok": True, "stopped": False}) is False
    assert started == [True, False]


def test_busy_is_what_a_held_restore_lock_says(cfg):
    with backup.no_restore_running(cfg):
        with pytest.raises(EfacturaError) as raised:
            with backup.no_restore_running(cfg):
                pass
    assert raised.value.code == BUSY


# --- found by the review ---------------------------------------------------------------------------


def test_a_restore_begun_during_the_pause_is_waited_for_too(cfg, computer):
    # A restore run by hand (docker exec ... efactura restore) while the program keeps failing:
    # the keeper looks again just before it starts the program, not only before its pause.
    computer.during_the_pause = lambda: setattr(computer, "restore_busy", 2)

    keeper.keep_serving(cfg, cfg.path, stop=computer.stop)

    assert computer.paused == [keeper.RESTART_PAUSE, keeper.LOOK_EVERY, keeper.LOOK_EVERY]
    assert len(computer.started) == 2


def test_a_program_started_just_as_the_keeper_is_told_to_stop_is_stopped_at_once(cfg, computer):
    computer.runs = [100.0]  # the stop comes while the program is being started

    keeper.keep_serving(cfg, cfg.path, stop=computer.stop)

    assert computer.servers[-1].terminated is True


def test_the_pause_ends_as_soon_as_the_keeper_is_told_to_stop(monkeypatch):
    monkeypatch.setattr(keeper, "pause", keeper.pause)  # the real one
    stop = threading.Event()
    stop.set()
    began = keeper.clock()

    keeper.pause(30, stop)

    assert keeper.clock() - began < 1


def test_the_keeper_never_opens_the_database(cfg, monkeypatch, capsys):
    # A restore replaces the database file under it: a connection the keeper held open (its
    # log lines go to the journal through the program's logging) ended in SIGBUS, at times.
    from efactura import cli

    configured, kept = [], []
    monkeypatch.setattr(cli, "configure_logging", lambda cfg: configured.append(cfg))
    monkeypatch.setattr(keeper, "keep_serving", lambda cfg, path: kept.append(path))

    assert cli.main(["--config", str(cfg.path), "keep-serving"]) == 0
    assert (kept, configured) == ([cfg.path], [])


def test_the_keeper_says_what_it_does_in_the_container_log_only(cfg, computer, capsys):
    computer.runs = [1.0, 100.0]

    keeper.keep_serving(cfg, cfg.path, stop=computer.stop)

    said = capsys.readouterr().err
    assert "AutoSaga keeper: the program ended 1 seconds after it started; it is started again in 4 seconds" in said


def test_a_program_stopped_on_purpose_is_not_counted_as_failing(cfg, computer):
    # Restores one after the other: each stops the program a few seconds after it started,
    # cleanly. That is no failure, and the program comes back as fast each time.
    computer.runs = [(5.0, 0), (5.0, 0), (5.0, 0), (5.0, 0)]

    keeper.keep_serving(cfg, cfg.path, stop=computer.stop)

    assert computer.paused == [keeper.RESTART_PAUSE] * 3
