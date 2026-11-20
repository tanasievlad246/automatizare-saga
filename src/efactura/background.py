"""Running as an installed program on the accountant's PC.

The installer and the two shortcuts it makes call these, through the commands of the
same names:

    setup   write the first config.toml, once
    start   run the program in the background, without a window, unless it already runs
    open    start, then show the page in the browser
    stop    ask the running program to stop (before an update replaces its files)
"""

from __future__ import annotations

import os
import re
import secrets
import socket
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

from .config import DEFAULT_PORT, Config, load_config, page_address
from .errors import CONFIG_ERROR, INTERNAL_ERROR, EfacturaError

EXAMPLE_SETTINGS = "config.example.toml"
# setup takes the usual port, or the first free one of this many after it. Port 80 is never
# taken: other programs on the PC expect to find it free.
PORTS_TRIED = 20
SERVICE = "efactura"  # what GET /health answers with
SERVER_OUTPUT = "server.log"  # in the data folder: what the background program printed
KEEPER_VARIABLE = "EFACTURA_KEEPER"  # set by `efactura keep-serving` for the program it runs

START_TIMEOUT = 30.0  # seconds; a first start behind an antivirus scan can be slow
STOP_TIMEOUT = 15.0
POLL = 0.25
# A program listening on this computer accepts a connection at once, so a short wait is
# enough to know that nothing listens. The answer itself may take longer while it starts.
CONNECT_TIMEOUT = 1.0
ANSWER_TIMEOUT = 5.0

# The two lines of the example that setup fills in.
_EMPTY_KEY = re.compile(r'(?m)^key = ""[ \t]*$')
_PORT = re.compile(r"(?m)^port = \d+[ \t]*$")


def first_settings(config_path: Path, port: int | None = None) -> dict:
    """Write config.toml from the example beside it, with a key of its own for the local
    API and the port to listen on. Existing settings are left exactly as they are."""
    if config_path.exists():
        port = load_config(config_path).api_port
        return _settings_reply(config_path, port, created=False)

    example = config_path.parent / EXAMPLE_SETTINGS
    if not example.is_file():
        raise EfacturaError(
            CONFIG_ERROR, f"{EXAMPLE_SETTINGS} was not found beside {config_path}; nothing to start from."
        )
    if port is None:
        port = free_port()
    key = secrets.token_urlsafe(32)
    text = _EMPTY_KEY.sub(f'key = "{key}"', example.read_text(encoding="utf-8"), count=1)
    text = _PORT.sub(f"port = {port}", text, count=1)
    config_path.write_text(text, encoding="utf-8")

    written = load_config(config_path)
    if (written.api_key, written.api_port) != (key, port):
        # The example changed shape. Half-filled settings would start a program nobody can use.
        config_path.unlink()
        raise EfacturaError(
            CONFIG_ERROR, f"{EXAMPLE_SETTINGS} no longer has the key and port lines setup fills in."
        )
    return _settings_reply(config_path, port, created=True)


def start(cfg: Config, config_path: Path, network: bool = False) -> dict:
    """Run `efactura serve` as a process of its own, unless this program already answers.
    `network`: in server mode, as it was before a restore or an update stopped it."""
    cfg.require_api_key()
    port = cfg.api_port
    if is_running(port):
        return {"ok": True, "started": False, "page": page_address(port)}
    output = cfg.data_dir / SERVER_OUTPUT
    spawn_server(config_path, output, network)
    if not _wait_until(lambda: is_running(port), START_TIMEOUT):
        raise EfacturaError(
            INTERNAL_ERROR,
            f"The program did not start within {START_TIMEOUT:.0f} seconds. What it printed is in {output}.",
        )
    return {"ok": True, "started": True, "page": page_address(port)}


def stop(cfg: Config) -> dict:
    """Ask the running program to stop, and wait until it has. `network` says whether it ran in
    server mode, so whoever stopped it can start it again the same way."""
    port = cfg.api_port
    answer = probe(port)
    if not answer or answer.get("service") != SERVICE:
        return {"ok": True, "stopped": False}  # not running; whatever else is there is not ours to stop
    ask_to_stop(port, cfg.api_key)
    if not _wait_until(lambda: probe(port) is None, STOP_TIMEOUT):
        raise EfacturaError(
            INTERNAL_ERROR, f"The program is still running {STOP_TIMEOUT:.0f} seconds after being asked to stop."
        )
    return {"ok": True, "stopped": True, "network": answer.get("mode") == "network"}


def start_again(cfg: Config, stopped: dict) -> bool:
    """After a restore or an update: start the program again in the mode it ran in. Under the
    keeper (a container) it is left to the keeper, which starts it once the work is done."""
    if not stopped.get("stopped"):
        return False
    if under_the_keeper():
        return False
    return start(cfg, cfg.path, network=stopped.get("network", False))["ok"]


def under_the_keeper() -> bool:
    """Was this process started by `efactura keep-serving`, which starts the program again by itself?"""
    return os.environ.get(KEEPER_VARIABLE) == "1"


def keep_house(cfg: Config, now=None) -> None:
    """What the running program does every quarter of an hour: the daily backup when it is
    due, and the clean-up of the journal and its technical side. Never raises: it runs where
    nobody is watching."""
    from . import backup, journal, technical  # here, because both of them import this module

    with journal.trace(fresh=True):  # each round is its own story, not part of the program's start
        backup.run_if_due(cfg, now)
        for prune in (journal.prune, technical.prune):
            try:
                prune(cfg.db_path, now or datetime.now().astimezone())
            except sqlite3.Error:
                pass


def is_running(port: int) -> bool:
    """Does this program answer on the port? Something else answering there is an error:
    starting beside it would fail, and its page is not ours to open."""
    answer = probe(port)
    if answer is None:
        return False
    if answer.get("service") != SERVICE:
        raise EfacturaError(
            CONFIG_ERROR,
            f"Port {port} on this computer is used by another program. "
            "Set another [api] port in config.toml.",
        )
    return True


# --- touching the computer: replaced in tests ------------------------------------------------


def free_port() -> int:
    """The usual port when nothing listens on it, else the next free one after it."""
    for port in range(DEFAULT_PORT, DEFAULT_PORT + PORTS_TRIED):
        if port_is_free(port):
            return port
    return any_free_port()


def any_free_port() -> int:
    """A port the computer itself picks as free."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def port_is_free(port: int) -> bool:
    """Can this program listen on the port?"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        # Windows lets a second program bind a port that another holds on every address,
        # unless the bind asks to be the only one. Without this, a taken port looks free.
        only_one = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
        if only_one is not None:
            listener.setsockopt(socket.SOL_SOCKET, only_one, 1)
        try:
            listener.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def probe(port: int) -> dict | None:
    """What answers GET /health on the port: None when nothing listens there, the reply
    when this program does, and an empty answer when something else does."""
    try:
        # trust_env off: a proxy set on the PC must never be asked for this computer itself.
        reply = httpx.get(f"http://127.0.0.1:{port}/health", timeout=_timeouts(), trust_env=False)
    except (httpx.ConnectError, httpx.ConnectTimeout):
        # Nothing listens there. Windows takes a couple of seconds to refuse such a
        # connection, so running out of time while connecting means the same as a refusal.
        return None
    except httpx.TransportError:
        return {}  # something took the connection, then did not answer as a web server
    try:
        answer = reply.json()
    except ValueError:
        return {}
    return answer if isinstance(answer, dict) else {}


def ask_to_stop(port: int, key: str) -> None:
    try:
        httpx.post(
            f"http://127.0.0.1:{port}/shutdown", headers={"X-API-Key": key},
            timeout=_timeouts(), trust_env=False,
        )
    except httpx.TransportError:
        pass  # it may close the connection as it goes; stop() checks what happened


def spawn_server(config_path: Path, output: Path, network: bool = False) -> None:
    spawn_command(config_path, output, "serve", *(["--network"] if network else []))


def spawn_command(config_path: Path, output: Path, *command: str) -> None:
    """Start one of this program's commands so that it outlives this one and shows no window.

    What it prints goes to `output`: without a window there is nowhere else, and uvicorn
    refuses to start with no output at all.
    """
    command = [_console_python(), "-m", "efactura", "--config", str(config_path), *command]
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "ab") as sink:
        streams = {"stdin": subprocess.DEVNULL, "stdout": sink, "stderr": sink, "cwd": config_path.parent}
        if os.name != "nt":
            subprocess.Popen(command, start_new_session=True, **streams)
            return
        no_window = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            # Out of any job the starting program belongs to, which would end it with that program.
            subprocess.Popen(command, creationflags=no_window | subprocess.CREATE_BREAKAWAY_FROM_JOB, **streams)
        except OSError:  # the job does not allow leaving it
            subprocess.Popen(command, creationflags=no_window, **streams)


def pause(seconds: float) -> None:
    time.sleep(seconds)


def clock() -> float:
    """Seconds that only ever go forward, for measuring a wait."""
    return time.monotonic()


# --- small helpers ---------------------------------------------------------------------------


def _console_python() -> str:
    """The interpreter to run the server with. The shortcuts use pythonw.exe, which has no
    output of its own; the server gets python.exe from the same folder."""
    here = Path(sys.executable)
    if here.name.lower() == "pythonw.exe" and here.with_name("python.exe").exists():
        return str(here.with_name("python.exe"))
    return str(here)


def _timeouts() -> httpx.Timeout:
    return httpx.Timeout(ANSWER_TIMEOUT, connect=CONNECT_TIMEOUT)


def _wait_until(happened, timeout: float) -> bool:
    """By the clock: asking can itself take seconds, so counting tries measures nothing."""
    deadline = clock() + timeout
    while not happened():
        if clock() >= deadline:
            return False
        pause(POLL)
    return True


def _settings_reply(config_path: Path, port: int, created: bool) -> dict:
    return {
        "ok": True,
        "created": created,
        "config": str(config_path),
        "port": port,
        "page": page_address(port),
    }
