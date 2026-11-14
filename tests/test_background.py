"""Running as an installed program: the first settings file, and start, open and stop."""

import json
import shutil
import socket
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from efactura import background, cli
from efactura.config import load_config

EXAMPLE = Path(__file__).resolve().parents[1] / "config.example.toml"
HEALTHY = {"ok": True, "service": "efactura", "version": "0.1.0"}


@pytest.fixture
def folder(tmp_path):
    """A freshly cloned project: the example settings, and no settings of its own yet."""
    shutil.copy(EXAMPLE, tmp_path / "config.example.toml")
    return tmp_path


@pytest.fixture
def settings(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[api]\nkey = "local-key"\nport = 9001\n', encoding="utf-8")
    return path


@pytest.fixture
def command(capsys):
    def invoke(config, *argv):
        code = cli.main(["--config", str(config), *argv])
        return code, json.loads(capsys.readouterr().out)

    return invoke


# --- the first settings file ---------------------------------------------------------------


def test_setup_writes_settings_the_program_can_start_with(folder, command, monkeypatch):
    monkeypatch.setattr(background, "port_is_free", lambda port: True)

    code, out = command(folder / "config.toml", "setup")

    cfg = load_config(folder / "config.toml")
    assert (code, out["ok"], out["created"]) == (0, True, True)
    assert (out["port"], out["page"]) == (8765, "http://autosaga.localhost:8765/ui/")
    assert out["config"] == str(folder / "config.toml")
    assert (cfg.api_port, len(cfg.api_key) >= 32) == (8765, True)
    assert cfg.api_key not in json.dumps(out)  # the key stays in the file


def test_setup_takes_the_next_free_port_when_the_usual_one_is_taken(folder, command, monkeypatch):
    asked = []
    monkeypatch.setattr(background, "port_is_free", lambda port: asked.append(port) or port == 8767)

    _, out = command(folder / "config.toml", "setup")

    assert asked == [8765, 8766, 8767]  # never port 80, which other programs want
    assert (out["port"], out["page"]) == (8767, "http://autosaga.localhost:8767/ui/")
    assert load_config(folder / "config.toml").api_port == 8767


def test_setup_lets_the_computer_choose_when_the_usual_ports_are_all_taken(folder, command, monkeypatch):
    monkeypatch.setattr(background, "port_is_free", lambda port: False)
    monkeypatch.setattr(background, "any_free_port", lambda: 51234)

    _, out = command(folder / "config.toml", "setup")

    assert (out["port"], load_config(folder / "config.toml").api_port) == (51234, 51234)


def test_setup_takes_the_port_it_is_given(folder, command, monkeypatch):
    monkeypatch.setattr(background, "port_is_free", lambda port: pytest.fail("not asked"))

    _, out = command(folder / "config.toml", "setup", "--port", "9100")

    assert (out["port"], load_config(folder / "config.toml").api_port) == (9100, 9100)


def test_setup_leaves_existing_settings_alone(folder, settings, command):
    before = settings.read_text(encoding="utf-8")

    code, out = command(settings, "setup")

    assert (code, out["created"], out["port"]) == (0, False, 9001)
    assert out["page"] == "http://autosaga.localhost:9001/ui/"
    assert settings.read_text(encoding="utf-8") == before


def test_each_setup_makes_a_key_of_its_own(folder, tmp_path, command, monkeypatch):
    monkeypatch.setattr(background, "port_is_free", lambda port: True)
    other = tmp_path / "other"
    other.mkdir()
    shutil.copy(EXAMPLE, other / "config.example.toml")

    command(folder / "config.toml", "setup")
    command(other / "config.toml", "setup")

    assert load_config(folder / "config.toml").api_key != load_config(other / "config.toml").api_key


def test_setup_needs_the_example_file_beside_it(tmp_path, command):
    code, out = command(tmp_path / "config.toml", "setup")

    assert (code, out["error"]["code"]) == (1, "config_error")
    assert not (tmp_path / "config.toml").exists()


def test_setup_leaves_nothing_behind_when_the_example_cannot_be_filled_in(folder, command, monkeypatch):
    monkeypatch.setattr(background, "port_is_free", lambda port: True)
    (folder / "config.example.toml").write_text('[api]\nkey = "already set"\n', encoding="utf-8")

    code, out = command(folder / "config.toml", "setup")

    assert (code, out["error"]["code"]) == (1, "config_error")
    assert not (folder / "config.toml").exists()


# --- start, open, stop: with stand-ins for the computer ---------------------------------------


@pytest.fixture
def computer(monkeypatch):
    """What answers on the port, and what the commands did to change that."""
    state = SimpleNamespace(
        answer=None, spawned=[], asked_to_stop=[], opened=[], waited=0.0, comes_up=True, goes_down=True
    )

    def spawn_server(config_path, output):
        state.spawned.append((config_path, output))
        if state.comes_up:
            state.answer = HEALTHY

    def ask_to_stop(port, key):
        state.asked_to_stop.append((port, key))
        if state.goes_down:
            state.answer = None

    def pause(seconds):
        state.waited += seconds

    monkeypatch.setattr(background, "probe", lambda port: state.answer)
    monkeypatch.setattr(background, "spawn_server", spawn_server)
    monkeypatch.setattr(background, "ask_to_stop", ask_to_stop)
    monkeypatch.setattr(background, "pause", pause)
    monkeypatch.setattr(background, "clock", lambda: state.waited)  # time passes only while waiting
    monkeypatch.setattr(cli, "open_browser", state.opened.append)
    return state


def test_start_runs_the_program_in_the_background(settings, command, computer):
    code, out = command(settings, "start")

    assert (code, out) == (0, {"ok": True, "started": True, "page": "http://autosaga.localhost:9001/ui/"})
    assert computer.spawned == [(settings, settings.parent / "data" / "server.log")]
    assert computer.opened == []


def test_start_does_nothing_when_it_is_already_running(settings, command, computer):
    computer.answer = HEALTHY

    _, out = command(settings, "start")

    assert (out["started"], computer.spawned) == (False, [])


def test_start_says_so_when_another_program_has_the_port(settings, command, computer):
    computer.answer = {"hello": "from something else"}

    code, out = command(settings, "start")

    assert (code, out["error"]["code"], computer.spawned) == (1, "config_error", [])
    assert "9001" in out["error"]["message"]


def test_start_gives_up_when_the_program_does_not_come_up(settings, command, computer):
    computer.comes_up = False

    code, out = command(settings, "start")

    assert (code, out["error"]["code"]) == (1, "internal_error")
    assert "server.log" in out["error"]["message"]
    assert computer.waited >= background.START_TIMEOUT


def test_start_needs_a_key_in_the_settings(tmp_path, command, computer):
    keyless = tmp_path / "config.toml"
    keyless.write_text("", encoding="utf-8")

    code, out = command(keyless, "start")

    assert (code, out["error"]["code"], computer.spawned) == (1, "config_error", [])


def test_open_starts_the_program_if_needed_and_shows_the_page(settings, command, computer):
    _, first = command(settings, "open")
    _, second = command(settings, "open")

    assert (first["started"], second["started"]) == (True, False)
    assert len(computer.spawned) == 1
    assert computer.opened == ["http://autosaga.localhost:9001/ui/"] * 2


def test_stop_asks_the_running_program_to_stop(settings, command, computer):
    computer.answer = HEALTHY

    code, out = command(settings, "stop")

    assert (code, out) == (0, {"ok": True, "stopped": True})
    assert computer.asked_to_stop == [(9001, "local-key")]


def test_stop_does_nothing_when_nothing_is_running(settings, command, computer):
    _, out = command(settings, "stop")

    assert (out, computer.asked_to_stop) == ({"ok": True, "stopped": False}, [])


def test_stop_says_so_when_the_program_keeps_running(settings, command, computer):
    computer.answer = HEALTHY
    computer.goes_down = False

    code, out = command(settings, "stop")

    assert (code, out["error"]["code"]) == (1, "internal_error")


def test_stop_leaves_another_program_on_the_port_alone(settings, command, computer):
    computer.answer = {"hello": "from something else"}

    code, out = command(settings, "stop")

    assert (code, out, computer.asked_to_stop) == (0, {"ok": True, "stopped": False}, [])


def test_a_failure_without_a_window_is_shown_in_a_box_and_logged(settings, computer, monkeypatch):
    shown = []
    monkeypatch.setattr(cli, "show_in_a_box", shown.append)
    monkeypatch.setattr(sys, "stdout", None)
    computer.answer = {"hello": "from something else"}  # the port is taken: start cannot work

    code = cli.main(["--config", str(settings), "open"])

    assert code == 1
    assert len(shown) == 1 and "9001" in shown[0] and shown[0].startswith("e-Factura pentru SAGA nu a putut porni.")
    assert "Port 9001" in (settings.parent / "data" / "efactura.log").read_text(encoding="utf-8")
    assert computer.opened == []


def test_a_failure_in_a_window_is_only_printed(settings, command, computer, monkeypatch):
    monkeypatch.setattr(cli, "show_in_a_box", lambda text: pytest.fail("there is a window to print in"))
    computer.answer = {"hello": "from something else"}

    code, out = command(settings, "open")

    assert (code, out["error"]["code"]) == (1, "config_error")


def test_a_command_started_without_a_window_has_nowhere_to_print(settings, computer, monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)  # as under pythonw.exe, which the shortcuts use

    assert cli.main(["--config", str(settings), "start"]) == 0
    assert len(computer.spawned) == 1


# --- telling a free port from a taken one -------------------------------------------------------


def free_port_here():
    with socket.socket() as chosen:
        chosen.bind(("127.0.0.1", 0))
        return chosen.getsockname()[1]


def test_a_port_nobody_listens_on_is_free(settings):
    port = free_port_here()

    assert background.probe(port) is None
    assert background.is_running(port) is False


@pytest.mark.parametrize("slow_refusal", [httpx.ConnectTimeout("timed out"), httpx.ConnectError("refused")])
def test_a_port_that_is_slow_to_refuse_is_still_free(monkeypatch, slow_refusal):
    # Windows takes about two seconds to refuse a connection to a port nobody listens on.
    # Read as "another program is there", that made every port look taken.
    def get(*args, **kwargs):
        raise slow_refusal

    monkeypatch.setattr(background.httpx, "get", get)

    assert background.probe(8080) is None
    assert background.is_running(8080) is False


def test_the_wait_for_a_refusal_is_shorter_than_the_wait_for_an_answer(monkeypatch):
    asked = {}

    def get(url, timeout, **kwargs):
        asked["timeout"] = timeout
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(background.httpx, "get", get)
    background.probe(8080)

    assert asked["timeout"].connect <= 1.0 < asked["timeout"].read


def test_something_that_accepts_but_never_answers_is_another_program(monkeypatch):
    def get(*args, **kwargs):
        raise httpx.ReadTimeout("no answer")

    monkeypatch.setattr(background.httpx, "get", get)

    assert background.probe(8080) == {}


def test_a_program_that_does_not_speak_like_ours_is_another_program(settings, command):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]

        def answer_once():
            connection, _ = listener.accept()
            with connection:
                connection.recv(1024)
                connection.sendall(b"220 some other service ready\r\n")

        threading.Thread(target=answer_once, daemon=True).start()

        assert background.probe(port) == {}


def test_waiting_gives_up_by_the_clock_not_by_counting_tries(monkeypatch):
    # A try can itself take seconds (see above), so tries are no measure of time.
    moment = {"now": 0.0}
    monkeypatch.setattr(background, "clock", lambda: moment["now"])
    monkeypatch.setattr(background, "pause", lambda seconds: None)

    def never(seconds_per_try=2.0):
        moment["now"] += seconds_per_try
        return False

    assert background._wait_until(never, timeout=30.0) is False
    assert moment["now"] <= 34.0


# --- for real: this computer, a free port -----------------------------------------------------


def test_the_program_really_starts_in_the_background_and_stops(tmp_path):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    path = tmp_path / "config.toml"
    path.write_text(f'[api]\nkey = "local-key"\nport = {port}\n', encoding="utf-8")
    cfg = load_config(path)

    try:
        started = background.start(cfg, path)
        again = background.start(cfg, path)
        answering = background.probe(port)
        stopped = background.stop(cfg)
    finally:
        if background.probe(port):
            background.ask_to_stop(port, cfg.api_key)

    assert (started["started"], again["started"]) == (True, False)
    assert answering["service"] == "efactura"
    assert stopped == {"ok": True, "stopped": True}
    assert background.probe(port) is None
    assert (tmp_path / "data" / "server.log").exists()
