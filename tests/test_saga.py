from decimal import Decimal
from xml.etree import ElementTree

from efactura import saga
from efactura.invoice import parse_invoice

from helpers import adjustment, line, rich_invoice_xml

ANTET_ORDER = [
    "FurnizorNume", "FurnizorCIF", "FurnizorNrRegCom", "FurnizorCapital", "FurnizorTara",
    "FurnizorLocalitate", "FurnizorJudet", "FurnizorAdresa", "FurnizorTelefon", "FurnizorMail",
    "FurnizorBanca", "FurnizorIBAN", "FurnizorInformatiiSuplimentare",
    "ClientNume", "ClientInformatiiSuplimentare", "ClientCIF", "ClientNrRegCom", "ClientJudet",
    "ClientTara", "ClientLocalitate", "ClientAdresa", "ClientBanca", "ClientIBAN",
    "ClientTelefon", "ClientMail",
    "FacturaNumar", "FacturaData", "FacturaScadenta", "FacturaTaxareInversa", "FacturaTVAIncasare",
    "FacturaInformatiiSuplimentare", "FacturaMoneda", "FacturaGreutate",
    "FacturaIndexSPV", "FacturaIndexDescarcareSPV",
]
LINE_ORDER = [
    "LinieNrCrt", "Descriere", "InformatiiSuplimentare", "UM", "Cantitate", "Pret", "Valoare",
    "ProcTVA", "TVA", "Cont",
]


def export(cont="628", upload_index="5001", download_id="3001", **kwargs):
    invoice = parse_invoice(rich_invoice_xml(**kwargs))
    return ElementTree.fromstring(saga.build_xml(invoice, cont, upload_index, download_id))


def antet(root):
    return {child.tag: child.text or "" for child in root.find("Factura/Antet")}


def lines_of(root):
    return [
        {child.tag: child.text or "" for child in node}
        for node in root.findall("Factura/Detalii/Continut/Linie")
    ]


def test_layout_follows_sagas_manual():
    root = export()

    assert root.tag == "Facturi"
    assert [child.tag for child in root] == ["Factura"]
    assert [child.tag for child in root.find("Factura")] == ["Antet", "Detalii"]
    assert [child.tag for child in root.find("Factura/Antet")] == ANTET_ORDER
    assert [child.tag for child in root.find("Factura/Detalii/Continut/Linie")] == LINE_ORDER


def test_supplier_and_client_are_carried_over():
    header = antet(export())

    assert header["FurnizorNume"] == "Furnizor SRL"
    assert header["FurnizorCIF"] == "RO87654321"
    assert header["FurnizorNrRegCom"] == "J40/1234/2020"
    assert (header["FurnizorTara"], header["FurnizorJudet"], header["FurnizorLocalitate"]) == (
        "RO", "B", "SECTOR3"
    )
    assert header["FurnizorAdresa"] == "Str. Fabricii 10"
    assert (header["FurnizorTelefon"], header["FurnizorMail"]) == ("0211234567", "office@furnizor.example")
    assert (header["FurnizorBanca"], header["FurnizorIBAN"]) == ("Banca Exemplu", "RO49AAAA1B31007593840000")
    assert (header["ClientNume"], header["ClientCIF"], header["ClientJudet"]) == (
        "Client SRL", "RO12345674", "CJ"
    )


def test_invoice_header_uses_sagas_date_format_and_carries_anafs_ids():
    header = antet(export(upload_index="5001", download_id="3001"))

    assert (header["FacturaNumar"], header["FacturaData"], header["FacturaScadenta"]) == (
        "FV-1042", "09.11.2026", "09.12.2026"
    )
    assert (header["FacturaMoneda"], header["FacturaInformatiiSuplimentare"]) == ("RON", "Contract 15/2026")
    assert (header["FacturaIndexSPV"], header["FacturaIndexDescarcareSPV"]) == ("5001", "3001")
    assert (header["FacturaTaxareInversa"], header["FacturaTVAIncasare"]) == ("Nu", "Nu")


def test_every_line_gets_the_same_account():
    rows = lines_of(export(cont="6022", lines=[line("Motorina", "450.00"), line("Spalare", "50.00")]))

    assert [row["Cont"] for row in rows] == ["6022", "6022"]
    assert [row["LinieNrCrt"] for row in rows] == ["1", "2"]


def test_line_values_units_and_vat():
    (row,) = lines_of(export(lines=[
        line("Motorina Euro 5", "450.00", quantity="60", unit="LTR", price="7.50"),
    ]))

    assert row["Descriere"] == "Motorina Euro 5"
    assert (row["UM"], row["Cantitate"], row["Pret"], row["Valoare"]) == ("L", "60", "7.50", "450.00")
    assert (row["ProcTVA"], row["TVA"]) == ("19", "85.50")


def test_unknown_unit_codes_pass_through():
    (row,) = lines_of(export(lines=[line("Ceva", "10.00", unit="ZZ")]))

    assert row["UM"] == "ZZ"


def test_line_vat_adds_up_to_the_invoices_vat_total():
    # 3 x 0.33 at 19% is 0.06 each when rounded per line (0.18), but 0.19 on the invoice.
    rows = lines_of(export(
        lines=[line("A", "0.33"), line("B", "0.33"), line("C", "0.33")], vat_total="0.19",
    ))

    assert sum(Decimal(row["TVA"]) for row in rows) == Decimal("0.19")


def test_a_large_vat_difference_is_left_alone_rather_than_hidden():
    rows = lines_of(export(lines=[line("A", "100.00")], vat_total="55.00"))

    assert rows[0]["TVA"] == "19.00"


def test_invoice_level_discount_and_charge_become_lines_so_totals_match():
    rows = lines_of(export(
        lines=[line("Marfa", "1000.00")],
        adjustments=[adjustment("100.00"), adjustment("25.00", charge=True, reason="Transport")],
    ))

    assert [(row["Descriere"], row["Valoare"], row["TVA"]) for row in rows] == [
        ("Marfa", "1000.00", "190.00"),
        ("Discount comercial", "-100.00", "-19.00"),
        ("Transport", "25.00", "4.75"),
    ]
    assert sum(Decimal(row["Valoare"]) for row in rows) == Decimal("925.00")
    assert [row["LinieNrCrt"] for row in rows] == ["1", "2", "3"]
    assert {row["Cont"] for row in rows} == {"628"}


def test_credit_note_is_written_with_negative_amounts():
    (row,) = lines_of(export(lines=[line("Retur marfa", "80.00", quantity="2", price="40.00")],
                             credit_note=True))

    assert (row["Cantitate"], row["Pret"], row["Valoare"], row["TVA"]) == ("-2", "40.00", "-80.00", "-15.20")


def test_reverse_charge_is_flagged_and_carries_no_vat():
    # The line states a rate, as some suppliers write it; reverse charge still means no VAT.
    root = export(lines=[line("Deseuri", "500.00", percent="0", vat_percent="19", category="AE")])

    assert antet(root)["FacturaTaxareInversa"] == "Da"
    assert lines_of(root)[0]["TVA"] == "0.00"


def test_vat_on_collection_is_flagged():
    assert antet(export(vat_on_collection=True))["FacturaTVAIncasare"] == "Da"


def test_supplier_article_codes_are_left_out_so_saga_books_on_the_account():
    root = export(lines=[line("Toner", "200.00", seller_code="TN-2420", barcode="5941234567890")])

    text = ElementTree.tostring(root, encoding="unicode")
    assert "TN-2420" not in text and "5941234567890" not in text


def test_output_is_utf8_xml_with_romanian_letters_intact():
    invoice = parse_invoice(rich_invoice_xml(lines=[line("Servicii de pază și întreținere", "10.00")]))

    data = saga.build_xml(invoice, "628", None, None)

    assert data.startswith(b"<?xml version='1.0' encoding='utf-8'?>")
    assert "Servicii de pază și întreținere".encode("utf-8") in data
    assert b"<FurnizorCapital></FurnizorCapital>" in data  # empty tags are written out in full


def test_file_name_follows_sagas_pattern():
    invoice = parse_invoice(rich_invoice_xml(number="FV-1042"))

    assert saga.file_name(invoice) == "F_87654321_FV-1042_09.11.2026.xml"


def test_file_name_is_safe_whatever_the_invoice_number_contains():
    invoice = parse_invoice(rich_invoice_xml(number="A/12 _..\\x"))

    name = saga.file_name(invoice)

    assert name == "F_87654321_A-12-..-x_09.11.2026.xml"
    assert "/" not in name and "\\" not in name


# --- quantity x price must give the value ------------------------------------------------


def test_a_line_discount_is_folded_into_the_price_so_quantity_times_price_is_the_value():
    # 10 x 100.00 with a 100.00 discount on the line: ANAF gives price 100.00, value 900.00.
    (row,) = lines_of(export(lines=[line("Marfa", "900.00", quantity="10", price="100.00")]))

    assert (row["Cantitate"], row["Pret"], row["Valoare"]) == ("10", "90.00", "900.00")


def test_a_price_with_many_decimals_is_kept_as_the_invoice_states_it():
    (row,) = lines_of(export(lines=[
        line("Gaz", "1234.57", quantity="1000.123", unit="MTQ", price="1.234418"),
    ]))

    assert (row["Cantitate"], row["Pret"], row["Valoare"]) == ("1000.123", "1.234418", "1234.57")


def test_a_line_without_a_quantity_is_written_as_one_unit_at_its_value():
    (row,) = lines_of(export(lines=[line("Abonament", "80.00", quantity="0", price="0")]))

    assert (row["Cantitate"], row["Pret"], row["Valoare"]) == ("1", "80.00", "80.00")


def test_a_credit_note_line_without_a_quantity_has_no_negative_zero():
    (row,) = lines_of(export(lines=[line("Storno", "80.00", quantity="0", price="0")], credit_note=True))

    assert (row["Cantitate"], row["Pret"], row["Valoare"]) == ("1", "-80.00", "-80.00")


def test_zero_vat_on_a_negative_line_is_written_without_a_minus_sign():
    (row,) = lines_of(export(lines=[line("Retur ambalaj", "-10.00", percent="0", category="Z")]))

    assert row["TVA"] == "0.00"


def test_a_rounding_difference_is_spread_a_cent_per_line_not_put_on_one():
    # Each small line rounds up by half a cent; the invoice's VAT is worked out on the total.
    small = [line(f"Articol {n}", "1.29") for n in range(40)]
    rows = lines_of(export(lines=small + [line("Utilaj", "500.00")], vat_total="104.80"))

    assert sum(Decimal(row["TVA"]) for row in rows) == Decimal("104.80")
    for row in rows:
        calculated = (Decimal(row["Valoare"]) * Decimal("0.19")).quantize(Decimal("0.01"))
        assert abs(Decimal(row["TVA"]) - calculated) <= Decimal("0.01")


def test_tiny_lines_never_end_up_with_negative_vat():
    rows = lines_of(export(lines=[line(f"Punga {n}", "0.03") for n in range(200)], vat_total="1.14"))

    assert sum(Decimal(row["TVA"]) for row in rows) == Decimal("1.14")
    assert min(Decimal(row["TVA"]) for row in rows) >= 0


def test_a_second_invoice_with_the_same_name_can_be_told_apart():
    invoice = parse_invoice(rich_invoice_xml(number="AB/12"))

    assert saga.file_name(invoice, distinct="3002") == "F_87654321_AB-12-3002_09.11.2026.xml"
