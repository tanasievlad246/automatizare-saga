"""Clients: reading a CSV or Excel file, and the list the screen shows."""

import io
from datetime import datetime, timedelta, timezone

import openpyxl
import pytest

from efactura import auth
from efactura.auth import Tokens
from efactura.clients_file import read_client_rows
from efactura.config import load_config
from efactura.errors import EfacturaError
from efactura.service import Service

from helpers import OTHER_VALID_CUI, VALID_CUI, FakeAnaf, line, rich_invoice_xml

NOW = datetime(2026, 11, 11, 9, 30, tzinfo=timezone(timedelta(hours=2)))


def xlsx(rows) -> bytes:
    book = openpyxl.Workbook()
    sheet = book.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


# --- reading the file --------------------------------------------------------------------


def test_reads_a_csv_with_a_header_whatever_the_column_order():
    rows = read_client_rows("clienti.csv", "CUI,Denumire\n12345674,Alfa Construct SRL\n".encode())

    assert rows == [(2, "Alfa Construct SRL", "12345674")]


def test_reads_a_semicolon_csv_saved_by_excel_on_a_romanian_computer():
    content = "Nume;Cod fiscal\r\nBrutăria Soarelui SRL;RO14399840\r\n".encode("cp1250")

    assert read_client_rows("clienti.csv", content) == [(2, "Brutăria Soarelui SRL", "RO14399840")]


def test_reads_a_csv_with_a_byte_order_mark():
    content = b"\xef\xbb\xbf" + "nume,cif\nAlfa,12345674\n".encode()

    assert read_client_rows("clienti.csv", content) == [(2, "Alfa", "12345674")]


def test_without_a_header_the_cell_that_is_a_valid_cui_is_the_cui():
    content = f"Alfa Construct SRL,{VALID_CUI}\nRO{OTHER_VALID_CUI},Brutaria Soarelui SRL\n".encode()

    assert read_client_rows("clienti.csv", content) == [
        (1, "Alfa Construct SRL", VALID_CUI),
        (2, "Brutaria Soarelui SRL", f"RO{OTHER_VALID_CUI}"),
    ]


def test_a_headerless_row_without_a_valid_cui_keeps_what_was_written():
    assert read_client_rows("clienti.csv", b"Delta Service SRL,12345678\n") == [
        (1, "Delta Service SRL", "12345678")
    ]


def test_reads_an_excel_file_where_the_cui_is_a_number():
    content = xlsx([["Client", "CUI"], ["Alfa Construct SRL", 12345674], ["Brutaria", "RO14399840"]])

    assert read_client_rows("clienti.xlsx", content) == [
        (2, "Alfa Construct SRL", "12345674"), (3, "Brutaria", "RO14399840")
    ]


def test_empty_rows_and_extra_columns_are_ignored():
    content = xlsx([["Nr", "Nume", "CUI", "Telefon"], [1, "Alfa", 12345674, "0711"], [None, None, None, None]])

    assert read_client_rows("clienti.xlsx", content) == [(2, "Alfa", "12345674")]


@pytest.mark.parametrize("name, content", [
    ("clienti.pdf", b"%PDF"),
    ("clienti.xlsx", b"this is not an excel file"),
    ("clienti.csv", b""),
    ("clienti", b"a,b"),
])
def test_a_file_that_cannot_be_read_is_invalid_input(name, content):
    with pytest.raises(EfacturaError) as info:
        read_client_rows(name, content)

    assert info.value.code == "invalid_input"


# --- the service -------------------------------------------------------------------------


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[anaf]\nclient_id = "c"\nclient_secret = "s"\n'
        f"token_file = '{tmp_path / 'private' / 'tokens.json'}'\n", encoding="utf-8",
    )
    cfg = load_config(path)
    auth.save_tokens(
        cfg.token_file,
        Tokens("access-1", "refresh-1", NOW + timedelta(days=30), NOW + timedelta(days=300), NOW),
    )
    return cfg


@pytest.fixture
def anaf():
    return FakeAnaf()


@pytest.fixture
def service(cfg, anaf):
    return Service(cfg, http=anaf.client(), now=lambda: NOW)


def error_code(call):
    with pytest.raises(EfacturaError) as info:
        call()
    return info.value.code


def test_there_are_no_clients_to_begin_with(service):
    assert service.clients() == {"ok": True, "count": 0, "clients": []}


def test_a_client_can_be_added_renamed_and_removed(service):
    added = service.save_client(f"RO {VALID_CUI}", "  Alfa Construct SRL ")
    renamed = service.save_client(VALID_CUI, "Alfa Construct & Fiii SRL")
    removed = service.remove_client(VALID_CUI)

    assert [(c["cui"], c["name"]) for c in added["clients"]] == [(VALID_CUI, "Alfa Construct SRL")]
    assert [c["name"] for c in renamed["clients"]] == ["Alfa Construct & Fiii SRL"]
    assert removed["count"] == 0


def test_a_client_needs_a_valid_cui_and_a_name(service):
    assert error_code(lambda: service.save_client("12345678", "Delta")) == "invalid_cui"
    assert error_code(lambda: service.save_client(VALID_CUI, "   ")) == "invalid_input"
    assert error_code(lambda: service.remove_client(VALID_CUI)) == "not_found"


def test_clients_are_listed_by_name(service):
    service.save_client(OTHER_VALID_CUI, "brutaria Soarelui")
    service.save_client(VALID_CUI, "Alfa Construct")

    assert [c["name"] for c in service.clients()["clients"]] == ["Alfa Construct", "brutaria Soarelui"]


def test_importing_a_file_says_what_was_added_updated_and_rejected(service):
    service.save_client(VALID_CUI, "Alfa (nume vechi)")
    content = xlsx([
        ["Nume", "CUI"],
        ["Alfa Construct SRL", int(VALID_CUI)],     # known: renamed
        ["Brutaria Soarelui SRL", f"RO{OTHER_VALID_CUI}"],  # new
        ["Delta Service SRL", "12345678"],          # wrong check digit
        [None, "18547290"],                         # no name
        ["Fara Cod SRL", None],                     # no CUI
    ])

    result = service.import_clients("clienti.xlsx", content)

    assert (result["ok"], result["rows"]) == (True, 5)
    assert result["added"] == [{"cui": OTHER_VALID_CUI, "name": "Brutaria Soarelui SRL"}]
    assert result["updated"] == [{"cui": VALID_CUI, "name": "Alfa Construct SRL"}]
    assert [(r["row"], r["code"]) for r in result["rejected"]] == [
        (4, "invalid_cui"), (5, "missing_name"), (6, "missing_cui"),
    ]
    assert result["rejected"][0]["name"] == "Delta Service SRL"
    assert {c["cui"] for c in service.clients()["clients"]} == {VALID_CUI, OTHER_VALID_CUI}


def test_importing_the_same_file_again_changes_nothing(service):
    content = f"Nume,CUI\nAlfa,{VALID_CUI}\n".encode()
    service.import_clients("clienti.csv", content)

    again = service.import_clients("clienti.csv", content)

    assert (again["added"], again["updated"], again["unchanged"]) == ([], [], 1)


def test_the_client_list_counts_invoices_and_remembers_the_last_download(service, anaf):
    service.save_client(VALID_CUI, "Alfa")
    service.save_client(OTHER_VALID_CUI, "Beta")
    anaf.add("3001", xml=rich_invoice_xml(lines=[line("Motorina", "100.00")], number="A1"))
    anaf.add("3002", xml=rich_invoice_xml(lines=[line("Ceva necunoscut", "100.00")], number="A2"))
    anaf.add("3003", tip="FACTURA TRIMISA", xml=rich_invoice_xml(number="A3"))
    service.sync(VALID_CUI)

    alfa, beta = service.clients()["clients"]

    assert (alfa["invoices"], alfa["new_count"], alfa["review_count"], alfa["ready_count"]) == (2, 2, 1, 1)
    assert alfa["last_sync_at"] == NOW.isoformat()
    assert (beta["invoices"], beta["new_count"], beta["last_sync_at"]) == (0, 0, None)


def test_removing_a_client_keeps_its_invoices(service, anaf):
    service.save_client(VALID_CUI, "Alfa")
    anaf.add("3001", xml=rich_invoice_xml(lines=[line("Motorina", "100.00")]))
    service.sync(VALID_CUI)

    service.remove_client(VALID_CUI)

    assert service.invoices(cui=VALID_CUI)["count"] == 1


# --- lists as accountants really keep them (found by the review) ------------------------------


def test_a_numbering_column_is_never_taken_for_the_name_or_the_cui():
    content = xlsx([
        ["Nr. crt.", "Denumire firmă", "C.U.I."],
        [1, "Alfa Construct SRL", int(VALID_CUI)],
        [19, "Brutaria Soarelui SRL", f"RO{OTHER_VALID_CUI}"],  # 19 passes the CUI check digit
    ])

    assert read_client_rows("clienti.xlsx", content) == [
        (2, "Alfa Construct SRL", VALID_CUI), (3, "Brutaria Soarelui SRL", f"RO{OTHER_VALID_CUI}"),
    ]


def test_the_header_may_sit_below_a_title_row():
    content = xlsx([
        ["Lista clienților 2026", None, None],
        [None, None, None],
        ["Nr", "Client", "Cod fiscal"],
        [1, "Alfa Construct SRL", VALID_CUI],
    ])

    assert read_client_rows("clienti.xlsx", content) == [(4, "Alfa Construct SRL", VALID_CUI)]


def test_a_header_with_only_the_cui_column_named_still_finds_the_names():
    content = xlsx([["Nr", "Societatea comercială", "CUI"], [7, "Alfa Construct SRL", VALID_CUI]])

    assert read_client_rows("clienti.xlsx", content) == [(2, "Alfa Construct SRL", VALID_CUI)]


def test_without_a_header_a_row_number_does_not_displace_the_real_cui():
    content = f"19,Brutaria Soarelui SRL,{OTHER_VALID_CUI}\n27,Alfa Construct SRL,RO{VALID_CUI}\n".encode()

    assert read_client_rows("clienti.csv", content) == [
        (1, "Brutaria Soarelui SRL", OTHER_VALID_CUI), (2, "Alfa Construct SRL", f"RO{VALID_CUI}"),
    ]
