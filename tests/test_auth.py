import base64
import json
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from efactura import auth
from efactura.auth import Tokens
from efactura.config import load_config
from efactura.errors import EfacturaError

NOW = datetime(2026, 11, 11, 9, 0, tzinfo=timezone(timedelta(hours=2)))


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[anaf]\nclient_id = "my-client"\nclient_secret = "my-secret"\n'
        'redirect_uri = "https://localhost/callback"\n'
        f"token_file = '{tmp_path / 'private' / 'tokens.json'}'\n",
        encoding="utf-8",
    )
    return load_config(path)


def tokens(access_in=timedelta(days=30), refresh_in=timedelta(days=300), refresh="refresh-1"):
    return Tokens(
        access_token="access-1",
        refresh_token=refresh,
        access_expires_at=NOW + access_in,
        refresh_expires_at=NOW + refresh_in if refresh else None,
        obtained_at=NOW - timedelta(days=60),
    )


def client_answering(handler):
    seen = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return httpx.Client(transport=httpx.MockTransport(wrapped)), seen


def token_reply(**overrides):
    body = {
        "access_token": "access-2",
        "token_type": "Bearer",
        "expires_in": 7776000,
        "refresh_token": "refresh-2",
    }
    body.update(overrides)
    return httpx.Response(200, json={k: v for k, v in body.items() if v is not None})


def form(request: httpx.Request) -> dict:
    return {k: v[0] for k, v in parse_qs(request.content.decode()).items()}


# --- deciding whether a login is needed --------------------------------------


def test_no_saved_login_needs_login():
    assert auth.token_state(None, NOW) == "needs_login"


def test_unexpired_access_token_is_valid():
    assert auth.token_state(tokens(), NOW) == "valid"


def test_expired_access_with_live_refresh_needs_refresh():
    assert auth.token_state(tokens(access_in=timedelta(days=-1)), NOW) == "needs_refresh"


def test_access_about_to_expire_is_refreshed_early():
    assert auth.token_state(tokens(access_in=timedelta(minutes=2)), NOW) == "needs_refresh"


def test_both_expired_needs_login():
    state = auth.token_state(
        tokens(access_in=timedelta(days=-10), refresh_in=timedelta(days=-1)), NOW
    )

    assert state == "needs_login"


def test_expired_access_without_refresh_token_needs_login():
    assert auth.token_state(tokens(access_in=timedelta(days=-1), refresh=None), NOW) == "needs_login"


# --- saving and loading ------------------------------------------------------


def test_saved_login_round_trips(cfg):
    auth.save_tokens(cfg.token_file, tokens())

    assert auth.load_tokens(cfg.token_file) == tokens()


def test_saving_leaves_no_temporary_file_behind(cfg):
    auth.save_tokens(cfg.token_file, tokens())

    assert [p.name for p in cfg.token_file.parent.iterdir()] == ["tokens.json"]


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_saved_login_is_readable_by_the_owner_only(cfg):
    auth.save_tokens(cfg.token_file, tokens())

    assert cfg.token_file.stat().st_mode & 0o777 == 0o600


def test_missing_saved_login_is_none(cfg):
    assert auth.load_tokens(cfg.token_file) is None


def test_corrupt_saved_login_is_treated_as_missing(cfg):
    cfg.token_file.parent.mkdir(parents=True)
    cfg.token_file.write_text("{not json", encoding="utf-8")

    assert auth.load_tokens(cfg.token_file) is None


# --- the browser step --------------------------------------------------------


def test_login_address_carries_client_callback_and_jwt_request(cfg):
    url = urlsplit(auth.authorize_url(cfg))
    query = {k: v[0] for k, v in parse_qs(url.query).items()}

    assert f"{url.scheme}://{url.netloc}{url.path}" == (
        "https://logincert.anaf.ro/anaf-oauth2/v1/authorize"
    )
    assert query == {
        "response_type": "code",
        "client_id": "my-client",
        "redirect_uri": "https://localhost/callback",
        "token_content_type": "jwt",
    }


def test_code_is_read_from_the_redirected_address():
    assert auth.code_from_redirect("https://localhost/callback?code=abc123") == "abc123"


def test_code_is_read_when_other_parameters_surround_it():
    address = "https://localhost/callback?state=x&code=abc%2F123&session=9"

    assert auth.code_from_redirect(address) == "abc/123"


def test_pasted_address_may_carry_quotes_and_spaces():
    assert auth.code_from_redirect('  "https://localhost/callback?code=abc123"\n') == "abc123"


def test_a_bare_code_is_accepted():
    assert auth.code_from_redirect("abc123-XYZ") == "abc123-XYZ"


def test_address_without_a_code_is_invalid_input():
    with pytest.raises(EfacturaError) as info:
        auth.code_from_redirect("https://logincert.anaf.ro/anaf-oauth2/v1/authorize?client_id=x")

    assert info.value.code == "invalid_input"


def test_empty_address_is_invalid_input():
    with pytest.raises(EfacturaError) as info:
        auth.code_from_redirect("   ")

    assert info.value.code == "invalid_input"


def test_anaf_refusal_in_the_address_is_reported():
    address = "https://localhost/callback?error=access_denied&error_description=No+rights"

    with pytest.raises(EfacturaError) as info:
        auth.code_from_redirect(address)

    assert info.value.code == "login_refused"
    # ANAF's own words are what whoever helps needs to see.
    assert info.value.message == "ANAF refused the login: access_denied (No rights)"


def test_an_address_saying_access_denied_is_a_refused_login_not_a_passing_error():
    with pytest.raises(EfacturaError) as refused:
        auth.code_from_redirect("https://localhost/callback?error=access_denied")
    assert refused.value.code == "login_refused"
    assert refused.value.message == "ANAF refused the login: access_denied"

    with pytest.raises(EfacturaError) as other:
        auth.code_from_redirect("https://localhost/callback?error=server_error&error_description=down")
    assert other.value.code == "anaf_error" and "down" in other.value.message


# --- exchanging the code -----------------------------------------------------


def test_code_exchange_sends_what_anaf_expects(cfg):
    http, seen = client_answering(lambda request: token_reply())

    auth.exchange_code(cfg, http, "abc123", NOW)

    (request,) = seen
    assert request.method == "POST"
    assert str(request.url) == "https://logincert.anaf.ro/anaf-oauth2/v1/token"
    expected_basic = base64.b64encode(b"my-client:my-secret").decode()
    assert request.headers["authorization"] == f"Basic {expected_basic}"
    assert form(request) == {
        "grant_type": "authorization_code",
        "code": "abc123",
        "redirect_uri": "https://localhost/callback",
        "token_content_type": "jwt",
    }


def test_code_exchange_returns_tokens_with_expiry_dates(cfg):
    http, _ = client_answering(lambda request: token_reply())

    result = auth.exchange_code(cfg, http, "abc123", NOW)

    assert result.access_token == "access-2"
    assert result.refresh_token == "refresh-2"
    assert result.access_expires_at == NOW + timedelta(seconds=7776000)
    assert result.refresh_expires_at == NOW + timedelta(days=365)
    assert result.obtained_at == NOW


def test_expiry_falls_back_to_the_date_inside_the_jwt(cfg):
    expiry = NOW + timedelta(days=10)
    payload = base64.urlsafe_b64encode(json.dumps({"exp": int(expiry.timestamp())}).encode())
    jwt = f"header.{payload.decode().rstrip('=')}.signature"
    http, _ = client_answering(lambda request: token_reply(access_token=jwt, expires_in=None))

    result = auth.exchange_code(cfg, http, "abc123", NOW)

    assert result.access_expires_at == expiry


def test_rejected_code_is_reported_as_expired(cfg):
    http, _ = client_answering(
        lambda request: httpx.Response(400, json={"error": "invalid_grant"})
    )

    with pytest.raises(EfacturaError) as info:
        auth.exchange_code(cfg, http, "stale", NOW)

    assert info.value.code == "login_code_expired"


def test_rejected_client_credentials_are_a_config_error(cfg):
    http, _ = client_answering(
        lambda request: httpx.Response(401, json={"error": "invalid_client"})
    )

    with pytest.raises(EfacturaError) as info:
        auth.exchange_code(cfg, http, "abc123", NOW)

    assert info.value.code == "config_error"


def test_reply_without_an_access_token_is_an_anaf_error(cfg):
    http, _ = client_answering(lambda request: httpx.Response(200, json={"token_type": "Bearer"}))

    with pytest.raises(EfacturaError) as info:
        auth.exchange_code(cfg, http, "abc123", NOW)

    assert info.value.code == "anaf_error"


# --- renewing ----------------------------------------------------------------


def test_refresh_sends_the_refresh_token_and_jwt_request(cfg):
    http, seen = client_answering(lambda request: token_reply())

    auth.refresh_tokens(cfg, http, tokens(), NOW)

    (request,) = seen
    assert request.headers["authorization"].startswith("Basic ")
    assert form(request) == {
        "grant_type": "refresh_token",
        "refresh_token": "refresh-1",
        "token_content_type": "jwt",
    }


def test_refresh_returns_the_new_pair(cfg):
    http, _ = client_answering(lambda request: token_reply())

    result = auth.refresh_tokens(cfg, http, tokens(), NOW)

    assert (result.access_token, result.refresh_token) == ("access-2", "refresh-2")
    assert result.refresh_expires_at == NOW + timedelta(days=365)


def test_refresh_reply_without_a_refresh_token_keeps_the_old_one(cfg):
    http, _ = client_answering(lambda request: token_reply(refresh_token=None))
    old = tokens()

    result = auth.refresh_tokens(cfg, http, old, NOW)

    assert result.access_token == "access-2"
    assert result.refresh_token == "refresh-1"
    assert result.refresh_expires_at == old.refresh_expires_at


def test_rejected_refresh_means_login_is_needed(cfg):
    http, _ = client_answering(
        lambda request: httpx.Response(400, json={"error": "invalid_grant"})
    )

    with pytest.raises(EfacturaError) as info:
        auth.refresh_tokens(cfg, http, tokens(), NOW)

    assert info.value.code == "login_needed"


def test_anaf_server_failure_during_refresh_is_not_a_login_problem(cfg):
    http, _ = client_answering(lambda request: httpx.Response(503, text="down"))

    with pytest.raises(EfacturaError) as info:
        auth.refresh_tokens(cfg, http, tokens(), NOW)

    assert info.value.code == "anaf_error"


def test_unreachable_anaf_is_a_network_error(cfg):
    def refuse(request):
        raise httpx.ConnectError("no route", request=request)

    http, _ = client_answering(refuse)

    with pytest.raises(EfacturaError) as info:
        auth.refresh_tokens(cfg, http, tokens(), NOW)

    assert info.value.code == "network_error"


# --- review fixes: rate limits, and a login file that is briefly in use (Windows) ---


def test_rate_limited_renewal_is_not_a_login_problem(cfg):
    http, _ = client_answering(lambda request: httpx.Response(429, text="slow down"))

    with pytest.raises(EfacturaError) as info:
        auth.refresh_tokens(cfg, http, tokens(), NOW)

    assert info.value.code == "anaf_limit_reached"


def test_request_timeout_during_renewal_is_not_a_login_problem(cfg):
    http, _ = client_answering(lambda request: httpx.Response(408, text="timeout"))

    with pytest.raises(EfacturaError) as info:
        auth.refresh_tokens(cfg, http, tokens(), NOW)

    assert info.value.code == "anaf_error"


def in_use(*args, **kwargs):
    raise PermissionError(13, "The process cannot access the file because it is being used")


def test_save_retries_while_the_file_is_briefly_in_use(cfg, monkeypatch):
    real_replace = os.replace
    attempts = []

    def busy_twice(source, target):
        attempts.append(target)
        if len(attempts) < 3:
            in_use()
        real_replace(source, target)

    monkeypatch.setattr(auth.os, "replace", busy_twice)
    monkeypatch.setattr(auth, "_pause", lambda seconds: None)

    auth.save_tokens(cfg.token_file, tokens())

    assert len(attempts) == 3
    assert auth.load_tokens(cfg.token_file) == tokens()


def test_new_pair_is_not_lost_when_the_file_stays_in_use(cfg, monkeypatch):
    auth.save_tokens(cfg.token_file, tokens())
    newer = Tokens("access-2", "refresh-2", NOW + timedelta(days=90), NOW + timedelta(days=365), NOW)
    with monkeypatch.context() as patched:
        patched.setattr(auth.os, "replace", in_use)
        patched.setattr(auth, "_pause", lambda seconds: None)
        auth.save_tokens(cfg.token_file, newer)  # must not raise

    assert auth.load_tokens(cfg.token_file) == newer
    assert [p.name for p in cfg.token_file.parent.iterdir()] == ["tokens.json"]


def test_unfinished_older_save_does_not_replace_a_newer_login(cfg):
    newer = Tokens("access-2", "refresh-2", NOW + timedelta(days=90), NOW + timedelta(days=365), NOW)
    auth.save_tokens(cfg.token_file, tokens())
    leftover = cfg.token_file.read_text(encoding="utf-8")
    auth.save_tokens(cfg.token_file, newer)
    cfg.token_file.with_name("tokens.json.tmp").write_text(leftover, encoding="utf-8")

    assert auth.load_tokens(cfg.token_file) == newer


def test_load_retries_while_the_file_is_being_swapped(cfg, monkeypatch):
    from pathlib import Path

    auth.save_tokens(cfg.token_file, tokens())
    real_read = Path.read_text
    reads = []

    def busy_once(self, *args, **kwargs):
        reads.append(self.name)
        if len(reads) == 1:
            in_use()
        return real_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", busy_once)
    monkeypatch.setattr(auth, "_pause", lambda seconds: None)

    assert auth.load_tokens(cfg.token_file) == tokens()
