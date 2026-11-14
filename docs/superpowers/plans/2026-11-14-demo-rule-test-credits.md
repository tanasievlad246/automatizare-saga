# Demo setup, rule test screen, menu foot and login without the browser — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One command that runs the program on made-up data with stand-ins for ANAF and Jev; a screen that classifies a trial invoice the way a real one is classified; a version check and an author line at the foot of the menu; and (gated) connecting to ANAF with the Windows certificate, without the browser.

**Architecture:** The stand-ins the tests already use move into the package, and a `[demo]` flag in the settings makes every `Service` talk to them instead of the network. The rule test is one service method that builds an invoice in memory and runs the same functions the real path runs. The menu foot is page work on top of a small change to the update status. The certificate login is a helper process on Windows whose answer goes through the existing `login_finish`.

**Tech Stack:** Python 3.11+ with `uv` (FastAPI, httpx, SQLite, pytest); React 19 + TypeScript + Tailwind 4 + shadcn/ui + TanStack Query 5, vitest; Windows PowerShell 5.1 for Tasks 8 and 10.

**Spec:** `docs/superpowers/specs/2026-11-14-demo-rule-test-credits-design.md`. Every Romanian text for the screen is quoted there and is used as written.

## Global Constraints

- Backend tests: `uv run pytest -q` (795 pass before Task 1). Page tests: `pnpm --dir frontend test` (67 pass), `pnpm --dir frontend exec tsc -b --noEmit` (clean), `pnpm --dir frontend lint` (exactly 3 old `only-export-components` warnings).
- Test first: write the test, run it, see it fail for the stated reason, then write the code.
- Text on screen is Romanian, formal ("dumneavoastră"), with ș ț ă â î. Identifiers, comments, log lines and the program's error messages are English. Comments say why, in plain words.
- `service.py`: one method per operation, returning a dict that starts `{"ok": True, ...}`. Failures are `EfacturaError(code, message)` from `efactura.errors`. `api.py` and `cli.py` stay thin.
- Nothing that holds a key, token, password or PIN is logged or written to the journal.
- Do not run `pnpm --dir frontend build` before Task 9: the built page is committed (`src/efactura/ui/`) and is rebuilt once.
- Do not edit `demo/` by hand (it is ignored by git and made by code), `install.ps1`, or the files of release 0.3.0's journal/backup code unless a task names them.
- Commit at the end of each task, on the branch the work is on. End each commit message with the line `Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>`. Never push.
- Task 10 was gated on the owner's run of the helper's steps on the Windows PC. The gate was passed on 2026-11-15; Task 10 rebuilds the page at its end.

## Review Focus

1. **Demo mode, the real network and real data.** A request to any host other than `logincert.anaf.ro`, `api.anaf.ro` and `openrouter.ai` in demo mode must be refused by the stand-in; settings that ask for demo over a data folder the demo builder did not make must be refused; an ordinary copy must never get the stand-in. Pinned in Task 2 (`test_settings_that_ask_for_demo_over_a_real_data_folder_are_refused`) and Task 3 (`test_demo_never_reaches_past_its_three_hosts`, `test_an_ordinary_app_has_no_demo_address`).
2. **Numbers typed by a person.** "28,50", "", " 20 ", "abc", a negative quantity, 51 lines: a sensible answer or `invalid_input`, never a 500. Pinned in Task 5 (`test_numbers_as_people_type_them`) and Task 6 (`trialInvoice.test.ts`).
3. **Rules for one client.** With no client chosen only the rules for every client apply; with a client chosen, that client's rules too. Pinned in Task 5 (`test_a_rule_for_one_client_applies_only_when_that_client_is_chosen`).
4. **The cost of a test.** A Jev call from the rule test is in the totals and the list of "Costuri Jev" with and without a client filter, is never counted as an invoice, and does not raise the average cost per invoice. Pinned in Task 5 (`test_nothing_is_saved_but_the_cost`, `test_a_trial_is_in_the_total_but_not_in_the_average_per_invoice`).
5. **Looking for a version where it cannot be found.** A development copy with no network, and a folder that is not a clone: a sentence, not a crash. Pinned in Task 7 (`test_a_development_copy_that_cannot_reach_the_remote_says_so`, `test_a_folder_that_is_not_a_clone_says_so`).

---

### Task 1: The stand-ins move into the package

**Files:**
- Create: `src/efactura/standins.py`
- Modify: `tests/helpers.py`, `scripts/seed_demo.py:18-25`
- Test: `tests/test_standins.py`

**Interfaces:**
- Produces: `efactura.standins.FakeAnaf`, `FakeOpenRouter`, `rich_invoice_xml`, `line`, `adjustment`, `invoice_xml`, `make_zip`, `SIGNATURE`, with the signatures they have in `tests/helpers.py` today. New: `FakeOpenRouter.valid_keys = None` accepts any key.

- [ ] **Step 1: Write the failing test**

```python
import httpx

import helpers
from efactura import jev, standins


def test_the_tests_and_the_program_share_one_set_of_stand_ins():
    for name in ("FakeAnaf", "FakeOpenRouter", "rich_invoice_xml", "line", "adjustment", "invoice_xml", "make_zip"):
        assert getattr(helpers, name) is getattr(standins, name)


def test_the_jev_stand_in_can_be_told_to_accept_any_key():
    openrouter = standins.FakeOpenRouter()
    openrouter.valid_keys = None
    request = {"model": "m", "state": {"linii": [{"descriere": "ciment"}]}, "questions": {}}
    with openrouter.client() as http:
        assert jev.ask(http, "any key at all", request).ok
```

- [ ] **Step 2: Run it** — `uv run pytest tests/test_standins.py -q`. Expected: FAIL, `No module named 'efactura.standins'` (or `cannot import name 'standins'`).
- [ ] **Step 3: Move the code.** Cut `SIGNATURE`, `invoice_xml`, `make_zip`, `FakeAnaf`, `_eroare`, `line`, `adjustment`, `rich_invoice_xml`, `FakeOpenRouter` and the private helpers only they use from `tests/helpers.py` into `src/efactura/standins.py`, unchanged, under a module docstring that says these answer like ANAF and OpenRouter for the tests and for demo mode. In `tests/helpers.py` import them back by name so every `from helpers import …` in the tests still works. In `FakeOpenRouter.handle` the key check becomes "refused only when `valid_keys` is not None and the key is not in it". `scripts/seed_demo.py` imports them from `efactura.standins` and drops its `sys.path.insert`.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: 797 passed.
- [ ] **Step 5: Commit** — `git add src/efactura/standins.py tests/helpers.py tests/test_standins.py scripts/seed_demo.py && git commit -m "Move the ANAF and Jev stand-ins into the package"`

### Task 2: A `[demo]` flag, and the demo data built by the package

**Files:**
- Create: `src/efactura/demo.py`
- Modify: `src/efactura/config.py` (the `Config` dataclass and `load_config`), `scripts/seed_demo.py`
- Test: `tests/test_demo.py`

**Interfaces:**
- Consumes: `efactura.standins` (Task 1).
- Produces: `Config.demo: bool` (default `False`). It is true when the file has `[demo]` with `enabled = true` **and** the data folder holds the marker file `demo.MARKER = "demo-data"`; the flag without the marker makes `load_config` raise `EfacturaError(CONFIG_ERROR, …)` saying the data folder was not made by `efactura demo`. `demo.FOLDER: Path` (`<project>/demo`). `demo.build(folder: Path, now: datetime | None = None) -> Config` — removes `folder`, writes `config.toml` (today's `CONFIG` text with `port = 8770` under `[api]`, plus `[demo]\nenabled = true`), makes the data folder with the marker in it, builds the database exactly as `scripts/seed_demo.py:main` does today, returns the loaded `Config`. `demo.JEV_ANSWERS`: the word table (`"ciment"`, `"hârtie"`, `"pungi"`, `"revizie"`) used for the data, as a module constant, in the shape `FakeOpenRouter.answer_for` takes.

- [ ] **Step 1: Write the failing tests**

```python
from efactura import demo, standins
from efactura.config import load_config
from efactura.service import Service


def test_the_demo_is_built_with_settings_that_say_demo_and_a_filled_database(tmp_path):
    cfg = demo.build(tmp_path / "demo")

    assert cfg.demo is True and cfg.path == tmp_path / "demo" / "config.toml"
    assert cfg.api_port == 8770 and (cfg.data_dir / demo.MARKER).is_file()
    desk = Service(cfg, http=standins.FakeAnaf().client())
    assert len(desk.clients()["clients"]) == 3
    assert len(desk.invoices()["invoices"]) >= 5
    assert desk.rule_suggestions()["count"] >= 1
    assert desk.auth_status()["state"] == "valid"


def test_building_again_starts_from_nothing(tmp_path):
    cfg = demo.build(tmp_path / "demo")
    (cfg.data_dir / "left-over.txt").write_text("x")

    demo.build(tmp_path / "demo")

    assert not (cfg.data_dir / "left-over.txt").exists()


def test_settings_are_demo_only_when_they_say_so(tmp_path):
    plain = tmp_path / "config.toml"
    plain.write_text('[api]\nkey = "k"\n', encoding="utf-8")
    off = tmp_path / "off.toml"
    off.write_text('[api]\nkey = "k"\n[demo]\nenabled = false\n', encoding="utf-8")

    assert load_config(plain).demo is False and load_config(off).demo is False


def test_settings_that_ask_for_demo_over_a_real_data_folder_are_refused(tmp_path):
    # Made-up invoices must never be written among real ones because of one line in a file.
    real = tmp_path / "config.toml"
    real.write_text('[api]\nkey = "k"\n[demo]\nenabled = true\n', encoding="utf-8")
    (tmp_path / "data").mkdir()

    with pytest.raises(EfacturaError) as refused:
        load_config(real)

    assert refused.value.code == "config_error" and "efactura demo" in refused.value.message
```

(`import pytest` and `from efactura.errors import EfacturaError` at the top of the file.)

- [ ] **Step 2: Run** `uv run pytest tests/test_demo.py -q`. Expected: FAIL, no module `efactura.demo`.
- [ ] **Step 3: Implement** `Config.demo` and its reading in `load_config`; `demo.build` by moving the body of `scripts/seed_demo.py:main` (with `CONFIG`, `CLIENTS`, `EARLIER`, `TODAY`, `BOOKED_BY_HAND`) into `src/efactura/demo.py`. `build` prints nothing. `scripts/seed_demo.py` becomes a wrapper that calls `demo.build(demo.FOLDER)` and prints the one line "Ready. Start it with: uv run efactura demo".
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: 801 passed. Run `uv run python scripts/seed_demo.py` once. Expected: it ends with the "Ready" line and `demo/config.toml` contains `[demo]`.
- [ ] **Step 5: Commit** — `git commit -m "Build the demo data from the package; a [demo] flag in the settings"`

### Task 3: In demo mode the program talks to the stand-ins

**Files:**
- Modify: `src/efactura/demo.py`, `src/efactura/api.py` (`create_app`, `OPEN_PATHS`), `src/efactura/cli.py:55` (`build_service`), `src/efactura/service.py` (`login_start`, and the method behind `GET /settings`)
- Test: `tests/test_demo.py`

**Interfaces:**
- Consumes: `demo.build`, `demo.JEV_ANSWERS`, `Config.demo` (Task 2).
- Produces: `demo.client(cfg: Config) -> httpx.Client` and `demo.service(cfg: Config) -> Service` (a `Service` on that client). The state file `cfg.data_dir / "standin.json"`. `GET /api/demo/anaf-login` (demo only, no key needed; under `/api` because the page's dev server passes on only that). `GET /settings` answers with `"demo": bool`. In demo, `login_start()["authorize_url"] == "/api/demo/anaf-login"`. `demo.JEV_ANSWERS` gains two words: `"nimic"` (Jev declines) and `"eroare"` (the call fails with status 500).

Behaviour the tests fix: each time the list is asked for a CUI the stand-in adds one or two new received invoices for it (alternating 1, 2, 1, …, per CUI), dated now (the invoice builder and `FakeAnaf.add` take the date and the CUI as new optional parameters; their defaults stay as they are), from a catalogue of at least six made-up suppliers with two or three lines each, and remembers them in the state file; a download returns the invoice for that id; any bearer token is accepted; a login code is accepted when it starts with `demo-`, and any refresh token renews; Jev answers from `demo.JEV_ANSWERS`, default 628 at 0.95, any key; any other host gets 404.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_demo.py`)

```python
import pytest
from fastapi.testclient import TestClient

from efactura.api import create_app
from efactura.errors import EfacturaError

KEY = {"X-API-Key": "EXEMPLU-cheie-locala"}
CLIENT = "12345674"


@pytest.fixture
def cfg(tmp_path):
    return demo.build(tmp_path / "demo")


def test_every_download_brings_one_or_two_new_invoices_and_they_are_remembered(cfg):
    first = demo.service(cfg).sync(CLIENT)
    second = demo.service(cfg).sync(CLIENT)  # a new Service each time, as each request makes one

    assert (first["new_count"], second["new_count"]) == (1, 2)
    assert (cfg.data_dir / "standin.json").is_file()


def test_demo_never_reaches_past_its_three_hosts(cfg):
    with demo.client(cfg) as http:
        assert http.get("https://example.com/").status_code == 404
        assert http.post("https://api.openai.com/v1/chat").status_code == 404


def test_the_demo_login_takes_a_demo_code_and_nothing_else(cfg):
    assert demo.service(cfg).login_finish("https://localhost/callback?code=demo-7")["state"] == "valid"
    with pytest.raises(EfacturaError):
        demo.service(cfg).login_finish("https://localhost/callback?code=abc")


def test_jev_in_the_demo_answers_whatever_key_is_set(cfg):
    demo.service(cfg).sync(CLIENT)  # the new invoices go through the rules and then to the stand-in Jev

    waiting = [each for each in demo.service(cfg).invoices(cui=CLIENT)["invoices"] if each["classification_status"] == "pending"]
    assert waiting == []  # none was left unanswered for want of a real key


def test_the_demo_app_uses_the_stand_ins_and_says_it_is_a_demo(cfg):
    api = TestClient(create_app(cfg))

    assert api.get("/settings", headers=KEY).json()["demo"] is True
    assert api.post("/auth/login/start", headers=KEY).json()["authorize_url"] == "/api/demo/anaf-login"
    sent = api.get("/api/demo/anaf-login", follow_redirects=False)  # no key: the browser opens it in a new tab
    assert sent.status_code == 307 and sent.headers["location"].startswith("https://localhost/callback?code=demo-")
    assert api.post("/sync", headers=KEY, json={"cui": CLIENT}).json()["new_count"] == 1


def test_an_ordinary_app_has_no_demo_address(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(f'[api]\nkey = "k"\n[anaf]\ntoken_file = \'{tmp_path / "tokens.json"}\'\n', encoding="utf-8")
    api = TestClient(create_app(load_config(path)))

    assert api.get("/settings", headers={"X-API-Key": "k"}).json()["demo"] is False
    assert api.get("/api/demo/anaf-login", headers={"X-API-Key": "k"}).status_code == 404


def test_two_words_make_the_demo_jev_decline_or_fail(cfg):
    from efactura import jev

    def asked(word):
        with demo.client(cfg) as http:
            request = {"model": "m", "state": {"linii": [{"descriere": f"Servicii {word}"}]}, "questions": {}}
            return jev.ask(http, "any key", request)

    assert asked("nimic").response["answers"]["cont"]["type"] == "refusal"
    assert asked("eroare").ok is False
```

- [ ] **Step 2: Run** `uv run pytest tests/test_demo.py -q`. Expected: the new tests FAIL (`module 'efactura.demo' has no attribute 'service'`).
- [ ] **Step 3: Implement.** In `demo.py`: a `FakeAnaf` subclass that loads and saves the state file and adds invoices when the list is asked; `client(cfg)` and `service(cfg)`. In `api.create_app`: `make_service = service_factory or (demo.service if cfg.demo else Service)`, the `/api/demo/anaf-login` route registered only when `cfg.demo` (a `RedirectResponse` to `cfg.redirect_uri + "?code=demo-<n>"`) and added to the open paths only then. `cli.build_service` likewise. `Service.login_start` gives `/api/demo/anaf-login` when `self.cfg.demo`. The settings answer gains `"demo": self.cfg.demo`.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: 808 passed.
- [ ] **Step 5: Commit** — `git commit -m "Demo mode: every Service talks to stand-ins for ANAF and Jev"`

### Task 4: `efactura demo`, and the label on the page

**Files:**
- Modify: `src/efactura/cli.py` (`_parser`, `main`), `README.md` (the "Trying it without ANAF" paragraph and the Commands table), `frontend/src/layout/AppShell.tsx`, `frontend/src/types.ts` (the settings type)
- Create: `frontend/src/layout/DemoLabel.tsx`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `demo.FOLDER`, `demo.build` (Task 2); `"demo"` in the settings answer (Task 3).
- Produces: the command `efactura demo [--fresh] [--port N]`. Like `setup`, it runs before any settings are loaded: builds `demo.FOLDER` (read when the command runs, so a test can point it elsewhere) when it is missing, when `--fresh` is given, or when the settings in it do not say demo (a folder left by an earlier version, which would otherwise be started against the real ANAF); the port is `--port` or the one in the demo's settings; sets `EFACTURA_CONFIG` to its `config.toml`, then calls `run_dev(cfg, port)` when `shutil.which("pnpm")` finds it, otherwise prints the same JSON `serve` prints plus `"note": "pnpm was not found, so the built page is served."` and calls `run_server(cfg, port)`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_cli.py`)

```python
def test_the_demo_command_builds_the_demo_once_and_starts_on_it(monkeypatch, tmp_path, capsys):
    from efactura import cli, demo

    started = []
    monkeypatch.setattr(demo, "FOLDER", tmp_path / "demo")
    monkeypatch.setattr(cli, "run_dev", lambda cfg, port: started.append(("dev", cfg.demo, port)))
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/pnpm")

    assert cli.main(["demo", "--port", "9100"]) == 0
    kept = tmp_path / "demo" / "data" / "kept.txt"
    kept.write_text("x")
    cli.main(["demo", "--port", "9100"])
    still_there = kept.exists()
    cli.main(["demo", "--fresh", "--port", "9100"])

    assert still_there and not kept.exists()
    assert started == [("dev", True, 9100)] * 3


def test_without_pnpm_the_demo_serves_the_built_page(monkeypatch, tmp_path, capsys):
    import json

    from efactura import cli, demo

    started = []
    monkeypatch.setattr(demo, "FOLDER", tmp_path / "demo")
    monkeypatch.setattr(cli, "run_server", lambda cfg, port: started.append(("serve", cfg.demo, port)))
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)

    cli.main(["demo", "--port", "9100"])

    said = json.loads(capsys.readouterr().out)
    assert started == [("serve", True, 9100)] and "pnpm" in said["note"] and said["page"].endswith(":9100/ui/")


def test_a_demo_folder_left_by_an_earlier_version_is_built_again(monkeypatch, tmp_path):
    from efactura import cli, demo

    old = tmp_path / "demo"
    (old / "data").mkdir(parents=True)
    (old / "config.toml").write_text('[api]\nkey = "k"\n', encoding="utf-8")  # says nothing of demo
    (old / "data" / "old.txt").write_text("x")
    started = []
    monkeypatch.setattr(demo, "FOLDER", old)
    monkeypatch.setattr(cli, "run_dev", lambda cfg, port: started.append((cfg.demo, port)))
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/bin/pnpm")

    cli.main(["demo"])

    assert started == [(True, 8770)] and not (old / "data" / "old.txt").exists()
```

- [ ] **Step 2: Run** `uv run pytest tests/test_cli.py -q -k demo`. Expected: FAIL, `invalid choice: 'demo'`.
- [ ] **Step 3: Implement** the command as the Interfaces block says.
- [ ] **Step 4: Run** `uv run pytest -q`. Expected: 811 passed.
- [ ] **Step 5: The label.** `DemoLabel` shows "Date de probă" (the page's attention colours, `title` = "Clienții și facturile sunt inventate. Nimic nu vine de la ANAF și nimic nu se plătește lui Jev."); `AppShell` renders it between the brand and the two chips when the settings it already reads say `demo`. Run `pnpm --dir frontend test`, `tsc -b --noEmit`, `lint`. Expected: 67 passed, clean, 3 warnings.
- [ ] **Step 6: README.** Replace the two commands under "Trying it without ANAF" with `uv run efactura demo`, say what works (each download brings one or two made-up invoices, the login is finished by pasting the address the browser ends on, Jev answers from a word table, with "nimic" and "eroare" on a line to see it decline or fail), what it does not cover (program updates, the Windows certificate login), why it cannot touch real data (the marker, its own folder, port 8770) and what it needs (`uv`; `pnpm` only to change the page). Add the `demo` row to the Commands table.
- [ ] **Step 7: Commit** — `git commit -m "efactura demo: one command for a working copy on made-up data"`

### Task 5: The rule test, in the program

**Files:**
- Modify: `src/efactura/service.py`, `src/efactura/api.py`, `src/efactura/store.py` (`_cost_summary`), `README.md` (the route table)
- Test: `tests/test_rule_test.py`

**Interfaces:**
- Produces:
  - `service.RULE_TEST = "rule-test"` — what stands in the `message_id` of a Jev call made from the rule test.
  - `Service.test_rules(self, *, lines: list[dict], supplier_name: str = "", supplier_cui: str = "", client_cui: str | None = None, currency: str = "RON", credit_note: bool = False, ask: str = "rules_then_jev") -> dict`. Each line: `{"description": str, "quantity": str, "unit_price": str, "seller_code": str | None, "barcode": str | None, "commodity_codes": list[str], "unit": str | None, "vat_percent": str | None}` (all but the first three optional). `unit`, `vat_percent`, `currency` and `credit_note` are what a trial started from a saved invoice carries, so that Jev is asked the same question as for that invoice.
  - It returns
    ```python
    {"ok": True,
     "decided_by": "rule" | "jev" | "nobody",
     "cont": str | None,                    # None: a real invoice would wait at "De verificat"
     "account_description": str | None,
     "deciding_line": str | None,           # the description of the largest line
     "rule": {"name": str, "line": int} | None,
     "jev": {"choice": str | None, "confidence": float | None, "threshold": float, "refused": bool,
             "probabilities": dict[str, float],          # every account Jev weighed, the chosen one included
             "cost_usd": float | None, "duration_ms": int, "error": str | None} | None,   # None: Jev was not asked
     "why_not": None | "no_lines" | "no_key" | "no_accounts" | "jev_failed" | "jev_declined" | "below_threshold",
     "reason": str,                         # in English, as the real path words it
     "suggestion": {"cont", "line", "words", "ticked", "supplier_cui", "supplier_name"} | None}
    ```
  - `POST /rules/test` with that JSON (`lines` required, the rest optional), answering the dict.
  - Journal: one `journal.record("rules", "rule.tested", …, decided_by=…, cont=…, asked_jev=bool, cost_usd=…)`.

- [ ] **Step 1: Write the failing tests**

```python
"""Classifying a trial invoice the way a real one is, and saving nothing but Jev's cost."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from efactura import journal
from efactura.api import create_app
from efactura.config import load_config
from efactura.errors import EfacturaError
from efactura.rules import Rule, Rulebook
from efactura.service import RULE_TEST, Service
from efactura.store import Store

from helpers import VALID_CUI, FakeAnaf, FakeOpenRouter, set_rulebook

NOW = datetime(2026, 11, 14, 9, 30, tzinfo=timezone(timedelta(hours=2)))
KEY = {"X-API-Key": "local-key"}
CIMENT = [{"description": "Ciment Portland 40 kg", "quantity": "20", "unit_price": "28.50"}]
MOTORINA = [{"description": "Motorina Euro 5", "quantity": "40", "unit_price": "7.20"}]
CONSULTANTA = [{"description": "Consultanta de specialitate", "quantity": "1", "unit_price": "900"}]


def settings(tmp_path, key='api_key = "or-test-key"'):
    path = tmp_path / "config.toml"
    path.write_text(
        f"[anaf]\nclient_id = \"id\"\nclient_secret = \"secret\"\ntoken_file = '{tmp_path / 'tokens.json'}'\n"
        f'[api]\nkey = "local-key"\n[openrouter]\n{key}\n', encoding="utf-8")
    return load_config(path)


@pytest.fixture
def cfg(tmp_path):
    cfg = settings(tmp_path)
    set_rulebook(cfg.db_path, Rulebook(
        accounts={"302": "Materiale consumabile", "6022": "Combustibil", "612": "Chirii", "628": "Alte servicii"},
        rules=(Rule("combustibil", "6022", keywords=("motorina",)),),
        instructions="Alege contul facturii.",
    ))
    return cfg


@pytest.fixture
def openrouter():
    answers = FakeOpenRouter()
    answers.answer_for("ciment", "302", confidence=0.93)
    answers.answer_for("consultanta", "628", confidence=0.61)
    return answers


@pytest.fixture
def desk(cfg, openrouter):
    anaf = FakeAnaf()
    anaf.openrouter = openrouter
    return Service(cfg, http=anaf.client(), now=lambda: NOW)


def test_a_rule_that_fits_decides_and_jev_is_not_asked(desk, openrouter):
    result = desk.test_rules(lines=MOTORINA, supplier_name="Rompetrol", supplier_cui="1860712")

    assert (result["decided_by"], result["cont"], result["account_description"]) == ("rule", "6022", "Combustibil")
    assert result["rule"] == {"name": "combustibil", "line": 1} and result["deciding_line"] == "Motorina Euro 5"
    assert result["jev"] is None and result["suggestion"] is None and openrouter.requests == []


def test_with_no_rule_fitting_jev_is_asked_and_its_account_stands(desk, openrouter):
    result = desk.test_rules(lines=CIMENT, supplier_name="Dedeman SRL", supplier_cui="2816464")

    assert (result["decided_by"], result["cont"], result["why_not"]) == ("jev", "302", None)
    asked = result["jev"]
    assert (asked["choice"], asked["confidence"], asked["threshold"], asked["refused"], asked["error"]) == ("302", 0.93, 0.8, False, None)
    assert asked["cost_usd"] == pytest.approx(0.00002) and len(openrouter.requests) == 1
    assert result["suggestion"]["cont"] == "302" and "ciment" in result["suggestion"]["words"]
    assert result["suggestion"]["supplier_name"] == "Dedeman SRL"


def test_jev_not_sure_enough_leaves_it_to_a_person(desk):
    result = desk.test_rules(lines=CONSULTANTA)

    assert (result["decided_by"], result["cont"], result["why_not"]) == ("nobody", None, "below_threshold")
    assert (result["jev"]["choice"], result["jev"]["confidence"]) == ("628", 0.61)
    assert result["suggestion"]["cont"] == "628"


def test_asking_jev_directly_skips_the_rules(desk, openrouter):
    result = desk.test_rules(lines=MOTORINA, ask="jev_only")

    assert (result["decided_by"], result["cont"], result["rule"]) == ("jev", "628", None)
    assert len(openrouter.requests) == 1
    assert result["suggestion"] is None  # a rule of the rulebook already fits this invoice


def test_what_a_saved_invoice_carries_reaches_jev(desk, openrouter):
    carried = [{"description": "Ciment Portland", "quantity": "20", "unit_price": "28.50", "unit": "KGM", "vat_percent": "9"}]

    desk.test_rules(lines=carried, currency="EUR", credit_note=True)

    asked = openrouter.requests[-1]["state"]  # `requests` holds the bodies the stand-in was sent
    assert asked["factura"]["moneda"] == "EUR" and asked["linii"][0]["um"] == "KGM"
    assert str(asked["linii"][0]["cota_tva"]).startswith("9")


def test_a_rule_for_one_client_applies_only_when_that_client_is_chosen(desk):
    desk.save_client(VALID_CUI, "Alfa Construct SRL")
    desk.save_rule(name="chirie", cont="612", keywords=["chirie"], client_cui=VALID_CUI)
    rent = [{"description": "Chirie birou noiembrie", "quantity": "1", "unit_price": "2000"}]

    assert desk.test_rules(lines=rent, client_cui=VALID_CUI)["decided_by"] == "rule"
    assert desk.test_rules(lines=rent)["decided_by"] == "jev"  # the general rules only


def test_nothing_is_saved_but_the_cost(desk, cfg):
    desk.test_rules(lines=CIMENT, client_cui=VALID_CUI)

    assert desk.invoices()["invoices"] == [] and desk.rule_suggestions()["count"] == 0
    assert not cfg.saga_dir.exists() or not any(cfg.saga_dir.rglob("*.xml"))
    for costs in (desk.costs(since="2026-01-01"), desk.costs(since="2026-01-01", cui=VALID_CUI)):
        assert (costs["calls"], costs["invoices"]) == (1, 0) and costs["cost_usd"] == pytest.approx(0.00002)
    (call,) = desk.jev_calls()["calls"]
    assert (call["message_id"], call["cui"], call["choice"]) == (RULE_TEST, VALID_CUI, "302")


def test_a_trial_is_in_the_total_but_not_in_the_average_per_invoice(desk, cfg):
    store = Store(cfg.db_path)
    for message_id, cost in (("3001", 0.5), (RULE_TEST, 0.25)):
        store.add_jev_call(
            message_id=message_id, cui=VALID_CUI, called_at=NOW.isoformat(), model="m", request_json="{}",
            response_json=None, http_status=200, input_tokens=1, output_tokens=1, cost_usd=cost, duration_ms=5, error=None,
        )
    store.close()

    costs = desk.costs(since="2026-01-01")

    assert (costs["calls"], costs["invoices"]) == (2, 1) and costs["cost_usd"] == pytest.approx(0.75)
    assert costs["average_cost_per_invoice_usd"] == pytest.approx(0.5)


@pytest.mark.parametrize("change, why", [
    ({"lines": []}, "no_lines"),
    ({"lines": [{"description": "  ", "quantity": "1", "unit_price": "1"}]}, "no_lines"),
])
def test_an_invoice_with_nothing_on_it_is_not_sent_anywhere(desk, openrouter, change, why):
    result = desk.test_rules(**change)

    assert (result["decided_by"], result["why_not"], result["jev"]) == ("nobody", why, None) and openrouter.requests == []


def test_without_a_key_or_accounts_jev_cannot_be_asked(tmp_path, openrouter):
    no_key = Service(settings(tmp_path, key=""), http=FakeAnaf().client(), now=lambda: NOW)
    set_rulebook(no_key.cfg.db_path, Rulebook(accounts={"302": "Materiale"}, rules=(), instructions="."))
    assert no_key.test_rules(lines=CIMENT)["why_not"] == "no_key"

    (tmp_path / "second").mkdir()
    no_accounts = Service(settings(tmp_path / "second"), http=FakeAnaf().client(), now=lambda: NOW)
    set_rulebook(no_accounts.cfg.db_path, Rulebook(accounts={}, rules=(), instructions="."))
    assert no_accounts.test_rules(lines=CIMENT)["why_not"] == "no_accounts"


def test_a_jev_that_fails_is_reported_at_once_not_tried_again(desk, openrouter):
    openrouter.fail_with = ["unreachable", "unreachable"]

    result = desk.test_rules(lines=CIMENT)

    assert (result["decided_by"], result["why_not"]) == ("nobody", "jev_failed")
    assert result["jev"]["error"] and len(openrouter.fail_with) == 1  # one attempt used, one left


def test_numbers_as_people_type_them(desk):
    typed = [{"description": "Ciment", "quantity": " 20 ", "unit_price": "28,50"}]
    assert desk.test_rules(lines=typed)["decided_by"] == "jev"

    for bad in (
        [{"description": "Ciment", "quantity": "abc", "unit_price": "1"}],
        [{"description": "Ciment", "quantity": "", "unit_price": "1"}],
        [{"description": "x" * 501, "quantity": "1", "unit_price": "1"}],
        CIMENT * 51,
    ):
        with pytest.raises(EfacturaError) as refused:
            desk.test_rules(lines=bad)
        assert refused.value.code == "invalid_input"
    with pytest.raises(EfacturaError):
        desk.test_rules(lines=CIMENT, ask="something else")


def test_the_route_and_the_journal(cfg, desk):
    api = TestClient(create_app(cfg, service_factory=lambda cfg: desk))

    reply = api.post("/rules/test", headers=KEY, json={"lines": MOTORINA, "client_cui": None})

    assert reply.status_code == 200 and reply.json()["decided_by"] == "rule"
    tested = [line for line in journal.events(cfg.db_path)["events"] if line["event"] == "rule.tested"]
    assert tested[0]["data"]["decided_by"] == "rule" and tested[0]["data"]["asked_jev"] is False
```

`test_the_route_and_the_journal` hands the app one `Service` for every request; the app closes it after the request, so make only the one request in that test.

- [ ] **Step 2: Run** `uv run pytest tests/test_rule_test.py -q`. Expected: FAIL at import, `cannot import name 'RULE_TEST'`.
- [ ] **Step 3: Implement `Service.test_rules`.** Build `Invoice` / `Party` / `Line` (from `efactura.invoice`) directly: number `"PROBA"`, currency `"RON"`, the supplier's CUI through `normalize_cui` when one is given, line numbers from 1, `value = quantity * unit_price`, lines with a blank description dropped, a decimal comma read as a point. Order, as `_classify_one` has it: the rules (unless `ask == "jev_only"`), then no lines, no key, no accounts, then `jev_request` → `jev.ask` once → `store.add_jev_call(message_id=RULE_TEST, cui=client_cui, …)` → `read_jev_answer` → the level from `_min_confidence(store)`. A failed call or an unreadable answer is `"jev_failed"` with the text in `jev["error"]`. `jev["probabilities"]` is `JevAnswer.probabilities`. `suggestion`: take the dict-building lines of `_rule_suggestion` out into a helper both use; it is `None` when a rule of the rulebook fits the invoice (whether or not the rules were asked), when there is no account to propose, or when `propose` gives nothing.
- [ ] **Step 4: The cost summary.** In `store._cost_summary` (and wherever invoices are counted for the periods) a row whose `message_id` is `'rule-test'` is not an invoice; and `average_cost_per_invoice_usd` in `Service.costs` divides the cost of the calls that belong to invoices, not the whole total, by the number of invoices.
- [ ] **Step 5: The route** in `api.py` (a pydantic model with the fields of the Interfaces block) and its row in the README's route table.
- [ ] **Step 6: Run** `uv run pytest -q`. Expected: 826 passed.
- [ ] **Step 7: Commit** — `git commit -m "Test the rules: classify a trial invoice as a real one, saving only Jev's cost"`

### Task 6: The rule test, on the screen

**Files:**
- Create: `frontend/src/rules/test/RuleTestPage.tsx`, `TrialInvoiceForm.tsx`, `TrialAnswer.tsx`, `SavedInvoicePicker.tsx`, `trialInvoice.ts`, `trialInvoice.test.ts`, `trialAnswer.ts`, `trialAnswer.test.ts`; `frontend/src/rules/ProposedRuleCardBody.tsx`
- Modify: `frontend/src/App.tsx` (route `reguli/test`), `frontend/src/rules/RulesPage.tsx` (the button), `frontend/src/rules/ProposedRuleCard.tsx` (becomes a thin wrapper around `ProposedRuleCardBody`), `frontend/src/api.ts`, `frontend/src/types.ts`, `frontend/src/costs/JevCallsTable.tsx`, `frontend/src/journal/eventTexts.ts` (+ its test), `frontend/src/layout/AppShell.tsx` (the menu entry stays marked on `/reguli/test`)

**Interfaces:**
- Consumes: `POST /rules/test` and its answer (Task 5); `api.receivedInvoices(cui)`, the invoice view (`InvoiceView.document`), `RuleDialog`'s `draft` prop, `ruleFromProposal`.
- Produces:
  - `types.ts`: `TrialLine = { description: string; quantity: string; unitPrice: string; sellerCode: string; barcode: string; commodityCodes: string; unit: string | null; vatPercent: string | null }`, `TrialInvoice = { clientCui: string | null; supplierName: string; supplierCui: string; currency: string; creditNote: boolean; startedFrom: string | null; lines: TrialLine[] }` (`unit`, `vatPercent`, `currency`, `creditNote` are carried from a saved invoice and not shown; `startedFrom` is that invoice's number, for the sentence under the form), `RuleTestResult` mirroring the answer.
  - `trialInvoice.ts`: `EMPTY: TrialInvoice` (one blank line), `EXAMPLES: { materiale: TrialInvoice; combustibil: TrialInvoice }`, `toRequest(trial: TrialInvoice, ask: 'rules_then_jev' | 'jev_only')` (the JSON for the route), `fromDocument(view: InvoiceView): TrialInvoice`.
  - `trialAnswer.ts`: `describeAnswer(result: RuleTestResult, ask): { tone: 'done' | 'attention'; title: string; subtitle: string; label: string | null; sentences: string[]; technical: string | null }`.
  - `api.testRules(body)`.
  - `ProposedRuleCardBody`: everything the card on an invoice's screen shows and does (words or supplier, how the rule would have done, "Creează regula"), taking `{ suggestion: RuleSuggestion; onNotNow: () => void }` and no saved invoice. `ProposedRuleCard` keeps its props and passes an `onNotNow` that remembers the refusal; the test screen passes one that only hides the card.

- [ ] **Step 1: Write the failing tests.** `trialInvoice.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { EMPTY, EXAMPLES, fromDocument, toRequest } from './trialInvoice'

const line = (description: string, quantity: string, unitPrice: string) =>
  ({ description, quantity, unitPrice, sellerCode: '', barcode: '', commodityCodes: '', unit: null, vatPercent: null })

describe('a trial invoice', () => {
  it('is sent with numbers the program can read', () => {
    const sent = toRequest({ ...EMPTY, clientCui: '12345674', supplierName: ' Dedeman SRL ', supplierCui: '2816464', lines: [line('Ciment', ' 20 ', '28,50')] }, 'rules_then_jev')
    expect(sent).toEqual({
      client_cui: '12345674', supplier_name: 'Dedeman SRL', supplier_cui: '2816464', currency: 'RON', credit_note: false, ask: 'rules_then_jev',
      lines: [{ description: 'Ciment', quantity: '20', unit_price: '28.50', seller_code: null, barcode: null, commodity_codes: [], unit: null, vat_percent: null }],
    })
  })

  it('leaves out the rows nothing was written on, and splits the codes', () => {
    const sent = toRequest({ ...EMPTY, lines: [line('', '', ''), { ...line('Adeziv', '6', '41'), commodityCodes: '32141010, 3214' }] }, 'jev_only')
    expect(sent.lines).toHaveLength(1)
    expect(sent.lines[0].commodity_codes).toEqual(['32141010', '3214'])
    expect(sent.client_cui).toBeNull()
  })

  it('starts from a saved invoice', () => {
    // The page's copy of an invoice has no codes on its lines, so those stay blank. The unit,
    // the VAT rate and the currency are carried, so Jev is asked what it was asked for that invoice.
    const trial = fromDocument({
      invoice: { cui: '12345674' },
      document: {
        number: 'FV-1042', currency: 'EUR', is_credit_note: false, supplier: { name: 'Dedeman SRL', cui: 'RO2816464' },
        lines: [{ number: 1, description: 'Ciment', unit_name: 'KGM', quantity: '20', unit_price: '28.5', vat_percent: '9' }],
      },
    } as never)
    expect(trial).toEqual({
      clientCui: '12345674', supplierName: 'Dedeman SRL', supplierCui: 'RO2816464', currency: 'EUR', creditNote: false, startedFrom: 'FV-1042',
      lines: [{ description: 'Ciment', quantity: '20', unitPrice: '28,5', sellerCode: '', barcode: '', commodityCodes: '', unit: 'KGM', vatPercent: '9' }],
    })
  })

  it('has two examples, each with something on it', () => {
    expect(EXAMPLES.materiale.lines.length).toBeGreaterThan(0)
    expect(EXAMPLES.combustibil.lines[0].description).toMatch(/motorin/i)
  })
})
```

`trialAnswer.test.ts` — one case per outcome of the spec's "The answer" list, asserting the exact strings quoted there, for example:

```ts
it('says a rule decided and Jev was not asked', () => {
  const said = describeAnswer({ decided_by: 'rule', cont: '6022', account_description: 'Combustibil', deciding_line: 'Motorină Euro 5',
    rule: { name: 'combustibil', line: 1 }, jev: null, why_not: null, reason: '', suggestion: null } as never, 'rules_then_jev')
  expect(said).toMatchObject({ tone: 'done', title: 'Contul 6022', subtitle: 'Combustibil', label: 'Ales de o regulă' })
  expect(said.sentences).toEqual(['Regula dumneavoastră „combustibil”, pentru rândul „Motorină Euro 5”.', 'Jev nu a fost întrebat, deci nu a costat nimic.'])
})
```

with the same for: Jev decided (both buttons' first sentence, and the "S-a gândit și la: …" sentence only when other accounts have a probability), below the threshold, Jev declined, and each of `no_lines`, `no_key` (two sentences), `no_accounts`, `jev_failed` (the last with `technical` set to Jev's error).

- [ ] **Step 2: Run** `pnpm --dir frontend test`. Expected: the two new files fail to load (`Cannot find module './trialInvoice'`).
- [ ] **Step 3: Implement** `trialInvoice.ts` and `trialAnswer.ts` until both pass.
- [ ] **Step 4: The screen**, laid out as the artboard "Testează regulile": the form card on the left, the answer and the proposed rule on the right, one column in a narrow window. The client list's first choice, the saved-invoice window, the hint while no client is chosen, the sentence under a form started from a saved invoice, and the texts of the two buttons while an answer is awaited are the ones in the spec's section 2. An error from the route is shown with the page's `ErrorNotice`. The proposed rule is `ProposedRuleCardBody`; after a rule is created the queries a rule changes are reloaded, as the card already does.
- [ ] **Step 5: The other places.** `RulesPage`: a button "Testează regulile" beside the title, linking to `/reguli/test`. `JevCallsTable`: a call whose `message_id` is `rule-test` shows "Probă de reguli" in place of the link, and "—" for the client when none was chosen. `eventTexts.ts`: `rule.tested` → "A fost încercată o factură de probă: contul {cont}, ales de o regulă." / "…, ales de Jev." / "A fost încercată o factură de probă: nu a primit niciun cont." (with tests).
- [ ] **Step 6: Run** `pnpm --dir frontend test`, `tsc -b --noEmit`, `lint`. Expected: all pass, clean, 3 warnings.
- [ ] **Step 7: Commit** — `git commit -m "The screen for testing the rules on a trial invoice"`

### Task 7: The foot of the menu

**Files:**
- Modify: `src/efactura/update.py` (`status`, `_why_not_updatable`), `frontend/src/layout/ProgramVersion.tsx`, `frontend/src/layout/programUpdate.ts` (+ `programUpdate.test.ts`), `frontend/src/layout/AppShell.tsx`, `frontend/src/types.ts` (`UpdateStatus`)
- Create: `frontend/src/layout/Credits.tsx`, `frontend/src/layout/credits.ts`
- Test: `tests/test_update.py`, `frontend/src/layout/programUpdate.test.ts`

**Interfaces:**
- Produces: `update.status(...)` gains `"why_not_kind": None | "development" | "not_a_clone"` and, with `check=True`, asks the remote for the newest release whenever the folder is a git clone (updatable or not). `whatTheLookFound(status: UpdateStatus): string` returns the sentences of the spec's section "3 and 4". `ProgramVersion` takes `{ status, onUpdate }`. `credits.ts`: `AUTHOR = 'Tanasie Vlad-Cristian'`, `AUTHOR_EMAIL = 'tanasievladcristian@gmail.com'`, `SINCE = 2026`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_update.py`)

```python
def test_a_development_copy_can_still_look_for_the_newest_release(installed):
    installed.release("0.2.0")
    git(installed.project, "checkout", "-q", "-b", "work")

    found = update.status(installed.cfg, check=True, project=installed.project, now=NOW)

    assert (found["can_update"], found["update_available"]) == (False, False)
    assert (found["latest_release"], found["why_not_kind"], found["check_error"]) == ("v0.2.0", "development", None)


def test_a_development_copy_that_cannot_reach_the_remote_says_so(installed):
    git(installed.project, "checkout", "-q", "-b", "work")
    git(installed.project, "remote", "set-url", "origin", str(installed.remote.parent / "gone"))

    found = update.status(installed.cfg, check=True, project=installed.project, now=NOW)

    assert found["why_not_kind"] == "development" and found["check_error"]


def test_a_folder_that_is_not_a_clone_says_so(tmp_path):
    (tmp_path / "config.toml").write_text('[api]\nkey = "k"\n', encoding="utf-8")

    found = update.status(load_config(tmp_path / "config.toml"), check=True, project=tmp_path, now=NOW)

    assert (found["why_not_kind"], found["latest_release"], found["check_error"]) == ("not_a_clone", None, None)


def test_an_installed_copy_has_no_reason_not_to_update(installed):
    assert update.status(installed.cfg, project=installed.project, now=NOW)["why_not_kind"] is None
```

and in `programUpdate.test.ts`, with a `status()` helper that fills an `UpdateStatus`:

```ts
it('says what a look found, for every kind of copy', () => {
  expect(whatTheLookFound(status({ latest_release: 'v0.3.0', installed_release: 'v0.3.0' }))).toBe('Aveți cea mai nouă versiune.')
  expect(whatTheLookFound(status({ update_available: true, latest_release: 'v0.4.0' }))).toBe('Există versiunea 0.4.0.')
  expect(whatTheLookFound(status({ can_update: false, why_not_kind: 'development', latest_release: 'v0.3.0' })))
    .toBe('Ultima versiune publicată este 0.3.0. O copie de dezvoltare se actualizează cu git, nu de aici.')
  expect(whatTheLookFound(status({ can_update: false, why_not_kind: 'not_a_clone' })))
    .toBe('Această copie nu a fost instalată cu programul de instalare, așa că nu are de unde căuta.')
  expect(whatTheLookFound(status({ check_error: 'no network' }))).toBe('Nu am putut căuta. Verificați conexiunea la internet.')
})
```

- [ ] **Step 2: Run** both. Expected: `KeyError: 'why_not_kind'`; the vitest case fails on the first new sentence.
- [ ] **Step 3: Implement** the status change, then `whatTheLookFound`.
- [ ] **Step 4: The foot.** `ProgramVersion`: "AutoSaga {version}"; the outline button "Caută o versiune nouă" ("Se caută…") always; when `status.update_available`, the sentence and the primary button "Actualizează programul" (calls `onUpdate`) in its place; the sentence of the look under it. `Credits`: a thin line, "© 2026 Tanasie Vlad-Cristian", the e-mail as a `mailto:` link, small and muted. `AppShell` passes `onUpdate` (the one it gives `UpdateNotice`) and renders `Credits` under `ProgramVersion`.
- [ ] **Step 5: Run** `uv run pytest -q` (830 passed), `pnpm --dir frontend test`, `tsc -b --noEmit`, `lint`.
- [ ] **Step 6: Commit** — `git commit -m "Menu foot: a button that looks for a new version, and the author line"`

### Task 8: Say what `access_denied` means, and the helper script the owner tries by hand

Not gated: the explanation serves the browser way of connecting too, and the script has to exist before it can be tried.

**Files:**
- Create: `src/efactura/certificate_login.ps1`
- Modify: `src/efactura/errors.py` (`LOGIN_REFUSED = "login_refused"`, HTTP 409 in `api.py`'s table), `src/efactura/auth.py` (`code_from_redirect`), `tests/test_auth.py:179` (the code it expects), `frontend/src/errorMessages.ts`, `README-ANAF.md`, `README.md`
- Test: `tests/test_auth.py`

**Interfaces:**
- Produces: `auth.code_from_redirect`: an address with `error=access_denied` raises `EfacturaError(LOGIN_REFUSED, "ANAF refused the login: access_denied")`; any other `error=` stays `ANAF_ERROR`. `errorMessages.ts`: `login_refused` → "ANAF nu a acceptat certificatul. Verificați că este certificatul cu care intrați în SPV și că nu a expirat."
- The script, exactly (it cannot be run on the development machine, so nothing in it is left to choice). It reads the address from the environment variable `AUTOSAGA_AUTHORIZE_URL` and prints one line of JSON: `{"location": "<address>"}`, `{"cancelled": true}` or `{"error": "<text>"}`. ASCII only, as `install.ps1` is.

```powershell
$ErrorActionPreference = 'Stop'
try {
    Add-Type -AssemblyName System.Security
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $now = Get-Date
    $mine = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2Collection
    Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.HasPrivateKey -and $_.NotAfter -gt $now } | ForEach-Object { [void]$mine.Add($_) }
    $picked = [System.Security.Cryptography.X509Certificates.X509Certificate2UI]::SelectFromCollection(
        $mine, 'AutoSaga', 'Alegeti certificatul cu care intrati in SPV.',
        [System.Security.Cryptography.X509Certificates.X509SelectionFlag]::SingleSelection)
    if ($picked.Count -eq 0) { '{"cancelled": true}'; exit 0 }
    $answer = Invoke-WebRequest -Uri $env:AUTOSAGA_AUTHORIZE_URL -Certificate $picked[0] -MaximumRedirection 0 -UseBasicParsing -ErrorAction SilentlyContinue
    @{ location = [string]$answer.Headers.Location } | ConvertTo-Json -Compress
} catch {
    @{ error = $_.Exception.Message } | ConvertTo-Json -Compress
}
```

- [ ] **Step 1: Write the failing test** (in `tests/test_auth.py`, beside the test at line 179, which is changed to expect the new code)

```python
def test_an_address_saying_access_denied_is_a_refused_login_not_a_passing_error():
    with pytest.raises(EfacturaError) as refused:
        auth.code_from_redirect("https://localhost/callback?error=access_denied")
    assert refused.value.code == "login_refused"

    with pytest.raises(EfacturaError) as other:
        auth.code_from_redirect("https://localhost/callback?error=server_error&error_description=down")
    assert other.value.code == "anaf_error" and "down" in other.value.message
```

- [ ] **Step 2: Run** `uv run pytest tests/test_auth.py -q`. Expected: FAIL, `'anaf_error' == 'login_refused'`.
- [ ] **Step 3: Implement** the code and the Romanian sentence; add `login_refused` to the README's list of 409 codes.
- [ ] **Step 4: The script file**, as above.
- [ ] **Step 5: The guides.** `README-ANAF.md`, under "Dacă ceva nu merge": what `access_denied` means and what to check (the token is in; no certificate window appeared → close the browser completely and try again; the certificate is the one used for SPV and has not expired; SPV opens with it in the same browser). `README.md`, a short section "Trying the certificate login by hand" with the three lines to run in Windows PowerShell from the installed folder:

```powershell
cd $env:LOCALAPPDATA\AutoSaga
$env:AUTOSAGA_AUTHORIZE_URL = (uv run efactura login-start | Out-String | ConvertFrom-Json).authorize_url
powershell -NoProfile -ExecutionPolicy Bypass -File src\efactura\certificate_login.ps1
```

and what each answer means (`location` with `code=`: it works, and the address can be pasted into the program's window within a minute; `location` with `error=access_denied`: ANAF refuses this certificate; `cancelled`; `error`).
- [ ] **Step 6: Run** `uv run pytest -q` (831 passed), `pnpm --dir frontend test`. Commit — `git commit -m "Say what access_denied means; the certificate helper script to try by hand"`

### Task 9: Rebuild the page, the README, version 0.4.0

**Files:**
- Modify: `README.md`, `pyproject.toml`, `src/efactura/__init__.py`, `uv.lock`, `src/efactura/ui/` (built)

- [ ] **Step 1: README.** "The screen": the row for "Reguli de clasificare" mentions "Testează regulile"; a short section "Testing the rules" (what the two buttons do, what is saved, the limits, `POST /rules/test`); the menu's foot (the button, the author line); "Not yet confirmed": the demo command was run on macOS only.
- [ ] **Step 2: Version.** `0.3.0` → `0.4.0` in `pyproject.toml` and `src/efactura/__init__.py`; `uv lock`.
- [ ] **Step 3: Build and run everything.** `pnpm --dir frontend build`; `uv run pytest -q`; `pnpm --dir frontend test`. Expected: built without errors; all pass.
- [ ] **Step 4: Try it.** `uv run efactura demo --port 8765` in the background; open `http://127.0.0.1:8765/ui/`; check: the label "Date de probă"; "Descarcă facturile" brings one or two invoices; "Conectați-vă la ANAF" ends connected with a pasted `…code=demo-…` address; "Testează regulile" answers for both buttons and for the two examples; the menu's foot shows the version, the button and the author line. Stop it.
- [ ] **Step 5: Commit** — `git commit -m "Version 0.4.0: demo command, rule test, menu foot"`

### Task 10: Connecting to ANAF with the Windows certificate

**The gate was passed on 2026-11-15.** The owner ran the helper's steps by hand on the Windows PC (Windows PowerShell 5.1, the token in) and ANAF answered with an address containing `code=`. This task is built on what that run showed:

- ANAF's login address answers in several hops on its own host before it sends the request to the callback: `302 /anaf-oauth2/v1/authorize -> 302 /my.policy -> 302 /my.policy -> 302 /my.policy_nonce -> the callback`. The cookies have to be kept from hop to hop and the certificate offered at each. The helper of Task 8 stopped at the first hop and printed `/my.policy`; it is rewritten here.
- With no certificate ANAF ends on `<callback>?error=access_denied`, after three hops. That is what the browser on that PC gets: it never shows its certificate window.
- A wrong Client ID is answered at once with HTTP 400 and `{"error":"invalid_client","error_description":"Invalid client_id <the id>"}`. A callback that differs from the registered one is answered with HTTP 400 and `{"error":"invalid_request","error_description":"Redirect-URI (<the address>) does not match with client app configuration."}`.
- With the certificate, the first run in a PowerShell window ends in `error=access_denied` and the second brings a code. The owner saw this twice. The first run is the one during which the token's PIN is typed; ANAF's last hop is named `/my.policy_nonce`. The reading this task is built on: ANAF does not wait for the PIN, and once the token is open a login goes through. So the helper opens the token first (it signs a few bytes, which makes the token ask for its PIN before ANAF is contacted) and, if ANAF still refuses, tries once more by itself. Whether the first step alone is enough is not known; the second covers it either way.
- The steps were started as `powershell -NoProfile -ExecutionPolicy Bypass -File <script>` from a PowerShell window. Started by the program itself, without a window, they have not been tried: that is the owner's check at the end.

**Files:**
- Rewrite: `src/efactura/certificate_login.ps1`
- Create: `src/efactura/certificate_login.py`, `tests/test_certificate_login.py`, `frontend/src/layout/certificateLogin.ts`, `frontend/src/layout/certificateLogin.test.ts`
- Modify: `src/efactura/errors.py` (`LOGIN_CANCELLED = "login_cancelled"`), `src/efactura/service.py` (`login_with_certificate`, `auth_status`), `src/efactura/api.py` (the route; `LOGIN_CANCELLED` is HTTP 409), `frontend/src/layout/AnafLoginDialog.tsx`, `frontend/src/errorMessages.ts`, `frontend/src/api.ts`, `frontend/src/types.ts` (`AuthStatus`), `frontend/src/journal/eventTexts.ts` and its test, `README.md`, `README-ANAF.md`, `pyproject.toml`, `src/efactura/__init__.py`, `uv.lock` (version 0.5.0), and the built page in `src/efactura/ui/`.
- The window may be split into more components under `frontend/src/layout/` if it reads better. No two file names may differ only by upper and lower case.

**Interfaces:**
- Consumes: `LOGIN_REFUSED` and `auth.code_from_redirect` (Task 8), `Config.demo` (Task 2), `Service.login_finish`, `auth.authorize_url`.
- Produces:
  - `certificate_login.HELPER` — the path of the `.ps1` beside the module. `certificate_login.TIMEOUT = 300` — seconds allowed for choosing the certificate and typing the PIN.
  - `certificate_login.available(cfg: Config, system: str | None = None) -> bool` — true when `system` (by default `os.name`) is `"nt"`, `_powershell()` finds Windows PowerShell, and `cfg.demo` is false. The system is a parameter, as in `cli.started_through_the_launcher`, because replacing `os.name` in a test breaks `pathlib` on a Mac.
  - `certificate_login._powershell() -> str | None` — where `powershell.exe` is (`shutil.which`), replaced in tests.
  - `certificate_login.ask_windows(authorize_url: str) -> str` — runs the helper and returns the address ANAF ended on. Raises `EfacturaError(LOGIN_CANCELLED, …)` when no certificate was chosen, and `EfacturaError(ANAF_ERROR, …)` carrying the helper's own words when it failed or printed nothing usable. Each call leaves one journal line, `journal.record("anaf", "anaf.certificate_asked", "Windows was asked for the certificate.", duration_ms=…, outcome=…, tries=…, opened_first=…)`: `outcome` is `"answered"` (ANAF sent the login somewhere, a refusal included), `"cancelled"` or `"failed"`; `tries` and `opened_first` are the helper's `tries` and `opened`, each left out when the helper printed none (the names avoid the words the journal hides, such as key, token and pin). How long Windows took and how many tries ANAF needed is what explains a refusal later. The address and the code are never recorded.
  - `certificate_login._run_helper(authorize_url: str) -> dict` — the one function that starts a process. It runs `[<powershell>, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HELPER)]`, exactly as the owner started it by hand (no `-NonInteractive`), with the address in the environment variable `AUTOSAGA_AUTHORIZE_URL` (never on the command line), `stdin` closed, the output captured, `timeout=TIMEOUT` and no console window (`creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)`). The output is read as UTF-8, with bytes that are not UTF-8 replaced, and its last non-empty line is parsed as JSON. It returns that object (the helper prints `location` or `error` together with `tries` and `opened`, or `cancelled` alone); `{}` when nothing readable was printed or the line is not a JSON object; `{"cancelled": True}` when the time ran out (`subprocess.run` ends the helper itself then); `{"error": <the failure, through errors.said_by>}` when PowerShell could not be started.
  - `Service.login_with_certificate() -> dict` — the same dict `login_finish` returns. It refuses with `EfacturaError(INVALID_INPUT, …)` where `available` is false. It does not hold the program's lock while Windows asks; `login_finish` takes it for the exchange as it does today.
  - `Service.auth_status()` gains `"certificate_login": bool`, which follows `available`.
  - `POST /auth/login/certificate`. The call can last minutes, so it must not run on the event loop: declare it the way the other routes that wait on the service are declared.
- No guard against two tries at once: the page disables its button while it waits, and a second helper window is harmless (whichever finishes is saved).

- [ ] **Step 1: Rewrite the helper.** Replace the whole of `src/efactura/certificate_login.ps1` with exactly this. It cannot be run on the development machine, and every step in it is one the owner ran by hand, so change nothing in it. ASCII only, as the file is today.

```powershell
# Asks ANAF for a login with a certificate Windows holds, and prints one line of JSON:
#   {"location": "...", "tries": 1, "opened": true}   the address ANAF sent the login to in the end
#   {"cancelled": true}                               no certificate was chosen
#   {"error": "...", "tries": 1, "opened": true}      it did not go through; the text is what Windows or ANAF said
# "tries" is how many times ANAF was asked; "opened" says whether using the key first worked.
# The address to ask is read from AUTOSAGA_AUTHORIZE_URL. ANAF answers in several hops on
# its own host: each is followed with the same cookies and the same certificate. The
# address it ends on is printed, never asked, and the certificate goes to no other host.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$tries = 0
$opened = $false
try {
    $first = $env:AUTOSAGA_AUTHORIZE_URL
    if (-not $first) { throw 'AUTOSAGA_AUTHORIZE_URL is not set.' }
    $anaf = ([Uri]$first).Host
    Add-Type -AssemblyName System.Security
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $now = Get-Date
    $mine = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2Collection
    Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.HasPrivateKey -and $_.NotAfter -gt $now } | ForEach-Object { [void]$mine.Add($_) }
    $picked = [System.Security.Cryptography.X509Certificates.X509Certificate2UI]::SelectFromCollection(
        $mine, 'AutoSaga', ('Alege' + [char]0x021B + 'i certificatul cu care intra' + [char]0x021B + 'i ' + [char]0x00EE + 'n SPV.'),
        [System.Security.Cryptography.X509Certificates.X509SelectionFlag]::SingleSelection)
    if ($picked.Count -eq 0) { '{"cancelled": true}'; exit 0 }
    $certificate = $picked[0]

    # The token asks for its PIN the first time its key is used, and ANAF does not wait for
    # that: a login during which the PIN was typed came back refused, and the next one, with
    # the token already open, went through. So the key is used once here, before ANAF is
    # asked. If this cannot be done, the second try below covers it.
    try {
        $key = [System.Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($certificate)
        if ($key) {
            [void]$key.SignData([byte[]](1..32), [System.Security.Cryptography.HashAlgorithmName]::SHA256, [System.Security.Cryptography.RSASignaturePadding]::Pkcs1)
            $opened = $true
        }
    } catch { }

    $location = $null
    while ($tries -lt 2) {
        if ($tries -gt 0) { Start-Sleep -Milliseconds 1500 }
        $tries++
        $location = $null
        $url = $first
        $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
        for ($hop = 0; $hop -lt 12 -and -not $location; $hop++) {
            $answer = $null
            $answer = Invoke-WebRequest -Uri $url -Certificate $certificate -WebSession $session -MaximumRedirection 0 -UseBasicParsing -ErrorAction SilentlyContinue
            if (-not $answer) { throw 'ANAF did not answer.' }
            $next = [string]$answer.Headers.Location
            if (-not $next) { throw ('ANAF stopped on a page instead of sending the login on (status ' + [int]$answer.StatusCode + ').') }
            $next = [Uri]::new([Uri]$url, $next)
            if ($next.Host -ne $anaf) { $location = $next.AbsoluteUri }
            elseif ($next.Scheme -ne 'https') { throw 'ANAF sent the login to an address that is not https.' }
            else { $url = $next.AbsoluteUri }
        }
        if (-not $location) { throw 'ANAF kept sending the login on, without an end.' }
        # Only a refusal is worth a second try; a code, or any other answer, ends it.
        if ($location -notmatch '[?&]error=access_denied') { break }
    }
    @{ location = $location; tries = $tries; opened = $opened } | ConvertTo-Json -Compress
} catch {
    $said = [string]$_.Exception.Message
    if ($_.ErrorDetails) { $said += ' | ' + $_.ErrorDetails.Message }
    @{ error = ($said -replace '\s+', ' '); tries = $tries; opened = $opened } | ConvertTo-Json -Compress
}
```

- [ ] **Step 2: Write the failing tests** in `tests/test_certificate_login.py`.

```python
"""Connecting to ANAF with the certificate Windows holds, without the browser."""

import subprocess

import pytest

from efactura import certificate_login
from efactura.errors import EfacturaError

LOGIN = "https://logincert.anaf.ro/anaf-oauth2/v1/authorize?client_id=abc"
ENDED_ON = "https://localhost/callback?code=good-code"


def test_the_address_anaf_ends_on_is_handed_back(monkeypatch):
    asked = []
    monkeypatch.setattr(certificate_login, "_run_helper", lambda url: asked.append(url) or {"location": ENDED_ON})

    assert certificate_login.ask_windows(LOGIN) == ENDED_ON
    assert asked == [LOGIN]


@pytest.mark.parametrize("printed, code", [
    ({"cancelled": True}, "login_cancelled"),
    ({"error": "The remote server returned an error: (400) Bad Request."}, "anaf_error"),
    ({"location": ""}, "anaf_error"),
    ({"location": None}, "anaf_error"),
    ({}, "anaf_error"),
])
def test_what_the_helper_can_come_back_with(monkeypatch, printed, code):
    monkeypatch.setattr(certificate_login, "_run_helper", lambda url: printed)

    with pytest.raises(EfacturaError) as failed:
        certificate_login.ask_windows(LOGIN)

    assert failed.value.code == code


def _printing(text: bytes):
    """Stands in for subprocess.run: prints `text` and remembers how the helper was started."""
    started = {}

    def run(command, **how):
        started["command"], started["how"] = command, how
        return subprocess.CompletedProcess(command, 0, stdout=text, stderr=b"")

    return run, started


def test_the_helper_gets_the_address_in_its_environment_never_on_the_command_line(monkeypatch):
    run, started = _printing(b'{"location":"https://localhost/callback?code=good-code"}\r\n')
    monkeypatch.setattr(certificate_login.subprocess, "run", run)
    monkeypatch.setattr(certificate_login, "_powershell", lambda: "powershell.exe")

    assert certificate_login._run_helper(LOGIN) == {"location": ENDED_ON}
    assert started["command"] == ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(certificate_login.HELPER)]
    assert started["how"]["env"]["AUTOSAGA_AUTHORIZE_URL"] == LOGIN
    assert started["how"]["timeout"] == certificate_login.TIMEOUT
```

and, in the same file and the same style:

- the helper's last non-empty line is the one read: lines of other text before it and blank lines after it change nothing;
- Windows PowerShell 5.1 prints an ampersand inside JSON as a backslash, the letter u and `0026`; an address printed that way comes back with the ampersand. Build that text in the test with `chr(92) + "u0026"`: typed directly, the editing tools turn it into a plain ampersand and the test proves nothing;
- nothing printed gives `{}`; a last line that is not JSON gives `{}`; a last line that is JSON but not an object (`[]`, `"x"`) gives `{}`; output that is not UTF-8 raises nothing;
- `subprocess.TimeoutExpired` gives `{"cancelled": True}`; `OSError` gives a dict with `"error"`;
- ANAF's own words reach whoever helps: with `_run_helper` returning `{"error": "(400) Bad Request. | Invalid client_id abc"}`, the raised error's message contains `Invalid client_id abc`;
- each call of `ask_windows` leaves exactly one journal line with the event `anaf.certificate_asked` and a duration: `outcome` is `answered`, `tries` is 2 and `opened_first` is false for `{"location": ENDED_ON, "tries": 2, "opened": False}`; `outcome` is `answered` for an address carrying `error=access_denied`; `cancelled` for `{"cancelled": True}`; `failed` for `{"error": …}` and for `{}`; and the line holds neither the address nor the code;
- `available(cfg, system="posix")` is false; `available(cfg, system="nt")` is true with `_powershell` replaced to return a path and false with it returning `None`; for a demo `Config` it is false even with `system="nt"`;
- the helper file exists beside the module, is ASCII only, and contains none of the words `Write-Host`, `Start-Process` or `Invoke-Expression`;
- `ask_windows` hands back the address when the helper's answer also carries `tries` and `opened`.

For the service and the route, in the style of the login tests in `tests/test_auth.py` and the API tests (a `Service` on the stand-in ANAF, whose token call accepts the code `good-code`), with `certificate_login.available` replaced to return true:

- `login_with_certificate()` with `ask_windows` replaced to return `…/callback?code=good-code` ends with `state == "valid"` and a saved login;
- replaced to return `…/callback?error=access_denied` it raises `login_refused` and saves nothing;
- replaced to raise `login_cancelled`, that error comes out and nothing is saved;
- with `available` false it raises `invalid_input` and `ask_windows` is not called;
- `auth_status()["certificate_login"]` follows `available`;
- `POST /auth/login/certificate` answers 200 with the login, 409 with `login_refused`, and 409 with `login_cancelled`;
- after a successful login neither the address nor the code `good-code` is anywhere in the journal table or in the log file.

- [ ] **Step 3: Run** `uv run pytest tests/test_certificate_login.py -q`. Expected: FAIL, no module `efactura.certificate_login`.
- [ ] **Step 4: Implement** the module, the error code, the service method and the route. Run the file again until it passes, then `uv run pytest -q` (863 pass before this task).

- [ ] **Step 5: The window's logic, test first.** The page's tests are for plain functions (there is no component test library, and none is to be added), so what the window shows is decided by a function in `frontend/src/layout/certificateLogin.ts`, tested in `certificateLogin.test.ts`, and `AnafLoginDialog.tsx` only draws the result. Whatever its shape, the tests must pin down:

| When | The window shows |
|---|---|
| it opens and `certificate_login` is true | the certificate way |
| it opens and `certificate_login` is false, or the login state has not been read yet | the three browser steps there are today, exactly as today |
| "Conectează-mă cu certificatul" or "Încearcă din nou" is pressed | the waiting view |
| the answer is `login_cancelled` | the certificate way again, with the sentence "Nu a fost ales niciun certificat." |
| the answer is any other failure | the failure view, holding that error |
| "Renunță" is pressed while waiting | the certificate way; an answer that arrives afterwards changes nothing on screen |
| "Nu merge așa? Conectare prin browser" or "Conectare prin browser" is pressed | the three browser steps |

Run `pnpm --dir frontend test` and see the new tests fail before the function exists (94 pass before this task).

- [ ] **Step 6: The window**, as the artboard "Fereastra: Conectare la ANAF cu certificatul". The artboard is saved at the path the controller gives you; its three cards are the certificate way, the waiting view and the failure view. Texts, to be used as written:

  - The certificate way: title "Conectare la ANAF"; "Aveți nevoie de tokenul USB și de PIN-ul lui. Se face cam o dată pe an."; the numbered steps "Introduceți tokenul USB în calculator.", "Apăsați butonul de mai jos. Windows vă arată certificatele: alegeți-l pe al dumneavoastră.", "Scrieți PIN-ul în fereastra tokenului."; the button "Conectează-mă cu certificatul"; the link "Nu merge așa? Conectare prin browser".
  - Waiting: title "Se așteaptă certificatul…"; "Alegeți certificatul în fereastra Windows, apoi scrieți PIN-ul."; in the quieter colour "Fereastra poate fi în spatele browserului. Dacă nu o vedeți, uitați-vă în bara de jos a ecranului."; a bar that shows work going on without a percentage; the button "Renunță".
  - Failure, for `login_refused`: the attention notice "ANAF nu a acceptat certificatul."; under it "Verificați că este certificatul cu care intrați în SPV și că nu a expirat."; then, small, "Detalii tehnice: " and the program's own words; the buttons "Încearcă din nou" and "Conectare prin browser". For any other failure the same view with that error's own sentence from `errorMessages.ts` (use `ErrorNotice`) and the same two buttons.
  - `errorMessages.ts`: `login_cancelled` → "Nu a fost ales niciun certificat."
  - `journal/eventTexts.ts`: `anaf.certificate_asked` → "Programul a cerut certificatul de la Windows."

  Behaviour: a login that succeeds does what a pasted address does today (refreshes the `auth` and `secrets` queries, says "Conectat la ANAF.", closes the window). "Renunță" only stops the page waiting: if the certificate is chosen afterwards the login is still saved, and when that answer arrives the top bar's ANAF chip must still refresh, with no message and no change to the window. Closing the window and opening it again starts from the first view. Where `certificate_login` is false the window is exactly today's.

- [ ] **Step 7: The two READMEs.**

  `README.md` (English, for whoever installs and maintains): in "How the login works", the certificate way on Windows and what it does (Windows' own certificate window, the token's own PIN prompt, the key never leaves the token, the program never sees the PIN, the one-time code is never shown or recorded); rewrite "Trying the certificate login by hand" for the helper as it is now (it follows ANAF's hops and prints the address ANAF ends on, which holds a one-time code: use it within a minute and send it to nobody); in "Local API" the route `POST /auth/login/certificate` and `certificate_login` in the login status; `login_cancelled` in the "Error code | Meaning" table; in "Not yet confirmed", replace the line saying the helper has never been run with what the run of 2026-11-15 confirmed (the five points at the top of this task, in a few lines) and what is still open: the script file as rewritten here, the program starting it by itself without a window, where Windows puts the certificate and PIN windows then, and the one refusal nobody could explain.

  `README-ANAF.md` (Romanian, for the accountant). Replace "Pasul 5" up to, and not including, the paragraph that starts "După aceasta programul rămâne conectat" with exactly:

```markdown
## Pasul 5 — Vă conectați la ANAF

1. Introduceți tokenul USB în calculator.
2. În bara de sus a programului apăsați **Conectați-vă la ANAF**.
3. Apăsați **Conectează-mă cu certificatul**. Windows vă arată certificatele: alegeți-l pe al dumneavoastră, apoi scrieți PIN-ul în fereastra tokenului. Fereastra poate apărea în spatele browserului; dacă nu o vedeți, uitați-vă în bara de jos a ecranului.

Atât: programul primește singur răspunsul de la ANAF.

**Dacă butonul „Conectează-mă cu certificatul” lipsește sau nu merge**, alegeți **Conectare prin browser** și urmați cei trei pași din fereastră: se deschide pagina ANAF, alegeți certificatul și scrieți PIN-ul. Browserul arată apoi o pagină de eroare („nu se poate accesa pagina”). **Este normal.** Copiați toată adresa din bara de adrese și lipiți-o în program, **în cel mult un minut**. Butonul cu certificatul există doar pe Windows.
```

  Under "Dacă ceva nu merge", replace the whole entry that starts "**ANAF a refuzat certificatul („access_denied”).**" (it and its four numbered lines) with exactly:

```markdown
- **ANAF a refuzat certificatul („access_denied”).** ANAF răspunde așa când nu primește niciun certificat. De obicei browserul nu a arătat fereastra de alegere a certificatului, deci nu a trimis nimic. Ce faceți:
  1. Verificați că tokenul USB este introdus în calculator.
  2. Pe Windows, folosiți **Conectează-mă cu certificatul** din fereastra „Conectare la ANAF”. Programul cere certificatul direct de la Windows, fără browser.
  3. Dacă ANAF refuză și așa, apăsați **Încearcă din nou**. La o probă, a doua încercare a mers fără nicio altă schimbare.
  4. Dacă tot nu merge, intrați în SPV cu același certificat. Dacă nici acolo nu merge, problema este la certificat sau la token, nu la program.
- **ANAF răspunde cu `invalid_client`.** Client ID-ul scris în program nu este cel dat de ANAF. Copiați-l din nou de la ANAF (Pasul 3) și scrieți-l în program (Pasul 4).
- **ANAF răspunde cu `invalid_request` și cu textul „Redirect-URI … does not match”.** Callback URL de la ANAF diferă de adresa pe care o trimite programul, `https://localhost/callback`. Vedeți mai sus „Ați greșit Callback URL sau serviciul”.
```

  and at the end of "De unde sunt acești pași" add the paragraph: "Răspunsurile ANAF de la „Dacă ceva nu merge” sunt cele primite la o probă pe un calculator cu Windows, la 15 noiembrie 2026."

- [ ] **Step 8: Version 0.5.0** in `pyproject.toml`, `src/efactura/__init__.py` and `uv.lock`, the way commit `a367834` set 0.4.1.
- [ ] **Step 9: Run every suite and build the page.** `uv run pytest -q`, `pnpm --dir frontend test`, `pnpm --dir frontend exec tsc -b --noEmit` (clean), `pnpm --dir frontend lint` (exactly the 3 old `only-export-components` warnings), then `pnpm --dir frontend build` (this task rebuilds the committed page in `src/efactura/ui/`).
- [ ] **Step 10: Commit** — `git commit -m "Connect to ANAF with the Windows certificate, without the browser (0.5.0)"`.
- [ ] **Step 11: Hand to the owner** for a real try on the Windows PC. The controller does this, not the implementer.

**After the review (2026-11-15).** The review approved the task; one round of fixes followed, and where it differs from the text above, it is what was built:

- The sentence in Windows' certificate window is written with its diacritics, through `[char]` codes, so the file stays ASCII (the script above already shows it).
- One helper at a time: `certificate_login.one_at_a_time` makes a second request wait for the first and share its answer. This replaces "no guard against two tries at once".
- ANAF's answers to a wrong Client ID or a callback that differs come out as `config_error`, with a sentence of their own in the window, instead of `anaf_error`.
- A helper that prints nothing readable reports its exit code and the first line of its standard error, instead of `{}`.
- A download in progress refuses the login before Windows is asked (`busy`), not after the PIN.
- An end address with neither a code nor an error is `anaf_error`, not `invalid_input`.
- A login that succeeds is always announced ("Conectat la ANAF.", the window closed), also for a try the person gave up on. Only a failure that arrives late changes nothing on screen.
- Closing the window keeps a pasted address.
