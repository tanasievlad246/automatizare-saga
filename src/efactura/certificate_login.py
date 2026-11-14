"""Connecting to ANAF with the certificate Windows holds, without the browser.

A PowerShell helper (certificate_login.ps1) asks Windows for the certificate and ANAF for the
login. The certificate's key stays in Windows or on the token, and the PIN is typed into the
token's own window: this program sees neither. The helper prints the address ANAF ended on;
it holds a one-time code, so it is handed back to the caller and never written anywhere.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future
from pathlib import Path

from . import journal
from .config import Config
from .errors import ANAF_ERROR, CONFIG_ERROR, LOGIN_CANCELLED, EfacturaError, said_by

HELPER = Path(__file__).with_name("certificate_login.ps1")
TIMEOUT = 300  # seconds allowed for choosing the certificate and typing the PIN
STDERR_SHOWN = 300  # characters of the helper's own complaint that are kept

_guard = threading.Lock()
_running: Future | None = None  # the try Windows is being asked for now, shared by late-comers


def one_at_a_time(work: Callable[[], dict]) -> dict:
    """Runs `work`, or, when it is already running for another request, waits for that run
    and hands back its answer (or raises its error). Pressing the button again while
    Windows' window is still open, perhaps hidden behind the browser, must not open a
    second one."""
    global _running
    with _guard:
        mine = _running is None
        if mine:
            _running = Future()
        shared = _running
    if not mine:
        return shared.result()
    try:
        answer = work()
    except BaseException as exc:
        shared.set_exception(exc)
        raise
    else:
        shared.set_result(answer)
        return answer
    finally:
        with _guard:
            _running = None


def _powershell() -> str | None:
    """Where Windows PowerShell is. Replaced in tests."""
    return shutil.which("powershell.exe")


def available(cfg: Config, system: str | None = None) -> bool:
    """Is the certificate way offered here? The system is a parameter because replacing
    `os.name` in a test breaks pathlib on a Mac."""
    system = os.name if system is None else system
    return system == "nt" and not cfg.demo and _powershell() is not None


def ask_windows(authorize_url: str) -> str:
    """Runs the helper and returns the address ANAF ended on (a refusal included)."""
    began = time.monotonic()
    printed = _run_helper(authorize_url)
    location = printed.get("location")
    if printed.get("cancelled"):
        outcome = "cancelled"
    elif isinstance(location, str) and location:
        outcome = "answered"
    else:
        outcome = "failed"
    # How long Windows took and how many tries ANAF needed is what explains a refusal later.
    # The names avoid the words the journal hides (key, token, pin); no address, no code.
    journal.record(
        "anaf", "anaf.certificate_asked", "Windows was asked for the certificate.",
        duration_ms=round((time.monotonic() - began) * 1000),
        outcome=outcome, tries=printed.get("tries"), opened_first=printed.get("opened"),
    )
    if outcome == "cancelled":
        raise EfacturaError(LOGIN_CANCELLED, "No certificate was chosen.")
    if outcome == "failed":
        said = printed.get("error")
        # ANAF's two answers to settings that are wrong: waiting does not help, the person
        # has to correct a setting, and the window says so.
        if isinstance(said, str) and "invalid_client" in said:
            raise EfacturaError(CONFIG_ERROR, f"ANAF does not know the Client ID: {said}")
        if isinstance(said, str) and "invalid_request" in said and "Redirect-URI" in said:
            raise EfacturaError(CONFIG_ERROR, f"ANAF does not accept the callback address: {said}")
        raise EfacturaError(
            ANAF_ERROR,
            f"Windows could not log in to ANAF with the certificate: {said}"
            if said else "The certificate helper printed nothing usable.",
        )
    return location


def _run_helper(authorize_url: str) -> dict:
    """The one place a process is started. Started as the owner started it by hand, with the
    address in the environment and not on the command line."""
    powershell = _powershell()
    if powershell is None:
        return {"error": "Windows PowerShell was not found."}
    try:
        done = subprocess.run(
            [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HELPER)],
            env={**os.environ, "AUTOSAGA_AUTHORIZE_URL": authorize_url},
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=TIMEOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return {"cancelled": True}  # subprocess.run has ended the helper itself
    except OSError as exc:
        return {"error": said_by(exc)}
    lines = _lines(done.stdout)
    try:
        answer = json.loads(lines[-1]) if lines else None
    except ValueError:
        answer = None
    if isinstance(answer, dict):
        return answer
    # Nothing readable: a script Windows refuses to run says why only here, on standard error.
    said = f"The helper ended with code {done.returncode}"
    complaint = _lines(done.stderr)
    return {"error": f"{said}: {complaint[0][:STDERR_SHOWN]}" if complaint else said}


def _lines(output: bytes) -> list[str]:
    return [line.strip() for line in output.decode("utf-8", errors="replace").splitlines() if line.strip()]
