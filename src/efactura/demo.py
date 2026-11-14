"""The demo: made-up clients and invoices in a folder of their own, to try the program
without ANAF, OpenRouter or SAGA.

The invoices are invented; they are pushed through the real sync and classification, with
stand-ins answering for ANAF and for Jev, so the screens show what the real program would
produce. The folder is thrown away and made again every time.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timedelta
from pathlib import Path

from . import auth
from .config import DEMO_MARKER, Config, load_config
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
# the first is "last week" (old by now), the second is "today" (new).
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
        ("Stația Carburant SRL", "RO20334455", "FV-1042", [line("Motorină Euro 5", "450.00", quantity="60", unit="LTR", price="7.50"), line("Spălare auto", "50.00")]),
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
    ],
}
# Booked by a person on another account than Jev chose for the same kind of work, so the
# rule proposed from it shows invoices on two accounts.
BOOKED_BY_HAND = ("12345674", "SA 3340", "611")


# What Jev answers, by a word in the invoice line: the arguments of FakeOpenRouter.answer_for.
JEV_ANSWERS = {
    "ciment": {"choice": "302", "confidence": 0.58, "probabilities_extra": {"371": 0.27, "628": 0.09}},
    "hârtie": {"choice": "302", "confidence": 0.91},
    "pungi": {"choice": "302", "confidence": 0.93},
    "revizie": {"choice": "628", "confidence": 0.88},
}


def build(folder: Path, now: datetime | None = None) -> Config:
    """Make the demo in `folder` from nothing and return its settings."""
    shutil.rmtree(folder, ignore_errors=True)
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

    jev = FakeOpenRouter()
    jev.valid_keys = {OPENROUTER_KEY}
    for word, answer in JEV_ANSWERS.items():
        jev.answer_for(word, **answer)

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

    message_id = 3000
    for moment, batch in ((now - timedelta(days=6), EARLIER), (now, TODAY)):
        for cui, invoices in batch.items():
            anaf = FakeAnaf()
            for supplier, supplier_cui, number, lines in invoices:
                message_id += 1
                anaf.add(str(message_id), xml=rich_invoice_xml(
                    lines=lines, number=number, supplier_cui=supplier_cui, supplier_name=supplier,
                ))
            service_at(moment, anaf).sync(cui)

    cui, number, cont = BOOKED_BY_HAND
    desk = service_at(now, FakeAnaf())
    by_hand = next(i for i in desk.invoices(cui=cui)["invoices"] if i["invoice_number"] == number)
    desk.set_cont(by_hand["id"], cont=cont)

    # Last week's invoices were imported into SAGA in the meantime.
    earlier_ids = [str(3000 + n) for n in range(1, 1 + sum(len(v) for v in EARLIER.values()))]
    service_at(now, FakeAnaf()).mark_uploaded(earlier_ids)
    return cfg
