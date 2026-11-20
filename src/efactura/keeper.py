"""Keeping the program running in a container, on the NAS: `efactura keep-serving`.

In a container the first process is the container: when it ends, everything in it is
stopped. The program cannot be that process, because a restore stops it and starts it again
from a process of its own, which would be killed halfway. So the keeper is the one that
stays: it runs `serve --network` as its child and, whenever that ends, waits until no
restore runs and nothing answers on the port, then starts it again. A program that keeps
failing at once is tried less and less often. Told to stop (the container is stopped), it
stops its child and ends.

The restore knows it runs under the keeper (EFACTURA_KEEPER=1, inherited) and leaves the
start to it. The keeper itself never opens the database: a restore replaces that file. The image puts tini before the keeper, to collect the processes left behind.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import background, backup
from .config import Config
from .errors import EfacturaError


RESTART_PAUSE = 2.0  # seconds before the program is started again
LONGEST_PAUSE = 60.0
QUICK_FAILURE = 30.0  # a run shorter than this failed at the start: the next pause doubles
LOOK_EVERY = 1.0  # seconds between two looks while a restore runs or another copy answers


def keep_serving(cfg: Config, config_path: Path, stop: threading.Event | None = None) -> None:
    """Run the program in server mode until told to stop. `stop` is for tests; the real run
    is stopped by SIGTERM or SIGINT."""
    current: dict = {"process": None}
    if stop is None:
        stop = threading.Event()

        def on_signal(signum, frame):
            stop.set()
            process = current["process"]
            if process is not None and process.poll() is None:
                process.terminate()  # the program finishes what it is answering, then ends

        signal.signal(signal.SIGTERM, on_signal)
        signal.signal(signal.SIGINT, on_signal)

    failing_pause = RESTART_PAUSE
    while not stop.is_set():
        # Looked at right before each start, after the pause too: a restore run by hand while
        # the program kept failing may have begun meanwhile.
        _wait_until_free(cfg, stop)
        if stop.is_set():
            break
        began = clock()
        process = current["process"] = spawn(config_path)
        if stop.is_set():  # told to stop while it was being started: the signal found no child
            process.terminate()
        code = process.wait()
        if stop.is_set():
            break
        ran_for = clock() - began
        # Ended cleanly (code 0): stopped on purpose, by a restore or `efactura stop`. Only a
        # failure soon after the start makes the next try wait longer.
        if code != 0 and ran_for < QUICK_FAILURE:
            failing_pause = min(failing_pause * 2, LONGEST_PAUSE)
            pause_for = failing_pause
            say(f"the program ended {ran_for:.0f} seconds after it started; it is started again in {pause_for:.0f} seconds")
        else:
            failing_pause = pause_for = RESTART_PAUSE
            say("the program ended; it is started again" if code == 0 else f"the program ended with code {code}; it is started again")
        pause(pause_for, stop)


def say(text: str) -> None:
    """To the container's log only, never through the program's logging: that writes to the
    database, which a restore replaces under an open connection (SIGBUS)."""
    print(f"AutoSaga keeper: {text}", file=sys.stderr, flush=True)


def _wait_until_free(cfg: Config, stop: threading.Event) -> None:
    """A restore that stopped the program puts the database back first; a copy started by
    hand answers until it is stopped. Neither is started over."""
    while not stop.is_set() and (restore_running(cfg) or answering(cfg.api_port)):
        pause(LOOK_EVERY, stop)


# --- touching the computer: replaced in tests ------------------------------------------------


def spawn(config_path: Path) -> subprocess.Popen:
    command = [sys.executable, "-m", "efactura", "--config", str(config_path), "serve", "--network"]
    return subprocess.Popen(command, env={**os.environ, background.KEEPER_VARIABLE: "1"})


def restore_running(cfg: Config) -> bool:
    try:
        with backup.no_restore_running(cfg):
            return False
    except EfacturaError:
        return True


def answering(port: int) -> bool:
    return background.probe(port) is not None


def pause(seconds: float, stop: threading.Event) -> None:
    """A wait the stop ends at once: `docker stop` must not wait out a long pause and be
    answered by SIGKILL."""
    stop.wait(seconds)


def clock() -> float:
    return time.monotonic()
