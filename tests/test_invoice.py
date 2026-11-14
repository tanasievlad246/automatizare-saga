import io
import zipfile

import pytest

from efactura.errors import EfacturaError
from efactura.invoice import FIELD_NAMES, decode_xml, extract_zip, parse_invoice_fields

from helpers import ANAF_ERROR_NOTICE, SIGNATURE, UBL_CREDIT_NOTE, invoice_xml, make_zip


def test_extracts_invoice_and_signature_from_an_anaf_zip():
    xml = invoice_xml()

    extracted = extract_zip(make_zip(xml, number="5001"))

    assert extracted.xml == xml
    assert extracted.signature == SIGNATURE
    assert extracted.xml_name == "5001.xml"


def test_signature_is_recognised_whatever_the_order_in_the_zip():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("semnatura_5001.xml", SIGNATURE)
        archive.writestr("5001.xml", b"<Invoice/>")

    extracted = extract_zip(buffer.getvalue())

    assert extracted.xml == b"<Invoice/>"
    assert extracted.signature == SIGNATURE


def test_zip_without_signature_still_yields_the_xml():
    extracted = extract_zip(make_zip(b"<Invoice/>", signature=None))

    assert extracted.xml == b"<Invoice/>"
    assert extracted.signature is None


def test_something_that_is_not_a_zip_is_an_anaf_error():
    with pytest.raises(EfacturaError) as info:
        extract_zip(b'{"eroare": "nope"}')

    assert info.value.code == "anaf_error"


def test_zip_with_no_xml_is_an_anaf_error():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", b"hello")

    with pytest.raises(EfacturaError) as info:
        extract_zip(buffer.getvalue())

    assert info.value.code == "anaf_error"


def test_oversized_zip_member_is_refused():
    with pytest.raises(EfacturaError) as info:
        extract_zip(make_zip(b"<Invoice>" + b"x" * 5000 + b"</Invoice>"), max_member_bytes=1000)

    assert info.value.code == "anaf_error"


def test_reads_invoice_fields():
    fields = parse_invoice_fields(invoice_xml(number="FV-1042", supplier_cui="RO87654321"))

    assert fields == {
        "invoice_number": "FV-1042",
        "invoice_issue_date": "2026-11-09",
        "invoice_due_date": "2026-12-09",
        "invoice_type_code": "380",
        "supplier_cui": "87654321",
        "supplier_name": "Furnizor SRL",
        "customer_cui": "12345674",
        "customer_name": "Client SRL",
        "currency": "RON",
        "total_without_vat": "1000.00",
        "total_vat": "190.00",
        "total_payable": "1190.00",
    }


def test_reads_credit_note_fields():
    fields = parse_invoice_fields(UBL_CREDIT_NOTE.encode("utf-8"))

    assert fields["invoice_number"] == "CN-7"
    assert fields["invoice_type_code"] == "381"
    assert fields["invoice_due_date"] == "2026-11-30"
    assert fields["supplier_name"] == "Lieferant GmbH"
    assert fields["currency"] == "EUR"
    assert fields["total_payable"] == "119.00"


def test_foreign_vat_id_is_kept_and_romanian_prefix_is_dropped():
    fields = parse_invoice_fields(UBL_CREDIT_NOTE.encode("utf-8"))

    assert fields["supplier_cui"] == "DE123456789"
    assert fields["customer_cui"] == "12345674"


def test_vat_total_is_the_one_in_the_document_currency():
    fields = parse_invoice_fields(UBL_CREDIT_NOTE.encode("utf-8"))

    assert fields["total_vat"] == "19.00"


def test_anaf_error_notice_has_no_invoice_fields():
    fields = parse_invoice_fields(ANAF_ERROR_NOTICE.encode("utf-8"))

    assert fields == dict.fromkeys(FIELD_NAMES)


def test_unreadable_xml_has_no_invoice_fields_and_does_not_raise():
    fields = parse_invoice_fields(b"<Invoice><unclosed>")

    assert fields == dict.fromkeys(FIELD_NAMES)


def test_decodes_utf8_with_or_without_a_byte_order_mark():
    text = "<n>Ștefan Țăran</n>"

    assert decode_xml(text.encode("utf-8")) == text
    assert decode_xml(b"\xef\xbb\xbf" + text.encode("utf-8")) == text


def test_undecodable_bytes_do_not_raise():
    assert "<n>" in decode_xml(b"<n>\xff\xfe</n>")


# --- the whole invoice: parties, lines, discounts ---------------------------------

from decimal import Decimal

from efactura.invoice import parse_invoice

from helpers import adjustment, line, rich_invoice_xml


def test_reads_every_line_with_its_value_quantity_and_vat():
    invoice = parse_invoice(rich_invoice_xml(lines=[
        line("Motorina Euro 5", "450.00", quantity="60", unit="LTR", price="7.50"),
        line("Spalare auto", "50.00", percent="9"),
    ]))

    first, second = invoice.lines
    assert (first.number, first.description, first.unit) == (1, "Motorina Euro 5", "LTR")
    assert (first.quantity, first.unit_price, first.value) == (
        Decimal("60"), Decimal("7.50"), Decimal("450.00")
    )
    assert (first.vat_percent, first.vat_category) == (Decimal("19"), "S")
    assert (second.number, second.value, second.vat_percent) == (2, Decimal("50.00"), Decimal("9"))


def test_line_carries_the_suppliers_codes():
    invoice = parse_invoice(rich_invoice_xml(lines=[
        line("Toner", "200.00", seller_code="TN-2420", barcode="5941234567890", commodity="30125100"),
    ]))

    (item,) = invoice.lines
    assert item.seller_code == "TN-2420"
    assert item.barcode == "5941234567890"
    assert item.commodity_codes == ("30125100",)


def test_description_is_used_when_a_line_has_no_name():
    xml = rich_invoice_xml(lines=[line("X", "10.00", description="Servicii de paza")])
    xml = xml.replace(b"<cbc:Name>X</cbc:Name>", b"")

    assert parse_invoice(xml).lines[0].description == "Servicii de paza"


def test_unit_price_is_per_one_unit_when_the_price_is_for_several():
    invoice = parse_invoice(rich_invoice_xml(lines=[
        line("Suruburi", "30.00", quantity="300", price="10.00", base_quantity="100"),
    ]))

    assert invoice.lines[0].unit_price == Decimal("0.1")


def test_reads_both_parties_with_address_and_ids():
    invoice = parse_invoice(rich_invoice_xml())

    supplier, customer = invoice.supplier, invoice.customer
    assert (supplier.name, supplier.cui, supplier.vat_id) == ("Furnizor SRL", "87654321", "RO87654321")
    assert supplier.registration == "J40/1234/2020"
    assert (supplier.country, supplier.county, supplier.city) == ("RO", "B", "SECTOR3")
    assert supplier.address == "Str. Fabricii 10"
    assert (supplier.phone, supplier.email) == ("0211234567", "office@furnizor.example")
    assert (supplier.iban, supplier.bank) == ("RO49AAAA1B31007593840000", "Banca Exemplu")
    assert (customer.name, customer.cui, customer.county) == ("Client SRL", "12345674", "CJ")


def test_reads_header_fields_and_totals():
    invoice = parse_invoice(rich_invoice_xml(lines=[line("Servicii", "1000.00")]))

    assert (invoice.number, invoice.issue_date, invoice.due_date) == (
        "FV-1042", "2026-11-09", "2026-12-09"
    )
    assert (invoice.currency, invoice.note, invoice.is_credit_note) == ("RON", "Contract 15/2026", False)
    assert (invoice.total_without_vat, invoice.total_vat) == (Decimal("1000.00"), Decimal("190.00"))
    assert invoice.vat_on_collection is False


def test_invoice_level_discounts_and_charges_are_read():
    invoice = parse_invoice(rich_invoice_xml(
        lines=[line("Marfa", "1000.00")],
        adjustments=[adjustment("100.00"), adjustment("25.00", charge=True, reason="Transport")],
    ))

    discount, charge = invoice.adjustments
    assert (discount.is_charge, discount.amount, discount.reason) == (
        False, Decimal("100.00"), "Discount comercial"
    )
    assert (charge.is_charge, charge.amount, charge.vat_percent) == (
        True, Decimal("25.00"), Decimal("19")
    )


def test_credit_note_lines_are_read():
    invoice = parse_invoice(rich_invoice_xml(lines=[line("Retur marfa", "80.00")], credit_note=True))

    assert invoice.is_credit_note is True
    assert invoice.lines[0].value == Decimal("80.00")


def test_vat_on_collection_is_recognised():
    assert parse_invoice(rich_invoice_xml(vat_on_collection=True)).vat_on_collection is True


def test_supplier_without_a_vat_number_falls_back_to_the_legal_id():
    xml = rich_invoice_xml()
    start = xml.index(b"<cac:PartyTaxScheme>")
    end = xml.index(b"</cac:PartyTaxScheme>") + len(b"</cac:PartyTaxScheme>")
    xml = (xml[:start] + xml[end:]).replace(b"J40/1234/2020", b"87654321", 1)

    supplier = parse_invoice(xml).supplier
    assert (supplier.cui, supplier.vat_id, supplier.registration) == ("87654321", None, None)


@pytest.mark.parametrize("xml", [ANAF_ERROR_NOTICE.encode(), b"not xml at all", b""])
def test_anything_that_is_not_an_invoice_gives_nothing(xml):
    assert parse_invoice(xml) is None


def test_line_with_an_unreadable_amount_counts_as_zero_rather_than_failing():
    xml = rich_invoice_xml(lines=[line("Ceva", "77.00")]).replace(b">77.00</cbc:Line", b">abc</cbc:Line")

    assert parse_invoice(xml).lines[0].value == Decimal("0")
