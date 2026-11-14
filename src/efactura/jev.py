"""OpenRouter's Decisions API, where the Jev model answers.

Jev is a decision model, not a chat model: it returns a typed answer with probabilities.
The endpoint is marked alpha by OpenRouter, so everything that depends on its shape is
kept in this file and in classify.py.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
TIMEOUT = 60.0
# A 402 with this marker means "too many requests in flight", not "out of credit".
IN_FLIGHT_BUDGET = "openrouter_in_flight_budget"
UNREADABLE_KEEP = 2000  # characters of a reply that was not JSON, kept for the log
# Key, credit, unknown model or route, timeout, rate limit: not about one invoice.
SERVICE_WIDE_STATUSES = (401, 402, 403, 404, 408, 429)


@dataclass(frozen=True)
class JevCall:
    """One request and what came back, whether it worked or not. Never holds the API key."""

    request: dict
    status: int | None  # None: OpenRouter was not reached
    response: dict | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    duration_ms: int
    error: str | None
    transient: bool  # worth trying again shortly

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def service_wide(self) -> bool:
        """Did it fail for a reason that would fail any invoice (no connection, key,
        credit, rate limit, server trouble), rather than because of this one request?"""
        if self.ok:
            return False
        return (
            self.status is None
            or self.status in SERVICE_WIDE_STATUSES
            or self.status >= 500
        )


def ask(http: httpx.Client, api_key: str, request: dict) -> JevCall:
    """Send one decisions request. Failures are returned, not raised, so each can be logged."""
    started = time.monotonic()

    def finished(status, response, error, transient=False) -> JevCall:
        usage = response.get("usage") if isinstance(response, dict) else None
        usage = usage if isinstance(usage, dict) else {}
        return JevCall(
            request=request,
            status=status,
            response=response,
            model=response.get("model") if isinstance(response, dict) else None,
            input_tokens=_whole(usage.get("input_tokens")),
            output_tokens=_whole(usage.get("output_tokens")),
            cost_usd=_number(usage.get("cost")),
            duration_ms=int((time.monotonic() - started) * 1000),
            error=error,
            transient=transient,
        )

    try:
        reply = http.post(
            DECISIONS_URL,
            json=request,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=TIMEOUT,
        )
    except httpx.RequestError as exc:
        return finished(None, None, f"Could not reach OpenRouter: {exc}", transient=True)

    try:
        body = reply.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        body = {"unreadable": reply.text[:UNREADABLE_KEEP]}
        if reply.status_code < 400:
            return finished(reply.status_code, body, "OpenRouter's reply could not be read.")

    if reply.status_code >= 400:
        return finished(
            reply.status_code, body, _refusal(reply.status_code, body),
            transient=_is_transient(reply.status_code, body),
        )
    return finished(reply.status_code, body, None)


def _refusal(status: int, body: dict) -> str:
    detail = body.get("error") if isinstance(body.get("error"), dict) else {}
    said = str(detail.get("message") or "").strip()
    if status in (401, 403):
        return (
            f"OpenRouter rejected the API key (HTTP {status}). "
            "Check [openrouter] api_key in config.toml."
        )
    if status == 402 and not _is_transient(status, body):
        return f"OpenRouter has no credit left for this key (HTTP 402). {said}".strip()
    return f"OpenRouter refused the request (HTTP {status}){': ' + said if said else '.'}"


def _is_transient(status: int, body: dict) -> bool:
    if status == 429 or status >= 500:
        return True
    if status == 402:
        detail = body.get("error") if isinstance(body.get("error"), dict) else {}
        metadata = detail.get("metadata") if isinstance(detail.get("metadata"), dict) else {}
        return metadata.get("limit_source") == IN_FLIGHT_BUDGET
    return False


def _whole(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
