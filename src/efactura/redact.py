"""Hiding secrets from anything the program writes down: the journal and its technical side.

Three nets, one behind the other:

    By name. A header, an address parameter, a form field or a JSON key whose name says it
    holds a secret (key, token, secret, password, PIN, cookie...) loses its value.

    By shape. Wherever it stands, a "Bearer ..." or "Basic ..." login, a JWT, an OpenRouter key,
    or a "token=..." pair loses its value.

    By value. The keys and tokens the program itself holds are remembered when it reads or
    receives them, and never written, whatever surrounds them.

What is hidden becomes HIDDEN. Nothing here raises on odd input: it is used where a failure
must never stop the work.
"""

from __future__ import annotations

import json
import re
import threading
from urllib.parse import parse_qsl, unquote_plus, urlsplit, urlunsplit

HIDDEN = "[hidden]"

# Words that mark a name as one whose value is a secret, wherever they stand in it.
_SECRET_WORDS = frozenset({
    "key", "apikey", "token", "secret", "password", "passwd", "pwd", "pin", "authorization",
    "auth", "cookie", "session", "sessionid", "credential", "credentials", "bearer", "jwt",
})
# A word that ends with one of these is a compound of it: accesstoken, clientsecret, apikey.
_SECRET_ENDINGS = ("token", "key", "secret", "password")
# Headers whose value is a login whatever they are called.
_SECRET_HEADERS = frozenset({"authorization", "proxy-authorization", "cookie", "set-cookie", "x-api-key"})
# In an address or a form, the one-time login code is a secret too. In JSON a "code" is an error code.
_SECRET_IN_FORMS = frozenset({"code"})

_SHAPES = (
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{6,}"), r"\1 " + HIDDEN),
    (re.compile(r"(?i)\b(basic)\s+[A-Za-z0-9+/=]{12,}"), r"\1 " + HIDDEN),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]*"), HIDDEN),  # a JWT
    (re.compile(r"\bsk-or-[A-Za-z0-9_-]{8,}"), HIDDEN),  # an OpenRouter key
    # name=value, name: value, "name": "value"
    (
        re.compile(
            r"(?i)\b((?:access|refresh|id)[_ -]?token|client[_ -]?secret|api[_ -]?key|password|secret|token|pin)"
            r"(\"?\s*[:=]\s*\"?)([^\s\"'&,;}<>]+)"
        ),
        r"\1\2" + HIDDEN,
    ),
)
_SHORTEST_REMEMBERED = 6  # a shorter value could be any ordinary word or number
_remembered: set[str] = set()
_remembering = threading.Lock()


def remember(*values) -> None:
    """Values the program holds that must never be written: its keys, the tokens it receives."""
    fresh = {str(value) for value in values if isinstance(value, str) and len(value.strip()) >= _SHORTEST_REMEMBERED}
    if not fresh:
        return
    with _remembering:
        _remembered.update(fresh)
        # Each part of a value with a line break in it too: an error may quote it one line at a time.
        _remembered.update(part for value in fresh for part in value.splitlines() if len(part) >= _SHORTEST_REMEMBERED)


def forget_all() -> None:
    """For the tests."""
    with _remembering:
        _remembered.clear()


def secret_name(name: str) -> bool:
    """Does a name (a header, a parameter, a JSON key) say that its value is a secret?"""
    text = str(name)
    if text.lower() in _SECRET_HEADERS:
        return True
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text).lower()
    return any(
        word in _SECRET_WORDS or word.endswith(_SECRET_ENDINGS)
        for word in re.findall(r"[a-z0-9]+", spaced)
    )


def clean(text: str) -> str:
    """Text with every secret it holds hidden, by value and by shape."""
    if not isinstance(text, str) or not text:
        return text
    with _remembering:
        known = sorted(_remembered, key=len, reverse=True)
    for value in known:
        if value in text:
            text = text.replace(value, HIDDEN)
    for shape, replacement in _SHAPES:
        text = shape.sub(replacement, text)
    return text


def value(item):
    """A JSON-like value with every secret hidden: by key at any depth, and by value."""
    if isinstance(item, dict):
        return {key: HIDDEN if secret_name(key) else value(inner) for key, inner in item.items()}
    if isinstance(item, (list, tuple)):
        return [value(inner) for inner in item]
    if isinstance(item, str):
        return clean(item)
    return item


def headers(pairs) -> list[list[str]]:
    """Headers as [name, value] pairs, in their order, with every secret one hidden."""
    return [[str(name), HIDDEN if secret_name(name) else clean(str(text))] for name, text in pairs]


def url(address: str) -> str:
    """An address without a login in it and with every secret parameter hidden. The rest
    stays as it was written, encoding included."""
    try:
        parts = urlsplit(str(address))
    except ValueError:
        return clean(str(address))
    netloc = parts.netloc.rsplit("@", 1)[-1]  # user:password@ never stays
    query = "&".join(_pair(part) for part in parts.query.split("&")) if parts.query else ""
    return clean(urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment)))


def form(text: str) -> str:
    """A form body (name=value&...) as it reads, with every secret field hidden."""
    try:
        fields = parse_qsl(text, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return clean(text)
    return clean("&".join(
        f"{name}={HIDDEN if _secret_field(name) else field}" for name, field in fields
    ))


def json_text(text: str) -> str:
    """JSON with every secret hidden, laid out as it came. Text that is not JSON is cleaned as text."""
    try:
        parsed = json.loads(text)
    except ValueError:
        return clean(text)
    return clean(json.dumps(value(parsed), ensure_ascii=False))


def _secret_field(name: str) -> bool:
    return secret_name(name) or name.lower() in _SECRET_IN_FORMS


def _pair(part: str) -> str:
    name, equals, _ = part.partition("=")
    return f"{name}={HIDDEN}" if equals and _secret_field(unquote_plus(name)) else part
