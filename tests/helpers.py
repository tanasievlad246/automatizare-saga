"""Builders shared by the tests: database rows, UBL documents, ANAF ZIPs."""

from __future__ import annotations

import io
import zipfile

VALID_CUI = "12345674"  # passes the CUI check digit
OTHER_VALID_CUI = "14399840"


def make_row(**overrides) -> dict:
    row = {
        "id": "3001",
        "cui": VALID_CUI,
        "message_type": "FACTURA PRIMITA",
        "anaf_created_at": "2026-11-10T14:15",
        "id_solicitare": "5001",
        "detalii": "Factura cu id_incarcare=5001 emisa de cif_emitent=87654321 pentru cif_beneficiar=12345674",
        "invoice_number": "FV-1042",
        "invoice_issue_date": "2026-11-09",
        "invoice_due_date": "2026-12-09",
        "invoice_type_code": "380",
        "supplier_cui": "87654321",
        "supplier_name": "Furnizor SRL",
        "customer_cui": VALID_CUI,
        "customer_name": "Client SRL",
        "currency": "RON",
        "total_without_vat": "1000.00",
        "total_vat": "190.00",
        "total_payable": "1190.00",
        "invoice_xml": "<Invoice/>",
        "signature_xml": "<Signature/>",
        "raw_metadata_json": "{}",
        "zip_sha256": "0" * 64,
        "xml_path": "invoices/11-11-2026/12345674_primita_3001.xml",
        "first_seen_at": "2026-11-11T09:30:00+02:00",
        "sync_run_id": None,
        "possible_duplicate_of": None,
    }
    row.update(overrides)
    return row


UBL_INVOICE = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:CustomizationID>urn:cen.eu:en16931:2017#compliant#urn:efactura.mfinante.ro:CIUS-RO:1.0.1</cbc:CustomizationID>
  <cbc:ID>{number}</cbc:ID>
  <cbc:IssueDate>2026-11-09</cbc:IssueDate>
  <cbc:DueDate>2026-12-09</cbc:DueDate>
  <cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode>
  <cbc:DocumentCurrencyCode>RON</cbc:DocumentCurrencyCode>
  <cac:AccountingSupplierParty>
    <cac:Party>
      <cac:PartyTaxScheme>
        <cbc:CompanyID>{supplier_cui}</cbc:CompanyID>
        <cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme>
      </cac:PartyTaxScheme>
      <cac:PartyLegalEntity>
        <cbc:RegistrationName>{supplier_name}</cbc:RegistrationName>
        <cbc:CompanyID>J40/1234/2020</cbc:CompanyID>
      </cac:PartyLegalEntity>
    </cac:Party>
  </cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty>
    <cac:Party>
      <cac:PartyLegalEntity>
        <cbc:RegistrationName>Client SRL</cbc:RegistrationName>
        <cbc:CompanyID>12345674</cbc:CompanyID>
      </cac:PartyLegalEntity>
    </cac:Party>
  </cac:AccountingCustomerParty>
  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="RON">190.00</cbc:TaxAmount>
  </cac:TaxTotal>
  <cac:LegalMonetaryTotal>
    <cbc:TaxExclusiveAmount currencyID="RON">1000.00</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="RON">1190.00</cbc:TaxInclusiveAmount>
    <cbc:PayableAmount currencyID="RON">1190.00</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
</Invoice>
"""

UBL_CREDIT_NOTE = """<?xml version="1.0" encoding="UTF-8"?>
<CreditNote xmlns="urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
            xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
            xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:ID>CN-7</cbc:ID>
  <cbc:IssueDate>2026-11-08</cbc:IssueDate>
  <cbc:CreditNoteTypeCode>381</cbc:CreditNoteTypeCode>
  <cbc:DocumentCurrencyCode>EUR</cbc:DocumentCurrencyCode>
  <cac:AccountingSupplierParty>
    <cac:Party>
      <cac:PartyName><cbc:Name>Lieferant GmbH</cbc:Name></cac:PartyName>
      <cac:PartyTaxScheme>
        <cbc:CompanyID>DE123456789</cbc:CompanyID>
        <cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme>
      </cac:PartyTaxScheme>
    </cac:Party>
  </cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty>
    <cac:Party>
      <cac:PartyTaxScheme>
        <cbc:CompanyID>RO 12345674</cbc:CompanyID>
        <cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme>
      </cac:PartyTaxScheme>
      <cac:PartyLegalEntity><cbc:RegistrationName>Client SRL</cbc:RegistrationName></cac:PartyLegalEntity>
    </cac:Party>
  </cac:AccountingCustomerParty>
  <cac:PaymentMeans>
    <cbc:PaymentMeansCode>30</cbc:PaymentMeansCode>
    <cbc:PaymentDueDate>2026-11-30</cbc:PaymentDueDate>
  </cac:PaymentMeans>
  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="RON">94.50</cbc:TaxAmount>
  </cac:TaxTotal>
  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="EUR">19.00</cbc:TaxAmount>
  </cac:TaxTotal>
  <cac:LegalMonetaryTotal>
    <cbc:TaxExclusiveAmount currencyID="EUR">100.00</cbc:TaxExclusiveAmount>
    <cbc:PayableAmount currencyID="EUR">119.00</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
</CreditNote>
"""

ANAF_ERROR_NOTICE = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<header xmlns="mfp:anaf:dgti:efactura:mesajEroriFactuta:v1" Index_incarcare="5009" Cif_emitent="12345674">
  <Error errorMessage="E: validari globale eroare regula: BR-CO-15"/>
</header>
"""

SIGNATURE = b'<?xml version="1.0" encoding="UTF-8"?><Signature xmlns="http://www.w3.org/2000/09/xmldsig#"/>'


def invoice_xml(number="FV-1042", supplier_cui="RO87654321", supplier_name="Furnizor SRL") -> bytes:
    return UBL_INVOICE.format(
        number=number, supplier_cui=supplier_cui, supplier_name=supplier_name
    ).encode("utf-8")


def make_zip(xml: bytes, number: str = "5001", signature: bytes | None = SIGNATURE) -> bytes:
    """An ANAF download: <number>.xml plus semnatura_<number>.xml."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{number}.xml", xml)
        if signature is not None:
            archive.writestr(f"semnatura_{number}.xml", signature)
    return buffer.getvalue()


# --- a stand-in for ANAF -------------------------------------------------------

import json as _json
from urllib.parse import parse_qs as _parse_qs

import httpx


class FakeAnaf:
    """Answers like logincert.anaf.ro (token calls) and api.anaf.ro (list, download)."""

    def __init__(self):
        self.entries: list[dict] = []
        self.zips: dict[str, bytes] = {}
        self.valid_access = {"access-1"}
        self.valid_refresh = {"refresh-1"}
        self.valid_codes = {"good-code"}
        self.page_size = 500
        self.list_error: str | None = None
        self.download_errors: dict[str, str] = {}
        self.unreachable_downloads: set[str] = set()
        self.issued = 1
        self.list_requests: list[dict] = []
        self.downloads: list[str] = []
        self.token_requests: list[dict] = []
        self.on_download = None  # called with the message id while a download is in flight
        self.openrouter = None  # a FakeOpenRouter, when the test also needs Jev

    # -- setting up what ANAF "has" --

    def add(self, message_id, tip="FACTURA PRIMITA", xml=None, created="202611101415",
            upload_index=None, with_zip=True):
        upload_index = upload_index or f"50{message_id}"
        self.entries.append(
            {
                "data_creare": created,
                "cif": VALID_CUI,
                "id_solicitare": upload_index,
                "detalii": f"Factura cu id_incarcare={upload_index} emisa de cif_emitent=87654321 "
                           f"pentru cif_beneficiar={VALID_CUI}",
                "tip": tip,
                "id": str(message_id),
            }
        )
        if with_zip:
            body = xml if xml is not None else invoice_xml(number=f"FV-{message_id}")
            self.zips[str(message_id)] = make_zip(body, number=upload_index)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self._handle))

    # -- answering --

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "logincert.anaf.ro":
            return self._token(request)
        if request.url.host == "openrouter.ai":
            if self.openrouter is None:
                raise AssertionError("This test did not expect a call to OpenRouter.")
            return self.openrouter.handle(request)
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        if token not in self.valid_access:
            return httpx.Response(401, text="Unauthorized")
        if request.url.path.endswith("/listaMesajePaginatieFactura"):
            return self._list(request)
        if request.url.path.endswith("/descarcare"):
            return self._download(request)
        return httpx.Response(404, text="not found")

    def _token(self, request: httpx.Request) -> httpx.Response:
        form = {k: v[0] for k, v in _parse_qs(request.content.decode()).items()}
        self.token_requests.append(form)
        if form.get("grant_type") == "authorization_code":
            accepted = form.get("code") in self.valid_codes
        else:
            accepted = form.get("refresh_token") in self.valid_refresh
        if not accepted:
            return httpx.Response(400, json={"error": "invalid_grant"})
        self.issued += 1
        access, refresh = f"access-{self.issued}", f"refresh-{self.issued}"
        self.valid_access.add(access)
        self.valid_refresh = {refresh}  # the previous refresh token stops working
        return httpx.Response(
            200,
            json={"access_token": access, "token_type": "Bearer",
                  "expires_in": 7776000, "refresh_token": refresh},
        )

    def _list(self, request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        self.list_requests.append(params)
        if self.list_error:
            return httpx.Response(200, json={"eroare": self.list_error, "titlu": "Lista Mesaje"})
        if not self.entries:
            return httpx.Response(
                200, json={"eroare": "Nu exista mesaje in intervalul selectat", "titlu": "Lista Mesaje"}
            )
        page = int(params["pagina"])
        pages = -(-len(self.entries) // self.page_size)
        chunk = self.entries[(page - 1) * self.page_size : page * self.page_size]
        return httpx.Response(
            200,
            json={
                "mesaje": chunk,
                "numar_inregistrari_in_pagina": str(len(chunk)),
                "numar_total_inregistrari_per_pagina": str(self.page_size),
                "numar_total_inregistrari": str(len(self.entries)),
                "numar_total_pagini": str(pages),
                "index_pagina_curenta": str(page),
                "serial": "1234AA456",
                "cui": params["cif"],
                "titlu": "Lista Mesaje",
            },
        )

    def _download(self, request: httpx.Request) -> httpx.Response:
        message_id = request.url.params["id"]
        self.downloads.append(message_id)
        if self.on_download:
            self.on_download(message_id)
        if message_id in self.unreachable_downloads:
            raise httpx.ConnectError("connection reset", request=request)
        if message_id in self.download_errors:
            return _eroare(self.download_errors[message_id], "Descarcare mesaj")
        if message_id not in self.zips:
            return _eroare(
                f"Pentru id={message_id} nu exista inregistrata nici o factura", "Descarcare mesaj"
            )
        return httpx.Response(
            200, content=self.zips[message_id], headers={"content-type": "application/zip"}
        )


def _eroare(text: str, title: str) -> httpx.Response:
    return httpx.Response(
        200,
        content=_json.dumps({"eroare": text, "titlu": title}).encode(),
        headers={"content-type": "application/json"},
    )


# --- invoices with lines, as the classification and the SAGA export need them -----

from decimal import Decimal as _Decimal

_RICH_INVOICE = """<?xml version="1.0" encoding="UTF-8"?>
<{root} xmlns="urn:oasis:names:specification:ubl:schema:xsd:{root}-2"
        xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
        xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:ID>{number}</cbc:ID>
  <cbc:IssueDate>2026-11-09</cbc:IssueDate>
  <cbc:DueDate>2026-12-09</cbc:DueDate>
  <cbc:{root}TypeCode>{type_code}</cbc:{root}TypeCode>
  <cbc:Note>Contract 15/2026</cbc:Note>
  <cbc:DocumentCurrencyCode>{currency}</cbc:DocumentCurrencyCode>
  {period}
  <cac:AccountingSupplierParty>
    <cac:Party>
      <cac:PostalAddress>
        <cbc:StreetName>Str. Fabricii 10</cbc:StreetName>
        <cbc:CityName>SECTOR3</cbc:CityName>
        <cbc:CountrySubentity>RO-B</cbc:CountrySubentity>
        <cac:Country><cbc:IdentificationCode>RO</cbc:IdentificationCode></cac:Country>
      </cac:PostalAddress>
      <cac:PartyTaxScheme>
        <cbc:CompanyID>{supplier_cui}</cbc:CompanyID>
        <cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme>
      </cac:PartyTaxScheme>
      <cac:PartyLegalEntity>
        <cbc:RegistrationName>{supplier_name}</cbc:RegistrationName>
        <cbc:CompanyID>J40/1234/2020</cbc:CompanyID>
      </cac:PartyLegalEntity>
      <cac:Contact>
        <cbc:Telephone>0211234567</cbc:Telephone>
        <cbc:ElectronicMail>office@furnizor.example</cbc:ElectronicMail>
      </cac:Contact>
    </cac:Party>
  </cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty>
    <cac:Party>
      <cac:PostalAddress>
        <cbc:StreetName>Bd. Unirii 1</cbc:StreetName>
        <cbc:CityName>Cluj-Napoca</cbc:CityName>
        <cbc:CountrySubentity>RO-CJ</cbc:CountrySubentity>
        <cac:Country><cbc:IdentificationCode>RO</cbc:IdentificationCode></cac:Country>
      </cac:PostalAddress>
      <cac:PartyTaxScheme>
        <cbc:CompanyID>RO12345674</cbc:CompanyID>
        <cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme>
      </cac:PartyTaxScheme>
      <cac:PartyLegalEntity>
        <cbc:RegistrationName>Client SRL</cbc:RegistrationName>
        <cbc:CompanyID>J12/55/2015</cbc:CompanyID>
      </cac:PartyLegalEntity>
    </cac:Party>
  </cac:AccountingCustomerParty>
  <cac:PaymentMeans>
    <cbc:PaymentMeansCode>30</cbc:PaymentMeansCode>
    <cac:PayeeFinancialAccount>
      <cbc:ID>RO49AAAA1B31007593840000</cbc:ID>
      <cbc:Name>Banca Exemplu</cbc:Name>
    </cac:PayeeFinancialAccount>
  </cac:PaymentMeans>
  {adjustments}
  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="{currency}">{vat_total}</cbc:TaxAmount>
  </cac:TaxTotal>
  <cac:LegalMonetaryTotal>
    <cbc:TaxExclusiveAmount currencyID="{currency}">{net_total}</cbc:TaxExclusiveAmount>
    <cbc:PayableAmount currencyID="{currency}">{payable}</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
  {lines}
</{root}>
"""


def line(name, value, quantity="1", unit="H87", percent="19", category="S", price=None,
         base_quantity=None, seller_code=None, barcode=None, commodity=None, description=None,
         vat_percent=None):
    """One invoice line, as the test wants to describe it.

    `percent` is what the invoice's VAT total is worked out from; `vat_percent` is what
    the line itself states, when the two must differ (reverse charge written with a rate).
    """
    return {
        "name": name, "value": value, "quantity": quantity, "unit": unit, "percent": percent,
        "stated_percent": vat_percent if vat_percent is not None else percent,
        "category": category, "price": price if price is not None else value,
        "base_quantity": base_quantity, "seller_code": seller_code, "barcode": barcode,
        "commodity": commodity, "description": description,
    }


def adjustment(amount, charge=False, reason="Discount comercial", percent="19", category="S"):
    """An invoice-level discount (or, with charge=True, an extra charge)."""
    return {"amount": amount, "charge": charge, "reason": reason, "percent": percent,
            "category": category}


def rich_invoice_xml(lines=None, number="FV-1042", supplier_cui="RO87654321",
                     supplier_name="Furnizor SRL", currency="RON", adjustments=(),
                     vat_total=None, credit_note=False, vat_on_collection=False) -> bytes:
    """A UBL invoice (or credit note) with addresses, a bank account and lines."""
    lines = [line("Servicii diverse", "1000.00")] if lines is None else lines
    root = "CreditNote" if credit_note else "Invoice"
    quantity_tag = "CreditedQuantity" if credit_note else "InvoicedQuantity"

    def optional(tag, value):
        return f"<{tag}>{value}</{tag}>" if value is not None else ""

    line_parts = []
    for position, item in enumerate(lines, start=1):
        base = optional("cbc:BaseQuantity", item["base_quantity"])
        commodity = (
            "<cac:CommodityClassification>"
            f'<cbc:ItemClassificationCode listID="STI">{item["commodity"]}</cbc:ItemClassificationCode>'
            "</cac:CommodityClassification>" if item["commodity"] else ""
        )
        seller = (f"<cac:SellersItemIdentification><cbc:ID>{item['seller_code']}</cbc:ID>"
                  "</cac:SellersItemIdentification>" if item["seller_code"] else "")
        barcode = (f'<cac:StandardItemIdentification><cbc:ID schemeID="0160">{item["barcode"]}</cbc:ID>'
                   "</cac:StandardItemIdentification>" if item["barcode"] else "")
        line_parts.append(
            f"<cac:{root}Line><cbc:ID>{position}</cbc:ID>"
            f'<cbc:{quantity_tag} unitCode="{item["unit"]}">{item["quantity"]}</cbc:{quantity_tag}>'
            f'<cbc:LineExtensionAmount currencyID="{currency}">{item["value"]}</cbc:LineExtensionAmount>'
            f"<cac:Item>{optional('cbc:Description', item['description'])}"
            f"<cbc:Name>{item['name']}</cbc:Name>{seller}{barcode}{commodity}"
            f"<cac:ClassifiedTaxCategory><cbc:ID>{item['category']}</cbc:ID>"
            f"<cbc:Percent>{item['stated_percent']}</cbc:Percent>"
            "<cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:ClassifiedTaxCategory></cac:Item>"
            f'<cac:Price><cbc:PriceAmount currencyID="{currency}">{item["price"]}</cbc:PriceAmount>'
            f"{base}</cac:Price></cac:{root}Line>"
        )

    adjustment_parts = [
        "<cac:AllowanceCharge>"
        f"<cbc:ChargeIndicator>{'true' if item['charge'] else 'false'}</cbc:ChargeIndicator>"
        f"<cbc:AllowanceChargeReason>{item['reason']}</cbc:AllowanceChargeReason>"
        f'<cbc:Amount currencyID="{currency}">{item["amount"]}</cbc:Amount>'
        f"<cac:TaxCategory><cbc:ID>{item['category']}</cbc:ID><cbc:Percent>{item['percent']}</cbc:Percent>"
        "<cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme></cac:TaxCategory>"
        "</cac:AllowanceCharge>"
        for item in adjustments
    ]

    net = sum((_Decimal(item["value"]) for item in lines), _Decimal(0))
    vat = sum((_Decimal(item["value"]) * _Decimal(item["percent"]) / 100 for item in lines), _Decimal(0))
    for item in adjustments:
        sign = 1 if item["charge"] else -1
        net += sign * _Decimal(item["amount"])
        vat += sign * _Decimal(item["amount"]) * _Decimal(item["percent"]) / 100
    vat = _Decimal(vat_total) if vat_total is not None else vat.quantize(_Decimal("0.01"))

    return _RICH_INVOICE.format(
        root=root, number=number, type_code="381" if credit_note else "380", currency=currency,
        supplier_cui=supplier_cui, supplier_name=supplier_name,
        period=("<cac:InvoicePeriod><cbc:DescriptionCode>432</cbc:DescriptionCode></cac:InvoicePeriod>"
                if vat_on_collection else ""),
        adjustments="".join(adjustment_parts), lines="".join(line_parts),
        vat_total=f"{vat:.2f}", net_total=f"{net:.2f}", payable=f"{net + vat:.2f}",
    ).encode("utf-8")


# --- a stand-in for OpenRouter's Decisions API ---------------------------------------


class FakeOpenRouter:
    """Answers like POST https://openrouter.ai/api/alpha/decisions.

    `answers` maps a word found in the invoice's line descriptions to the answer Jev gives;
    anything else gets `default`.
    """

    def __init__(self):
        self.valid_keys = {"or-test-key"}
        self.default = {"choice": "628", "confidence": 0.95}
        self.answers: dict[str, dict] = {}
        self.fail_with: list = []  # statuses (or "unreachable") for the next calls, in order
        self.fail_for: dict[str, int] = {}  # word in the invoice -> status, every time
        self.cost_per_call = 0.00002
        self.requests: list[dict] = []
        self.keys_seen: list[str] = []

    def answer_for(self, word, choice, confidence=0.95, **extra):
        self.answers[word] = {"choice": choice, "confidence": confidence, **extra}

    def handle(self, request: httpx.Request) -> httpx.Response:
        key = request.headers.get("authorization", "").removeprefix("Bearer ")
        self.keys_seen.append(key)
        body = _json.loads(request.content)
        self.requests.append(body)
        if self.fail_with:
            failure = self.fail_with.pop(0)
            if failure == "unreachable":
                raise httpx.ConnectError("connection reset", request=request)
            message = {402: "Insufficient credits. Add more using https://openrouter.ai/credits",
                       429: "Rate limit exceeded"}.get(failure, "Provider returned error")
            return httpx.Response(failure, json={"error": {"code": failure, "message": message}})
        if key not in self.valid_keys:
            return httpx.Response(401, json={"error": {"code": 401, "message": "No auth credentials found"}})

        described = " ".join(item["descriere"] for item in body["state"]["linii"]).lower()
        for word, status in self.fail_for.items():
            if word.lower() in described:
                return httpx.Response(
                    status, json={"error": {"code": status, "message": "Invalid request parameters"}}
                )
        chosen = next((a for word, a in self.answers.items() if word.lower() in described), self.default)
        if chosen.get("refusal"):
            answer = {"type": "refusal"}
        else:
            answer = {"type": "choice", "choice": chosen["choice"],
                      "probabilities": {chosen["choice"]: chosen.get("confidence") or 0.5,
                                        **chosen.get("probabilities_extra", {})}}
            if chosen.get("confidence") is not None:
                answer["confidence"] = chosen["confidence"]
        return httpx.Response(200, json={
            "id": f"gen-dec-{len(self.requests)}",
            "model": body["model"] + "-20261001",
            "provider": "TypeSafe",
            "answers": {"cont": answer},
            "usage": {"input_tokens": 400, "output_tokens": 12, "cost": self.cost_per_call},
        })

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handle))


# --- rules and accounts in a test database ----------------------------------------------


def set_rulebook(db_path, book) -> None:
    """Replace the accounts, rules and Jev question in a database with `book`'s."""
    from efactura.store import JEV_INSTRUCTIONS, Store

    store = Store(db_path)
    for cont in list(store.accounts()):
        store.delete_account(cont)
    for rule in store.rules():
        store.delete_rule(rule["id"])
    for cont, description in book.accounts.items():
        store.save_account(cont, description)
    for rule in book.rules:
        store.add_rule(
            name=rule.name, cont=rule.cont, keywords=rule.keywords, item_codes=rule.item_codes,
            commodity_prefixes=rule.commodity_prefixes, supplier_cuis=rule.supplier_cuis,
            client_cui=None, enabled=True,
        )
    store.set_setting(JEV_INSTRUCTIONS, book.instructions)
    store.close()
