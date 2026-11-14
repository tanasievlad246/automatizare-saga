"""Builders shared by the tests: database rows, UBL documents, ANAF ZIPs."""

from __future__ import annotations

from efactura.standins import (  # noqa: F401  (the tests import these from here)
    SIGNATURE,
    UBL_INVOICE,
    VALID_CUI,
    FakeAnaf,
    FakeOpenRouter,
    adjustment,
    invoice_xml,
    line,
    make_zip,
    rich_invoice_xml,
)

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
