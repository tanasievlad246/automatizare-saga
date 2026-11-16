import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from efactura import auth, certificate_login, service as service_module
from efactura.auth import Tokens
from efactura.config import load_config
from efactura.errors import EfacturaError
from efactura.service import Service
from efactura.store import Store

from helpers import ANAF_ERROR_NOTICE, OTHER_VALID_CUI, VALID_CUI, FakeAnaf, invoice_xml

NOW = datetime(2026, 11, 11, 9, 30, tzinfo=timezone(timedelta(hours=2)))
TODAY_FOLDER = "11-11-2026"


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[anaf]\nclient_id = "my-client"\nclient_secret = "my-secret"\n'
        f"token_file = '{tmp_path / 'private' / 'tokens.json'}'\n",
        encoding="utf-8",
    )
    return load_config(path)


@pytest.fixture
def anaf():
    return FakeAnaf()


@pytest.fixture
def clock():
    return {"now": NOW}


@pytest.fixture
def service(cfg, anaf, clock):
    return Service(cfg, http=anaf.client(), now=lambda: clock["now"])


def save_login(cfg, access="access-1", refresh="refresh-1", access_in=timedelta(days=30)):
    auth.save_tokens(
        cfg.token_file,
        Tokens(
            access_token=access,
            refresh_token=refresh,
            access_expires_at=NOW + access_in,
            refresh_expires_at=NOW + timedelta(days=300),
            obtained_at=NOW - timedelta(days=60),
        ),
    )


@pytest.fixture
def logged_in(cfg):
    save_login(cfg)


def record_run(cfg, cui, started, status="ok"):
    store = Store(cfg.db_path)
    run_id = store.start_run(cui, 7, started.isoformat())
    store.finish_run(
        run_id, started.isoformat(), listed=0, new=0, failed=0, status=status,
        advances_coverage=(status == "ok"),
    )
    store.close()


def error_code(call):
    with pytest.raises(EfacturaError) as info:
        call()
    return info.value.code


# --- login state -------------------------------------------------------------


def test_status_without_a_saved_login(service, monkeypatch):
    monkeypatch.setattr(certificate_login, "available", lambda cfg, system=None: False)  # any machine
    assert service.auth_status() == {
        "ok": True,
        "state": "needs_login",
        "access_expires_at": None,
        "refresh_expires_at": None,
        "access_days_left": None,
        "refresh_days_left": None,
        "certificate_login": False,
    }


def test_status_with_a_valid_login_gives_expiry_dates(service, logged_in):
    status = service.auth_status()

    assert status["state"] == "valid"
    assert status["access_expires_at"] == (NOW + timedelta(days=30)).isoformat()
    assert status["refresh_expires_at"] == (NOW + timedelta(days=300)).isoformat()


def test_status_contacts_nothing(service, anaf, cfg):
    save_login(cfg, access_in=timedelta(days=-1))

    assert service.auth_status()["state"] == "needs_refresh"
    assert anaf.token_requests == []


def test_login_start_returns_the_anaf_address(service):
    started = service.login_start()

    assert started["ok"] is True
    assert started["authorize_url"].startswith("https://logincert.anaf.ro/anaf-oauth2/v1/authorize?")
    assert "client_id=my-client" in started["authorize_url"]
    assert started["redirect_uri"] == "https://localhost/callback"


def test_login_start_without_client_settings_is_a_config_error(tmp_path, anaf):
    path = tmp_path / "bare.toml"
    path.write_text("", encoding="utf-8")
    bare = Service(load_config(path), http=anaf.client(), now=lambda: NOW)

    assert error_code(bare.login_start) == "config_error"


def test_login_finish_saves_the_login(service, cfg):
    finished = service.login_finish("https://localhost/callback?code=good-code")

    assert finished["ok"] is True
    assert finished["state"] == "valid"
    assert finished["access_expires_at"] == (NOW + timedelta(seconds=7776000)).isoformat()
    assert service.auth_status()["state"] == "valid"
    assert auth.load_tokens(cfg.token_file).refresh_token == "refresh-2"


def test_login_finish_with_a_stale_code_saves_nothing(service, cfg):
    code = error_code(lambda: service.login_finish("https://localhost/callback?code=stale"))

    assert code == "login_code_expired"
    assert auth.load_tokens(cfg.token_file) is None


# --- sync: saving ------------------------------------------------------------


def test_sync_saves_each_new_message_as_row_and_file(service, anaf, cfg, logged_in):
    anaf.add("3001", xml=invoice_xml(number="FV-1042"))
    anaf.add("3002", tip="FACTURA TRIMISA")

    result = service.sync(VALID_CUI)

    folder = cfg.data_dir / "invoices" / TODAY_FOLDER
    assert result["ok"] is True
    assert (result["listed"], result["new_count"], result["failed_count"]) == (2, 2, 0)
    assert result["folder"] == str(folder)
    assert sorted(p.name for p in folder.iterdir()) == [
        f"{VALID_CUI}_primita_3001.xml",
        f"{VALID_CUI}_trimisa_3002.xml",
    ]
    assert (folder / f"{VALID_CUI}_primita_3001.xml").read_bytes() == invoice_xml(number="FV-1042")
    store = Store(cfg.db_path)
    assert store.existing_ids(["3001", "3002"]) == {"3001", "3002"}
    store.close()


def test_sync_reply_describes_each_saved_invoice(service, anaf, cfg, logged_in):
    anaf.add("3001", xml=invoice_xml(number="FV-1042", supplier_name="Furnizor SRL"))

    (saved,) = service.sync(VALID_CUI)["new"]

    assert saved["id"] == "3001"
    assert saved["cui"] == VALID_CUI
    assert saved["message_type"] == "FACTURA PRIMITA"
    assert saved["anaf_created_at"] == "2026-11-10T14:15"
    assert saved["invoice_number"] == "FV-1042"
    assert saved["supplier_cui"] == "87654321"
    assert saved["supplier_name"] == "Furnizor SRL"
    assert saved["total_payable"] == "1190.00"
    assert saved["currency"] == "RON"
    assert saved["uploaded_to_accounting"] is False
    assert saved["first_seen_at"] == NOW.isoformat()
    assert saved["xml_path"] == str(
        cfg.data_dir / "invoices" / TODAY_FOLDER / f"{VALID_CUI}_primita_3001.xml"
    )
    assert Path(saved["xml_path"]).is_file()


def test_database_keeps_xml_signature_and_anafs_list_entry(service, anaf, cfg, logged_in):
    anaf.add("3001", xml=invoice_xml(number="FV-1042"))
    service.sync(VALID_CUI)

    connection = sqlite3.connect(cfg.db_path)
    connection.row_factory = sqlite3.Row
    row = connection.execute("SELECT * FROM messages WHERE id = '3001'").fetchone()
    connection.close()

    assert "<cbc:ID>FV-1042</cbc:ID>" in row["invoice_xml"]
    assert "Signature" in row["signature_xml"]
    assert '"tip": "FACTURA PRIMITA"' in row["raw_metadata_json"]
    assert len(row["zip_sha256"]) == 64
    assert row["xml_path"] == f"invoices/{TODAY_FOLDER}/{VALID_CUI}_primita_3001.xml"
    assert row["uploaded_to_accounting"] == 0


def test_error_notices_and_buyer_messages_are_saved_without_invoice_fields(service, anaf, cfg, logged_in):
    anaf.add("3003", tip="ERORI FACTURA", xml=ANAF_ERROR_NOTICE.encode())
    anaf.add("3004", tip="MESAJ CUMPARATOR PRIMIT / MESAJ CUMPARATOR TRANSMIS", xml=b"<mesaj/>")

    result = service.sync(VALID_CUI)

    folder = cfg.data_dir / "invoices" / TODAY_FOLDER
    assert sorted(p.name for p in folder.iterdir()) == [
        f"{VALID_CUI}_erori_3003.xml",
        f"{VALID_CUI}_mesaj_3004.xml",
    ]
    assert [m["invoice_number"] for m in result["new"]] == [None, None]


def test_unreadable_xml_is_still_saved(service, anaf, logged_in):
    anaf.add("3001", xml=b"<Invoice><unclosed>")

    result = service.sync(VALID_CUI)

    assert result["new_count"] == 1
    assert result["new"][0]["invoice_number"] is None
    assert Path(result["new"][0]["xml_path"]).read_bytes() == b"<Invoice><unclosed>"


def test_message_id_cannot_steer_the_file_outside_the_dated_folder(service, anaf, cfg, logged_in):
    anaf.add("../../evil")

    (saved,) = service.sync(VALID_CUI)["new"]

    assert Path(saved["xml_path"]).parent == cfg.data_dir / "invoices" / TODAY_FOLDER


def test_a_download_counts_the_received_and_the_issued_invoices_apart(service, anaf, logged_in):
    anaf.add("3001")
    anaf.add("3002", tip="FACTURA TRIMISA")
    anaf.add("3003", tip="FACTURA TRIMISA")
    anaf.add("3004", tip="ERORI FACTURA")

    result = service.sync(VALID_CUI)

    assert (result["new_count"], result["received_count"], result["issued_count"]) == (4, 1, 2)


def test_an_issued_invoice_can_be_looked_at_and_has_nothing_for_saga(service, anaf, logged_in):
    anaf.add("3002", tip="FACTURA TRIMISA", xml=invoice_xml(number="AC-2031"))
    service.sync(VALID_CUI)

    (listed,) = service.invoices(cui=VALID_CUI, message_type="trimisa")["invoices"]
    view = service.invoice_view("3002")

    assert (listed["invoice_number"], listed["customer_name"]) == ("AC-2031", "Client SRL")
    assert (listed["classification_status"], listed["is_new"]) == (None, False)
    assert view["document"]["number"] == "AC-2031"
    assert (view["saga_xml"], view["rule_suggestion"], view["jev"]) == (None, None, None)


def test_one_clients_list_says_how_many_invoices_the_client_issued(service, anaf, logged_in):
    anaf.add("3001")
    anaf.add("3002", tip="FACTURA TRIMISA")
    anaf.add("3003", tip="factura trimisa")
    anaf.add("3004", tip="ERORI FACTURA")
    service.sync(VALID_CUI)

    received = service.invoices(cui=VALID_CUI, message_type="primita")

    assert (received["count"], received["issued_count"]) == (1, 2)
    assert service.invoices(cui=OTHER_VALID_CUI)["issued_count"] == 0
    assert "issued_count" not in service.invoices()  # it is one client's count


def test_no_messages_is_a_successful_empty_run(service, cfg, logged_in):
    result = service.sync(VALID_CUI)

    assert result == {
        "ok": True,
        "cui": VALID_CUI,
        "window_days": 7,
        "listed": 0,
        "new_count": 0,
        "received_count": 0,
        "issued_count": 0,
        "failed_count": 0,
        "folder": None,
        "new": [],
        "failed": [],
        "classification": {
            "classified": 0, "review": 0, "pending": 0, "skipped": 0, "jev_calls": 0, "jev_cost_usd": 0,
        },
        "saga_folder": None,
    }
    assert not (cfg.data_dir / "invoices").exists()


# --- sync: duplicates --------------------------------------------------------


def test_second_sync_of_the_same_list_saves_and_downloads_nothing(service, anaf, logged_in):
    anaf.add("3001")
    anaf.add("3002")
    service.sync(VALID_CUI)
    downloads_after_first = list(anaf.downloads)

    second = service.sync(VALID_CUI)

    assert (second["listed"], second["new_count"]) == (2, 0)
    assert second["new"] == []
    assert anaf.downloads == downloads_after_first


def test_only_the_unseen_message_is_downloaded_when_the_list_grows(service, anaf, logged_in):
    anaf.add("3001")
    service.sync(VALID_CUI)
    anaf.add("3002")

    second = service.sync(VALID_CUI)

    assert [m["id"] for m in second["new"]] == ["3002"]
    assert anaf.downloads == ["3001", "3002"]


def test_same_invoice_number_from_same_supplier_is_saved_and_pointed_out(service, anaf, logged_in):
    anaf.add("3001", xml=invoice_xml(number="FV-1"))
    anaf.add("3002", xml=invoice_xml(number="FV-1"))

    first, second = service.sync(VALID_CUI)["new"]

    assert first["possible_duplicate_of"] is None
    assert second["possible_duplicate_of"] == "3001"


# --- sync: window ------------------------------------------------------------


def window_of(anaf):
    params = anaf.list_requests[-1]
    return int(params["startTime"]), int(params["endTime"])


def ms(moment):
    return int(moment.timestamp() * 1000)


def test_default_window_is_seven_days_ending_a_minute_ago(service, anaf, logged_in):
    result = service.sync(VALID_CUI)

    end = NOW - timedelta(minutes=1)
    assert result["window_days"] == 7
    assert window_of(anaf) == (ms(end - timedelta(days=7)), ms(end))


def test_days_can_be_set_for_one_call(service, anaf, logged_in):
    result = service.sync(VALID_CUI, days=30)

    end = NOW - timedelta(minutes=1)
    assert result["window_days"] == 30
    assert window_of(anaf) == (ms(end - timedelta(days=30)), ms(end))


@pytest.mark.parametrize("days", [0, 61, -3])
def test_days_outside_anafs_range_are_invalid_input(service, logged_in, days):
    assert error_code(lambda: service.sync(VALID_CUI, days=days)) == "invalid_input"


def test_window_widens_to_cover_the_time_since_the_last_clean_run(service, anaf, cfg, logged_in):
    record_run(cfg, VALID_CUI, NOW - timedelta(days=10))

    result = service.sync(VALID_CUI)

    assert result["window_days"] == 11


def test_recent_clean_run_keeps_the_seven_day_window(service, cfg, logged_in):
    record_run(cfg, VALID_CUI, NOW - timedelta(days=2))

    assert service.sync(VALID_CUI)["window_days"] == 7


def test_runs_for_another_company_or_with_failures_do_not_narrow_the_gap(service, cfg, logged_in):
    record_run(cfg, VALID_CUI, NOW - timedelta(days=20))
    record_run(cfg, VALID_CUI, NOW - timedelta(days=1), status="partial")
    record_run(cfg, OTHER_VALID_CUI, NOW - timedelta(days=1))

    assert service.sync(VALID_CUI)["window_days"] == 21


def test_window_never_reaches_back_past_anafs_sixty_days(service, anaf, cfg, logged_in):
    record_run(cfg, VALID_CUI, NOW - timedelta(days=200))

    result = service.sync(VALID_CUI)

    start, _ = window_of(anaf)
    assert result["window_days"] == 60
    assert start > ms(NOW - timedelta(days=60))


# --- sync: failures ----------------------------------------------------------


def test_one_failed_download_does_not_stop_the_others(service, anaf, cfg, logged_in):
    anaf.add("3001")
    anaf.add("3002")
    anaf.add("3003")
    anaf.download_errors["3002"] = "S-au facut deja 10 descarcari de mesaj in cursul zilei"

    result = service.sync(VALID_CUI)

    assert [m["id"] for m in result["new"]] == ["3001", "3003"]
    assert result["failed_count"] == 1
    assert result["failed"] == [
        {
            "id": "3002",
            "message_type": "FACTURA PRIMITA",
            "error": {
                "code": "anaf_limit_reached",
                "message": "ANAF: S-au facut deja 10 descarcari de mesaj in cursul zilei",
            },
        }
    ]
    store = Store(cfg.db_path)
    assert store.runs()[-1]["status"] == "partial"
    store.close()


def test_failed_message_is_retried_on_the_next_run(service, anaf, logged_in):
    anaf.add("3001")
    anaf.download_errors["3001"] = "Eroare tehnica"
    service.sync(VALID_CUI)
    anaf.download_errors.clear()

    second = service.sync(VALID_CUI)

    assert [m["id"] for m in second["new"]] == ["3001"]
    assert anaf.downloads == ["3001", "3001"]


def test_three_unreachable_downloads_in_a_row_stop_the_run(service, anaf, logged_in):
    for n in range(1, 6):
        anaf.add(f"300{n}")
    anaf.unreachable_downloads = {"3001", "3002", "3003"}

    result = service.sync(VALID_CUI)

    assert anaf.downloads == ["3001", "3002", "3003"]
    assert result["new_count"] == 0
    assert result["failed_count"] == 5
    assert {f["error"]["code"] for f in result["failed"]} == {"network_error"}


def test_file_is_removed_when_the_row_cannot_be_saved(service, anaf, cfg, logged_in, monkeypatch):
    anaf.add("3001")

    def refuse(self, row):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(Store, "insert_message", refuse)

    result = service.sync(VALID_CUI)

    assert result["new_count"] == 0
    assert result["failed"][0]["error"]["code"] == "internal_error"
    assert list((cfg.data_dir / "invoices" / TODAY_FOLDER).glob("*.xml")) == []


def test_invalid_cui_is_refused_before_anaf_is_contacted(service, anaf, logged_in):
    assert error_code(lambda: service.sync("12345678")) == "invalid_cui"
    assert anaf.list_requests == []


def test_cui_may_be_given_with_the_ro_prefix(service, anaf, logged_in):
    result = service.sync(f"RO{VALID_CUI}")

    assert result["cui"] == VALID_CUI
    assert anaf.list_requests[-1]["cif"] == VALID_CUI


def test_company_without_spv_rights_is_reported_and_logged_as_a_failed_run(service, anaf, cfg, logged_in):
    anaf.list_error = f"Nu aveti drept in SPV pentru CIF={VALID_CUI}"

    assert error_code(lambda: service.sync(VALID_CUI)) == "no_spv_rights"
    store = Store(cfg.db_path)
    (run,) = store.runs()
    store.close()
    assert run["status"] == "error"
    assert run["error"].startswith("no_spv_rights")


def test_original_error_is_reported_when_the_failed_run_cannot_be_recorded(
    service, anaf, logged_in, monkeypatch, caplog
):
    anaf.list_error = f"Nu aveti drept in SPV pentru CIF={VALID_CUI}"

    def refuse(self, *args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(Store, "finish_run", refuse)

    with caplog.at_level("ERROR", logger="efactura"):
        assert error_code(lambda: service.sync(VALID_CUI)) == "no_spv_rights"

    logged = caplog.text
    assert "no_spv_rights" in logged
    assert "database is locked" in logged


def test_a_lock_that_waits_gets_in_once_the_other_lets_go(tmp_path):
    import threading

    first = service_module._FileLock(tmp_path / "x.lock")
    first.__enter__()
    threading.Timer(0.1, first.__exit__, (None, None, None)).start()

    with service_module._FileLock(tmp_path / "x.lock", wait=5):
        got_in = True

    assert got_in


def test_a_lock_that_waits_gives_up_when_its_time_is_over(tmp_path):
    import time

    with service_module._FileLock(tmp_path / "x.lock"):
        began = time.monotonic()
        with pytest.raises(EfacturaError) as refused:
            with service_module._FileLock(tmp_path / "x.lock", wait=0.2, busy="Somebody else is writing."):
                pass

    assert (refused.value.code, refused.value.message) == ("busy", "Somebody else is writing.")
    assert time.monotonic() - began >= 0.2


def test_a_second_sync_while_one_is_running_is_told_busy(service, anaf, cfg, logged_in):
    anaf.add("3001")
    other = Service(cfg, http=anaf.client(), now=lambda: NOW)
    seen = []
    anaf.on_download = lambda message_id: seen.append(error_code(lambda: other.sync(VALID_CUI)))

    result = service.sync(VALID_CUI)

    assert seen == ["busy"]
    assert result["new_count"] == 1


def test_lock_is_released_after_a_run(service, anaf, logged_in):
    service.sync(VALID_CUI)

    assert service.sync(VALID_CUI)["ok"] is True


# --- sync: login -------------------------------------------------------------


def test_without_a_saved_login_sync_asks_for_login_and_contacts_nothing(service, anaf):
    assert error_code(lambda: service.sync(VALID_CUI)) == "login_needed"
    assert anaf.list_requests == []
    assert anaf.token_requests == []


def test_expired_access_token_is_renewed_and_the_new_pair_saved(service, anaf, cfg):
    save_login(cfg, access_in=timedelta(days=-1))
    anaf.add("3001")

    result = service.sync(VALID_CUI)

    assert result["new_count"] == 1
    assert [r["grant_type"] for r in anaf.token_requests] == ["refresh_token"]
    saved = auth.load_tokens(cfg.token_file)
    assert (saved.access_token, saved.refresh_token) == ("access-2", "refresh-2")


def test_rejected_renewal_asks_for_login(service, anaf, cfg):
    save_login(cfg, refresh="revoked", access_in=timedelta(days=-1))

    assert error_code(lambda: service.sync(VALID_CUI)) == "login_needed"


def test_token_rejected_mid_run_is_renewed_once_and_the_run_continues(service, anaf, cfg):
    save_login(cfg, access="looks-valid-but-revoked")
    anaf.add("3001")

    result = service.sync(VALID_CUI)

    assert result["new_count"] == 1
    assert len(anaf.token_requests) == 1
    assert auth.load_tokens(cfg.token_file).access_token == "access-2"


# --- list (preview) ----------------------------------------------------------


def test_list_marks_new_and_saved_messages_and_saves_nothing(service, anaf, cfg, logged_in):
    anaf.add("3001")
    service.sync(VALID_CUI)
    anaf.add("3002", tip="FACTURA TRIMISA")
    downloads_before = list(anaf.downloads)

    listed = service.list_remote(VALID_CUI)

    assert listed["ok"] is True
    assert (listed["listed"], listed["new_count"], listed["window_days"]) == (2, 1, 7)
    assert [(m["id"], m["message_type"], m["is_new"]) for m in listed["messages"]] == [
        ("3001", "FACTURA PRIMITA", False),
        ("3002", "FACTURA TRIMISA", True),
    ]
    assert listed["messages"][0]["anaf_created_at"] == "2026-11-10T14:15"
    assert anaf.downloads == downloads_before
    store = Store(cfg.db_path)
    assert store.existing_ids(["3002"]) == set()
    store.close()


# --- reading the database and the flag ---------------------------------------


@pytest.fixture
def synced(service, anaf, logged_in):
    anaf.add("3001", xml=invoice_xml(number="FV-1"))
    anaf.add("3002", tip="FACTURA TRIMISA", xml=invoice_xml(number="OUT-9"))
    anaf.add("3003", tip="ERORI FACTURA", xml=ANAF_ERROR_NOTICE.encode())
    service.sync(VALID_CUI)


def test_invoices_lists_what_was_saved_with_full_paths(service, cfg, synced):
    listing = service.invoices()

    assert listing["ok"] is True
    assert listing["count"] == 3
    assert [i["id"] for i in listing["invoices"]] == ["3001", "3002", "3003"]
    assert listing["invoices"][0]["xml_path"] == str(
        cfg.data_dir / "invoices" / TODAY_FOLDER / f"{VALID_CUI}_primita_3001.xml"
    )
    assert "invoice_xml" not in listing["invoices"][0]


def test_invoices_can_be_narrowed_by_type(service, synced):
    assert [i["id"] for i in service.invoices(message_type="trimisa")["invoices"]] == ["3002"]


def test_unknown_type_is_invalid_input(service, synced):
    assert error_code(lambda: service.invoices(message_type="received")) == "invalid_input"


def test_invoices_since_a_date(service, clock, anaf, synced):
    clock["now"] = NOW + timedelta(days=2)
    anaf.add("3009")
    service.sync(VALID_CUI)

    assert [i["id"] for i in service.invoices(since="2026-11-12")["invoices"]] == ["3009"]


def test_badly_formed_since_date_is_invalid_input(service, synced):
    assert error_code(lambda: service.invoices(since="12/11/2026")) == "invalid_input"


def test_invoices_for_another_company_is_empty(service, synced):
    listed = service.invoices(cui=OTHER_VALID_CUI)

    assert (listed["ok"], listed["count"], listed["invoices"]) == (True, 0, [])


def test_single_invoice_with_and_without_xml(service, synced):
    plain = service.invoice("3001")
    full = service.invoice("3001", include_xml=True)

    assert plain["ok"] is True
    assert plain["invoice"]["invoice_number"] == "FV-1"
    assert "invoice_xml" not in plain["invoice"]
    assert "<cbc:ID>FV-1</cbc:ID>" in full["invoice"]["invoice_xml"]
    assert "Signature" in full["invoice"]["signature_xml"]


def test_unknown_invoice_is_not_found(service, synced):
    assert error_code(lambda: service.invoice("9999")) == "not_found"


def test_marking_uploaded_removes_it_from_pending(service, synced):
    marked = service.mark_uploaded(["3001"])

    assert marked == {
        "ok": True,
        "uploaded_to_accounting": True,
        "uploaded_at": NOW.isoformat(),
        "updated": ["3001"],
    }
    assert [i["id"] for i in service.invoices(pending=True)["invoices"]] == ["3002", "3003"]
    assert service.invoice("3001")["invoice"]["uploaded_to_accounting"] is True


def test_undo_puts_it_back_in_pending(service, synced):
    service.mark_uploaded(["3001"])

    undone = service.mark_uploaded(["3001"], undo=True)

    assert undone["uploaded_to_accounting"] is False
    assert undone["uploaded_at"] is None
    assert len(service.invoices(pending=True)["invoices"]) == 3


def test_marking_an_unknown_id_is_not_found(service, synced):
    assert error_code(lambda: service.mark_uploaded(["3001", "9999"])) == "not_found"
    assert service.invoice("3001")["invoice"]["uploaded_to_accounting"] is False


def test_marking_nothing_is_invalid_input(service, synced):
    assert error_code(lambda: service.mark_uploaded([])) == "invalid_input"


def test_health_reports_the_tool(service):
    health = service.health()

    assert health["ok"] is True
    assert health["service"] == "efactura"


# --- review fixes --------------------------------------------------------------


def test_short_explicit_window_after_a_long_pause_does_not_hide_the_gap(service, cfg, logged_in):
    record_run(cfg, VALID_CUI, NOW - timedelta(days=20))
    service.sync(VALID_CUI, days=1)

    assert service.sync(VALID_CUI)["window_days"] == 21


def test_explicit_window_that_covers_the_pause_counts_as_caught_up(service, clock, cfg, logged_in):
    record_run(cfg, VALID_CUI, NOW - timedelta(days=20))
    service.sync(VALID_CUI, days=30)
    clock["now"] = NOW + timedelta(days=10)

    assert service.sync(VALID_CUI)["window_days"] == 11


def test_sixty_day_run_counts_as_caught_up_after_an_even_longer_pause(service, clock, cfg, logged_in):
    record_run(cfg, VALID_CUI, NOW - timedelta(days=200))
    service.sync(VALID_CUI)
    clock["now"] = NOW + timedelta(days=2)

    assert service.sync(VALID_CUI)["window_days"] == 7


def renewed_elsewhere_just_before_the_lock(service, cfg, anaf, monkeypatch):
    """Another process renews the login in the moment before this one gets the lock."""
    take_lock = service._lock
    anaf.valid_access.add("access-9")

    class Lock:
        def __enter__(self):
            save_login(cfg, access="access-9", refresh="refresh-9")
            self.inner = take_lock()
            return self.inner.__enter__()

        def __exit__(self, *exc_info):
            return self.inner.__exit__(*exc_info)

    monkeypatch.setattr(service, "_lock", Lock)


def test_login_renewed_by_another_process_is_used_rather_than_renewed_again(
    service, anaf, cfg, monkeypatch
):
    save_login(cfg, access_in=timedelta(days=-1))
    anaf.add("3001")
    renewed_elsewhere_just_before_the_lock(service, cfg, anaf, monkeypatch)

    listed = service.list_remote(VALID_CUI)

    assert listed["listed"] == 1
    assert anaf.token_requests == []


def test_token_anaf_rejected_but_already_renewed_elsewhere_is_not_renewed_twice(
    service, anaf, cfg, monkeypatch
):
    save_login(cfg, access="revoked-but-looks-valid")
    anaf.add("3001")
    renewed_elsewhere_just_before_the_lock(service, cfg, anaf, monkeypatch)

    listed = service.list_remote(VALID_CUI)

    assert listed["listed"] == 1
    assert anaf.token_requests == []


# --- a window given as two dates -----------------------------------------------------------

TZ = NOW.tzinfo


def test_a_date_range_is_fetched_from_the_first_morning_to_the_last_night(service, anaf, logged_in):
    result = service.sync(VALID_CUI, start="2026-11-03", end="2026-11-05")

    assert window_of(anaf) == (
        ms(datetime(2026, 11, 3, 0, 0, tzinfo=TZ)), ms(datetime(2026, 11, 6, 0, 0, tzinfo=TZ)),
    )
    assert result["window_days"] == 3


def test_a_range_ending_today_stops_a_minute_ago(service, anaf, logged_in):
    service.sync(VALID_CUI, start="2026-11-10", end="2026-11-11")

    assert window_of(anaf) == (ms(datetime(2026, 11, 10, tzinfo=TZ)), ms(NOW - timedelta(minutes=1)))


def test_a_range_with_only_a_start_runs_until_now(service, anaf, logged_in):
    service.sync(VALID_CUI, start="2026-11-10")

    assert window_of(anaf)[1] == ms(NOW - timedelta(minutes=1))


@pytest.mark.parametrize("kwargs", [
    {"start": "2026-11-05", "end": "2026-11-03"},   # backwards
    {"start": "2026-11-12"},                        # starts tomorrow
    {"start": "2026-11-05", "end": "2026-11-12"},   # ends tomorrow
    {"start": "2026-08-01", "end": "2026-11-05"},   # more than 60 days back
    {"end": "2026-11-05"},                          # no start
    {"start": "05.11.2026"},                        # not a date
    {"start": "2026-11-05", "days": 3},             # both ways at once
])
def test_a_range_that_makes_no_sense_is_invalid_input(service, anaf, logged_in, kwargs):
    assert error_code(lambda: service.sync(VALID_CUI, **kwargs)) == "invalid_input"
    assert anaf.list_requests == []


def test_a_range_that_stops_before_today_does_not_count_as_caught_up(service, cfg, logged_in):
    service.sync(VALID_CUI, start="2026-11-03", end="2026-11-05")

    store = Store(cfg.db_path)
    (run,) = store.runs()
    store.close()
    assert (run["status"], run["advances_coverage"]) == ("ok", 0)


def test_a_range_up_to_today_that_covers_the_gap_counts_as_caught_up(service, cfg, logged_in):
    record_run(cfg, VALID_CUI, NOW - timedelta(days=3))

    service.sync(VALID_CUI, start="2026-11-06")  # five days back: covers the three-day gap

    store = Store(cfg.db_path)
    assert store.runs()[-1]["advances_coverage"] == 1
    store.close()


def test_a_range_up_to_today_that_leaves_a_gap_does_not_count_as_caught_up(service, cfg, logged_in):
    record_run(cfg, VALID_CUI, NOW - timedelta(days=10))

    service.sync(VALID_CUI, start="2026-11-09")

    store = Store(cfg.db_path)
    assert store.runs()[-1]["advances_coverage"] == 0
    store.close()


# --- new and old ---------------------------------------------------------------------------


def test_invoices_of_the_latest_download_are_new_until_marked_uploaded(service, anaf, logged_in):
    anaf.add("3001")
    service.sync(VALID_CUI)

    assert [e["is_new"] for e in service.invoices()["invoices"]] == [True]
    service.mark_uploaded(["3001"])
    assert [e["is_new"] for e in service.invoices()["invoices"]] == [False]
    assert service.invoice("3001")["invoice"]["is_new"] is False


def test_a_later_download_that_brings_invoices_makes_the_earlier_ones_old(service, anaf, logged_in):
    anaf.add("3001")
    service.sync(VALID_CUI)
    anaf.add("3002")
    result = service.sync(VALID_CUI)

    by_id = {e["id"]: e["is_new"] for e in service.invoices()["invoices"]}
    assert by_id == {"3001": False, "3002": True}
    assert result["new"][0]["is_new"] is True


def test_a_later_download_that_brings_nothing_leaves_the_new_ones_new(service, anaf, logged_in):
    anaf.add("3001")
    service.sync(VALID_CUI)
    service.sync(VALID_CUI)  # nothing new at ANAF

    assert [e["is_new"] for e in service.invoices()["invoices"]] == [True]


def test_only_received_invoices_are_ever_new(service, anaf, logged_in):
    anaf.add("3001", tip="FACTURA TRIMISA")
    anaf.add("3002", tip="ERORI FACTURA", xml=ANAF_ERROR_NOTICE.encode())
    service.sync(VALID_CUI)

    assert [e["is_new"] for e in service.invoices()["invoices"]] == [False, False]


def test_each_company_has_its_own_latest_download(service, anaf, logged_in):
    anaf.add("3001")
    service.sync(VALID_CUI)
    anaf.add("3002")
    service.sync(OTHER_VALID_CUI)  # saves both under the other company in this stand-in

    assert service.invoices(cui=VALID_CUI)["invoices"][0]["is_new"] is True


def test_invoices_can_be_narrowed_to_the_new_ones(service, anaf, logged_in):
    anaf.add("3001")
    service.sync(VALID_CUI)
    anaf.add("3002")
    service.sync(VALID_CUI)

    assert [e["id"] for e in service.invoices(only_new=True)["invoices"]] == ["3002"]


# --- days left on the login ------------------------------------------------------------------


def test_status_says_how_many_days_the_login_still_lasts(service, logged_in):
    status = service.auth_status()

    assert (status["access_days_left"], status["refresh_days_left"]) == (30, 300)


def test_status_without_a_login_has_no_days_left(service):
    status = service.auth_status()

    assert (status["access_days_left"], status["refresh_days_left"]) == (None, None)


def test_an_expired_login_has_zero_days_left(service, cfg):
    save_login(cfg, access_in=timedelta(days=-400))
    auth.save_tokens(
        cfg.token_file,
        Tokens("a", "r", NOW - timedelta(days=5), NOW - timedelta(hours=1), NOW - timedelta(days=400)),
    )

    assert service.auth_status()["refresh_days_left"] == 0


# --- found by the review of the screen -------------------------------------------------------


def test_a_period_can_be_a_minimum_that_widens_to_cover_the_gap(service, anaf, cfg, logged_in):
    record_run(cfg, VALID_CUI, NOW - timedelta(days=20))

    result = service.sync(VALID_CUI, days=5, cover_gap=True)

    assert result["window_days"] == 21
    store = Store(cfg.db_path)
    assert store.runs()[-1]["advances_coverage"] == 1
    store.close()


def test_a_minimum_period_is_kept_when_it_already_covers_the_gap(service, cfg, logged_in):
    record_run(cfg, VALID_CUI, NOW - timedelta(days=2))

    assert service.sync(VALID_CUI, days=10, cover_gap=True)["window_days"] == 10


def test_without_asking_days_are_still_taken_literally(service, cfg, logged_in):
    record_run(cfg, VALID_CUI, NOW - timedelta(days=20))

    assert service.sync(VALID_CUI, days=5)["window_days"] == 5


def test_a_range_may_start_on_the_sixtieth_day_back(service, anaf, logged_in):
    service.sync(VALID_CUI, start="2026-09-12")  # 60 days before 11 November

    start, _ = window_of(anaf)
    assert start == ms(NOW - timedelta(days=60) + timedelta(minutes=5))  # as far back as ANAF goes
    assert error_code(lambda: service.sync(VALID_CUI, start="2026-09-11")) == "invalid_input"


def test_a_range_anaf_keeps_no_moment_of_is_refused(service, anaf, clock, logged_in):
    # The sixtieth day back, asked for in its last minutes: what ANAF still reaches of it begins after it ends.
    clock["now"] = NOW.replace(hour=23, minute=57)

    assert error_code(lambda: service.sync(VALID_CUI, start="2026-09-12", end="2026-09-12")) == "invalid_input"
    assert anaf.list_requests == []
