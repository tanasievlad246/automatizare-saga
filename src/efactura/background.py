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
import subprocess
import sys
import time
from pathlib import Path

import httpx

from .config import DEFAULT_PORT, Config, load_config, page_address
from .errors import CONFIG_ERROR, INTERNAL_ERROR, EfacturaError

EXAMPLE_SETTINGS = "config.example.toml"
# On this port the address needs no port: http://autosaga.localhost
FRIENDLY_PORT = 80
SERVICE = "efactura"  # what GET /health answers with
SERVER_OUTPUT = "server.log"  # in the data folder: what the background program printed

START_TIMEOUT = 30.0  # seconds; a first start behind an antivirus scan can be slow
STOP_TIMEOUT = 15.0
POLL = 0.25
PROBE_TIMEOUT = 2.0

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
        port = FRIENDLY_PORT if port_is_free(FRIENDLY_PORT) else DEFAULT_PORT
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


def start(cfg: Config, config_path: Path) -> dict:
    """Run `efactura serve` as a process of its own, unless this program already answers."""
    cfg.require_api_key()
    port = cfg.api_port
    if is_running(port):
        return {"ok": True, "started": False, "page": page_address(port)}
    output = cfg.data_dir / SERVER_OUTPUT
    spawn_server(config_path, output)
    if not _wait_until(lambda: is_running(port), START_TIMEOUT):
        raise EfacturaError(
            INTERNAL_ERROR,
            f"The program did not start within {START_TIMEOUT:.0f} seconds. What it printed is in {output}.",
        )
    return {"ok": True, "started": True, "page": page_address(port)}


def stop(cfg: Config) -> dict:
    """Ask the running program to stop, and wait until it has."""
    port = cfg.api_port
    answer = probe(port)
    if not answer or answer.get("service") != SERVICE:
        return {"ok": True, "stopped": False}  # not running; whatever else is there is not ours to stop
    ask_to_stop(port, cfg.api_key)
    if not _wait_until(lambda: probe(port) is None, STOP_TIMEOUT):
        raise EfacturaError(
            INTERNAL_ERROR, f"The program is still running {STOP_TIMEOUT:.0f} seconds after being asked to stop."
        )
    return {"ok": True, "stopped": True}


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


def port_is_free(port: int) -> bool:
    """Can this program listen on the port? Tried the way the server will."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
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
        reply = httpx.get(f"http://127.0.0.1:{port}/health", timeout=PROBE_TIMEOUT, trust_env=False)
    except httpx.TimeoutException:
        return {}  # something holds the port without answering
    except httpx.TransportError:
        return None
    try:
        answer = reply.json()
    except ValueError:
        return {}
    return answer if isinstance(answer, dict) else {}


def ask_to_stop(port: int, key: str) -> None:
    try:
        httpx.post(
            f"http://127.0.0.1:{port}/shutdown", headers={"X-API-Key": key},
            timeout=PROBE_TIMEOUT, trust_env=False,
        )
    except httpx.TransportError:
        pass  # it may close the connection as it goes; stop() checks what happened


def spawn_server(config_path: Path, output: Path) -> None:
    """Start the server so that it outlives this command and shows no window.

    What it prints goes to `output`: without a window there is nowhere else, and uvicorn
    refuses to start with no output at all.
    """
    command = [_console_python(), "-m", "efactura", "--config", str(config_path), "serve"]
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


# --- small helpers ---------------------------------------------------------------------------


def _console_python() -> str:
    """The interpreter to run the server with. The shortcuts use pythonw.exe, which has no
    output of its own; the server gets python.exe from the same folder."""
    here = Path(sys.executable)
    if here.name.lower() == "pythonw.exe" and here.with_name("python.exe").exists():
        return str(here.with_name("python.exe"))
    return str(here)


def _wait_until(happened, timeout: float) -> bool:
    waited = 0.0
    while not happened():
        if waited >= timeout:
            return False
        pause(POLL)
        waited += POLL
    return True


def _settings_reply(config_path: Path, port: int, created: bool) -> dict:
    return {
        "ok": True,
        "created": created,
        "config": str(config_path),
        "port": port,
        "page": page_address(port),
    }
