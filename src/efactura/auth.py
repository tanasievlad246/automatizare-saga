"""ANAF OAuth: the saved login, when it must be renewed, and the calls that renew it.

The certificate on the USB token is used only by the browser, at the authorize step.
Nothing here needs the token, the PIN or the private key.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from .config import Config
from .errors import (
    ANAF_ERROR,
    ANAF_LIMIT_REACHED,
    CONFIG_ERROR,
    INVALID_INPUT,
    LOGIN_CODE_EXPIRED,
    LOGIN_NEEDED,
    NETWORK_ERROR,
    EfacturaError,
)

log = logging.getLogger(__name__)

AUTHORIZE_URL = "https://logincert.anaf.ro/anaf-oauth2/v1/authorize"
TOKEN_URL = "https://logincert.anaf.ro/anaf-oauth2/v1/token"

# ANAF's documented lifetimes, used when the reply does not state them.
ACCESS_LIFETIME = timedelta(days=90)
REFRESH_LIFETIME = timedelta(days=365)
# Renew a little early so a token cannot expire in the middle of a run.
EXPIRY_MARGIN = timedelta(minutes=5)
# How long to keep trying when the login file is briefly in use (about 2 seconds).
FILE_ATTEMPTS = 10
FILE_RETRY_DELAY = 0.2
# The only replies that mean "this code or refresh token is not accepted".
REJECTED_STATUSES = (400, 401, 403)

VALID = "valid"
NEEDS_REFRESH = "needs_refresh"
NEEDS_LOGIN = "needs_login"

_BARE_CODE = re.compile(r"^[A-Za-z0-9._~-]+$")


@dataclass(frozen=True)
class Tokens:
    access_token: str
    refresh_token: str | None
    access_expires_at: datetime
    refresh_expires_at: datetime | None
    obtained_at: datetime


def token_state(tokens: Tokens | None, now: datetime) -> str:
    if tokens is None:
        return NEEDS_LOGIN
    if tokens.access_expires_at - now > EXPIRY_MARGIN:
        return VALID
    if tokens.refresh_token and tokens.refresh_expires_at and tokens.refresh_expires_at > now:
        return NEEDS_REFRESH
    return NEEDS_LOGIN


# --- saved login ----------------------------------------------------------------


def load_tokens(path: Path) -> Tokens | None:
    path = Path(path)
    saved = _read_tokens(path)
    # A save whose final swap did not complete leaves the newer pair in the pending file.
    pending_path = _pending(path)
    pending = _read_tokens(pending_path)
    if pending and (saved is None or pending.obtained_at > saved.obtained_at):
        try:
            os.replace(pending_path, path)
        except OSError:
            pass
        return pending
    return saved


def _pending(path: Path) -> Path:
    return path.with_name(path.name + ".tmp")


def _pause(seconds: float) -> None:
    time.sleep(seconds)


def _read_tokens(path: Path) -> Tokens | None:
    for attempt in range(FILE_ATTEMPTS):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            refresh_expiry = raw.get("refresh_expires_at")
            return Tokens(
                access_token=raw["access_token"],
                refresh_token=raw.get("refresh_token"),
                access_expires_at=datetime.fromisoformat(raw["access_expires_at"]),
                refresh_expires_at=(
                    datetime.fromisoformat(refresh_expiry) if refresh_expiry else None
                ),
                obtained_at=datetime.fromisoformat(raw["obtained_at"]),
            )
        except FileNotFoundError:
            return None
        except PermissionError:
            # Windows: the file is being swapped by another process. Try again shortly.
            if attempt == FILE_ATTEMPTS - 1:
                raise
            _pause(FILE_RETRY_DELAY)
        except (ValueError, KeyError, TypeError, AttributeError):
            log.warning("Saved login at %s is unreadable.", path)
            return None


def save_tokens(path: Path, tokens: Tokens) -> None:
    """Write to a temporary file, then swap it in: an interrupted save cannot lose the pair.

    On Windows the swap fails while another program has the file open (a reader, an
    antivirus scan). It is retried; if it still fails the new pair stays in the pending
    file, where load_tokens finds it. ANAF has already retired the old refresh token by
    then, so the new one must never be dropped.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "access_expires_at": tokens.access_expires_at.isoformat(),
        "refresh_expires_at": (
            tokens.refresh_expires_at.isoformat() if tokens.refresh_expires_at else None
        ),
        "obtained_at": tokens.obtained_at.isoformat(),
    }
    temporary = _pending(path)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    for _ in range(FILE_ATTEMPTS):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            _pause(FILE_RETRY_DELAY)
    log.warning(
        "%s is in use; the renewed login is kept in %s and is picked up on the next read.",
        path, temporary,
    )


# --- the browser step -----------------------------------------------------------


def authorize_url(cfg: Config) -> str:
    cfg.require_oauth()
    query = urlencode(
        {
            "response_type": "code",
            "client_id": cfg.client_id,
            "redirect_uri": cfg.redirect_uri,
            "token_content_type": "jwt",
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def code_from_redirect(address: str) -> str:
    """The one-time code from the address the browser was sent to after the login."""
    cleaned = address.strip().strip("\"'").strip()
    if not cleaned:
        raise EfacturaError(INVALID_INPUT, "No address was given.")
    if _BARE_CODE.match(cleaned):
        return cleaned

    parts = urlsplit(cleaned)
    params = parse_qs(parts.query) or parse_qs(parts.fragment)
    if "error" in params:
        description = params.get("error_description", params["error"])[0]
        raise EfacturaError(ANAF_ERROR, f"ANAF refused the login: {description}")
    if "code" not in params:
        raise EfacturaError(
            INVALID_INPUT,
            "That address has no login code. After the certificate and PIN step, copy the "
            "whole address from the browser's address bar; it contains '?code='.",
        )
    return params["code"][0]


# --- token calls ----------------------------------------------------------------


def exchange_code(cfg: Config, http: httpx.Client, code: str, now: datetime) -> Tokens:
    cfg.require_oauth()
    payload = _token_call(
        cfg,
        http,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": cfg.redirect_uri,
            "token_content_type": "jwt",
        },
        rejected=EfacturaError(
            LOGIN_CODE_EXPIRED,
            "ANAF did not accept the login code. It is valid for about a minute and only "
            "once: start the login again and hand the address back straight away.",
        ),
    )
    return _tokens_from_reply(payload, now, previous=None)


def refresh_tokens(cfg: Config, http: httpx.Client, tokens: Tokens, now: datetime) -> Tokens:
    cfg.require_oauth()
    payload = _token_call(
        cfg,
        http,
        {
            "grant_type": "refresh_token",
            "refresh_token": tokens.refresh_token or "",
            "token_content_type": "jwt",
        },
        rejected=EfacturaError(
            LOGIN_NEEDED,
            "ANAF did not renew the saved login. Plug in the USB token and log in again.",
        ),
    )
    return _tokens_from_reply(payload, now, previous=tokens)


def _token_call(cfg: Config, http: httpx.Client, form: dict, rejected: EfacturaError) -> dict:
    try:
        response = http.post(TOKEN_URL, data=form, auth=(cfg.client_id, cfg.client_secret))
    except httpx.RequestError as exc:
        raise EfacturaError(NETWORK_ERROR, f"Could not reach ANAF's login service: {exc}") from None

    try:
        payload = response.json()
    except ValueError:
        payload = None

    if response.status_code >= 500:
        raise EfacturaError(
            ANAF_ERROR, f"ANAF's login service failed (HTTP {response.status_code})."
        )
    if response.status_code == 429:
        raise EfacturaError(
            ANAF_LIMIT_REACHED, "ANAF's login service is limiting calls; try again later."
        )
    if response.status_code >= 400:
        if isinstance(payload, dict) and payload.get("error") == "invalid_client":
            raise EfacturaError(
                CONFIG_ERROR,
                "ANAF rejected the client ID or client secret. Check [anaf] in config.toml.",
            )
        if response.status_code in REJECTED_STATUSES:
            raise rejected
        raise EfacturaError(
            ANAF_ERROR, f"ANAF's login service refused the request (HTTP {response.status_code})."
        )
    if not isinstance(payload, dict) or not payload.get("access_token"):
        raise EfacturaError(ANAF_ERROR, "ANAF's login service replied without an access token.")
    return payload


def _tokens_from_reply(payload: dict, now: datetime, previous: Tokens | None) -> Tokens:
    access_token = payload["access_token"]
    new_refresh = payload.get("refresh_token")
    if new_refresh:
        refresh_token, refresh_expires_at = new_refresh, now + REFRESH_LIFETIME
    elif previous is not None:
        refresh_token, refresh_expires_at = previous.refresh_token, previous.refresh_expires_at
    else:
        refresh_token, refresh_expires_at = None, None
    return Tokens(
        access_token=access_token,
        refresh_token=refresh_token,
        access_expires_at=_access_expiry(payload, access_token, now),
        refresh_expires_at=refresh_expires_at,
        obtained_at=now,
    )


def _access_expiry(payload: dict, access_token: str, now: datetime) -> datetime:
    try:
        return now + timedelta(seconds=int(payload["expires_in"]))
    except (KeyError, TypeError, ValueError):
        pass
    try:
        body = access_token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        return datetime.fromtimestamp(int(claims["exp"]), tz=now.tzinfo)
    except (IndexError, KeyError, TypeError, ValueError):
        return now + ACCESS_LIFETIME
