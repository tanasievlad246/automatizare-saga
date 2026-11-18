"""The local REST API: the same functions as the terminal commands, over HTTP.

It listens on 127.0.0.1 only (see cli.run_server). Every route is served twice:

    /sync, /invoices, ...      for other programs (Power Automate). They must send the key
                               from config.toml in an X-API-Key header.
    /api/sync, /api/...        for the page this program serves at /ui/. The page needs no
                               key; see _from_own_page for why that is safe.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import time
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Callable, Literal, Optional, Union

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, StrictBool, StrictInt
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__, backup, journal, update
from .config import PAGE_HOSTNAME, Config, load_config
from .errors import (
    ANAF_ERROR,
    ANAF_LIMIT_REACHED,
    BUSY,
    CLIENT_OFF,
    SAGA_FILES_CHANGED,
    SAGA_FILES_STALE,
    SAGA_ARCHIVE_ERROR,
    CONFIG_ERROR,
    INTERNAL_ERROR,
    INVALID_CUI,
    INVALID_INPUT,
    JEV_ERROR,
    LOGIN_CANCELLED,
    LOGIN_CODE_EXPIRED,
    LOGIN_NEEDED,
    LOGIN_REFUSED,
    NETWORK_ERROR,
    NO_SPV_RIGHTS,
    NOT_CLASSIFIABLE,
    BACKUP_ERROR,
    NOT_FOUND,
    UNAUTHORIZED,
    UPDATE_ERROR,
    EfacturaError,
)
from .service import Service, configure_logging
from .store import Store

log = logging.getLogger(__name__)

HTTP_STATUS = {
    INVALID_INPUT: 400,
    INVALID_CUI: 400,
    UNAUTHORIZED: 401,
    NOT_FOUND: 404,
    LOGIN_NEEDED: 409,
    LOGIN_CODE_EXPIRED: 409,
    LOGIN_REFUSED: 409,
    LOGIN_CANCELLED: 409,
    BUSY: 409,
    NOT_CLASSIFIABLE: 409,
    UPDATE_ERROR: 409,
    BACKUP_ERROR: 409,
    CLIENT_OFF: 409,
    SAGA_FILES_CHANGED: 409,
    SAGA_FILES_STALE: 409,
    SAGA_ARCHIVE_ERROR: 409,
    JEV_ERROR: 502,
    NO_SPV_RIGHTS: 502,
    ANAF_LIMIT_REACHED: 502,
    ANAF_ERROR: 502,
    NETWORK_ERROR: 502,
    CONFIG_ERROR: 500,
    INTERNAL_ERROR: 500,
}

# Reachable without the key: they reveal the list of routes, never data.
OPEN_PATHS = {"/", "/health", "/api/health", "/openapi.json"}
# No other site may show this page inside its own (and trick the person into clicking in it).
NO_FRAMING = {"X-Frame-Options": "DENY", "Content-Security-Policy": "frame-ancestors 'none'"}
PAGE_PREFIX = "/ui"  # the built page and its files: no data in them
PAGE_API_PREFIX = "/api"
DEMO_LOGIN_PATH = "/api/demo/anaf-login"
BUILT_PAGE = Path(__file__).parent / "ui"  # written there by `pnpm --dir frontend build`


class AsciiJSONResponse(JSONResponse):
    """Same encoding as the commands: non-English letters as \\u escapes."""

    def render(self, content) -> bytes:
        return json.dumps(content, ensure_ascii=True).encode("ascii")


class SyncRequest(BaseModel):
    cui: Union[str, int]
    days: int | None = None
    classify: bool = True
    start: str | None = None  # first day, YYYY-MM-DD, instead of days
    end: str | None = None  # last day; today when left out
    cover_gap: bool = False  # days is a minimum, widened back to the last complete run


class UploadedRequest(BaseModel):
    ids: list[Union[str, int]]
    uploaded: bool = True


class ClassifyRequest(BaseModel):
    force: bool = False


class SetContRequest(BaseModel):
    accept: bool = False
    cont: Union[str, int, None] = None
    force: bool = False
    line: StrictInt | None = None  # one line of an invoice decided line by line; left out: every line


class SettingsRequest(BaseModel):
    min_confidence: float | None = None
    jev_instructions: str | None = None
    jev_line_instructions: str | None = None  # the question about one line
    jev_issued_instructions: str | None = None  # the two questions about the invoices a client issued
    jev_issued_line_instructions: str | None = None


class AccountRequest(BaseModel):
    description: str = ""
    kind: str = "received"  # or "issued": the list of accounts for the invoices a client issued


class RuleRequest(BaseModel):
    name: str
    cont: Union[str, int]
    keywords: list[str] = []
    item_codes: list[str] = []
    commodity_prefixes: list[str] = []
    supplier_cuis: list[str] = []
    client_cui: Union[str, int, None] = None
    enabled: bool = True
    direction: str | None = None  # received or issued; left out when a rule is replaced: it keeps its own


class RulePreviewRequest(BaseModel):
    keywords: list[str] = []
    item_codes: list[str] = []
    commodity_prefixes: list[str] = []
    supplier_cuis: list[str] = []
    client_cui: Union[str, int, None] = None  # try it on this client's invoices only


class TrialLine(BaseModel):
    description: str
    quantity: Union[str, int, float, None] = None  # missing or blank: 1
    unit_price: Union[str, int, float, None] = None  # missing or blank: 0
    seller_code: str | None = None
    barcode: str | None = None
    commodity_codes: list[str] = []
    unit: str | None = None
    vat_percent: Union[str, int, float, None] = None
    value: Union[str, int, float, None] = None  # without VAT; when missing, quantity × price


class RuleTestRequest(BaseModel):
    lines: list[TrialLine]
    supplier_name: str = ""
    supplier_cui: Union[str, int] = ""
    client_cui: Union[str, int, None] = None
    currency: str = "RON"
    credit_note: bool = False
    ask: str = "rules_then_jev"


class DismissSuggestionsRequest(BaseModel):
    invoice_ids: list[Union[str, int]]


class BackupFolderRequest(BaseModel):
    folder: str


class RestoreRequest(BaseModel):
    name: str  # the file name of a snapshot in the backup folder


class MoveRequest(BaseModel):
    up: bool


class ClientRequest(BaseModel):
    cui: Union[str, int]
    name: str


class ClientSwitchRequest(BaseModel):
    enabled: bool


class PerLineRequest(BaseModel):
    enabled: StrictBool


class ClassifyAgainRequest(BaseModel):
    jev: StrictBool = True  # false: the rules alone, and Jev is not asked


class PeriodRequest(BaseModel):
    days: StrictInt | None = None  # the last so many days, 1-60; a number, not "7" or true
    start: str | None = None  # or a first day, YYYY-MM-DD, with a last one
    end: str | None = None


class ScheduleRequest(BaseModel):
    enabled: bool
    days: list[int]
    times: list[str]
    period: PeriodRequest | None = None  # which invoices each run asks for; left out, it stays as stored


class ScreenSettingsRequest(BaseModel):
    saga_folder: str | None = None  # left out, it stays as it is
    saga_file_per: str | None = None  # "client" or "invoice"; left out, it stays as it is
    show_issued: StrictBool | None = None  # issued invoices on a client's screen; left out, it stays


class SagaFilesRequest(BaseModel):
    cui: Union[str, int, None] = None  # left out: every client


class SagaImportedRequest(BaseModel):
    version: Optional[str] = None  # from GET /saga-files; left out, whatever the files hold now
    source: Literal["api", "screen"] = "api"  # "screen": confirmed by a person on the page


class OpenFolderRequest(BaseModel):
    cui: Union[str, int, None] = None
    invoice_id: Union[str, int, None] = None  # the folder that invoice's SAGA file is in


class SecretRequest(BaseModel):
    value: str = ""


class LoginFinishRequest(BaseModel):
    address: str


def _failure(error: EfacturaError) -> AsciiJSONResponse:
    return AsciiJSONResponse(error.to_dict(), status_code=HTTP_STATUS.get(error.code, 500))


def _from_own_page(request: Request, own_hosts: set[str]) -> bool:
    """Is this the page this program serves, calling its own API?

    Browsers add Sec-Fetch-Site to every request and a page cannot change it, so a page
    from any other site arrives as "cross-site" and is turned away. The Host check stops
    another name from being pointed at this computer to pass as "same-origin". A program
    on this PC could send both headers, but it could equally read the key from config.toml.
    """
    return (
        request.url.path.startswith(PAGE_API_PREFIX + "/")
        and request.headers.get("sec-fetch-site") == "same-origin"
        and request.headers.get("host") in own_hosts
    )


def _worth_a_line(path: str, method: str) -> bool:
    """Should this request be written in the journal? Not the journal's own requests
    (reading it would write to it), nor the page's files, nor "are you there", nor the page
    reading the schedule (it does so every few seconds while a run is shown)."""
    plain = path.removeprefix(PAGE_API_PREFIX)
    return not (
        path in OPEN_PATHS or path.startswith(PAGE_PREFIX) or plain.startswith("/events") or plain == "/health"
        or (plain == "/sync/schedule" and method == "GET")
    )


def _own_hosts(port: int) -> set[str]:
    """The names the page may be opened under, as a browser writes them in the Host
    header: with the port, except port 80, which browsers leave out."""
    names = ("127.0.0.1", "localhost", PAGE_HOSTNAME)
    return {name if port == 80 else f"{name}:{port}" for name in names}


def create_app(
    cfg: Config,
    service_factory: Callable[[Config], Service] | None = None,
    port: int | None = None,
    ui_dir: Path | None = None,
) -> FastAPI:
    cfg.require_api_key()
    make_service = service_factory or Service  # on demo settings it takes the stand-ins by itself
    # The demo's login address is opened in a new tab, which carries no key.
    open_paths = OPEN_PATHS | {DEMO_LOGIN_PATH} if cfg.demo else OPEN_PATHS
    expected_key = cfg.api_key.encode()
    port = port or cfg.api_port
    own_hosts = _own_hosts(port)
    ui_dir = ui_dir or BUILT_PAGE
    router = APIRouter()

    # Create or upgrade the database now, once, rather than in the first requests, which
    # arrive several at a time when the page opens.
    Store(cfg.db_path).close()
    journal.configure(cfg.db_path)

    app = FastAPI(
        title="efactura local API",
        version=__version__,
        description="Send the key from config.toml in an X-API-Key header.",
        default_response_class=AsciiJSONResponse,
        # FastAPI's interactive documentation loads its scripts from a CDN. On this address
        # the page is trusted without a key, so a script from elsewhere could read every key.
        # The route list is still at /openapi.json, and in the README.
        docs_url=None,
        redoc_url=None,
    )
    # Only so the documentation page offers a field for the key; the check is the middleware.
    documented_key = [Depends(APIKeyHeader(name="X-API-Key", auto_error=False))]

    @app.middleware("http")
    async def require_key(request: Request, call_next):
        path = request.url.path
        is_open = path in open_paths or path == PAGE_PREFIX or path.startswith(PAGE_PREFIX + "/")
        allowed = is_open or _from_own_page(request, own_hosts) or hmac.compare_digest(
            request.headers.get("x-api-key", "").encode(), expected_key
        )
        # One trace per request: every line written while it is served carries the same number.
        # Fresh, because the server itself runs inside the trace of the command that started it.
        with journal.trace(fresh=True) as trace_id:
            began = time.monotonic()
            if not allowed:
                response = _failure(EfacturaError(UNAUTHORIZED, "Missing or wrong X-API-Key header."))
            else:
                try:
                    response = await call_next(request)
                except Exception as exc:
                    # Left alone, a bug is answered by the outermost layer, after this trace has
                    # ended: its traceback would be filed under no request, and the answer
                    # would name no trace.
                    log.exception("Unexpected failure in %s %s", request.method, path)
                    response = _failure(EfacturaError(INTERNAL_ERROR, f"{type(exc).__name__}: {exc}"))
            if _worth_a_line(path, request.method):
                # The method, the path and how it ended. Never the body: it may hold a key.
                # Written from a worker thread: the line may wait for a busy database, and
                # every other request would wait behind it here.
                await run_in_threadpool(partial(
                    journal.record,
                    "page", "page.request", f"{request.method} {path} answered {response.status_code}.",
                    level="detail" if response.status_code < 500 else "error",
                    method=request.method, path=path, status=response.status_code,
                    duration_ms=round((time.monotonic() - began) * 1000),
                ))
        response.headers.update(NO_FRAMING)
        response.headers["X-Trace-Id"] = trace_id
        return response

    @app.exception_handler(EfacturaError)
    async def on_known_error(request: Request, exc: EfacturaError):
        return _failure(exc)

    @app.exception_handler(RequestValidationError)
    async def on_bad_request(request: Request, exc: RequestValidationError):
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'][1:]) or error['loc'][0]}: {error['msg']}"
            for error in exc.errors()
        )
        return _failure(EfacturaError(INVALID_INPUT, problems or "The request could not be read."))

    @app.exception_handler(StarletteHTTPException)
    async def on_http_error(request: Request, exc: StarletteHTTPException):
        code = NOT_FOUND if exc.status_code == 404 else INVALID_INPUT
        message = f"No such route: {request.method} {request.url.path}" if code == NOT_FOUND else str(exc.detail)
        return AsciiJSONResponse(EfacturaError(code, message).to_dict(), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def on_bug(request: Request, exc: Exception):
        log.exception("Unexpected failure in %s %s", request.method, request.url.path)
        return _failure(EfacturaError(INTERNAL_ERROR, f"{type(exc).__name__}: {exc}"))

    def call(action: Callable[[Service], dict]) -> dict:
        service = make_service(cfg)
        try:
            return action(service)
        finally:
            service.close()

    @router.get("/health", summary="Is the API running?")
    def health():
        return call(lambda s: s.health())

    @router.get("/auth/status", dependencies=documented_key, summary="Is a login needed?")
    def auth_status():
        return call(lambda s: s.auth_status())

    @router.post("/auth/login/start", dependencies=documented_key, summary="ANAF login address")
    def login_start():
        return call(lambda s: s.login_start())

    @router.post("/auth/login/finish", dependencies=documented_key, summary="Save the login")
    def login_finish(body: LoginFinishRequest):
        return call(lambda s: s.login_finish(body.address))

    @router.post("/auth/login/certificate", dependencies=documented_key, summary="Log in with the Windows certificate")
    def login_certificate():
        # Waits for Windows and the person (minutes): a plain `def` runs off the event loop.
        return call(lambda s: s.login_with_certificate())

    @router.get("/anaf/messages", dependencies=documented_key, summary="Preview; saves nothing")
    def anaf_messages(cui: str = Query(...), days: int | None = None):
        return call(lambda s: s.list_remote(cui, days))

    @router.post("/sync", dependencies=documented_key, summary="Fetch and save new messages")
    def sync(body: SyncRequest):
        return call(
            lambda s: s.sync(
                str(body.cui), body.days, classify=body.classify, start=body.start, end=body.end,
                cover_gap=body.cover_gap,
            )
        )

    @router.get("/sync/schedule", dependencies=documented_key, summary="When the program downloads by itself")
    def sync_schedule():
        return call(lambda s: s.schedule())

    @router.put("/sync/schedule", dependencies=documented_key, summary="Choose when the program downloads by itself")
    def set_sync_schedule(body: ScheduleRequest):
        period = body.period.model_dump(exclude_none=True) if body.period else None
        return call(lambda s: s.set_schedule(body.enabled, body.days, body.times, period))

    @router.get("/invoices", dependencies=documented_key, summary="Saved messages")
    def invoices(
        cui: str | None = None,
        pending: bool = False,
        type: str | None = Query(None, description="primita, trimisa, erori or mesaj"),
        since: str | None = Query(None, description="YYYY-MM-DD"),
        classification: str | None = Query(None, description="pending, classified or review"),
        new: bool = Query(False, description="only those from the latest sync, not yet uploaded: received ones unless type is given"),
    ):
        return call(lambda s: s.invoices(cui, pending, type, since, classification, new))

    @router.post(
        "/invoices/uploaded", dependencies=documented_key,
        summary="Set or clear the uploaded flag on several invoices",
    )
    def mark_many_uploaded(body: UploadedRequest):
        return call(lambda s: s.mark_uploaded([str(i) for i in body.ids], undo=not body.uploaded))

    @router.get("/invoices/{message_id}", dependencies=documented_key, summary="One saved message")
    def invoice(message_id: str, xml: bool = False):
        return call(lambda s: s.invoice(message_id, include_xml=xml))

    @router.post("/invoices/{message_id}/uploaded", dependencies=documented_key, summary="Set the flag")
    def mark_uploaded(message_id: str):
        return call(lambda s: s.mark_uploaded([message_id]))

    @router.delete("/invoices/{message_id}/uploaded", dependencies=documented_key, summary="Clear the flag")
    def unmark_uploaded(message_id: str):
        return call(lambda s: s.mark_uploaded([message_id], undo=True))

    @router.post(
        "/invoices/{message_id}/classify", dependencies=documented_key,
        summary="Give one saved invoice its account",
    )
    def classify(message_id: str, body: ClassifyRequest | None = None):
        return call(lambda s: s.classify(message_id, force=bool(body and body.force)))

    @router.get("/review", dependencies=documented_key, summary="Invoices a person must decide")
    def review(cui: str | None = None):
        return call(lambda s: s.review(cui))

    @router.post(
        "/invoices/{message_id}/cont", dependencies=documented_key,
        summary="Accept Jev's suggestion, or set an account",
    )
    def set_cont(message_id: str, body: SetContRequest):
        cont = str(body.cont) if body.cont is not None else None
        return call(
            lambda s: s.set_cont(message_id, cont=cont, accept=body.accept, force=body.force, line=body.line)
        )

    @router.get(
        "/classification/settings", dependencies=documented_key,
        summary="The confidence level and the accounts on offer",
    )
    def classification_settings():
        return call(lambda s: s.classification_settings())

    @router.put(
        "/classification/settings", dependencies=documented_key, summary="Change the confidence level"
    )
    def change_classification_settings(body: SettingsRequest):
        if all(value is None for value in body.model_dump().values()):
            raise EfacturaError(
                INVALID_INPUT,
                "Give min_confidence, jev_instructions, jev_line_instructions, jev_issued_instructions, "
                "jev_issued_line_instructions, or several.",
            )

        def change(service: Service) -> dict:
            if body.min_confidence is not None:
                service.set_min_confidence(body.min_confidence)
            if body.jev_instructions is not None:
                service.set_jev_instructions(body.jev_instructions)
            if body.jev_line_instructions is not None:
                service.set_jev_line_instructions(body.jev_line_instructions)
            if body.jev_issued_instructions is not None:
                service.set_jev_issued_instructions(body.jev_issued_instructions)
            if body.jev_issued_line_instructions is not None:
                service.set_jev_issued_line_instructions(body.jev_issued_line_instructions)
            return service.classification_settings()

        return call(change)

    @router.get("/classification/costs", dependencies=documented_key, summary="What Jev has cost")
    def classification_costs(
        since: str | None = Query(None, description="YYYY-MM-DD"),
        until: str | None = Query(None, description="YYYY-MM-DD, included"),
        cui: str | None = None,
        group: str = Query("month", description="day, week, month or year"),
    ):
        return call(lambda s: s.costs(since, cui, until, group))

    @router.get("/classification/calls", dependencies=documented_key, summary="What Jev was asked")
    def classification_calls(
        since: str | None = None, until: str | None = None, cui: str | None = None, limit: int = 200
    ):
        return call(lambda s: s.jev_calls(since, until, cui, limit))

    @router.get(
        "/invoices/{message_id}/view", dependencies=documented_key,
        summary="One message with its parsed invoice, both XML texts and Jev's answer",
    )
    def invoice_view(message_id: str):
        return call(lambda s: s.invoice_view(message_id))

    # --- rules and accounts (the "Reguli de clasificare" screen) ---

    def rule_fields(body: RuleRequest) -> dict:
        fields = body.model_dump()
        fields["cont"] = str(body.cont)
        fields["client_cui"] = str(body.client_cui) if body.client_cui is not None else None
        return fields

    @router.get("/rules", dependencies=documented_key, summary="Accounts, rules and the question for Jev")
    def rules():
        return call(lambda s: s.rules_overview())

    @router.put("/accounts/{cont}", dependencies=documented_key, summary="Add or describe an account")
    def save_account(cont: str, body: AccountRequest):
        return call(lambda s: s.save_account(cont, body.description, body.kind))

    @router.delete("/accounts/{cont}", dependencies=documented_key, summary="Remove an account")
    def delete_account(cont: str, kind: str = Query("received", description="received or issued")):
        return call(lambda s: s.delete_account(cont, kind))

    @router.post("/rules", dependencies=documented_key, summary="Add a rule")
    def add_rule(body: RuleRequest):
        return call(lambda s: s.save_rule(**rule_fields(body)))

    @router.put("/rules/{rule_id}", dependencies=documented_key, summary="Replace a rule")
    def change_rule(rule_id: int, body: RuleRequest):
        return call(lambda s: s.save_rule(rule_id, **rule_fields(body)))

    @router.delete("/rules/{rule_id}", dependencies=documented_key, summary="Remove a rule")
    def delete_rule(rule_id: int):
        return call(lambda s: s.delete_rule(rule_id))

    @router.post("/rules/{rule_id}/move", dependencies=documented_key, summary="Move a rule up or down")
    def move_rule(rule_id: int, body: MoveRequest):
        return call(lambda s: s.move_rule(rule_id, body.up))

    # --- proposed rules: what Jev or a person decided, offered as a rule ---

    @router.get(
        "/rules/suggestions", dependencies=documented_key,
        summary="Rules worth creating from recent decisions made without a rule",
    )
    def rule_suggestions():
        return call(lambda s: s.rule_suggestions())

    @router.post(
        "/rules/preview", dependencies=documented_key,
        summary="How a rule would have done on recently classified invoices; saves nothing",
    )
    def rule_preview(body: RulePreviewRequest):
        conditions = body.model_dump()
        client_cui = conditions.pop("client_cui")
        return call(lambda s: s.rule_preview(
            **conditions, client_cui=str(client_cui) if client_cui is not None else None
        ))

    @router.post(
        "/rules/test", dependencies=documented_key,
        summary="Classify a trial invoice as a real one is; saves nothing but the cost of asking Jev",
    )
    def rule_test(body: RuleTestRequest):
        fields = body.model_dump()
        client_cui = fields.pop("client_cui")
        fields["supplier_cui"] = str(fields["supplier_cui"])
        return call(lambda s: s.test_rules(
            **fields, client_cui=str(client_cui) if client_cui is not None else None
        ))

    @router.post(
        "/rules/suggestions/dismiss", dependencies=documented_key,
        summary="Stop proposing a rule for these invoices",
    )
    def dismiss_rule_suggestions(body: DismissSuggestionsRequest):
        return call(lambda s: s.dismiss_rule_suggestions([str(i) for i in body.invoice_ids]))

    # --- clients ---

    @router.get("/clients", dependencies=documented_key, summary="Clients, with invoice counts")
    def clients():
        return call(lambda s: s.clients())

    @router.post("/clients", dependencies=documented_key, summary="Add or rename a client")
    def save_client(body: ClientRequest):
        return call(lambda s: s.save_client(str(body.cui), body.name))

    @router.delete("/clients/{cui}", dependencies=documented_key, summary="Take a client off the list")
    def remove_client(cui: str):
        return call(lambda s: s.remove_client(cui))

    @router.put(
        "/clients/{cui}/enabled", dependencies=documented_key,
        summary="Switch a client on or off for downloading",
    )
    def switch_client(cui: str, body: ClientSwitchRequest):
        return call(lambda s: s.set_client_enabled(cui, body.enabled))

    @router.put(
        "/clients/{cui}/per-line", dependencies=documented_key,
        summary="An account for each invoice line of this client, or one for the whole invoice",
    )
    def switch_per_line(cui: str, body: PerLineRequest):
        return call(lambda s: s.set_client_per_line(cui, body.enabled))

    @router.post(
        "/clients/{cui}/classify-again", dependencies=documented_key,
        summary="Send this client's invoices to check or waiting for Jev back through the rules and Jev",
    )
    def classify_again(cui: str, body: ClassifyAgainRequest | None = None):
        return call(lambda s: s.classify_again(cui, jev=body.jev if body else True))

    @router.post(
        "/clients/import", dependencies=documented_key,
        summary="Add clients from a CSV or Excel file sent as the request body",
    )
    async def import_clients(request: Request, filename: str = Query(...)):
        content = await request.body()
        return call(lambda s: s.import_clients(filename, content))

    # --- settings and keys changed on screen ---

    @router.get(
        "/settings", dependencies=documented_key,
        summary="The folder for SAGA, one file per client or per invoice, and whether issued invoices are shown",
    )
    def settings():
        return call(lambda s: s.app_settings())

    @router.put(
        "/settings", dependencies=documented_key,
        summary="Change the folder for SAGA, the way its files are written, or whether issued invoices are shown",
    )
    def change_settings(body: ScreenSettingsRequest):
        return call(lambda s: s.change_settings(body.saga_folder, body.saga_file_per, body.show_issued))

    @router.post(
        "/saga-files/write", dependencies=documented_key,
        summary="Bring the files for SAGA up to date, for one client or for all",
    )
    def write_saga_files(body: SagaFilesRequest):
        cui = str(body.cui) if body.cui is not None else None
        return call(lambda s: s.write_saga_files(cui))

    # --- an import in SAGA, confirmed, and the archive ---

    @router.get("/saga-files", dependencies=documented_key, summary="Every client with a file for SAGA waiting")
    def saga_files():
        return call(lambda s: s.saga_files())

    @router.get("/saga-files/{cui}", dependencies=documented_key, summary="One client's files for SAGA and their version")
    def saga_files_of(cui: str):
        return call(lambda s: s.saga_files(cui))

    @router.post(
        "/saga-files/{cui}/imported", dependencies=documented_key,
        summary="SAGA imported this client's files: mark their invoices and archive the files",
    )
    def saga_imported(cui: str, body: SagaImportedRequest):
        return call(lambda s: s.confirm_saga_import(cui, version=body.version, source=body.source))

    @router.get("/saga-archive", dependencies=documented_key, summary="One client's confirmed imports, newest first")
    def saga_archive(cui: str):
        return call(lambda s: s.saga_archive(cui))

    @router.get("/saga-archive/{import_id}", dependencies=documented_key, summary="One confirmed import, with its invoices")
    def saga_archive_entry(import_id: int):
        return call(lambda s: s.saga_archive_entry(import_id))

    @router.get(
        "/saga-archive/{import_id}/files/{name}", dependencies=documented_key,
        summary="A file of a confirmed import, as SAGA got it",
    )
    def saga_archive_file(import_id: int, name: str):
        service = make_service(cfg)
        try:
            path = service.saga_archive_file(import_id, name)
        finally:
            service.close()
        return FileResponse(path, media_type="application/xml", filename=path.name)

    @router.post("/saga-archive/{import_id}/open", dependencies=documented_key, summary="Show a confirmed import's folder")
    def open_saga_archive(import_id: int):
        return call(lambda s: s.open_saga_archive(import_id))

    @router.post(
        "/settings/choose-folder", dependencies=documented_key,
        summary="Pick a folder in the computer's own dialog",
    )
    def choose_folder(purpose: str = "saga"):
        return call(lambda s: s.choose_folder(purpose))

    @router.post("/folders/open", dependencies=documented_key, summary="Show the SAGA folder")
    def open_folder(body: OpenFolderRequest):
        cui = str(body.cui) if body.cui is not None else None
        invoice_id = str(body.invoice_id) if body.invoice_id is not None else None
        return call(lambda s: s.open_saga_folder(cui, invoice_id))

    @router.get("/secrets", dependencies=documented_key, summary="Every key, in full")
    def secrets():
        return call(lambda s: s.secrets())

    @router.put("/secrets/{key}", dependencies=documented_key, summary="Change a key")
    def change_secret(key: str, body: SecretRequest):
        return call(lambda s: s.set_secret(key, body.value))

    # --- backups of the database (the "Copii de siguranță" screen) ---

    @router.get("/backups", dependencies=documented_key, summary="The backup folder, the snapshots and when the next is due")
    def backups():
        return backup.status(cfg)

    @router.put("/backups/folder", dependencies=documented_key, summary="Choose where backups go")
    def set_backup_folder(body: BackupFolderRequest):
        return backup.set_folder(cfg, body.folder)

    @router.post("/backups", dependencies=documented_key, summary="Make a backup now")
    def make_backup():
        return backup.snapshot(cfg, "manual")

    @router.post("/backups/restore", dependencies=documented_key, summary="Put a snapshot back, in the background")
    def restore_backup(body: RestoreRequest):
        return backup.start_restore_in_background(cfg, body.name)

    @router.post("/backups/open-folder", dependencies=documented_key, summary="Show the backup folder")
    def open_backup_folder():
        return call(lambda s: s.open_folder(backup.status(cfg)["folder"]))

    # --- the journal (the "Jurnal" screen) ---

    def journal_lines(details, problems, area, q, since, trace, before, limit, everything=False) -> dict:
        return journal.events(
            cfg.db_path, details=details, problems_only=problems, area=area, text=q, since=since,
            trace=trace, before=before, limit=limit, everything=everything,
        )

    @router.get("/events", dependencies=documented_key, summary="The journal, newest line first")
    def events(
        details: bool = False, problems: bool = False, area: str | None = None, q: str | None = None,
        since: str | None = None, trace: str | None = None, before: int | None = None, limit: int = journal.PAGE,
    ):
        return journal_lines(details, problems, area, q, since, trace, before, limit)

    @router.get("/events/export", dependencies=documented_key, summary="The same lines as a text file")
    def export_events(
        details: bool = True, problems: bool = False, area: str | None = None, q: str | None = None,
        since: str | None = None, trace: str | None = None,
    ):
        # Whole: a file cut short without saying so would send whoever reads it down the wrong path.
        lines = journal_lines(details, problems, area, q, since, trace, None, journal.PAGE, everything=True)["events"]
        name = f"autosaga-jurnal-{datetime.now():%Y%m%d-%H%M}.txt"
        return PlainTextResponse(
            journal.as_text(lines) + "\n", headers={"Content-Disposition": f'attachment; filename="{name}"'}
        )

    # --- updating the installed program ---

    @router.get("/update", dependencies=documented_key, summary="Installed release, and whether a newer one exists")
    def update_status(check: bool = False):
        return update.status(cfg, check=check)

    @router.post("/update", dependencies=documented_key, summary="Update to the newest release, in the background")
    def start_update():
        return update.start_in_background(cfg)

    @app.post("/shutdown", summary="Stop the program")
    def shutdown():
        """Used by `efactura stop` before an update replaces the program's files. It exists
        only here, with the key: the page has no way to reach it."""
        stop = getattr(app.state, "stop", None)  # put there by `efactura serve`
        if stop:
            stop()
        return {"ok": True, "stopping": stop is not None}

    app.include_router(router)  # for other programs, with the key
    app.include_router(router, prefix=PAGE_API_PREFIX, include_in_schema=False)  # for the page

    if cfg.demo:

        @app.get(DEMO_LOGIN_PATH, include_in_schema=False)
        def demo_anaf_login():
            """What ANAF's login page would send the browser back with, for the demo."""
            return RedirectResponse(f"{cfg.redirect_uri}?code=demo-{int(time.time())}")

    # --- the page ---

    @app.get("/", include_in_schema=False)
    def to_the_page():
        return RedirectResponse(PAGE_PREFIX + "/")

    if (ui_dir / "index.html").is_file():
        app.mount(PAGE_PREFIX, StaticFiles(directory=ui_dir, html=True), name="page")
    else:

        @app.get(PAGE_PREFIX + "/{rest:path}", include_in_schema=False)
        def page_not_built(rest: str):
            raise EfacturaError(
                NOT_FOUND,
                "The page has not been built yet. Run: pnpm --dir frontend build "
                "(or, while developing: uv run efactura dev).",
            )

    return app


def dev_app() -> FastAPI:
    """The app as `efactura dev` runs it: built again each time the code changes.
    The settings file is the one named in EFACTURA_CONFIG (set by the dev command)."""
    cfg = load_config()
    configure_logging(cfg)
    return create_app(cfg, port=int(os.environ.get("EFACTURA_API_PORT") or cfg.api_port))
