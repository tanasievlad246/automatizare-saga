"""Proba in SAGA: trei fisiere facute din doua facturi reale ale unui client.

Se ruleaza o singura data, pe calculatorul pe care este instalat programul:

    "%LOCALAPPDATA%\\AutoSaga\\.venv\\Scripts\\python.exe" saga_trial.py "%LOCALAPPDATA%\\AutoSaga\\config.toml" CUI

Optional: --primite 628,6022 (doua conturi pentru liniile facturii primite) si --emise 704.

Nu schimba nimic in baza de date si nu trimite nimic nicaieri. Scrie, in folderul din care
este rulat, "proba-saga\\<CUI>\\" cu trei subfoldere, fiecare de importat pe rand in SAGA
("Diverse" > "Import date", calea = subfolderul):

    1-primita-conturi-pe-linii   o factura primita, cu doua conturi diferite pe liniile ei
    2-emisa                      o factura emisa de client, singura
    3-amestecat                  amandoua intr-un singur fisier (de importat de doua ori)
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from xml.etree import ElementTree

from efactura import saga
from efactura.config import load_config
from efactura.invoice import parse_invoice


def newest(database: sqlite3.Connection, cui: str, kind: str, wanted) -> tuple[sqlite3.Row, object] | None:
    """The newest saved invoice of this kind that can be read and that `wanted` accepts."""
    rows = database.execute(
        "SELECT id, id_solicitare, invoice_xml FROM messages WHERE cui = ? AND message_type LIKE ? "
        "ORDER BY first_seen_at DESC, id DESC",
        (cui, f"{kind}%"),
    )
    for row in rows:
        invoice = parse_invoice(row["invoice_xml"] or "")
        if invoice is not None and invoice.lines and wanted(invoice):
            return row, invoice
    return None


def with_two_accounts(xml: bytes, second: str) -> bytes:
    """The same file with every second line on another account."""
    root = ElementTree.fromstring(xml)
    for position, line in enumerate(root.iter("Linie")):
        if position % 2 == 1:
            line.find("Cont").text = second
    ElementTree.indent(root)
    return ElementTree.tostring(root, encoding=saga.ENCODING, xml_declaration=True, short_empty_elements=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fisiere de proba pentru importul in SAGA.")
    parser.add_argument("config", help="calea catre config.toml al programului")
    parser.add_argument("cui", help="CUI-ul clientului, fara RO")
    parser.add_argument("--primite", default="628,6022", help="doua conturi pentru liniile facturii primite")
    parser.add_argument("--emise", default="704", help="contul pentru factura emisa")
    asked = parser.parse_args()
    first, _, second = asked.primite.partition(",")
    cui = asked.cui.upper().removeprefix("RO").strip()

    cfg = load_config(asked.config)
    database = sqlite3.connect(f"file:{cfg.db_path}?mode=ro", uri=True)
    database.row_factory = sqlite3.Row
    try:
        received = (
            newest(database, cui, "FACTURA PRIMITA", lambda invoice: len(invoice.lines) >= 2)
            or newest(database, cui, "FACTURA PRIMITA", lambda invoice: True)
        )
        issued = newest(database, cui, "FACTURA TRIMISA", lambda invoice: invoice.supplier.cui == cui)
    finally:
        database.close()
    if received is None or issued is None:
        missing = "primita" if received is None else "emisa"
        print(f"Nu am gasit nicio factura {missing} salvata pentru CUI {cui}. Descarcati facturile clientului si incercati din nou.")
        return 1

    (received_row, received_invoice), (issued_row, issued_invoice) = received, issued
    as_received = saga.Entry(received_invoice, first, received_row["id_solicitare"], received_row["id"])
    as_issued = saga.Entry(issued_invoice, asked.emise, issued_row["id_solicitare"], issued_row["id"])
    folder = Path.cwd() / "proba-saga" / cui
    files = {
        folder / "1-primita-conturi-pe-linii" / saga.file_name(received_invoice):
            with_two_accounts(saga.build_file([as_received]), second or first),
        folder / "2-emisa" / saga.file_name(issued_invoice): saga.build_file([as_issued]),
        folder / "3-amestecat" / saga.file_name(received_invoice): saga.build_file([as_received, as_issued]),
    }
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    print(f"Factura primita: {received_invoice.number} din {received_invoice.issue_date}, {len(received_invoice.lines)} linii, conturi {first} si {second or first}.")
    print(f"Factura emisa:   {issued_invoice.number} din {issued_invoice.issue_date}, {len(issued_invoice.lines)} linii, cont {asked.emise}.")
    print(f"Fisierele sunt in: {folder}")
    print()
    print("De incercat in SAGA, pe firma acestui client, cu sincronizare dupa \"Nr.+data\":")
    print("  1. Importati subfolderul 1. Liniile facturii au conturile diferite, asa cum sunt in fisier?")
    print("  2. Importati subfolderul 2. Factura apare in \"Iesiri\", cu contul si TVA-ul corecte?")
    print("     SAGA incearca sa o trimita din nou in e-Factura? Ce face cu un cumparator persoana fizica?")
    print("  3. Stergeti din SAGA cele doua facturi, apoi importati subfolderul 3. Una ajunge in \"Intrari\" si una in \"Iesiri\"?")
    print("  4. Importati subfolderul 3 inca o data. Le sare, sau le dubleaza?")
    return 0


if __name__ == "__main__":
    sys.exit(main())
