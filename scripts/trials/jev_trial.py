"""Proba cu Jev: raspunde la mai multe intrebari intr-o singura cerere?

Se ruleaza o singura data, pe calculatorul pe care este instalat programul si cheia OpenRouter:

    "%LOCALAPPDATA%\\AutoSaga\\.venv\\Scripts\\python.exe" jev_trial.py "%LOCALAPPDATA%\\AutoSaga\\config.toml"

Trimite catre Jev o factura inventata, cu trei linii: o data cu o singura intrebare (ca azi),
o data cu trei intrebari, cate una pentru fiecare linie. Costa cat doua facturi obisnuite.
Nu citeste nicio factura reala, nu scrie nimic in baza de date si nu afiseaza cheia.
"""

from __future__ import annotations

import sys

from efactura import jev
from efactura.config import load_config
from efactura.service import Service

ACCOUNTS = {
    "6022": "Combustibil pentru vehicule: motorina, benzina.",
    "626": "Telefonie, internet, servicii postale.",
    "628": "Alte servicii prestate de terti.",
    "altul": "Niciun cont din aceasta lista nu se potriveste.",
}
LINES = [
    {"nr": 1, "descriere": "Motorina Euro 5", "um": "LTR", "cantitate": "60", "valoare_fara_tva": "450.00", "cota_tva": "19"},
    {"nr": 2, "descriere": "Abonament telefonie mobila", "um": "H87", "cantitate": "1", "valoare_fara_tva": "200.00", "cota_tva": "19"},
    {"nr": 3, "descriere": "Spalare auto", "um": "H87", "cantitate": "1", "valoare_fara_tva": "50.00", "cota_tva": "19"},
]


def request(model: str, questions: dict) -> dict:
    return {
        "model": model,
        "state": {
            "furnizor": {"nume": "Furnizor de proba SRL", "cui": "00000000"},
            "factura": {"tip": "factura", "moneda": "RON", "total_fara_tva": "700.00"},
            "linii": LINES,
        },
        "questions": questions,
    }


def question(text: str) -> dict:
    return {"type": "choice", "instructions": text, "criteria": ACCOUNTS}


def show(title: str, call: jev.JevCall, wanted: list[str]) -> bool:
    print(title)
    print(f"  raspuns HTTP: {call.status}, durata: {call.duration_ms} ms, cost: {call.cost_usd}")
    if not call.ok:
        print(f"  nu a mers: {call.error}")
        return False
    answers = call.response.get("answers") if isinstance(call.response, dict) else None
    answers = answers if isinstance(answers, dict) else {}
    for name in wanted:
        answer = answers.get(name)
        said = f"{answer.get('choice')} (sigur {answer.get('confidence')})" if isinstance(answer, dict) else "LIPSA"
        print(f"  {name}: {said}")
    return all(isinstance(answers.get(name), dict) for name in wanted)


def main() -> int:
    service = Service(load_config(sys.argv[1] if len(sys.argv) > 1 else "config.toml"))
    try:
        key, model, http = service.cfg.openrouter_api_key, service.cfg.jev_model, service._http
        if not key:
            print("Nu este setata nicio cheie OpenRouter (pagina \"Chei si parole\").")
            return 1
        one = jev.ask(http, key, request(model, {
            "cont": question("Pe ce cont se inregistreaza linia cu valoarea cea mai mare a acestei facturi primite?"),
        }))
        show("O intrebare, ca azi:", one, ["cont"])
        names = [f"linia_{line['nr']}" for line in LINES]
        three = jev.ask(http, key, request(model, {
            name: question(f"Pe ce cont se inregistreaza linia cu numarul {line['nr']} a acestei facturi primite? Celelalte linii sunt doar context.")
            for name, line in zip(names, LINES)
        }))
        together = show("Trei intrebari intr-o singura cerere:", three, names)
        print()
        print("REZULTAT: " + (
            "Jev raspunde la mai multe intrebari deodata." if together
            else "Jev NU a raspuns la toate cele trei intrebari; programul va intreba linie cu linie."
        ))
        print("Trimiteti-mi tot ce scrie mai sus.")
        return 0
    finally:
        service.close()


if __name__ == "__main__":
    sys.exit(main())
