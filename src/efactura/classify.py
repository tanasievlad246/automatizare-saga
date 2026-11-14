"""Deciding an invoice's account: the rules first, and the question for Jev when they cannot."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from decimal import Decimal

from .errors import JEV_ERROR, EfacturaError
from .invoice import Invoice, Line
from .rules import Rulebook, Subject

# Jev always picks one of the options it is given, so "none of them" has to be an option.
NONE_OF_THESE = "altul"
NONE_OF_THESE_MEANS = "Niciun cont din această listă nu se potrivește cu ceea ce s-a cumpărat."
QUESTION = "cont"
# Above about 32,000 bytes of text Jev switches to a slower, less accurate mode.
MAX_REQUEST_BYTES = 30_000


@dataclass(frozen=True)
class Decision:
    cont: str
    rule: str  # the rule that decided
    line: int  # the line it decided on


@dataclass(frozen=True)
class JevAnswer:
    choice: str | None  # None: Jev refused, or picked "none of these"
    confidence: float | None
    probabilities: dict[str, float]
    refused: bool


def deciding_line(invoice: Invoice) -> Line | None:
    """The line with the largest value, whatever its sign; the first of equals."""
    return max(invoice.lines, key=lambda item: abs(item.value), default=None)


def subject_of(invoice: Invoice) -> Subject | None:
    """What the rules read from this invoice; None when it has no lines."""
    heaviest = deciding_line(invoice)
    if heaviest is None:
        return None
    return Subject(
        supplier_cui=invoice.supplier.cui,
        description=heaviest.description,
        seller_code=heaviest.seller_code,
        barcode=heaviest.barcode,
        commodity_codes=heaviest.commodity_codes,
    )


def decide_by_rules(invoice: Invoice, rulebook: Rulebook) -> Decision | None:
    """The account the rules give the deciding line; None when they give it none."""
    subject = subject_of(invoice)
    rule = rulebook.rule_for(subject) if subject else None
    if rule is None:
        return None
    return Decision(cont=rule.cont, rule=rule.name, line=deciding_line(invoice).number)


# --- Jev --------------------------------------------------------------------------


def jev_request(invoice: Invoice, rulebook: Rulebook, model: str) -> dict:
    """The body for OpenRouter's Decisions API.

    Only what is needed to pick an account is sent: the supplier and the lines. The buyer,
    addresses, bank accounts and contacts stay here.
    """
    heaviest = deciding_line(invoice)
    request = {
        "model": model,
        "state": {
            "furnizor": {"nume": invoice.supplier.name, "cui": invoice.supplier.cui},
            "factura": {
                "tip": "nota de credit" if invoice.is_credit_note else "factura",
                "moneda": invoice.currency,
                "total_fara_tva": _plain(invoice.total_without_vat),
            },
            "linia_cu_valoarea_cea_mai_mare": heaviest.number if heaviest else None,
            "linii": [],
            "linii_omise": 0,
        },
        "questions": {
            QUESTION: {
                "type": "choice",
                "instructions": rulebook.instructions,
                "criteria": {**rulebook.accounts, NONE_OF_THESE: NONE_OF_THESE_MEANS},
            }
        },
    }

    # Largest lines first, as many as fit; then back in invoice order.
    budget = MAX_REQUEST_BYTES - _size(request)
    kept = []
    for item in sorted(invoice.lines, key=lambda item: abs(item.value), reverse=True):
        described = _describe(item)
        cost = _size(described) + 2  # the separator between list items
        if cost > budget:
            break
        budget -= cost
        kept.append(described)
    request["state"]["linii"] = sorted(kept, key=lambda item: item["nr"])
    request["state"]["linii_omise"] = len(invoice.lines) - len(kept)
    return request


def read_jev_answer(body, rulebook: Rulebook) -> JevAnswer:
    try:
        answer = body["answers"][QUESTION]
        kind = answer["type"]
    except (KeyError, TypeError):
        raise EfacturaError(JEV_ERROR, "Jev's reply has no answer to the question.") from None

    if kind == "refusal":
        return JevAnswer(choice=None, confidence=None, probabilities={}, refused=True)
    choice = answer.get("choice")
    if kind != "choice" or (choice != NONE_OF_THESE and choice not in rulebook.accounts):
        raise EfacturaError(JEV_ERROR, f"Jev's reply is not one of the accounts offered: {choice!r}.")

    confidence = answer.get("confidence")
    probabilities = answer.get("probabilities") or {}
    if not _is_number(confidence, allow_none=True) or not isinstance(probabilities, dict) or not all(
        _is_number(value) for value in probabilities.values()
    ):
        raise EfacturaError(JEV_ERROR, "Jev's reply carries a confidence that is not a number.")
    if confidence is not None and not 0 <= confidence <= 1:
        # On another scale (0-100, say) every answer would clear the level. Do not guess.
        raise EfacturaError(
            JEV_ERROR, f"Jev's reply carries a confidence outside 0 to 1: {confidence!r}."
        )
    return JevAnswer(
        choice=None if choice == NONE_OF_THESE else choice,
        confidence=float(confidence) if confidence is not None else None,
        probabilities={str(key): float(value) for key, value in probabilities.items()},
        refused=False,
    )


def _describe(item: Line) -> dict:
    described = {
        "nr": item.number,
        "descriere": item.description,
        "cod_furnizor": item.seller_code,
        "coduri_clasificare": list(item.commodity_codes),
        "um": item.unit,
        "cantitate": _plain(item.quantity),
        "valoare_fara_tva": _plain(item.value),
        "cota_tva": _plain(item.vat_percent),
    }
    return {key: value for key, value in described.items() if value not in (None, [], "")}


def _plain(number: Decimal | None) -> str | None:
    return format(number, "f") if number is not None else None


def _size(value) -> int:
    return len(json.dumps(value).encode("utf-8"))


def _is_number(value, allow_none: bool = False) -> bool:
    if value is None:
        return allow_none
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
