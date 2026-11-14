"""Build a made-up database to try the page against, without ANAF, OpenRouter or SAGA.

    uv run python scripts/seed_demo.py
    uv run efactura --config demo/config.toml dev

Everything goes into demo/ (ignored by git). The invoices are invented; they are pushed
through the real sync and classification, with stand-ins answering for ANAF and for Jev,
so the screens show what the real program would produce.
"""

from __future__ import annotations

import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "tests"))  # the stand-ins and invoice builders live with the tests

from helpers import FakeAnaf, FakeOpenRouter, line, rich_invoice_xml  # noqa: E402

from efactura import auth  # noqa: E402
from efactura.config import load_config  # noqa: E402
from efactura.service import Service  # noqa: E402

DEMO = PROJECT / "demo"
CONFIG = """\
[anaf]
client_id = "EXEMPLU-client-id"
client_secret = "EXEMPLU-client-secret"
token_file = "tokens.json"

[api]
key = "EXEMPLU-cheie-locala"

[openrouter]
api_key = "sk-or-v1-EXEMPLU"
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


def main() -> None:
    shutil.rmtree(DEMO, ignore_errors=True)
    DEMO.mkdir()
    (DEMO / "config.toml").write_text(CONFIG, encoding="utf-8")
    cfg = load_config(DEMO / "config.toml")
    now = datetime.now().astimezone()

    auth.save_tokens(cfg.token_file, auth.Tokens(
        "EXEMPLU-access-token", "EXEMPLU-refresh-token",
        now + timedelta(days=60), now + timedelta(days=342, hours=1), now,
    ))

    jev = FakeOpenRouter()
    jev.valid_keys = {"sk-or-v1-EXEMPLU"}
    jev.answer_for("ciment", "302", confidence=0.58, probabilities_extra={"371": 0.27, "628": 0.09})
    jev.answer_for("hârtie", "302", confidence=0.91)
    jev.answer_for("pungi", "302", confidence=0.93)
    jev.answer_for("revizie", "628", confidence=0.88)

    def service_at(moment: datetime, anaf: FakeAnaf) -> Service:
        anaf.openrouter = jev
        anaf.valid_access = {"EXEMPLU-access-token"}
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
            result = service_at(moment, anaf).sync(cui)
            print(f"{CLIENTS[cui]}: {result['new_count']} saved, {result['classification']}")

    cui, number, cont = BOOKED_BY_HAND
    desk = service_at(now, FakeAnaf())
    by_hand = next(i for i in desk.invoices(cui=cui)["invoices"] if i["invoice_number"] == number)
    desk.set_cont(by_hand["id"], cont=cont)
    proposed = desk.rule_suggestions()
    print(f"\nProposed rules: {proposed['count']}")
    for rule in proposed["suggestions"]:
        print(f"  {rule['keywords'] or rule['supplier_name']} -> {rule['cont']}: {rule['by_cont']}")

    # Last week's invoices were imported into SAGA in the meantime.
    earlier_ids = [str(3000 + n) for n in range(1, 1 + sum(len(v) for v in EARLIER.values()))]
    service_at(now, FakeAnaf()).mark_uploaded(earlier_ids)
    print(f"\nReady. Start it with:\n  uv run efactura --config {DEMO.relative_to(PROJECT)}/config.toml dev")


if __name__ == "__main__":
    main()
