"""Terminal commands. Each prints one JSON document and sets the exit code:
0 success, 3 login needed, 1 any other failure."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path, PureWindowsPath

from . import __version__, backup, background, demo, journal, schedule, update
from .anaf import TYPE_PREFIXES
from .config import Config, load_config, page_address
from .errors import (
    CONFIG_ERROR,
    INTERNAL_ERROR,
    INVALID_INPUT,
    LOGIN_CODE_EXPIRED,
    LOGIN_NEEDED,
    UPDATE_ERROR,
    EfacturaError,
)
from .service import COST_GROUPS, STATUSES, Service, configure_logging

log = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_LOGIN_NEEDED = 3
LOGIN_ATTEMPTS = 3

LOGIN_STEPS = """\
Logging in to ANAF (plug in the USB token first):
  1. ANAF's login page opens in the browser. Choose your certificate and type the PIN.
  2. The browser then shows an error page ("can't reach this page"). That is expected.
  3. Copy the whole address from the address bar (it contains "?code=") and paste it
     below within one minute.
If the browser did not open, open this address yourself:
  {url}
"""


PAGE_PATH = "/ui/"
DEV_PAGE_PORT = 5173  # Vite's dev server, see frontend/vite.config.ts
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
OPEN_DELAY = 1.5  # seconds: the server has to be listening before the browser asks


def started_through_the_launcher(system: str | None = None, started_as: str | None = None) -> bool:
    """On Windows, was this started through efactura.exe (which `uv run efactura` does too)
    and not as `python -m efactura`?

    The launcher hands Python the .exe itself as the script to run, so the file is in use for
    as long as the command lasts. Started as a module, the script is `__main__.py`."""
    system = os.name if system is None else system
    started_as = sys.argv[0] if started_as is None else started_as
    return system == "nt" and PureWindowsPath(started_as).name.lower() != "__main__.py"


# The functions below are replaced in tests.
def build_service(cfg: Config) -> Service:
    return Service(cfg)  # on demo settings it takes the stand-ins by itself


def open_browser(url: str) -> None:
    webbrowser.open(url)


def show_in_a_box(text: str) -> None:
    """Say something to the person when there is no window to print in: a shortcut started
    the command. Windows only; elsewhere the log has it."""
    if os.name == "nt":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, text, "AutoSaga", 0x10)  # 0x10: the stop sign


def open_page_soon(url: str) -> None:
    threading.Timer(OPEN_DELAY, open_browser, [url]).start()


def run_server(cfg: Config, port: int) -> None:
    import uvicorn

    from .api import create_app

    app = create_app(cfg, port=port)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    app.state.stop = lambda: setattr(server, "should_exit", True)  # what POST /shutdown calls
    stopped = threading.Event()
    threading.Thread(target=_bring_saga_files_up_to_date, args=(cfg,), daemon=True).start()
    threading.Thread(target=_keep_house_until, args=(cfg, stopped), daemon=True).start()
    threading.Thread(target=_download_on_schedule_until, args=(cfg, stopped), daemon=True).start()
    try:
        server.run()
    finally:
        stopped.set()


def _bring_saga_files_up_to_date(cfg: Config) -> None:
    """Beside the server, once, as the program starts: the files for SAGA are made to say
    what the database says. They may not after an update (an earlier version wrote them
    another way), after a backup was put back, or when the PC went off in the middle."""
    try:
        with journal.trace(fresh=True):
            Service(cfg).write_saga_files()
    except Exception:  # this thread has nobody above it, and the page must start all the same
        log.exception("The files for SAGA could not be brought up to date at the start")


FIRST_HOUSEKEEPING = 60  # seconds after the program starts
HOUSEKEEPING_EVERY = 15 * 60


def _keep_house_until(cfg: Config, stopped: threading.Event) -> None:
    """Beside the server: the daily backup and the journal's clean-up, looked at soon after
    the program starts (a PC that was off overnight is behind) and every quarter of an hour."""
    wait = FIRST_HOUSEKEEPING
    while not stopped.wait(wait):
        try:
            background.keep_house(cfg)
        except Exception:  # this thread has nobody above it: one bad round must not be the last
            log.exception("Housekeeping failed; it is tried again at the next round")
        wait = HOUSEKEEPING_EVERY


FIRST_SCHEDULE_LOOK = 30  # seconds after the program starts
SCHEDULE_LOOK_EVERY = 30


def _download_on_schedule_until(cfg: Config, stopped: threading.Event) -> None:
    """Beside the server: look at the schedule soon after the program starts (a moment may
    have passed while the PC was off) and every half minute, and download when one is due."""
    wait = FIRST_SCHEDULE_LOOK
    while not stopped.wait(wait):
        try:
            schedule.run_if_due(cfg)
        except Exception:  # run_if_due does not raise; this thread has nobody above it all the same
            log.exception("Looking at the schedule failed; it is looked at again soon")
        wait = SCHEDULE_LOOK_EVERY


def run_dev(cfg: Config, port: int) -> None:
    """For development: the API, restarted whenever the code changes, and the page's own
    dev server (Vite), which reloads the page as it is edited. Ctrl+C stops both."""
    import uvicorn

    pnpm = shutil.which("pnpm")
    if pnpm is None or not FRONTEND_DIR.is_dir():
        raise EfacturaError(
            CONFIG_ERROR, f"The dev command needs pnpm and the page's source in {FRONTEND_DIR}."
        )
    # The restarting API process and Vite's proxy both learn the port from here.
    os.environ["EFACTURA_API_PORT"] = str(port)
    page = subprocess.Popen([pnpm, "dev"], cwd=FRONTEND_DIR)
    try:
        uvicorn.run(
            "efactura.api:dev_app", factory=True, host="127.0.0.1", port=port,
            reload=True, reload_dirs=[str(Path(__file__).parent)], log_level="warning",
        )
    finally:
        page.terminate()
        page.wait(timeout=10)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):
        raise EfacturaError(INVALID_INPUT, f"{message} (see: efactura --help)")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="efactura",
        description="ANAF e-Factura sync. Every command prints one JSON document.",
    )
    parser.add_argument("--config", help="path to config.toml (default: ./config.toml)")
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")

    commands.add_parser("auth-status", help="is a login needed? contacts nothing")

    login = commands.add_parser("login", help="log in at the keyboard: browser, then paste the address")
    login.add_argument("--no-browser", action="store_true", help="only print the address")

    start = commands.add_parser("login-start", help="return the ANAF login address")
    start.add_argument("--open", action="store_true", help="also open it in the browser")

    finish = commands.add_parser("login-finish", help="save the login from the redirected address")
    finish.add_argument("address", help="the address the browser ended on (contains ?code=)")

    for name, text in (
        ("list", "what ANAF has, each marked new or saved; saves nothing"),
        ("sync", "fetch and save the messages not saved yet"),
    ):
        command = commands.add_parser(name, help=text)
        command.add_argument("cui", help="company CUI, with or without RO")
        command.add_argument("--days", type=int, help="days back, 1-60 (default: 7, widened after a gap)")
        if name == "sync":
            command.add_argument("--from", dest="start", help="first day, YYYY-MM-DD (instead of --days)")
            command.add_argument("--to", dest="end", help="last day, YYYY-MM-DD (default: today)")
            command.add_argument(
                "--no-classify", action="store_true",
                help="only save; these messages are never classified automatically",
            )

    commands.add_parser("sync-all", help="fetch and save for every client that is switched on")

    invoices = commands.add_parser("invoices", help="read saved messages from the database")
    invoices.add_argument("--cui")
    invoices.add_argument("--pending", action="store_true", help="only those not yet uploaded")
    invoices.add_argument("--type", choices=sorted(TYPE_PREFIXES), dest="message_type")
    invoices.add_argument("--since", help="saved on or after this date, YYYY-MM-DD")
    invoices.add_argument("--classification", choices=STATUSES, help="only those in this state")
    invoices.add_argument(
        "--new", action="store_true", dest="only_new",
        help="only received invoices from the latest sync, not yet uploaded",
    )

    classify = commands.add_parser("classify", help="give one saved invoice its account (cont)")
    classify.add_argument("id")
    classify.add_argument(
        "--force", action="store_true",
        help="also an invoice saved outside classification, or one already classified",
    )

    review = commands.add_parser("review", help="invoices a person must decide, with Jev's suggestion")
    review.add_argument("--cui")

    set_cont = commands.add_parser("set-cont", help="a person's decision for one invoice")
    set_cont.add_argument("id")
    decision = set_cont.add_mutually_exclusive_group(required=True)
    decision.add_argument("--accept", action="store_true", help="accept Jev's suggestion")
    decision.add_argument("--cont", help="the account to book the invoice on, e.g. 628 or 371.01")
    set_cont.add_argument("--force", action="store_true", help="also an invoice saved outside classification")
    set_cont.add_argument(
        "--line", type=int, help="only this line, on an invoice decided line by line (default: every line)"
    )

    confidence = commands.add_parser(
        "confidence", help="show, or set, the confidence below which Jev's answer goes to review"
    )
    confidence.add_argument("value", nargs="?", type=float, help="a number from 0 to 1")

    costs = commands.add_parser("costs", help="what the Jev calls have cost")
    costs.add_argument("--since", help="calls on or after this date, YYYY-MM-DD")
    costs.add_argument("--until", help="calls up to and including this date, YYYY-MM-DD")
    costs.add_argument("--group", choices=COST_GROUPS, default="month", help="how to break the cost down")
    costs.add_argument("--cui")

    invoice = commands.add_parser("invoice", help="one saved message")
    invoice.add_argument("id")
    invoice.add_argument("--xml", action="store_true", help="include the XML text")

    mark = commands.add_parser("mark-uploaded", help="set the uploaded flag")
    mark.add_argument("ids", nargs="+", metavar="id")
    mark.add_argument("--undo", action="store_true", help="clear the flag instead")

    serve = commands.add_parser("serve", help="start the page and the local REST API")
    serve.add_argument("--port", type=int)
    serve.add_argument("--open", action="store_true", help="also open the page in the browser")

    dev = commands.add_parser("dev", help="for development: API and page, both reloading on change")
    dev.add_argument("--port", type=int)

    setup = commands.add_parser("setup", help="write the first config.toml, once (used by the installer)")
    setup.add_argument("--port", type=int, help="default: 8765, or the next free port after it")
    made_up = commands.add_parser("demo", help="start the program on made-up data, building it first if needed")
    made_up.add_argument("--fresh", action="store_true", help="build the demo again, dropping what was done in it")
    made_up.add_argument("--port", type=int, help="default: the one in the demo's settings")
    commands.add_parser("start", help="run the program in the background, unless it already runs")
    commands.add_parser("open", help="start it if needed, then open the page in the browser")
    commands.add_parser("stop", help="stop the program running in the background")
    commands.add_parser("backup", help="make a backup of the database now, in the chosen folder")
    put_back = commands.add_parser("restore", help="replace the database with a backup")
    put_back.add_argument("name", help="the file name of a backup in the backup folder")
    newer = commands.add_parser("update", help="move this installed copy to the newest release")
    newer.add_argument("--check", action="store_true", help="only say whether a newer release exists")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        config_path = Path(args.config or os.environ.get("EFACTURA_CONFIG") or "config.toml").resolve()
        if args.command == "setup":  # the one command that runs before there are settings
            _emit(background.first_settings(config_path, args.port))
            return EXIT_OK
        if args.command == "demo":  # also before there are settings: it makes its own
            return _run_demo(args)
        cfg = load_config(args.config)
        if args.config:  # so a restarted dev server reads the same settings file
            os.environ["EFACTURA_CONFIG"] = str(Path(args.config).resolve())
        configure_logging(cfg)
        with journal.trace():  # everything this command writes in the journal belongs together
            result = _dispatch(args, cfg, config_path)
    except EfacturaError as exc:
        _emit(exc.to_dict())
        if sys.stdout is None:
            # A shortcut started this, so nobody saw that reply. Without this, a double
            # click on the Desktop would simply do nothing.
            log.error("%s", exc.message)
            show_in_a_box(f"AutoSaga nu a putut porni.\n\nDetalii tehnice: {exc.message}")
        return EXIT_LOGIN_NEEDED if exc.code == LOGIN_NEEDED else EXIT_FAILURE
    except Exception as exc:  # a bug: still answer in JSON, keep the traceback in the log
        log.exception("Unexpected failure")
        _emit(EfacturaError(INTERNAL_ERROR, f"{type(exc).__name__}: {exc}").to_dict())
        return EXIT_FAILURE
    if result is not None:
        _emit(result)
    return EXIT_OK


def _demo_config(fresh: bool) -> Config:
    """The demo's settings, building the demo first when it is missing or cannot be trusted."""
    folder = demo.FOLDER  # read here, not at import: a test points it elsewhere
    if not fresh:
        try:
            cfg = load_config(folder / "config.toml")
            if cfg.demo:
                return cfg
        except EfacturaError as exc:
            if exc.code != CONFIG_ERROR:
                raise
        # Settings that do not say demo, or say it over data without the marker, are a folder
        # left by an earlier version: started as they are, they would reach the real ANAF.
    return demo.build(folder)


def _run_demo(args: argparse.Namespace) -> int:
    cfg = _demo_config(args.fresh)
    os.environ["EFACTURA_CONFIG"] = str(demo.FOLDER / "config.toml")  # so a restarted dev server reads the same settings
    configure_logging(cfg)
    port = args.port or cfg.api_port
    address = f"http://127.0.0.1:{port}"
    said = {"listening": address, "routes": f"{address}/openapi.json"}
    if shutil.which("pnpm"):
        _emit({"ok": True, "page": f"http://localhost:{DEV_PAGE_PORT}{PAGE_PATH}", **said})
        run_dev(cfg, port)
    else:
        _emit({"ok": True, "page": page_address(port), **said,
               "note": "pnpm was not found, so the built page is served."})
        run_server(cfg, port)
    return EXIT_OK


def _dispatch(args: argparse.Namespace, cfg: Config, config_path: Path) -> dict | None:
    match args.command:
        case "start":
            return background.start(cfg, config_path)
        case "open":
            started = background.start(cfg, config_path)
            open_browser(started["page"])
            return started
        case "stop":
            return background.stop(cfg)
        case "backup":
            return backup.snapshot(cfg, "manual")
        case "restore":
            return backup.restore(cfg, args.name)
        case "update":
            if args.check:
                return update.status(cfg, check=True)
            if started_through_the_launcher():
                # Said here, before the program is stopped or a file is switched: left to run,
                # the update fails halfway, on "Access is denied" removing efactura.exe.
                raise EfacturaError(
                    UPDATE_ERROR,
                    "On Windows the update cannot be started through efactura.exe (or `uv run efactura`): "
                    "it has to replace that file, and Windows does not replace a program that is running. "
                    "Nothing was changed. Run update.bat in the program's folder, or: "
                    ".venv\\Scripts\\python.exe -m efactura update. "
                    'On the page, "Actualizează programul" does the same.',
                )
            return update.update(cfg)

    if args.command in ("serve", "dev"):
        cfg.require_api_key()
        port = args.port or cfg.api_port
        address = f"http://127.0.0.1:{port}"
        if args.command == "dev":
            page = f"http://localhost:{DEV_PAGE_PORT}{PAGE_PATH}"
            _emit({"ok": True, "page": page, "listening": address, "routes": f"{address}/openapi.json"})
            run_dev(cfg, port)
            return None
        page = page_address(port)
        _emit({"ok": True, "page": page, "listening": address, "routes": f"{address}/openapi.json"})
        if args.open:
            open_page_soon(page)
        journal.record("program", "program.started", f"The program started: version {__version__}, port {port}.",
                       version=__version__, port=port)
        run_server(cfg, port)
        journal.record("program", "program.stopped", "The program stopped.")
        return None

    service = build_service(cfg)
    try:
        match args.command:
            case "auth-status":
                return service.auth_status()
            case "login":
                return _login_at_keyboard(service, open_page=not args.no_browser)
            case "login-start":
                started = service.login_start()
                if args.open:
                    open_browser(started["authorize_url"])
                return started
            case "login-finish":
                return service.login_finish(args.address)
            case "list":
                return service.list_remote(args.cui, args.days)
            case "sync":
                return service.sync(
                    args.cui, args.days, classify=not args.no_classify, start=args.start, end=args.end
                )
            case "sync-all":
                return service.sync_all()
            case "invoices":
                return service.invoices(
                    args.cui, args.pending, args.message_type, args.since, args.classification,
                    args.only_new,
                )
            case "classify":
                return service.classify(args.id, force=args.force)
            case "review":
                return service.review(args.cui)
            case "set-cont":
                return service.set_cont(
                    args.id, cont=args.cont, accept=args.accept, force=args.force, line=args.line
                )
            case "confidence":
                if args.value is None:
                    return service.classification_settings()
                return service.set_min_confidence(args.value)
            case "costs":
                return service.costs(args.since, args.cui, args.until, args.group)
            case "invoice":
                return service.invoice(args.id, include_xml=args.xml)
            case "mark-uploaded":
                return service.mark_uploaded(args.ids, undo=args.undo)
    finally:
        service.close()


def _login_at_keyboard(service: Service, open_page: bool) -> dict:
    """Instructions and prompts go to standard error; standard output stays JSON only."""
    url = service.login_start()["authorize_url"]
    sys.stderr.write(LOGIN_STEPS.format(url=url))
    open_now = open_page
    for attempt in range(1, LOGIN_ATTEMPTS + 1):
        if open_now:
            open_browser(url)
        sys.stderr.write("Paste the address here and press Enter: ")
        sys.stderr.flush()
        address = sys.stdin.readline()
        if not address:
            raise EfacturaError(INVALID_INPUT, "No address was pasted.")
        try:
            return service.login_finish(address)
        except EfacturaError as exc:
            if exc.code not in (LOGIN_CODE_EXPIRED, INVALID_INPUT) or attempt == LOGIN_ATTEMPTS:
                raise
            sys.stderr.write(f"\n{exc.message}\n")
            # A bad paste can be retried with the same page; an expired code needs a new login.
            open_now = open_page and exc.code == LOGIN_CODE_EXPIRED


def _emit(document: dict) -> None:
    if sys.stdout is None:  # started without a window (pythonw.exe): nobody is reading
        return
    # ensure_ascii: Romanian letters become \u escapes, immune to the Windows console code page.
    sys.stdout.write(json.dumps(document, ensure_ascii=True, indent=2) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    sys.exit(main())
