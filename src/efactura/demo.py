"""The demo: made-up clients and invoices in a folder of their own, to try the program
without ANAF, OpenRouter or SAGA.

The invoices are invented; they are pushed through the real sync and classification, with
stand-ins answering for ANAF and for Jev, so the screens show what the real program would
produce. The folder is thrown away and made again every time.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import threading
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs

import httpx

from . import auth
from .config import DEMO_MARKER, Config, load_config
from .errors import CONFIG_ERROR, EfacturaError
from .service import Service
from .standins import FakeAnaf, FakeOpenRouter, line, rich_invoice_xml

FOLDER = Path(__file__).resolve().parents[2] / "demo"
MARKER = DEMO_MARKER
OPENROUTER_KEY = "sk-or-v1-EXEMPLU"
ACCESS_TOKEN = "EXEMPLU-access-token"

CONFIG = """\
[anaf]
client_id = "EXEMPLU-client-id"
client_secret = "EXEMPLU-client-secret"
token_file = "tokens.json"

[api]
key = "EXEMPLU-cheie-locala"
port = 8770

[openrouter]
api_key = "sk-or-v1-EXEMPLU"

[demo]
enabled = true
"""

CLIENTS = {
    "12345674": "Alfa Construct SRL",
    "14399840": "Brutăria Soarelui SRL",
    "18547290": "Cabinet Medical Ionescu",
}

# (supplier name, supplier CUI, invoice number, lines) per client, in two downloads:
# the first is "last week" (old by now), the second is "today" (new). A fifth value is the
# amount already paid: with a minus, an earlier unpaid balance the supplier adds to what is due.
EARLIER = {
    "12345674": [
        ("Birotică Expert SRL", "RO30112233", "BE-0412", [line("Hârtie A4 80g", "120.00", quantity="10", price="12.00")]),
        ("Stația Carburant SRL", "RO20334455", "FV-0998", [line("Motorină Euro 5", "400.00", quantity="50", unit="LTR", price="8.00")]),
    ],
    "14399840": [
        ("Telefonie Mobilă SA", "RO10556677", "TM 87001", [line("Abonament telefonie mobilă", "150.00")]),
    ],
}
TODAY = {
    "12345674": [
        # Two accounts on one invoice, and a discount that takes the account of the largest line.
        ("Stația Carburant SRL", "RO20334455", "FV-1042", [line("Motorină Euro 5", "450.00", quantity="60", unit="LTR", price="7.50"), line("Spălare auto", "50.00"), line("Discount card flotă", "-15.00")]),
        ("Telefonie Mobilă SA", "RO10556677", "TM 88213", [line("Abonament telefonie mobilă", "200.00")]),
        ("Materiale Construcții SRL", "RO23456789", "MC 5521", [line("Ciment 40 kg", "840.00", quantity="30", price="28.00"), line("Transport marfă", "60.00")]),
        # Paper again, and a repair: Jev decides both, so rules are proposed from them.
        ("Birotică Expert SRL", "RO30112233", "BE-0467", [line("Hârtie A4 80g", "240.00", quantity="20", price="12.00")]),
        ("Service Auto Nord SRL", "RO50990011", "SA 3340", [line("Revizie utilaj", "1500.00")]),
    ],
    "14399840": [
        ("Ambalaje Pro SRL", "RO40778899", "AP 771", [line("Pungi hârtie 500 buc", "310.00", quantity="2", price="155.00")]),
        ("Service Auto Nord SRL", "RO50990011", "SA 3301", [line("Revizie autoutilitară", "980.00")]),
        # Sent a second time by the supplier, under a new ANAF id: held back for a person.
        ("Telefonie Mobilă SA", "RO10556677", "TM 87001", [line("Abonament telefonie mobilă", "150.00")]),
        # The line says nothing telling, so the rule proposed is for the supplier.
        ("Contabil Expert SRL", "RO70445566", "CE 0911", [line("Servicii conform contract", "600.00")]),
    ],
    "18547290": [
        ("Papetărie Centrală SRL", "RO60223344", "PC 118", [line("Hârtie copiator A4", "95.00", quantity="5", price="19.00")]),
        # What is left to pay is not what these two are worth: an earlier balance, and an advance.
        ("Compania de Apă Exemplu SA", "RO40111222", "CO 1879", [
            line("Apă potabilă", "177.65", quantity="17", unit="MTQ", price="10.45", percent="9"),
            line("Canalizare", "139.23", quantity="17", unit="MTQ", price="8.19", percent="9"),
        ], "-312.40"),
        ("Energie Exemplu SA", "RO50112233", "EN 4410", [line("Energie electrică", "1000.00")], "200.00"),
    ],
}
# What a client issued itself: (buyer name, buyer CUI, invoice number, lines) per client. ANAF
# lists these too; they get income accounts like the received ones get theirs: one by Jev,
# one with a line Jev is unsure of, one by a rule and Jev, line by line.
ISSUED = {
    "12345674": [
        ("Gama Imobiliare SA", "31557788", "AC-2029", [line("Reparații acoperiș", "600.00")]),
        ("Primăria Comunei Valea Mare", "4553380", "AC-2030", [
            line("Lucrări de zidărie", "10000.00"), line("Cărămidă plină", "1900.00", quantity="950", unit="H87", price="2.00"),
        ]),
        ("Beta Instal SRL", "27745431", "AC-2031", [
            line("Manoperă instalații", "1500.00"), line("Țeavă PPR 25 mm", "500.00", quantity="40", unit="MTR", price="12.50"),
        ]),
    ],
}
BUYERS = [(name, cui) for name, cui, _, _ in ISSUED["12345674"]]
# Booked by a person on another account than Jev chose for the same kind of work, so the
# rule proposed from it shows invoices on two accounts.
BOOKED_BY_HAND = ("12345674", "SA 3340", "611")


# What Jev answers, by a word in the invoice line: the arguments of FakeOpenRouter.answer_for.
JEV_ANSWERS = {
    "ciment": {"choice": "302", "confidence": 0.58, "probabilities_extra": {"371": 0.27, "628": 0.09}},
    "hârtie": {"choice": "302", "confidence": 0.91},
    "pungi": {"choice": "302", "confidence": 0.93},
    "revizie": {"choice": "628", "confidence": 0.88},
    # What a client sold: income accounts.
    "reparații": {"choice": "704", "confidence": 0.9},
    "cărămidă": {"choice": "707", "confidence": 0.55, "probabilities_extra": {"704": 0.3}},
    "țeavă": {"choice": "707", "confidence": 0.91},
    # Jev declines: the invoice goes to a person.
    "nimic": {"choice": "", "refusal": True},
    # Jev finds that none of the accounts fits ("altul"), as "Testează regulile" can show.
    "cadou": {"choice": "altul", "confidence": 0.72, "probabilities_extra": {"628": 0.18, "302": 0.06}},
}
# A word in the invoice line that makes the call itself fail, with this status.
JEV_FAILS = {"eroare": 500}


def _jev() -> FakeOpenRouter:
    jev = FakeOpenRouter()
    for word, answer in JEV_ANSWERS.items():
        jev.answer_for(word, **answer)
    jev.fail_for = dict(JEV_FAILS)
    return jev


def build(folder: Path, now: datetime | None = None) -> Config:
    """Make the demo in `folder` from nothing and return its settings."""
    if folder.exists():
        try:
            shutil.rmtree(folder)
        except OSError as exc:
            # On Windows a file a running demo still has open cannot be deleted.
            raise EfacturaError(
                CONFIG_ERROR,
                f"The demo folder {folder} is in use and cannot be built again: stop the running demo "
                f"first, then try again. ({exc})",
            ) from None
    folder.mkdir(parents=True)
    (folder / "config.toml").write_text(CONFIG, encoding="utf-8")
    # The marker comes before the settings are read: they say [demo], which is refused
    # over a data folder that does not hold it.
    (folder / "data").mkdir()
    (folder / "data" / MARKER).write_text("made by efactura demo\n", encoding="utf-8")
    cfg = load_config(folder / "config.toml")
    now = now or datetime.now().astimezone()

    auth.save_tokens(cfg.token_file, auth.Tokens(
        ACCESS_TOKEN, "EXEMPLU-refresh-token",
        now + timedelta(days=60), now + timedelta(days=342, hours=1), now,
    ))

    jev = _jev()
    jev.valid_keys = {OPENROUTER_KEY}

    def service_at(moment: datetime, anaf: FakeAnaf) -> Service:
        anaf.openrouter = jev
        anaf.valid_access = {ACCESS_TOKEN}
        return Service(cfg, http=anaf.client(), now=lambda: moment)

    setup = service_at(now, FakeAnaf())
    for cui, name in CLIENTS.items():
        setup.save_client(cui, name)
    setup.save_account("302", "Materiale consumabile: papetărie, ambalaje, materiale de construcții folosite în lucrări.")
    setup.save_account("611", "Întreținere și reparații: revizii, reparații la utilaje și vehicule.")
    setup.save_rule(name="chirie birou", cont="612", supplier_cuis=["11112222"], client_cui="12345674")
    setup.save_rule(name="manoperă", cont="704", keywords=["manoperă", "montaj*", "lucrări"], direction="issued")

    message_id = 3000
    issued_id = FIRST_ISSUED_ID
    for moment, batch in ((now - timedelta(days=6), EARLIER), (now, TODAY)):
        for cui, invoices in batch.items():
            anaf = FakeAnaf()
            for supplier, supplier_cui, number, lines, *paid in invoices:
                message_id += 1
                anaf.add(str(message_id), xml=rich_invoice_xml(
                    lines=lines, number=number, supplier_cui=supplier_cui, supplier_name=supplier,
                    prepaid=paid[0] if paid else None,
                ))
            for buyer, buyer_cui, number, lines in ISSUED.get(cui, []) if batch is TODAY else []:
                issued_id += 1
                anaf.add(str(issued_id), tip="FACTURA TRIMISA", xml=_issued_xml(cui, buyer, buyer_cui, number, lines))
            service_at(moment, anaf).sync(cui)

    cui, number, cont = BOOKED_BY_HAND
    desk = service_at(now, FakeAnaf())
    by_hand = next(i for i in desk.invoices(cui=cui)["invoices"] if i["invoice_number"] == number)
    desk.set_cont(by_hand["id"], cont=cont)

    # Last week's invoices were imported into SAGA in the meantime.
    earlier_ids = [str(3000 + n) for n in range(1, 1 + sum(len(v) for v in EARLIER.values()))]
    service_at(now, FakeAnaf()).mark_uploaded(earlier_ids)
    return cfg


def _issued_xml(cui: str, buyer: str, buyer_cui: str, number: str, lines: list, **dates) -> bytes:
    """An invoice the client itself issued: the client is its supplier."""
    return rich_invoice_xml(
        lines=lines, number=number, supplier_cui=f"RO{cui}", supplier_name=CLIENTS.get(cui, f"Client {cui}"),
        customer_cui=buyer_cui, customer_name=buyer, **dates,
    )


# --- the stand-ins the running program talks to ---------------------------------------

STATE_FILE = "standin.json"
FIRST_ISSUED_ID = 3500  # `build` numbers the issued invoices from here, apart from the received ones
FIRST_MESSAGE_ID = 7000  # above the ids `build` used, which are in the database already
HOSTS = ("logincert.anaf.ro", "api.anaf.ro", "openrouter.ai")

# What a supplier sends: (name, CUI, the lines it may invoice). Each invoice takes two or
# three of them. Words like "hârtie", "ciment" and "revizie" are ones Jev knows (JEV_ANSWERS).
SUPPLIERS = [
    ("Birotică Expert SRL", "RO30112233", [("Hârtie A4 80g", "120.00"), ("Toner imprimantă", "340.00"), ("Dosare arhivare", "45.00")]),
    ("Stația Carburant SRL", "RO20334455", [("Motorină Euro 5", "450.00"), ("Spălare auto", "50.00"), ("Soluție parbriz", "30.00")]),
    ("Telefonie Mobilă SA", "RO10556677", [("Abonament telefonie mobilă", "200.00"), ("Internet mobil", "60.00")]),
    ("Materiale Construcții SRL", "RO23456789", [("Ciment 40 kg", "840.00"), ("Nisip sac", "120.00"), ("Transport marfă", "60.00")]),
    ("Service Auto Nord SRL", "RO50990011", [("Revizie autoutilitară", "980.00"), ("Schimb ulei", "150.00")]),
    ("Contabil Expert SRL", "RO70445566", [("Servicii conform contract", "600.00"), ("Consultanță fiscală", "250.00")]),
    ("Ambalaje Pro SRL", "RO40778899", [("Pungi hârtie 500 buc", "310.00"), ("Cutii carton", "180.00"), ("Bandă adezivă", "35.00")]),
]

_state_lock = threading.Lock()  # one request at a time reads and rewrites the state file


class StateAnaf(FakeAnaf):
    """A stand-in for ANAF that keeps what it "has" in a file, because the program makes a
    new Service for every request and nothing can be remembered in memory. Each time the
    list is asked for a CUI, one or two new received invoices appear in it, and every second
    time an invoice the client issued as well."""

    def __init__(self, path: Path, now=None):
        super().__init__()
        self.path = path
        self.now = now or (lambda: datetime.now().astimezone())
        self.openrouter = _jev()
        self.openrouter.valid_keys = None  # any key: the demo has none that is real

    # -- the file --

    def _load(self) -> dict:
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        self.entries = state.get("entries", [])
        self.zips = {i: base64.b64decode(z) for i, z in state.get("zips", {}).items()}
        return state

    def _save(self, state: dict) -> None:
        state["entries"] = self.entries
        state["zips"] = {i: base64.b64encode(z).decode("ascii") for i, z in self.zips.items()}
        temporary = self.path.with_name(self.path.name + ".new")
        temporary.write_text(json.dumps(state), encoding="utf-8")
        os.replace(temporary, self.path)

    # -- answering --

    def _handle(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        if host not in HOSTS:  # before anything else, so nothing else is ever reached
            return httpx.Response(404, text="not found")
        if host == "logincert.anaf.ro":
            return self._token(request)
        if host == "openrouter.ai":
            return self.openrouter.handle(request)
        with _state_lock:  # any bearer token is good: the tokens of an earlier request are gone
            state = self._load()
            if request.url.path.endswith("/listaMesajePaginatieFactura"):
                if request.url.params.get("pagina", "1") == "1":
                    self._receive(state, request.url.params["cif"])
                    self._save(state)
                return self._list_for(request)
            if request.url.path.endswith("/descarcare"):
                return self._download(request)
        return httpx.Response(404, text="not found")

    def _list_for(self, request: httpx.Request) -> httpx.Response:
        everything = self.entries
        self.entries = [e for e in everything if e["cif"] == request.url.params["cif"]]
        try:
            return self._list(request)
        finally:
            self.entries = everything

    def _receive(self, state: dict, cui: str) -> None:
        """Invoices that arrived since the last time: one, then two, then one again. With
        the two comes one the client issued."""
        asked = state.setdefault("asked", {})
        count = asked.get(cui, 0)
        asked[cui] = count + 1
        moment = self.now()
        dates = {
            "issue_date": moment.date().isoformat(),
            "due_date": (moment + timedelta(days=30)).date().isoformat(),
        }
        if count % 2 == 1:
            message_id = state.get("next_id", FIRST_MESSAGE_ID)
            state["next_id"] = message_id + 1
            buyer, buyer_cui = BUYERS[message_id % len(BUYERS)]
            self.add(
                str(message_id), cui=cui, tip="FACTURA TRIMISA", created=moment.strftime("%Y%m%d%H%M"),
                xml=_issued_xml(cui, buyer, buyer_cui, f"DEMO {message_id}", [line("Lucrări conform contract", "1200.00")], **dates),
            )
        for _ in range(1 if count % 2 == 0 else 2):
            message_id = state.get("next_id", FIRST_MESSAGE_ID)
            state["next_id"] = message_id + 1
            name, supplier_cui, offered = SUPPLIERS[message_id % len(SUPPLIERS)]
            chosen = offered[: 2 + message_id % 2]
            self.add(
                str(message_id), cui=cui, created=moment.strftime("%Y%m%d%H%M"),
                xml=rich_invoice_xml(
                    lines=[line(text, value) for text, value in chosen],
                    number=f"DEMO {message_id}", supplier_cui=supplier_cui, supplier_name=name,
                    customer_cui=cui, **dates,
                ),
            )

    def _token(self, request: httpx.Request) -> httpx.Response:
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        if form.get("grant_type") == "authorization_code" and not str(form.get("code", "")).startswith("demo-"):
            return httpx.Response(400, json={"error": "invalid_grant"})
        return httpx.Response(200, json={
            "access_token": ACCESS_TOKEN, "token_type": "Bearer", "expires_in": 7776000,
            "refresh_token": "EXEMPLU-refresh-token",
        })


def client(cfg: Config, now=None) -> httpx.Client:
    """An HTTP client for which ANAF and Jev are the stand-ins; any other host is a 404."""
    return StateAnaf(cfg.data_dir / STATE_FILE, now).client()


def service(cfg: Config) -> Service:
    return Service(cfg)  # on the demo's settings, a Service takes the stand-ins by itself
