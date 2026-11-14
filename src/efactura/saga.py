"""An e-Factura invoice rewritten in the layout SAGA C imports ("Import date din fisiere XML").

SAGA does not read ANAF's UBL file; it reads its own layout, which has an account
(<Cont>) on every line. Layout and file name are from SAGA's manual:
https://manual.sagasoft.ro/sagac/topic-76-import-date.html

The manual does not state the date, number or text formats. The values below follow
what SAGA uses elsewhere and are kept together here so they can be corrected in one
place once a file produced by SAGA itself has been compared.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from xml.etree import ElementTree

from .invoice import Invoice, Party

log = logging.getLogger(__name__)

DATE_FORMAT = "%d.%m.%Y"  # inside the file
FILE_DATE_FORMAT = "%d.%m.%Y"  # in the file name
ENCODING = "utf-8"
CENT = Decimal("0.01")
REVERSE_CHARGE = "AE"

# ANAF carries UN/ECE unit codes; SAGA shows the unit as text.
UNITS = {
    "H87": "BUC", "C62": "BUC", "EA": "BUC", "XPP": "BUC", "NAR": "BUC",
    "KGM": "KG", "GRM": "G", "TNE": "T",
    "LTR": "L", "MLT": "ML", "HLT": "HL",
    "MTR": "M", "CMT": "CM", "MMT": "MM", "KMT": "KM", "MTK": "MP", "MTQ": "MC",
    "HUR": "ORA", "MIN": "MIN", "DAY": "ZI", "MON": "LUNA", "ANN": "AN",
    "KWH": "KWH", "MWH": "MWH",
    "SET": "SET", "PR": "PER", "XBX": "CUTIE", "XPK": "PACHET", "XBG": "SAC", "XPX": "PALET",
    "XRO": "ROLA", "XBO": "STICLA",
}

_UNSAFE_IN_FILE_NAME = re.compile(r"[^A-Za-z0-9.]+")


@dataclass
class _Row:
    description: str
    unit: str
    quantity: Decimal
    price: Decimal
    value: Decimal
    percent: Decimal
    vat: Decimal


def file_name(invoice: Invoice, distinct: str | None = None) -> str:
    """F_<cod-fiscal>_<numar-factura>_<data-factura>.xml, with the supplier's code so that
    the same number from two suppliers cannot collide.

    Characters a file name cannot hold are replaced, so "AB 12" and "AB/12" give the same
    name. `distinct` (the ANAF message id) is added to the number to tell such a second
    invoice apart.
    """
    number = _safe(invoice.number) or "fara-numar"
    if distinct:
        number = f"{number}-{_safe(distinct)}"
    return "F_{}_{}_{}.xml".format(
        _safe(invoice.supplier.cui) or "fara-cod",
        number,
        _date(invoice.issue_date, FILE_DATE_FORMAT) or "fara-data",
    )


def build_xml(
    invoice: Invoice, cont: str, upload_index: str | None, download_id: str | None
) -> bytes:
    """The invoice as a SAGA import file, every line booked on `cont`.

    `upload_index` and `download_id` are ANAF's ids for the e-Factura (SPV).
    """
    rows = _rows(invoice)
    root = ElementTree.Element("Facturi")
    factura = ElementTree.SubElement(root, "Factura")

    antet = ElementTree.SubElement(factura, "Antet")
    for tag, value in (
        *_party_tags("Furnizor", invoice.supplier, extra_after_iban=True),
        *_party_tags("Client", invoice.customer, extra_after_iban=False),
        ("FacturaNumar", invoice.number),
        ("FacturaData", _date(invoice.issue_date, DATE_FORMAT)),
        ("FacturaScadenta", _date(invoice.due_date, DATE_FORMAT)),
        ("FacturaTaxareInversa", _yes(any(i.vat_category == REVERSE_CHARGE for i in invoice.lines))),
        ("FacturaTVAIncasare", _yes(invoice.vat_on_collection)),
        ("FacturaInformatiiSuplimentare", invoice.note),
        ("FacturaMoneda", invoice.currency),
        ("FacturaGreutate", "0"),
        ("FacturaIndexSPV", upload_index),
        ("FacturaIndexDescarcareSPV", download_id),
    ):
        ElementTree.SubElement(antet, tag).text = value or ""

    continut = ElementTree.SubElement(ElementTree.SubElement(factura, "Detalii"), "Continut")
    for position, row in enumerate(rows, start=1):
        linie = ElementTree.SubElement(continut, "Linie")
        # The supplier's article code and barcode are left out on purpose: with them SAGA
        # may match a stock article and take the account from that article instead.
        for tag, value in (
            ("LinieNrCrt", str(position)),
            ("Descriere", row.description),
            ("InformatiiSuplimentare", ""),
            ("UM", row.unit),
            ("Cantitate", _plain(row.quantity)),
            ("Pret", _price(row.price)),
            ("Valoare", _money(row.value)),
            ("ProcTVA", _plain(row.percent)),
            ("TVA", _money(row.vat)),
            ("Cont", cont),
        ):
            ElementTree.SubElement(linie, tag).text = value

    ElementTree.indent(root)
    return ElementTree.tostring(
        root, encoding=ENCODING, xml_declaration=True, short_empty_elements=False
    )


def _party_tags(prefix: str, party: Party, extra_after_iban: bool) -> list[tuple[str, str | None]]:
    """SAGA orders the supplier's and the client's fields differently."""
    code = party.vat_id or party.cui
    if extra_after_iban:
        return [
            (f"{prefix}Nume", party.name), (f"{prefix}CIF", code),
            (f"{prefix}NrRegCom", party.registration), (f"{prefix}Capital", None),
            (f"{prefix}Tara", party.country), (f"{prefix}Localitate", party.city),
            (f"{prefix}Judet", party.county), (f"{prefix}Adresa", party.address),
            (f"{prefix}Telefon", party.phone), (f"{prefix}Mail", party.email),
            (f"{prefix}Banca", party.bank), (f"{prefix}IBAN", party.iban),
            (f"{prefix}InformatiiSuplimentare", None),
        ]
    return [
        (f"{prefix}Nume", party.name), (f"{prefix}InformatiiSuplimentare", None),
        (f"{prefix}CIF", code), (f"{prefix}NrRegCom", party.registration),
        (f"{prefix}Judet", party.county), (f"{prefix}Tara", party.country),
        (f"{prefix}Localitate", party.city), (f"{prefix}Adresa", party.address),
        (f"{prefix}Banca", party.bank), (f"{prefix}IBAN", party.iban),
        (f"{prefix}Telefon", party.phone), (f"{prefix}Mail", party.email),
    ]


def _rows(invoice: Invoice) -> list[_Row]:
    # SAGA has no credit-note document; its manual says to enter one as an invoice,
    # so the amounts are written negative.
    sign = Decimal(-1) if invoice.is_credit_note else Decimal(1)
    rows = []
    for item in invoice.lines:
        percent = _percent(item.vat_percent, item.vat_category)
        value = sign * item.value
        quantity, price = sign * item.quantity, item.unit_price
        # SAGA must be able to get the value back from quantity x price. ANAF's value
        # already includes discounts on the line, its price does not; and a line may
        # carry no quantity at all.
        if not item.quantity:
            quantity, price = Decimal(1), value
        elif abs(quantity * price - value) > CENT:
            price = value / quantity
        rows.append(_Row(
            description=item.description,
            unit=UNITS.get((item.unit or "").upper(), item.unit or ""),
            quantity=quantity,
            price=price,
            value=value,
            percent=percent,
            vat=_vat(value, percent),
        ))
    # Discounts and charges on the invoice as a whole: one line each, so the totals match.
    for item in invoice.adjustments:
        percent = _percent(item.vat_percent, item.vat_category)
        value = sign * (item.amount if item.is_charge else -item.amount)
        rows.append(_Row(
            description=item.reason or ("Taxa suplimentara" if item.is_charge else "Discount"),
            unit="BUC",
            quantity=Decimal(1),
            price=value.quantize(CENT, ROUND_HALF_UP),
            value=value,
            percent=percent,
            vat=_vat(value, percent),
        ))
    _settle_vat(rows, sign * invoice.total_vat if invoice.total_vat is not None else None)
    return rows


def _settle_vat(rows: list[_Row], invoice_vat: Decimal | None) -> None:
    """ANAF's file has no VAT per line, so it is calculated. Rounding line by line can
    drift from the invoice's own VAT total, which is worked out on the sum. Close the gap
    one cent per line, largest lines first, so that no line moves by more than a cent."""
    taxed = [row for row in rows if row.percent]
    if invoice_vat is None or not taxed:
        return
    difference = (invoice_vat - sum(row.vat for row in rows)).quantize(CENT, ROUND_HALF_UP)
    cents = int(abs(difference) / CENT)
    if not cents:
        return
    if cents > len(taxed):
        # More than rounding can explain: something else differs, so leave it visible.
        log.warning(
            "Line VAT differs from the invoice's VAT total by %s; left as calculated.", difference
        )
        return
    step = CENT.copy_sign(difference)
    for row in sorted(taxed, key=lambda row: abs(row.value), reverse=True)[:cents]:
        row.vat += step


def _percent(percent: Decimal | None, category: str | None) -> Decimal:
    return Decimal(0) if percent is None or category == REVERSE_CHARGE else percent


def _vat(value: Decimal, percent: Decimal) -> Decimal:
    return (value * percent / 100).quantize(CENT, ROUND_HALF_UP)


def _money(amount: Decimal) -> str:
    return format(_no_minus_zero(amount.quantize(CENT, ROUND_HALF_UP)), "f")


def _plain(number: Decimal) -> str:
    """As written on the invoice."""
    return format(_no_minus_zero(number), "f")


def _price(number: Decimal) -> str:
    """As on the invoice when it has two to six decimals; a calculated price is brought
    into that range."""
    exponent = number.as_tuple().exponent
    if exponent < -6:
        number = number.quantize(Decimal("0.000001"), ROUND_HALF_UP)
    elif exponent > -2:
        number = number.quantize(CENT, ROUND_HALF_UP)
    return format(_no_minus_zero(number), "f")


def _no_minus_zero(number: Decimal) -> Decimal:
    return abs(number) if number == 0 else number


def _yes(flag: bool) -> str:
    return "Da" if flag else "Nu"


def _date(iso: str | None, pattern: str) -> str | None:
    try:
        return date.fromisoformat((iso or "")[:10]).strftime(pattern)
    except ValueError:
        return None


def _safe(text: str | None) -> str:
    return _UNSAFE_IN_FILE_NAME.sub("-", text or "").strip("-")
