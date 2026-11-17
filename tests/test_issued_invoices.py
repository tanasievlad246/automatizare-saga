"""The invoices a client issued itself, in the process: an account for each line from the
rules and the questions of their own kind, a person when they do not fit, and the same file
for SAGA as the received ones."""

import json
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree

import pytest

from efactura import auth, journal, service as service_module
from efactura.auth import Tokens
from efactura.config import load_config
from efactura.errors import EfacturaError
from efactura.rules import DEFAULT_JEV_ISSUED_INSTRUCTIONS, DEFAULT_JEV_ISSUED_LINE_INSTRUCTIONS, Rule, Rulebook
from efactura.service import Service
from efactura.store import Store

from helpers import VALID_CUI, FakeAnaf, FakeOpenRouter, line, make_row, rich_invoice_xml, set_rulebook

NOW = datetime(2026, 11, 11, 9, 30, tzinfo=timezone(timedelta(hours=2)))
BUYER, BUYER_CUI = "Beta Instal SRL", "87654321"

BOOK = Rulebook(
    accounts={"6022": "Combustibil.", "628": "Alte servicii."},
    rules=(Rule("combustibil", "6022", keywords=("motorina",)),),
    instructions="Alege contul facturii.",
)


def sold(lines, number="AC-2031", supplier_cui=f"RO{VALID_CUI}", customer_cui=BUYER_CUI):
    """An invoice the client Alfa Construct issued to Beta Instal."""
    return rich_invoice_xml(
        lines=lines, number=number, supplier_cui=supplier_cui, supplier_name="Alfa Construct SRL",
        customer_cui=customer_cui, customer_name=BUYER,
    )


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[anaf]\nclient_id = "my-client"\nclient_secret = "my-secret"\n'
        f"token_file = '{tmp_path / 'private' / 'tokens.json'}'\n"
        '[openrouter]\napi_key = "or-test-key"\n',
        encoding="utf-8",
    )
    cfg = load_config(path)
    set_rulebook(cfg.db_path, BOOK)
    return cfg


@pytest.fixture
def openrouter():
    return FakeOpenRouter()


@pytest.fixture
def anaf(openrouter):
    fake = FakeAnaf()
    fake.openrouter = openrouter
    return fake


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(service_module, "_pause", lambda seconds: None)


@pytest.fixture(autouse=True)
def logged_in(cfg):
    auth.save_tokens(
        cfg.token_file,
        Tokens("access-1", "refresh-1", NOW + timedelta(days=30), NOW + timedelta(days=300), NOW),
    )


@pytest.fixture
def service(cfg, anaf):
    """Alfa Construct is a client, decided line by line, with one rule for what it sells."""
    service = Service(cfg, http=anaf.client(), now=lambda: NOW)
    service.save_client(VALID_CUI, "Alfa Construct SRL")
    service.save_rule(name="manopera", cont="704", keywords=["manopera"], direction="issued")
    return service


def saved(cfg, message_id="3001"):
    store = Store(cfg.db_path)
    row = store.get_message(message_id)
    store.close()
    return row


def error_code(call):
    with pytest.raises(EfacturaError) as info:
        call()
    return info.value.code


def test_an_issued_invoice_is_decided_by_a_rule_for_issued_invoices(service, anaf, openrouter, cfg):
    anaf.add("3001", tip="FACTURA TRIMISA", xml=sold([line("Manopera instalatii sanitare", "1500.00")]))

    service.sync(VALID_CUI)

    row = saved(cfg)
    assert (row["classification_status"], row["cont"], row["classification_method"]) == ("classified", "704", "rules")
    assert openrouter.requests == []


def test_a_rule_for_received_invoices_never_decides_an_issued_one(service, anaf, openrouter, cfg):
    openrouter.answer_for("motorina", "707", confidence=0.9)
    anaf.add("3001", tip="FACTURA TRIMISA", xml=sold([line("Motorina Euro 5", "450.00")]))

    service.sync(VALID_CUI)

    row = saved(cfg)
    assert (row["cont"], row["classification_method"]) == ("707", "jev")
    (asked,) = openrouter.requests
    assert set(asked["questions"]["cont"]["criteria"]) == {"701", "704", "707", "altul"}  # the accounts for issued invoices


def test_a_rule_for_issued_invoices_never_decides_a_received_one(service, anaf, openrouter, cfg):
    anaf.add("3001", xml=rich_invoice_xml(lines=[line("Manopera service auto", "300.00")]))

    service.sync(VALID_CUI)

    assert saved(cfg)["classification_method"] == "jev"


def test_jev_is_told_neither_party_of_an_issued_invoice(service, anaf, openrouter):
    anaf.add("3001", tip="FACTURA TRIMISA", xml=sold([line("Teava PPR 25 mm", "500.00")]))

    service.sync(VALID_CUI)

    (asked,) = openrouter.requests
    sent = json.dumps(asked, ensure_ascii=False)
    for party in (BUYER, BUYER_CUI, "Alfa Construct", VALID_CUI):
        assert party not in sent
    assert asked["questions"]["cont"]["instructions"] == DEFAULT_JEV_ISSUED_INSTRUCTIONS
    assert "vândut" in asked["questions"]["cont"]["criteria"]["altul"]


def test_each_line_of_an_issued_invoice_gets_its_own_account(service, anaf, openrouter, cfg):
    openrouter.answer_for("teava", "707", confidence=0.91)
    anaf.add("3001", tip="FACTURA TRIMISA", xml=sold([
        line("Manopera instalatii", "1500.00"), line("Teava PPR 25 mm", "500.00"),
    ]))

    service.sync(VALID_CUI)

    accounts = service.invoice("3001")["invoice"]["line_accounts"]
    assert [(entry["cont"], entry["method"]) for entry in accounts] == [("704", "rules"), ("707", "jev")]
    (asked,) = openrouter.requests
    assert asked["questions"]["cont"]["instructions"] == DEFAULT_JEV_ISSUED_LINE_INSTRUCTIONS
    assert "furnizor" not in asked["state"]


def test_the_questions_for_issued_invoices_can_be_changed(service, anaf, openrouter):
    service.set_jev_issued_instructions("Ce ai vandut?")
    service.set_jev_issued_line_instructions("Ce ai vandut pe linie?")
    anaf.add("3001", tip="FACTURA TRIMISA", xml=sold([line("Teava PPR", "500.00")]))
    anaf.add("3002", tip="FACTURA TRIMISA", xml=sold([line("Teava PPR", "500.00"), line("Cot PPR", "40.00")], number="AC-2032"))

    service.sync(VALID_CUI)

    assert [asked["questions"]["cont"]["instructions"] for asked in openrouter.requests] == [
        "Ce ai vandut?", "Ce ai vandut pe linie?", "Ce ai vandut pe linie?",
    ]
    settings = service.classification_settings()
    assert (settings["jev_issued_instructions"], settings["jev_issued_line_instructions"]) == (
        "Ce ai vandut?", "Ce ai vandut pe linie?",
    )


def test_an_issued_invoice_whose_supplier_is_not_the_client_goes_to_a_person(service, anaf, openrouter, cfg):
    anaf.add("3001", tip="FACTURA TRIMISA", xml=sold([line("Manopera", "100.00")], supplier_cui="RO14399840"))

    service.sync(VALID_CUI)

    row = saved(cfg)
    assert row["classification_status"] == "review"
    assert "not the client" in row["classification_reason"]
    assert openrouter.requests == []


def test_an_invoice_a_client_issued_to_itself_goes_to_a_person(service, anaf, openrouter, cfg):
    anaf.add("3001", tip="FACTURA TRIMISA", xml=sold([line("Manopera", "100.00")], customer_cui=VALID_CUI))
    anaf.add("3002", xml=sold([line("Manopera", "100.00")], customer_cui=VALID_CUI, number="AC-2032"))

    service.sync(VALID_CUI)

    for message_id in ("3001", "3002"):
        row = saved(cfg, message_id)
        assert (row["classification_status"], "invoiced itself" in row["classification_reason"]) == ("review", True)


def test_without_accounts_for_issued_invoices_jev_is_not_asked(service, anaf, openrouter, cfg):
    for cont in ("701", "704", "707"):
        service.delete_account(cont, kind="issued")
    anaf.add("3001", tip="FACTURA TRIMISA", xml=sold([line("Teava PPR", "500.00")]))

    service.sync(VALID_CUI)

    row = saved(cfg)
    assert row["classification_status"] == "review"
    assert "no accounts" in row["classification_reason"]
    assert openrouter.requests == []


def test_issued_invoices_saved_before_wait_for_the_next_download_and_are_decided_then(service, anaf, cfg):
    store = Store(cfg.db_path)
    store.insert_message(make_row(
        id="2001", message_type="FACTURA TRIMISA", classification_status="pending",
        invoice_xml=sold([line("Manopera", "100.00")]).decode(),
    ))
    store.close()

    service.sync(VALID_CUI)  # brings nothing new

    assert (saved(cfg, "2001")["classification_status"], saved(cfg, "2001")["cont"]) == ("classified", "704")


def test_an_invoice_waiting_that_cannot_be_read_leaves_classification_instead_of_waiting_forever(service, cfg):
    store = Store(cfg.db_path)
    store.insert_message(make_row(id="2001", message_type="FACTURA TRIMISA", classification_status="pending",
                                  invoice_xml="<ceva/>"))
    store.close()

    service.sync(VALID_CUI)
    service.sync(VALID_CUI)

    row = saved(cfg, "2001")
    assert row["classification_status"] is None
    assert "cannot be read" in row["classification_error"]


def test_a_person_chooses_the_account_of_an_issued_invoice(service, anaf, openrouter, cfg):
    openrouter.answer_for("teava", "707", confidence=0.5)
    anaf.add("3001", tip="FACTURA TRIMISA", xml=sold([line("Teava PPR", "500.00")]))
    service.sync(VALID_CUI)

    service.set_cont("3001", cont="706")

    assert (saved(cfg)["classification_status"], saved(cfg)["cont"]) == ("classified", "706")


def test_one_file_for_saga_holds_the_received_and_the_issued_invoices(service, anaf, cfg):
    anaf.add("3001", xml=rich_invoice_xml(lines=[line("Motorina", "450.00")]))
    anaf.add("3002", tip="FACTURA TRIMISA", xml=sold([line("Manopera", "1500.00")]))

    service.sync(VALID_CUI)

    (path,) = (cfg.saga_dir / VALID_CUI).iterdir()
    facturi = ElementTree.parse(path).getroot().findall("Factura")
    assert [factura.findtext("Antet/FurnizorCIF") for factura in facturi] == ["RO87654321", f"RO{VALID_CUI}"]
    assert [factura.findtext("Detalii/Continut/Linie/Cont") for factura in facturi] == ["6022", "704"]
    state = service.invoices(cui=VALID_CUI)["saga"]
    assert state["written_at"] is not None


def test_the_buyers_phone_and_e_mail_stay_out_of_the_file_for_saga(service, anaf, cfg):
    xml = sold([line("Manopera", "1500.00")]).decode()
    assert "<cbc:Telephone>" in xml and "<cbc:ElectronicMail>" in xml  # the stand-in invoice has both
    anaf.add("3001", tip="FACTURA TRIMISA", xml=xml.encode())

    service.sync(VALID_CUI)

    (path,) = (cfg.saga_dir / VALID_CUI).iterdir()
    antet = ElementTree.parse(path).getroot().find("Factura/Antet")
    assert (antet.findtext("ClientTelefon"), antet.findtext("ClientMail")) == ("", "")
    assert antet.findtext("ClientNume") == BUYER


def test_marking_the_file_as_imported_takes_both_kinds_out_of_it(service, anaf, cfg):
    anaf.add("3001", xml=rich_invoice_xml(lines=[line("Motorina", "450.00")]))
    anaf.add("3002", tip="FACTURA TRIMISA", xml=sold([line("Manopera", "1500.00")]))
    service.sync(VALID_CUI)

    service.mark_uploaded(["3001", "3002"])

    assert list((cfg.saga_dir / VALID_CUI).iterdir()) == []


def test_the_journal_never_names_the_buyer_of_an_issued_invoice(service, anaf, openrouter, cfg):
    openrouter.answer_for("teava", "707", confidence=0.5)
    anaf.add("3001", tip="FACTURA TRIMISA", xml=sold([line("Teava PPR", "500.00"), line("Manopera", "100.00")]))
    anaf.add("3002", tip="FACTURA TRIMISA", xml=sold([line("Manopera", "100.00")], customer_cui=VALID_CUI, number="AC-2"))
    service.sync(VALID_CUI)
    service.set_cont("3001", accept=True)

    written = json.dumps(journal.events(cfg.db_path, details=True, limit=500)["events"], ensure_ascii=False)
    assert BUYER not in written and BUYER_CUI not in written


# --- rules and accounts of each kind ------------------------------------------------------


def test_the_rules_screen_holds_the_accounts_rules_and_questions_of_each_kind(service):
    overview = service.rules_overview()

    assert list(overview["issued_accounts"]) == ["701", "704", "707"]
    assert "704" not in overview["accounts"]
    assert [(rule["name"], rule["direction"]) for rule in overview["rules"] if rule["direction"] == "issued"] == [
        ("manopera", "issued"),
    ]
    assert overview["jev_issued_instructions"] == DEFAULT_JEV_ISSUED_INSTRUCTIONS
    assert overview["jev_issued_line_instructions"] == DEFAULT_JEV_ISSUED_LINE_INSTRUCTIONS


def test_an_account_for_issued_invoices_is_added_to_their_list_only(service):
    overview = service.save_account("706", "Venituri din chirii.", kind="issued")

    assert overview["issued_accounts"]["706"] == "Venituri din chirii."
    assert "706" not in overview["accounts"]


def test_a_rule_for_issued_invoices_cannot_look_at_the_supplier(service):
    assert error_code(lambda: service.save_rule(
        name="x", cont="704", supplier_cuis=["14399840"], direction="issued",
    )) == "invalid_input"


def test_a_rule_is_for_one_kind_of_invoice_only(service):
    assert error_code(lambda: service.save_rule(name="x", cont="704", keywords=["a"], direction="both")) == "invalid_input"


def test_a_rule_keeps_its_kind_when_it_is_changed_without_naming_one(service):
    (rule,) = [rule for rule in service.rules_overview()["rules"] if rule["name"] == "manopera"]

    service.save_rule(rule["id"], name="manopera", cont="704", keywords=["manopera", "montaj*"])

    (changed,) = [each for each in service.rules_overview()["rules"] if each["id"] == rule["id"]]
    assert changed["direction"] == "issued"


def test_proposed_rules_never_come_from_issued_invoices(service, anaf, openrouter):
    openrouter.answer_for("teava", "707", confidence=0.95)
    anaf.add("3001", tip="FACTURA TRIMISA", xml=sold([line("Teava PPR 25 mm", "500.00")]))
    service.sync(VALID_CUI)

    assert service.rule_suggestions()["suggestions"] == []


def test_the_client_list_counts_received_and_issued_invoices_apart(service, anaf):
    anaf.add("3001", xml=rich_invoice_xml(lines=[line("Motorina", "450.00")]))
    anaf.add("3002", tip="FACTURA TRIMISA", xml=sold([line("Manopera", "1500.00")]))
    service.sync(VALID_CUI)

    (client,) = service.clients()["clients"]
    assert (client["invoices"], client["issued_count"], client["new_count"], client["issued_new_count"]) == (1, 1, 1, 1)
    assert client["ready_count"] == 2


def test_an_issued_invoices_screen_proposes_no_rule(service, anaf, openrouter):
    openrouter.answer_for("teava", "707", confidence=0.95)
    anaf.add("3001", tip="FACTURA TRIMISA", xml=sold([line("Teava PPR 25 mm", "500.00")]))
    service.sync(VALID_CUI)

    assert service.invoice_view("3001")["rule_suggestion"] is None
