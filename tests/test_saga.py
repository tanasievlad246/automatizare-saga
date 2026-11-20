from decimal import Decimal
from xml.etree import ElementTree

import pytest

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


def test_a_service_unit_is_written_in_words():
    # E48 is the code for "service unit": what a ride or a subscription is counted in.
    (row,) = lines_of(export(lines=[line("Tarif de calatorie", "16.10", unit="E48")]))

    assert row["UM"] == "SERV"


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


def test_a_worked_out_price_that_no_longer_gives_the_value_is_written_as_one_unit_at_the_value():
    # 100000 kWh with a discount: 33333.33 / 100000 is 0.3333333, and 0.333333 x 100000 is 33333.30.
    (row,) = lines_of(export(lines=[line("Energie", "33333.33", quantity="100000", unit="KWH", price="0.35")]))

    assert (row["Cantitate"], row["Pret"], row["Valoare"]) == ("1", "33333.33", "33333.33")


def test_a_price_with_more_than_six_decimals_that_rounds_away_from_the_value_is_written_as_one_unit():
    # The invoice's 0.12345678 gives the value within a cent, but written as 0.123457 it would not.
    (row,) = lines_of(export(lines=[line("Energie", "12345.68", quantity="100000", unit="KWH", price="0.12345678")]))

    assert (row["Cantitate"], row["Pret"], row["Valoare"]) == ("1", "12345.68", "12345.68")


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


# --- several invoices in one file ---------------------------------------------------


def entry(cont="628", upload_index="5001", download_id="3001", line_conts=(), **kwargs):
    return saga.Entry(parse_invoice(rich_invoice_xml(**kwargs)), cont, upload_index, download_id, line_conts)


def test_a_file_can_hold_several_invoices_each_with_its_own_account_and_ids():
    root = ElementTree.fromstring(saga.build_file([
        entry(cont="6022", upload_index="5001", download_id="3001", number="FV-1"),
        entry(cont="626", upload_index="5002", download_id="3002", number="FV-2",
              lines=[line("Abonament", "100.00"), line("Internet", "50.00")]),
    ]))

    assert root.tag == "Facturi"
    assert [child.tag for child in root] == ["Factura", "Factura"]
    first, second = root
    assert [child.tag for child in second] == ["Antet", "Detalii"]
    assert [child.tag for child in second.find("Antet")] == ANTET_ORDER
    assert [factura.findtext("Antet/FacturaNumar") for factura in root] == ["FV-1", "FV-2"]
    assert [factura.findtext("Antet/FacturaIndexSPV") for factura in root] == ["5001", "5002"]
    assert [factura.findtext("Antet/FacturaIndexDescarcareSPV") for factura in root] == ["3001", "3002"]
    assert [node.text for node in first.iter("Cont")] == ["6022"]
    assert [node.text for node in second.iter("Cont")] == ["626", "626"]
    assert [node.text for node in second.iter("LinieNrCrt")] == ["1", "2"]  # counted within each invoice


def test_a_file_with_one_invoice_is_that_invoices_own_file():
    one = entry()

    assert saga.build_file([one]) == saga.build_xml(one.invoice, "628", "5001", "3001")


# --- which files a client's waiting invoices make -------------------------------------


def waiting(*numbers, **kwargs):
    """Invoices with these numbers; ANAF's download id is the message id: 3001, 3002, ..."""
    return [
        entry(download_id=f"30{position:02d}", number=number, **kwargs)
        for position, number in enumerate(numbers, start=1)
    ]


def numbers_in(file):
    return [node.text for node in ElementTree.fromstring(file.content).iter("FacturaNumar")]


def test_one_file_per_client_holds_every_waiting_invoice_under_the_first_ones_name():
    (file,) = saga.files_for(waiting("FV-7", "FV-8", "FV-9"), saga.PER_CLIENT)

    # SAGA has been seen to accept a file of many invoices under the name of one of them.
    assert file.name == "F_87654321_FV-7_09.11.2026.xml"
    assert file.ids == ("3001", "3002", "3003")
    assert numbers_in(file) == ["FV-7", "FV-8", "FV-9"]


def test_no_waiting_invoice_means_no_file():
    assert saga.files_for([], saga.PER_CLIENT) == []
    assert saga.files_for([], saga.PER_INVOICE) == []


def test_one_file_per_invoice_gives_each_its_own_name():
    first, second = saga.files_for(waiting("FV-7", "FV-8"), saga.PER_INVOICE)

    assert (first.name, first.ids) == ("F_87654321_FV-7_09.11.2026.xml", ("3001",))
    assert (second.name, second.ids) == ("F_87654321_FV-8_09.11.2026.xml", ("3002",))
    assert (numbers_in(first), numbers_in(second)) == (["FV-7"], ["FV-8"])


def test_invoices_whose_names_would_collide_are_told_apart_by_their_message_id():
    # Punctuation is replaced in a file name, and Windows ignores letter case in one.
    files = saga.files_for(waiting("AB 12", "AB/12", "ab-12"), saga.PER_INVOICE)

    assert [file.name for file in files] == [
        "F_87654321_AB-12_09.11.2026.xml",
        "F_87654321_AB-12-3002_09.11.2026.xml",
        "F_87654321_ab-12-3003_09.11.2026.xml",
    ]


# --- an account on each line --------------------------------------------------------


def conts_of(xml: bytes) -> list[str]:
    return [node.text for node in ElementTree.fromstring(xml).iter("Cont")]


def descriptions_of(xml: bytes) -> list[str]:
    return [node.text for node in ElementTree.fromstring(xml).iter("Descriere")]


def test_each_line_is_written_with_its_own_account():
    lines = [line("Apa potabila", "177.65"), line("Canalizare", "139.23"), line("Majorari", "17.17", percent="0", category="E")]

    written = saga.build_file([entry(cont="605", lines=lines, line_conts=((1, "605"), (2, "605"), (3, "6581")))])

    assert descriptions_of(written) == ["Apa potabila", "Canalizare", "Majorari"]
    assert conts_of(written) == ["605", "605", "6581"]


def test_a_discount_on_the_whole_invoice_takes_the_account_of_the_invoice():
    written = saga.build_file([entry(
        cont="371", lines=[line("Marfa", "1000.00"), line("Transport", "50.00")],
        adjustments=[adjustment("30.00", reason="Discount comercial")], line_conts=((1, "371"), (2, "624")),
    )])

    assert descriptions_of(written) == ["Marfa", "Transport", "Discount comercial"]
    assert conts_of(written) == ["371", "624", "371"]


def test_a_line_without_an_account_of_its_own_takes_the_invoices():
    written = saga.build_file([entry(cont="628", lines=[line("A", "10.00"), line("B", "5.00")], line_conts=((1, "605"),))])

    assert conts_of(written) == ["605", "628"]


def test_an_invoice_on_one_account_is_written_as_before():
    assert conts_of(saga.build_file([entry(cont="626", lines=[line("A", "10.00"), line("B", "5.00")])])) == ["626", "626"]


def test_an_invoice_on_its_own_carries_its_line_accounts_too():
    invoice = parse_invoice(rich_invoice_xml(lines=[line("A", "10.00"), line("B", "5.00")]))

    assert conts_of(saga.build_xml(invoice, "605", "5001", "3001", line_conts=((2, "6581"),))) == ["605", "6581"]


# --- the client's folder: its name and its CUI ---------------------------------

CUI = "12345674"


def test_a_clients_folder_carries_its_name_and_its_cui():
    assert saga.client_folder_name("Alfa Construct SRL", CUI) == "Alfa Construct SRL - 12345674"


@pytest.mark.parametrize("name", [None, "", "   ", "///", '"?"', "..."])
def test_a_client_without_a_usable_name_gets_a_folder_named_by_its_cui(name):
    assert saga.client_folder_name(name, CUI) == CUI


@pytest.mark.parametrize("name, folder", [
    ("S.C. ALFA/BETA S.R.L.", "S.C. ALFA-BETA S.R.L. - 12345674"),
    ("ALFA\\BETA", "ALFA-BETA - 12345674"),
    ('Gamma "Trade": Est', "Gamma Trade Est - 12345674"),
    ("A*B?C<D>E|F", "A B C D E F - 12345674"),
    ("Alfa\tBeta\nSRL", "Alfa Beta SRL - 12345674"),
    ("\u201eGamma\u201d \u0218tefan & Fiii", "\u201eGamma\u201d \u0218tefan & Fiii - 12345674"),
])
def test_what_windows_refuses_in_a_folder_name_is_taken_out(name, folder):
    assert saga.client_folder_name(name, CUI) == folder


@pytest.mark.parametrize("name, folder", [
    ("  Alfa SRL  ", "Alfa SRL - 12345674"),
    ("Alfa    Beta", "Alfa Beta - 12345674"),
    ("..Alfa", "Alfa - 12345674"),
    ("Alfa S.R.L.", "Alfa S.R.L. - 12345674"),  # the folder ends with the CUI, so this dot is never last
])
def test_spaces_around_a_name_and_dots_before_it_are_dropped(name, folder):
    assert saga.client_folder_name(name, CUI) == folder


def test_a_long_name_is_cut_so_the_path_stays_within_what_windows_takes():
    assert saga.client_folder_name("X" * 200, CUI) == "X" * 60 + " - 12345674"
    # Cut after a space: the space does not stay before the dash.
    assert saga.client_folder_name("A" * 59 + " " + "B" * 30, CUI) == "A" * 59 + " - 12345674"


@pytest.mark.parametrize("name, folder", [
    ("AUX.IT SRL", "_AUX.IT SRL - 12345674"),
    ("con.srl", "_con.srl - 12345674"),
    ("COM1.RO", "_COM1.RO - 12345674"),
    ("LPT9 .ro", "_LPT9 .ro - 12345674"),
    ("CON", "CON - 12345674"),  # no dot: the whole name is "CON - 12345674", which is nobody's device
    ("CONSTRUCT.RO", "CONSTRUCT.RO - 12345674"),
])
def test_a_name_windows_keeps_for_a_device_gets_an_underscore_in_front(name, folder):
    assert saga.client_folder_name(name, CUI) == folder


def test_the_same_name_written_with_combining_marks_gives_the_same_folder():
    assert saga.client_folder_name("S\u0326tefan SRL", CUI) == saga.client_folder_name("\u0218tefan SRL", CUI)


@pytest.mark.parametrize("folder, belongs", [
    ("12345674", True),
    ("Alfa Construct SRL - 12345674", True),
    ("Alfa - 112345674", False),
    ("Alfa - 12345674 vechi", False),
    ("Alfa 12345674", False),
])
def test_a_clients_folder_is_known_by_the_cui_at_its_end(folder, belongs):
    assert saga.is_client_folder(folder, CUI) is belongs


# --- a discount on the whole invoice, with its own account ---------------------------------


def ride_with_a_discount(**entry):
    invoice = parse_invoice(rich_invoice_xml(
        lines=[line("Tarif de calatorie", "16.10", unit="E48", percent="0", category="Z")],
        adjustments=[adjustment("4.30", reason="Reducere", percent="0", category="Z")],
    ))
    return lines_of(ElementTree.fromstring(saga.build_xml(invoice, "704", "5001", "3001", **entry)))


def test_a_discount_on_the_whole_invoice_is_booked_on_its_own_account():
    # It is the line after the invoice's own, and is named by that number.
    rows = ride_with_a_discount(line_conts=((1, "704"), (2, "729")))

    assert [(row["LinieNrCrt"], row["Descriere"], row["Valoare"], row["Cont"]) for row in rows] == [
        ("1", "Tarif de calatorie", "16.10", "704"), ("2", "Reducere", "-4.30", "729"),
    ]


def test_a_discount_without_an_account_of_its_own_is_booked_on_the_invoices():
    rows = ride_with_a_discount(line_conts=((1, "701"),))

    assert [row["Cont"] for row in rows] == ["701", "704"]
