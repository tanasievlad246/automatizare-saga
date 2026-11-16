"""Reading what ANAF's download returns: a ZIP with the message XML and a signature XML."""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

from .errors import ANAF_ERROR, EfacturaError

CBC = "{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}"
CAC = "{urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2}"
UBL_ROOTS = {
    "{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}Invoice": "InvoiceTypeCode",
    "{urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2}CreditNote": "CreditNoteTypeCode",
}

FIELD_NAMES = (
    "invoice_number", "invoice_issue_date", "invoice_due_date", "invoice_type_code",
    "supplier_cui", "supplier_name", "customer_cui", "customer_name",
    "currency", "total_without_vat", "total_vat", "total_payable",
)

_SIGNATURE_NAME = re.compile(r"^semnatura_.*\.xml$", re.IGNORECASE)
_ROMANIAN_VAT_ID = re.compile(r"^RO(\d+)$")
# A trade-register number such as J40/1234/2020, as opposed to a fiscal code.
_TRADE_REGISTER = re.compile(r"^[JFC]\d{0,2}/")
# UN/EDIFACT code 432 on the invoice period: VAT falls due when the invoice is paid.
VAT_ON_COLLECTION_CODE = "432"
MAX_MEMBER_BYTES = 200 * 1024 * 1024


@dataclass(frozen=True)
class Extracted:
    xml: bytes
    signature: bytes | None
    xml_name: str


def extract_zip(data: bytes, max_member_bytes: int = MAX_MEMBER_BYTES) -> Extracted:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise EfacturaError(ANAF_ERROR, "ANAF's download was not a ZIP file.") from None

    xml = signature = xml_name = None
    with archive:
        for info in archive.infolist():
            name = info.filename.rsplit("/", 1)[-1]
            if info.is_dir() or not name.lower().endswith(".xml"):
                continue
            if info.file_size > max_member_bytes:
                raise EfacturaError(
                    ANAF_ERROR, f"{name} in ANAF's ZIP is too large ({info.file_size} bytes)."
                )
            content = archive.read(info)
            if _SIGNATURE_NAME.match(name):
                signature = content
            elif xml is None:
                xml, xml_name = content, name

    if xml is None:
        raise EfacturaError(ANAF_ERROR, "ANAF's ZIP did not contain a message XML.")
    return Extracted(xml=xml, signature=signature, xml_name=xml_name)


def decode_xml(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


def parse_invoice_fields(xml: bytes) -> dict:
    """Invoice fields from a UBL invoice or credit note; all None for anything else."""
    fields = dict.fromkeys(FIELD_NAMES)
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        return fields
    type_code_tag = UBL_ROOTS.get(root.tag)
    if type_code_tag is None:
        return fields

    fields["invoice_number"] = _text(root, f"{CBC}ID")
    fields["invoice_issue_date"] = _text(root, f"{CBC}IssueDate")
    fields["invoice_due_date"] = _text(root, f"{CBC}DueDate") or _text(
        root, f"{CAC}PaymentMeans/{CBC}PaymentDueDate"
    )
    fields["invoice_type_code"] = _text(root, f"{CBC}{type_code_tag}")
    fields["currency"] = _text(root, f"{CBC}DocumentCurrencyCode")

    for side, tag in (("supplier", "AccountingSupplierParty"), ("customer", "AccountingCustomerParty")):
        party = root.find(f"{CAC}{tag}/{CAC}Party")
        if party is not None:
            fields[f"{side}_cui"] = _company_id(party)
            fields[f"{side}_name"] = _text(
                party, f"{CAC}PartyLegalEntity/{CBC}RegistrationName"
            ) or _text(party, f"{CAC}PartyName/{CBC}Name")

    totals = root.find(f"{CAC}LegalMonetaryTotal")
    if totals is not None:
        fields["total_without_vat"] = _text(totals, f"{CBC}TaxExclusiveAmount")
        fields["total_payable"] = _text(totals, f"{CBC}PayableAmount")
    fields["total_vat"] = _vat_total(root, fields["currency"])
    return fields


def _text(node, path: str) -> str | None:
    found = node.find(path)
    if found is None or found.text is None:
        return None
    return found.text.strip() or None


def _company_id(party) -> str | None:
    """VAT id if present, else the legal registration id. 'RO123' becomes '123'."""
    raw = _text(party, f"{CAC}PartyTaxScheme/{CBC}CompanyID") or _text(
        party, f"{CAC}PartyLegalEntity/{CBC}CompanyID"
    )
    return normalise_company_id(raw) if raw is not None else None


def normalise_company_id(raw: str) -> str:
    """A company id as this tool compares it: no spaces, upper case, and a Romanian VAT
    number without its RO ("ro 123" becomes "123"). Foreign ids are kept ("DE123456789")."""
    compact = "".join(raw.split()).upper()
    match = _ROMANIAN_VAT_ID.match(compact)
    return match.group(1) if match else compact


def _vat_total(root, currency: str | None) -> str | None:
    amounts = root.findall(f"{CAC}TaxTotal/{CBC}TaxAmount")
    for amount in amounts:
        if currency and amount.get("currencyID") == currency:
            return (amount.text or "").strip() or None
    return (amounts[0].text or "").strip() or None if amounts else None


# --- the whole invoice, for classification and the SAGA export --------------------


@dataclass(frozen=True)
class Party:
    name: str | None
    cui: str | None  # fiscal code without the RO prefix
    vat_id: str | None  # VAT number as written (RO87654321); None when not registered for VAT
    registration: str | None  # trade-register number (J40/1234/2020)
    country: str | None
    county: str | None  # "B", "CJ": the part after "RO-"
    city: str | None
    address: str | None
    phone: str | None
    email: str | None
    bank: str | None
    iban: str | None


@dataclass(frozen=True)
class Line:
    number: int  # position on the invoice, from 1
    description: str
    seller_code: str | None
    barcode: str | None
    commodity_codes: tuple[str, ...]  # CPV / NC classification codes
    unit: str | None  # UN/ECE unit code as ANAF carries it (H87, KGM, LTR)
    quantity: Decimal
    unit_price: Decimal
    value: Decimal  # without VAT
    vat_percent: Decimal | None
    vat_category: str | None  # S standard, AE reverse charge, Z zero, E exempt, O outside scope


@dataclass(frozen=True)
class Adjustment:
    """A discount or an extra charge on the invoice as a whole."""

    is_charge: bool
    reason: str | None
    amount: Decimal
    vat_percent: Decimal | None
    vat_category: str | None


@dataclass(frozen=True)
class Invoice:
    number: str | None
    issue_date: str | None
    due_date: str | None
    type_code: str | None
    currency: str | None
    note: str | None
    is_credit_note: bool
    vat_on_collection: bool
    supplier: Party
    customer: Party
    lines: tuple[Line, ...]
    adjustments: tuple[Adjustment, ...]
    total_without_vat: Decimal | None
    total_vat: Decimal | None
    total_payable: Decimal | None
    # What was paid before (BT-113) and a rounding of what is due (BT-114), as written. Some
    # suppliers carry an earlier unpaid balance in the paid amount, with a minus.
    total_prepaid: Decimal | None = None
    total_rounding: Decimal | None = None

    @property
    def total_with_vat(self) -> Decimal | None:
        return total_with_vat(self.total_without_vat, self.total_vat, self.total_payable)


def total_with_vat(
    without_vat: Decimal | None, vat: Decimal | None, payable: Decimal | None
) -> Decimal | None:
    """What an invoice itself is worth, VAT included: BT-109 + BT-110, which EN 16931 makes
    equal to BT-112. It is not what is left to pay (BT-115): that also counts what was paid
    before and, at some suppliers, what is still owed from earlier invoices. An invoice
    without a readable net total or VAT has only the amount to pay to go by."""
    if without_vat is None or vat is None:
        return payable
    return without_vat + vat


def total_with_vat_of(stored: dict) -> Decimal | None:
    """The same, from an invoice's totals as they are stored: as text."""
    return total_with_vat(
        *(_amount(stored.get(name)) for name in ("total_without_vat", "total_vat", "total_payable"))
    )


def parse_invoice(xml: bytes | str) -> Invoice | None:
    """A UBL invoice or credit note in full; None for anything else."""
    data = xml.encode("utf-8") if isinstance(xml, str) else xml
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError:
        return None
    if root.tag not in UBL_ROOTS:
        return None
    is_credit_note = root.tag.endswith("}CreditNote")
    line_tag, quantity_tag = (
        ("CreditNoteLine", "CreditedQuantity") if is_credit_note else ("InvoiceLine", "InvoicedQuantity")
    )
    fields = parse_invoice_fields(data)
    totals = root.find(f"{CAC}LegalMonetaryTotal")

    def total(tag: str) -> Decimal | None:
        return _amount(_text(totals, f"{CBC}{tag}")) if totals is not None else None

    return Invoice(
        number=fields["invoice_number"],
        issue_date=fields["invoice_issue_date"],
        due_date=fields["invoice_due_date"],
        type_code=fields["invoice_type_code"],
        currency=fields["currency"],
        note=_text(root, f"{CBC}Note"),
        is_credit_note=is_credit_note,
        vat_on_collection=(
            _text(root, f"{CAC}InvoicePeriod/{CBC}DescriptionCode") == VAT_ON_COLLECTION_CODE
        ),
        supplier=_party(root, "AccountingSupplierParty", payee_account=True),
        customer=_party(root, "AccountingCustomerParty", payee_account=False),
        lines=tuple(
            _line(node, position, quantity_tag)
            for position, node in enumerate(root.findall(f"{CAC}{line_tag}"), start=1)
        ),
        adjustments=tuple(_adjustment(node) for node in root.findall(f"{CAC}AllowanceCharge")),
        total_without_vat=_amount(fields["total_without_vat"]),
        total_vat=_amount(fields["total_vat"]),
        total_payable=_amount(fields["total_payable"]),
        total_prepaid=total("PrepaidAmount"),
        total_rounding=total("PayableRoundingAmount"),
    )


def _party(root, tag: str, payee_account: bool) -> Party:
    party = root.find(f"{CAC}{tag}/{CAC}Party")
    if party is None:
        return Party(*([None] * 12))
    vat_id = _text(party, f"{CAC}PartyTaxScheme/{CBC}CompanyID")
    legal_id = _text(party, f"{CAC}PartyLegalEntity/{CBC}CompanyID")
    county = _text(party, f"{CAC}PostalAddress/{CBC}CountrySubentity")
    account = root.find(f"{CAC}PaymentMeans/{CAC}PayeeFinancialAccount") if payee_account else None
    return Party(
        name=_text(party, f"{CAC}PartyLegalEntity/{CBC}RegistrationName")
        or _text(party, f"{CAC}PartyName/{CBC}Name"),
        cui=_company_id(party),
        vat_id="".join(vat_id.split()).upper() if vat_id else None,
        registration=legal_id if legal_id and _TRADE_REGISTER.match(legal_id.upper()) else None,
        country=_text(party, f"{CAC}PostalAddress/{CAC}Country/{CBC}IdentificationCode"),
        county=county.split("-", 1)[-1] if county else None,
        city=_text(party, f"{CAC}PostalAddress/{CBC}CityName"),
        address=_text(party, f"{CAC}PostalAddress/{CBC}StreetName"),
        phone=_text(party, f"{CAC}Contact/{CBC}Telephone"),
        email=_text(party, f"{CAC}Contact/{CBC}ElectronicMail"),
        bank=_text(account, f"{CBC}Name") if account is not None else None,
        iban=_text(account, f"{CBC}ID") if account is not None else None,
    )


def _line(node, position: int, quantity_tag: str) -> Line:
    quantity = node.find(f"{CBC}{quantity_tag}")
    item = node.find(f"{CAC}Item")
    price = _amount(_text(node, f"{CAC}Price/{CBC}PriceAmount")) or Decimal(0)
    per = _amount(_text(node, f"{CAC}Price/{CBC}BaseQuantity"))
    if per:  # the price is for `per` units
        price = price / per
    return Line(
        number=position,
        description=(_text(item, f"{CBC}Name") or _text(item, f"{CBC}Description") or "")
        if item is not None else "",
        seller_code=_text(item, f"{CAC}SellersItemIdentification/{CBC}ID") if item is not None else None,
        barcode=_text(item, f"{CAC}StandardItemIdentification/{CBC}ID") if item is not None else None,
        commodity_codes=tuple(
            code.text.strip()
            for code in (
                item.findall(f"{CAC}CommodityClassification/{CBC}ItemClassificationCode")
                if item is not None else ()
            )
            if code.text and code.text.strip()
        ),
        unit=quantity.get("unitCode") if quantity is not None else None,
        quantity=_amount(quantity.text if quantity is not None else None) or Decimal(0),
        unit_price=price,
        value=_amount(_text(node, f"{CBC}LineExtensionAmount")) or Decimal(0),
        vat_percent=_amount(_text(item, f"{CAC}ClassifiedTaxCategory/{CBC}Percent"))
        if item is not None else None,
        vat_category=_text(item, f"{CAC}ClassifiedTaxCategory/{CBC}ID") if item is not None else None,
    )


def _adjustment(node) -> Adjustment:
    return Adjustment(
        is_charge=(_text(node, f"{CBC}ChargeIndicator") or "").lower() == "true",
        reason=_text(node, f"{CBC}AllowanceChargeReason"),
        amount=_amount(_text(node, f"{CBC}Amount")) or Decimal(0),
        vat_percent=_amount(_text(node, f"{CAC}TaxCategory/{CBC}Percent")),
        vat_category=_text(node, f"{CAC}TaxCategory/{CBC}ID"),
    )


def _amount(text: str | None) -> Decimal | None:
    if text is None:
        return None
    try:
        value = Decimal(text.strip())
    except InvalidOperation:
        return None
    return value if value.is_finite() else None
