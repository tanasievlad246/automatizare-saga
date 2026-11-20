"""The two e-Factura calls this tool makes: list messages and download one.

ANAF reports most problems as HTTP 200 with an "eroare" text, so replies are
inspected rather than trusted by status code.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from typing import Callable

import httpx

from . import journal, technical
from .config import Config
from .errors import (
    ANAF_ERROR,
    ANAF_LIMIT_REACHED,
    INVALID_CUI,
    LOGIN_NEEDED,
    NETWORK_ERROR,
    NO_SPV_RIGHTS,
    EfacturaError,
    said_by,
)

log = logging.getLogger(__name__)

# File-name part and --type value for each ANAF message type ("tip").
TYPE_PREFIXES = {
    "primita": "FACTURA PRIMITA",
    "trimisa": "FACTURA TRIMISA",
    "erori": "ERORI FACTURA",
    "mesaj": "MESAJ",
}
OTHER_TYPE = "alt"

_CUI_KEY = "753217532"
_CNP_KEY = "279146358279"
# ANAF's answer for a window with nothing in it. It arrives as an "eroare" but is not one.
_NO_MESSAGES = "Nu exista mesaje"
# ANAF's wording when the certificate holder has no SPV rights for the company.
_NO_SPV_RIGHTS = "Nu aveti drept"
# ANAF's wording when a daily call limit is used up ("S-au facut deja 1000 ...").
_LIMIT_REACHED = re.compile(r"S-au facut deja \d+", re.IGNORECASE)
# HTTP 429: ANAF limits every call, not only this one. A download stops on it, where a limit
# on one message ("10 descarcari de mesaj") only fails that message.
LIMITING_EVERY_CALL = "ANAF is limiting calls; try again later."
# Far more pages than 60 days of messages can fill: stops a list that never ends.
_MAX_PAGES = 1000


def normalize_cui(value: str) -> str:
    """Digits only, without 'RO'. Accepts a company CUI or a 13-digit personal code."""
    digits = "".join(str(value).split()).upper().removeprefix("RO")
    if not digits.isdigit():
        raise EfacturaError(INVALID_CUI, f"{value!r} is not a CUI: only digits are allowed.")
    if len(digits) == 13:
        expected = sum(int(d) * int(k) for d, k in zip(digits, _CNP_KEY)) % 11
        expected = 1 if expected == 10 else expected
    elif 2 <= len(digits) <= 10:
        body = digits[:-1].zfill(len(_CUI_KEY))
        expected = sum(int(d) * int(k) for d, k in zip(body, _CUI_KEY)) * 10 % 11 % 10
    else:
        raise EfacturaError(INVALID_CUI, f"{value!r} is not a CUI: wrong number of digits.")
    if expected != int(digits[-1]):
        raise EfacturaError(
            INVALID_CUI, f"{value!r} is not a valid CUI: the check digit does not match (typo?)."
        )
    return digits


def type_slug(message_type: str) -> str:
    upper = (message_type or "").upper()
    for slug, prefix in TYPE_PREFIXES.items():
        if upper.startswith(prefix):
            return slug
    return OTHER_TYPE


def parse_created_at(value: str) -> str | None:
    """ANAF's 'YYYYMMDDHHmm' (Romanian local time) as ISO 'YYYY-MM-DDTHH:MM'."""
    try:
        return datetime.strptime(value, "%Y%m%d%H%M").strftime("%Y-%m-%dT%H:%M")
    except (TypeError, ValueError):
        return None


class AnafService:
    """ANAF's e-Factura API for one saved login: list a company's messages, download one.

    `get_token(force_refresh)` returns the access token, renewed first when asked to.
    """

    def __init__(self, cfg: Config, http: httpx.Client, get_token: Callable[[bool], str]):
        self._base = cfg.api_base
        self._http = http
        self._get_token = get_token

    def list_messages(self, cui: str, start: datetime, end: datetime) -> list[dict]:
        """ANAF's list entry for every message of `cui` created between `start` and `end`."""
        window = {"startTime": _millis(start), "endTime": _millis(end), "cif": cui}
        messages: dict[str, dict] = {}  # by id, so a message repeated across pages counts once
        for page in range(1, _MAX_PAGES + 1):
            payload = _json(self._get("listaMesajePaginatieFactura", {**window, "pagina": str(page)}))
            if str(payload.get("eroare", "")).startswith(_NO_MESSAGES):
                log.debug("ANAF has no messages for %s from %s to %s", cui, start.isoformat(), end.isoformat())
                break
            _raise_if_refused(payload)
            log.debug(
                "Page %s of %s of the messages of %s: %s message(s)", page,
                payload.get("numar_total_pagini", "?"), cui, len(payload.get("mesaje") or []),
            )
            for entry in payload.get("mesaje") or []:
                message_id = str(entry.get("id") or "")
                if message_id:
                    messages.setdefault(message_id, {**entry, "id": message_id})
                else:
                    log.warning("ANAF listed a message without an id: %r", entry)
            if page >= _int(payload.get("numar_total_pagini"), default=1):
                break
        else:  # no break: ANAF kept announcing more pages
            raise EfacturaError(ANAF_ERROR, "ANAF's message list did not end.")
        return list(messages.values())

    def download(self, message_id: str) -> bytes:
        """The ZIP ANAF keeps for a message: its XML and ANAF's signature."""
        response = self._get("descarcare", {"id": message_id})
        if response.content.startswith(b"PK"):  # the first two bytes of every ZIP file
            return response.content
        # Anything else is ANAF's reason for not handing the file over.
        _raise_if_refused(_json(response))
        raise EfacturaError(ANAF_ERROR, f"ANAF's download for id={message_id} was not a ZIP file.")

    def _get(self, endpoint: str, params: dict) -> httpx.Response:
        """A GET with the saved login. A rejected token is renewed and the call repeated once."""
        response = self._send(endpoint, params, renew_token=False)
        if response.status_code == 401:
            log.debug("ANAF refused the access token for %s; it is renewed and the call made again", endpoint)
            response = self._send(endpoint, params, renew_token=True)
        if response.status_code == 401:
            raise EfacturaError(
                LOGIN_NEEDED, "ANAF rejected the saved login. Plug in the USB token and log in again."
            )
        if response.status_code == 429:
            raise EfacturaError(ANAF_LIMIT_REACHED, LIMITING_EVERY_CALL)
        if response.status_code >= 400:
            raise EfacturaError(ANAF_ERROR, f"ANAF refused the request (HTTP {response.status_code}).")
        return response

    def _send(self, endpoint: str, params: dict, renew_token: bool) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._get_token(renew_token)}"}
        started = time.monotonic()
        try:
            response = self._http.get(f"{self._base}/{endpoint}", params=params, headers=headers)
        except httpx.RequestError as exc:
            technical.unanswered(exc, _elapsed_ms(started))
            journal.record(
                "anaf", "anaf.unreachable", f"ANAF could not be reached for {endpoint}.", level="warning",
                endpoint=endpoint, error=type(exc).__name__, duration_ms=_elapsed_ms(started),
                **_what_was_asked(params),
            )
            raise EfacturaError(NETWORK_ERROR, f"Could not reach ANAF: {said_by(exc)}") from None
        # The address and what was asked for, never the login sent with it.
        journal.record(
            "anaf", "anaf.call", f"ANAF answered {response.status_code} for {endpoint}.", level="detail",
            endpoint=endpoint, status=response.status_code, duration_ms=_elapsed_ms(started),
            **_what_was_asked(params),
        )
        return response


def _what_was_asked(params: dict) -> dict:
    """The page of the list, or the message downloaded, for the journal line of a call."""
    asked = {}
    if "pagina" in params:
        asked["page"] = _int(params["pagina"], default=None)
    if "id" in params:
        asked["id"] = str(params["id"])
    return asked


def _elapsed_ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)


def _millis(moment: datetime) -> str:
    """ANAF takes times as milliseconds since 1970."""
    return str(int(moment.timestamp() * 1000))


def _json(response: httpx.Response) -> dict:
    try:
        payload = json.loads(response.content)
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        raise EfacturaError(ANAF_ERROR, "ANAF sent a reply that could not be read.")
    return payload


def _int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _raise_if_refused(payload: dict) -> None:
    """ANAF reports a refusal as an ordinary reply (HTTP 200) carrying an "eroare" text."""
    if "eroare" not in payload:
        return
    text = str(payload["eroare"])
    if _NO_SPV_RIGHTS in text:
        code = NO_SPV_RIGHTS
    elif _LIMIT_REACHED.search(text):
        code = ANAF_LIMIT_REACHED
    else:
        code = ANAF_ERROR
    raise EfacturaError(code, f"ANAF: {text}")
