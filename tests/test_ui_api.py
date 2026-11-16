"""The routes that exist for the screen: rules, settings, clients, invoice view, costs."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from efactura import auth, service as service_module
from efactura.api import create_app
from efactura.auth import Tokens
from efactura.config import load_config
from efactura.rules import Rule, Rulebook
from efactura.service import Service

from helpers import VALID_CUI, FakeAnaf, FakeOpenRouter, line, rich_invoice_xml, set_rulebook

NOW = datetime(2026, 11, 11, 9, 30, tzinfo=timezone(timedelta(hours=2)))
KEY = {"X-API-Key": "local-key"}
BOOK = Rulebook(
    accounts={"6022": "Combustibil.", "628": "Alte servicii."},
    rules=(Rule("combustibil", "6022", keywords=("motorina",)),),
    instructions="Alege contul facturii.",
)
FUEL = [line("Motorina", "450.00")]
PARTS = [line("Piese de schimb", "900.00")]


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[anaf]\nclient_id = "my-client"\nclient_secret = "my-secret"\n'
        f"token_file = '{tmp_path / 'private' / 'tokens.json'}'\n"
        '[api]\nkey = "local-key"\n[openrouter]\napi_key = "or-test-key"\n',
        encoding="utf-8",
    )
    cfg = load_config(path)
    set_rulebook(cfg.db_path, BOOK)
    auth.save_tokens(
        cfg.token_file,
        Tokens("access-1", "refresh-1", NOW + timedelta(days=30), NOW + timedelta(days=300), NOW),
    )
    return cfg


@pytest.fixture
def openrouter():
    return FakeOpenRouter()


@pytest.fixture
def anaf(openrouter):
    fake = FakeAnaf()
    fake.openrouter = openrouter
    return fake


@pytest.fixture
def make_service(anaf, monkeypatch):
    monkeypatch.setattr(service_module, "_pause", lambda seconds: None)
    return lambda cfg: Service(cfg, http=anaf.client(), now=lambda: NOW)


@pytest.fixture
def api(cfg, make_service):
    client = TestClient(create_app(cfg, service_factory=make_service))
    client.headers.update(KEY)
    return client


# --- rules and accounts ------------------------------------------------------------------


def test_rules_route_shows_accounts_rules_and_the_question(api):
    overview = api.get("/rules").json()

    assert overview["accounts"] == BOOK.accounts
    assert [rule["name"] for rule in overview["rules"]] == ["combustibil"]
    assert overview["jev_instructions"] == "Alege contul facturii."


def test_an_account_can_be_added_and_removed_over_the_api(api):
    added = api.put("/accounts/302", json={"description": "Materiale consumabile."})
    removed = api.delete("/accounts/302")

    assert (added.status_code, added.json()["accounts"]["302"]) == (200, "Materiale consumabile.")
    assert "302" not in removed.json()["accounts"]
    assert api.put("/accounts/abc", json={"description": "x"}).status_code == 400
    assert api.delete("/accounts/999").status_code == 404


def test_a_rule_can_be_added_changed_moved_and_removed_over_the_api(api):
    added = api.post("/rules", json={"name": "piese", "cont": 3024, "keywords": ["piese"],
                                     "client_cui": VALID_CUI})
    new_id = added.json()["rules"][-1]["id"]
    changed = api.put(f"/rules/{new_id}", json={"name": "piese auto", "cont": "3024",
                                                "supplier_cuis": ["11112222"], "enabled": False})
    moved = api.post(f"/rules/{new_id}/move", json={"up": True})
    removed = api.delete(f"/rules/{new_id}")

    assert (added.status_code, added.json()["rules"][-1]["client_cui"]) == (200, VALID_CUI)
    last = changed.json()["rules"][-1]
    assert (last["name"], last["keywords"], last["supplier_cuis"], last["enabled"]) == (
        "piese auto", [], ["11112222"], False
    )
    assert [rule["name"] for rule in moved.json()["rules"]] == ["piese auto", "combustibil"]
    assert [rule["name"] for rule in removed.json()["rules"]] == ["combustibil"]


def test_a_rule_without_a_condition_or_an_unknown_rule_is_refused_over_the_api(api):
    no_condition = api.post("/rules", json={"name": "gol", "cont": "628"})
    unknown = api.put("/rules/999", json={"name": "x", "cont": "628", "keywords": ["x"]})

    assert (no_condition.status_code, no_condition.json()["error"]["code"]) == (400, "invalid_input")
    assert unknown.status_code == 404
    assert api.delete("/rules/999").status_code == 404
    assert api.post("/rules/999/move", json={"up": False}).status_code == 404


def test_the_question_for_jev_can_be_changed_with_or_without_the_level(api):
    only_question = api.put("/classification/settings", json={"jev_instructions": "Ce cont?"})
    both = api.put("/classification/settings", json={"min_confidence": 0.7, "jev_instructions": "Care cont?"})
    nothing = api.put("/classification/settings", json={})

    assert (only_question.json()["jev_instructions"], only_question.json()["min_confidence"]) == ("Ce cont?", 0.8)
    assert (both.json()["jev_instructions"], both.json()["min_confidence"]) == ("Care cont?", 0.7)
    assert nothing.status_code == 400


# --- proposed rules ------------------------------------------------------------------------


def test_proposed_rules_are_listed_tried_and_turned_down_over_the_api(api, anaf):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))  # no rule for it: Jev puts it on 628
    api.post("/sync", json={"cui": VALID_CUI})

    listed = api.get("/rules/suggestions").json()
    on_the_invoice = api.get("/invoices/3001/view").json()["rule_suggestion"]
    tried = api.post("/rules/preview", json={"keywords": ["piese"], "client_cui": int(VALID_CUI)})
    turned_down = api.post("/rules/suggestions/dismiss", json={"invoice_ids": [3001]})

    assert (listed["count"], listed["days"]) == (1, 90)
    assert listed["suggestions"] == [{
        "cont": "628", "keywords": ["piese"], "supplier_cuis": [], "supplier_name": None,
        "invoice_ids": ["3001"], "matches": 1, "by_cont": {"628": 1},
    }]
    assert (on_the_invoice["cont"], on_the_invoice["ticked"]) == ("628", ["piese"])
    assert tried.json() == {"ok": True, "matches": 1, "by_cont": {"628": 1}, "days": 90}
    assert turned_down.json() == {"ok": True, "dismissed": ["3001"]}
    assert api.get("/rules/suggestions").json()["count"] == 0
    assert api.get("/invoices/3001/view").json()["rule_suggestion"] is None


def test_a_rule_created_from_a_proposal_takes_it_off_the_list(api, anaf):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))
    api.post("/sync", json={"cui": VALID_CUI})
    (proposal,) = api.get("/rules/suggestions").json()["suggestions"]

    created = api.post("/rules", json={"name": "piese", "cont": proposal["cont"],
                                       "keywords": proposal["keywords"]})

    assert created.status_code == 200
    assert api.get("/rules/suggestions").json()["suggestions"] == []


def test_proposed_rule_routes_refuse_what_makes_no_sense(api):
    nothing = api.post("/rules/suggestions/dismiss", json={"invoice_ids": []})
    unknown = api.post("/rules/suggestions/dismiss", json={"invoice_ids": ["nope"]})
    not_a_list = api.post("/rules/preview", json={"keywords": "piese"})

    assert (nothing.status_code, nothing.json()["error"]["code"]) == (400, "invalid_input")
    assert unknown.status_code == 404
    assert (not_a_list.status_code, not_a_list.json()["error"]["code"]) == (400, "invalid_input")


# --- settings kept in the database ---------------------------------------------------------


def test_settings_show_the_saga_folder_from_the_settings_file_by_default(api, cfg):
    settings = api.get("/settings").json()

    assert (settings["ok"], settings["saga_folder"]) == (True, str(cfg.data_dir / "SAGA Import"))


def test_the_saga_folder_can_be_changed_and_new_files_go_there(api, anaf, tmp_path):
    elsewhere = tmp_path / "pentru saga"

    changed = api.put("/settings", json={"saga_folder": f"  {elsewhere}  "})
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))
    (entry,) = api.post("/sync", json={"cui": VALID_CUI}).json()["new"]

    assert (changed.status_code, changed.json()["saga_folder"]) == (200, str(elsewhere))
    assert entry["saga_xml_path"] == str(elsewhere / VALID_CUI / "F_87654321_FV-1042_09.11.2026.xml")
    assert (elsewhere / VALID_CUI / "F_87654321_FV-1042_09.11.2026.xml").exists()
    assert api.get("/settings").json()["saga_folder"] == str(elsewhere)


def test_what_is_waiting_for_saga_moves_when_the_folder_changes(api, anaf, cfg, tmp_path):
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))
    api.post("/sync", json={"cui": VALID_CUI})

    api.put("/settings", json={"saga_folder": str(tmp_path / "nou")})

    before = cfg.data_dir / "SAGA Import" / VALID_CUI / "F_87654321_FV-1042_09.11.2026.xml"
    after = tmp_path / "nou" / VALID_CUI / "F_87654321_FV-1042_09.11.2026.xml"
    assert not before.exists() and after.exists()
    assert api.get("/invoices/3001").json()["invoice"]["saga_xml_path"] == str(after)


def saga_files_of(folder):
    return sorted(path.name for path in (folder / VALID_CUI).glob("*"))


def two_waiting(api, anaf):
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL, number="A1"))
    anaf.add("3002", xml=rich_invoice_xml(lines=FUEL, number="A2"))
    api.post("/sync", json={"cui": VALID_CUI})


def test_settings_say_one_file_per_client_until_another_way_is_chosen(api):
    assert api.get("/settings").json()["saga_file_per"] == "client"


def test_the_way_the_saga_files_are_written_can_be_changed_on_its_own(api, anaf, cfg):
    two_waiting(api, anaf)

    changed = api.put("/settings", json={"saga_file_per": "invoice"})

    assert (changed.status_code, changed.json()["saga_file_per"]) == (200, "invoice")
    assert changed.json()["saga_folder"] == str(cfg.data_dir / "SAGA Import")
    assert saga_files_of(cfg.data_dir / "SAGA Import") == [
        "F_87654321_A1_09.11.2026.xml", "F_87654321_A2_09.11.2026.xml"
    ]


def test_the_folder_and_the_way_can_be_changed_together(api, anaf, cfg, tmp_path):
    api.put("/settings", json={"saga_file_per": "invoice"})
    two_waiting(api, anaf)

    changed = api.put("/settings", json={"saga_folder": str(tmp_path / "nou"), "saga_file_per": "client"})

    assert (changed.json()["saga_folder"], changed.json()["saga_file_per"]) == (str(tmp_path / "nou"), "client")
    assert saga_files_of(tmp_path / "nou") == ["F_87654321_A1_09.11.2026.xml"]
    assert saga_files_of(cfg.data_dir / "SAGA Import") == []


@pytest.mark.parametrize("body", [{}, {"saga_file_per": "both"}, {"saga_file_per": True}, {"saga_file_per": ""}])
def test_settings_that_name_neither_a_folder_nor_one_of_the_two_ways_are_refused(api, body):
    refused = api.put("/settings", json=body)

    assert (refused.status_code, refused.json()["error"]["code"]) == (400, "invalid_input")
    assert api.get("/settings").json()["saga_file_per"] == "client"


def test_a_way_that_does_not_exist_leaves_the_folder_as_it_was_too(api, cfg, tmp_path):
    refused = api.put("/settings", json={"saga_folder": str(tmp_path / "nou"), "saga_file_per": "both"})

    assert refused.status_code == 400
    assert api.get("/settings").json()["saga_folder"] == str(cfg.data_dir / "SAGA Import")
    assert not (tmp_path / "nou").exists()


def test_changing_the_settings_says_whose_files_could_not_be_written(api, anaf, monkeypatch):
    two_waiting(api, anaf)
    fine = api.put("/settings", json={"saga_file_per": "invoice"})
    real_write = service_module._write_file

    def refuse_saga(path, content):
        if "SAGA Import" in str(path):
            raise PermissionError("the file is open in another program")
        real_write(path, content)

    monkeypatch.setattr(service_module, "_write_file", refuse_saga)

    changed = api.put("/settings", json={"saga_file_per": "client"})

    assert fine.json()["problems"] == []
    assert (changed.status_code, changed.json()["saga_file_per"]) == (200, "client")
    assert [problem["cui"] for problem in changed.json()["problems"]] == [VALID_CUI]
    assert "problems" not in api.get("/settings").json()


def test_a_clients_invoice_list_carries_how_its_saga_files_stand(api, anaf, cfg):
    two_waiting(api, anaf)

    state = api.get("/invoices", params={"cui": VALID_CUI}).json()["saga"]

    assert state == {"file_per": "client", "written_at": NOW.isoformat(), "problem": None}


def test_the_saga_files_can_be_written_again_when_asked(api, anaf, cfg):
    two_waiting(api, anaf)
    (cfg.data_dir / "SAGA Import" / VALID_CUI / "F_87654321_A1_09.11.2026.xml").unlink()  # by hand

    one = api.post("/saga-files/write", json={"cui": VALID_CUI})
    everyone = api.post("/saga-files/write", json={})
    bad = api.post("/saga-files/write", json={"cui": "../../etc"})

    assert (one.status_code, one.json()) == (200, {"ok": True, "clients": 1, "problems": []})
    assert everyone.json()["clients"] == 1
    assert saga_files_of(cfg.data_dir / "SAGA Import") == ["F_87654321_A1_09.11.2026.xml"]
    assert bad.status_code == 400


@pytest.mark.parametrize("folder", ["", "   ", "relativ/fara/litera"])
def test_a_saga_folder_that_is_not_a_full_path_is_refused(api, folder):
    reply = api.put("/settings", json={"saga_folder": folder})

    assert (reply.status_code, reply.json()["error"]["code"]) == (400, "invalid_input")


def test_a_saga_folder_that_cannot_be_created_is_refused(api, tmp_path):
    blocker = tmp_path / "un-fisier"
    blocker.write_text("nu sunt folder")

    reply = api.put("/settings", json={"saga_folder": str(blocker / "sub")})

    assert (reply.status_code, reply.json()["error"]["code"]) == (400, "invalid_input")


def test_choosing_a_folder_asks_the_computer_and_returns_the_answer(api, monkeypatch, tmp_path):
    monkeypatch.setattr(service_module, "_ask_for_folder", lambda start, title: str(tmp_path / "ales"))
    picked = api.post("/settings/choose-folder").json()
    monkeypatch.setattr(service_module, "_ask_for_folder", lambda start, title: None)
    cancelled = api.post("/settings/choose-folder").json()

    assert picked == {"ok": True, "folder": str(tmp_path / "ales")}
    assert cancelled == {"ok": True, "folder": None}


def test_the_dialog_for_the_backup_folder_has_its_own_title_and_starts_in_that_folder(api, monkeypatch, tmp_path):
    asked = []
    monkeypatch.setattr(service_module, "_ask_for_folder", lambda start, title: asked.append((start, title)))
    chosen = tmp_path / "stick" / "Copii AutoSaga"
    api.put("/backups/folder", json={"folder": str(chosen)})

    api.post("/settings/choose-folder?purpose=backups")
    api.post("/settings/choose-folder")
    unknown = api.post("/settings/choose-folder?purpose=altceva")

    assert asked[0] == (str(chosen), "Folderul pentru copiile de siguranță")
    assert asked[1][1] == "Folderul pentru SAGA" and asked[1][0] != str(chosen)
    assert (unknown.status_code, len(asked)) == (400, 2)


def test_opening_a_clients_saga_folder_reveals_it_on_the_computer(api, anaf, cfg, monkeypatch):
    revealed = []
    monkeypatch.setattr(service_module, "_reveal", revealed.append)
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))
    api.post("/sync", json={"cui": VALID_CUI})

    with_files = api.post("/folders/open", json={"cui": VALID_CUI})
    without = api.post("/folders/open", json={})
    bad = api.post("/folders/open", json={"cui": "../../etc"})

    saga = cfg.data_dir / "SAGA Import"
    assert (with_files.status_code, without.status_code) == (200, 200)
    assert revealed == [saga / VALID_CUI, saga]
    assert bad.status_code == 400


# --- keys and passwords --------------------------------------------------------------------


def secrets_by_key(reply):
    return {entry["key"]: entry for entry in reply.json()["secrets"]}


def test_secrets_are_listed_with_what_can_be_changed(api):
    secrets = secrets_by_key(api.get("/secrets"))

    assert secrets["openrouter_api_key"] == {"key": "openrouter_api_key", "value": "or-test-key", "editable": True}
    assert (secrets["anaf_client_id"]["value"], secrets["anaf_client_secret"]["value"]) == (
        "my-client", "my-secret"
    )
    assert secrets["api_key"] == {"key": "api_key", "value": "local-key", "editable": False}
    assert (secrets["anaf_access_token"]["value"], secrets["anaf_access_token"]["editable"]) == (
        "access-1", False
    )
    assert secrets["anaf_refresh_token"]["value"] == "refresh-1"


def test_a_key_changed_on_screen_wins_over_the_settings_file_and_is_used(api, anaf, openrouter):
    openrouter.valid_keys = {"or-new-key"}

    changed = api.put("/secrets/openrouter_api_key", json={"value": "  or-new-key "})
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))
    (entry,) = api.post("/sync", json={"cui": VALID_CUI}).json()["new"]

    assert secrets_by_key(changed)["openrouter_api_key"]["value"] == "or-new-key"
    assert entry["classification_status"] == "classified"
    assert openrouter.keys_seen == ["or-new-key"]


def test_clearing_a_key_falls_back_to_the_settings_file(api):
    api.put("/secrets/openrouter_api_key", json={"value": "or-new-key"})

    cleared = api.put("/secrets/openrouter_api_key", json={"value": ""})

    assert secrets_by_key(cleared)["openrouter_api_key"]["value"] == "or-test-key"


def test_the_anaf_client_details_can_be_changed_on_screen(api):
    api.put("/secrets/anaf_client_id", json={"value": "alt-client"})
    api.put("/secrets/anaf_client_secret", json={"value": "alt-secret"})

    assert "client_id=alt-client" in api.post("/auth/login/start").json()["authorize_url"]


@pytest.mark.parametrize("key", ["api_key", "anaf_access_token", "necunoscut"])
def test_keys_that_are_read_only_or_unknown_cannot_be_changed(api, key):
    reply = api.put(f"/secrets/{key}", json={"value": "x"})

    assert (reply.status_code, reply.json()["error"]["code"]) == (400, "invalid_input")


def test_secrets_need_the_key_like_everything_else(cfg, make_service):
    bare = TestClient(create_app(cfg, service_factory=make_service))

    assert bare.get("/secrets").status_code == 401
    assert bare.put("/secrets/openrouter_api_key", json={"value": "x"}).status_code == 401


# --- clients -------------------------------------------------------------------------------


def test_clients_can_be_added_listed_and_removed_over_the_api(api):
    added = api.post("/clients", json={"cui": int(VALID_CUI), "name": "Alfa Construct SRL"})
    listed = api.get("/clients").json()
    removed = api.delete(f"/clients/RO{VALID_CUI}")

    assert added.status_code == 200
    assert [(c["cui"], c["name"], c["invoices"]) for c in listed["clients"]] == [
        (VALID_CUI, "Alfa Construct SRL", 0)
    ]
    assert removed.json()["count"] == 0
    assert api.post("/clients", json={"cui": "12345678", "name": "Delta"}).status_code == 400
    assert api.delete(f"/clients/{VALID_CUI}").status_code == 404


def test_a_client_is_switched_off_through_the_api(api):
    api.post("/clients", json={"cui": VALID_CUI, "name": "Alfa Construct SRL"})

    reply = api.put(f"/clients/RO{VALID_CUI}/enabled", json={"enabled": False})

    assert reply.status_code == 200
    assert [(c["cui"], c["enabled"]) for c in reply.json()["clients"]] == [(VALID_CUI, False)]


def test_downloading_a_client_that_is_off_answers_409(api):
    api.post("/clients", json={"cui": VALID_CUI, "name": "Alfa Construct SRL"})
    api.put(f"/clients/{VALID_CUI}/enabled", json={"enabled": False})

    reply = api.post("/sync", json={"cui": VALID_CUI})

    assert (reply.status_code, reply.json()["error"]["code"]) == (409, "client_off")


def test_switching_an_unknown_client_answers_404(api):
    reply = api.put(f"/clients/{VALID_CUI}/enabled", json={"enabled": False})

    assert (reply.status_code, reply.json()["error"]["code"]) == (404, "not_found")


def test_a_client_file_is_imported_from_the_request_body(api):
    content = f"Nume;CUI\nAlfa Construct SRL;{VALID_CUI}\nDelta Service SRL;12345678\n".encode()

    reply = api.post("/clients/import", params={"filename": "clienti.csv"}, content=content)

    result = reply.json()
    assert reply.status_code == 200
    assert result["added"] == [{"cui": VALID_CUI, "name": "Alfa Construct SRL"}]
    assert [(r["row"], r["code"]) for r in result["rejected"]] == [(3, "invalid_cui")]
    assert api.get("/clients").json()["count"] == 1


def test_a_file_of_the_wrong_kind_is_refused(api):
    reply = api.post("/clients/import", params={"filename": "clienti.pdf"}, content=b"%PDF")

    assert (reply.status_code, reply.json()["error"]["code"]) == (400, "invalid_input")


# --- dates, new and old, several invoices at once --------------------------------------------


def test_sync_route_takes_a_date_range(api, anaf):
    reply = api.post("/sync", json={"cui": VALID_CUI, "start": "2026-11-03", "end": "2026-11-05"})

    assert (reply.status_code, reply.json()["window_days"]) == (200, 3)
    assert api.post("/sync", json={"cui": VALID_CUI, "start": "2026-11-05", "days": 2}).status_code == 400


def test_invoices_route_marks_and_filters_the_new_ones(api, anaf):
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL, number="A1"))
    api.post("/sync", json={"cui": VALID_CUI})
    anaf.add("3002", xml=rich_invoice_xml(lines=FUEL, number="A2"))
    api.post("/sync", json={"cui": VALID_CUI})

    everything = api.get("/invoices").json()["invoices"]
    only_new = api.get("/invoices", params={"new": "true"}).json()["invoices"]

    assert {e["id"]: e["is_new"] for e in everything} == {"3001": False, "3002": True}
    assert [e["id"] for e in only_new] == ["3002"]


def test_several_invoices_can_be_marked_uploaded_in_one_request(api, anaf):
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL, number="A1"))
    anaf.add("3002", xml=rich_invoice_xml(lines=FUEL, number="A2"))
    api.post("/sync", json={"cui": VALID_CUI})

    marked = api.post("/invoices/uploaded", json={"ids": ["3001", "3002"]})
    undone = api.post("/invoices/uploaded", json={"ids": ["3001"], "uploaded": False})

    assert (marked.status_code, marked.json()["updated"]) == (200, ["3001", "3002"])
    assert undone.json()["uploaded_to_accounting"] is False
    pending = api.get("/invoices", params={"pending": "true"}).json()["invoices"]
    assert [e["id"] for e in pending] == ["3001"]
    assert api.post("/invoices/uploaded", json={"ids": ["nope"]}).status_code == 404
    assert api.post("/invoices/uploaded", json={"ids": []}).status_code == 400


# --- one invoice, costs, the login -----------------------------------------------------------


def test_invoice_view_route(api, anaf):
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))
    api.post("/sync", json={"cui": VALID_CUI})

    view = api.get("/invoices/3001/view")

    assert view.status_code == 200
    assert view.json()["document"]["lines"][0]["description"] == "Motorina"
    assert "<Cont>6022</Cont>" in view.json()["saga_xml"]
    assert api.get("/invoices/nope/view").status_code == 404


def test_costs_route_groups_by_the_period_asked_for(api, anaf):
    anaf.add("3001", xml=rich_invoice_xml(lines=PARTS))
    api.post("/sync", json={"cui": VALID_CUI})

    by_day = api.get("/classification/costs", params={"group": "day", "until": "2026-11-11"}).json()
    calls = api.get("/classification/calls", params={"limit": 5}).json()

    assert (by_day["group"], by_day["by_period"][0]["period"], by_day["calls"]) == ("day", "2026-11-11", 1)
    assert (calls["count"], calls["calls"][0]["message_id"]) == (1, "3001")
    assert api.get("/classification/costs", params={"group": "decade"}).status_code == 400


def test_auth_status_route_reports_the_days_left(api):
    assert api.get("/auth/status").json()["refresh_days_left"] == 300


# --- found by the review of the screen -------------------------------------------------------


def test_sync_route_can_widen_the_period_to_cover_the_gap(api, anaf):
    reply = api.post("/sync", json={"cui": VALID_CUI, "days": 5, "cover_gap": True})

    assert (reply.status_code, reply.json()["window_days"]) == (200, 5)  # no earlier run: nothing to cover


def test_open_folder_route_takes_an_invoice(api, anaf, cfg, monkeypatch):
    revealed = []
    monkeypatch.setattr(service_module, "_reveal", revealed.append)
    anaf.add("3001", xml=rich_invoice_xml(lines=FUEL))
    api.post("/sync", json={"cui": VALID_CUI})

    reply = api.post("/folders/open", json={"invoice_id": "3001"})

    assert reply.status_code == 200
    assert revealed == [cfg.data_dir / "SAGA Import" / VALID_CUI]
    assert api.post("/folders/open", json={"invoice_id": "nope"}).status_code == 404


# --- the schedule ------------------------------------------------------------------------


def test_the_schedule_is_off_to_begin_with(api):
    shown = api.get("/sync/schedule").json()

    assert shown["ok"] is True
    assert shown["enabled"] is False
    assert shown["days"] == [0, 1, 2, 3, 4]
    assert shown["times"] == ["08:00"]
    assert shown["next_at"] is None
    assert shown["running"] is None
    assert shown["last_run"] is None


def test_the_schedule_is_saved_through_the_api(api):
    saved = api.put("/sync/schedule", json={"enabled": True, "days": [1, 3], "times": ["07:30", "13:00"]})
    shown = api.get("/sync/schedule").json()

    assert saved.status_code == 200
    assert saved.json()["enabled"] is True
    assert (shown["enabled"], shown["days"], shown["times"]) == (True, [1, 3], ["07:30", "13:00"])
    assert shown["next_at"] is not None


def test_a_bad_schedule_answers_400(api):
    answer = api.put("/sync/schedule", json={"enabled": True, "days": [0], "times": ["25:00"]})

    assert answer.status_code == 400
    assert api.get("/sync/schedule").json()["enabled"] is False


def test_the_schedule_holds_the_period_to_download(api):
    assert api.get("/sync/schedule").json()["period"] == {"days": 7}

    body = {"enabled": False, "days": [0], "times": ["08:00"]}
    saved = api.put("/sync/schedule", json={**body, "period": {"days": 3}})
    assert (saved.status_code, saved.json()["period"]) == (200, {"days": 3})

    dates = {"start": "2026-11-01", "end": "2026-11-30"}
    assert api.put("/sync/schedule", json={**body, "period": dates}).json()["period"] == dates
    # A program written before the period existed says nothing about it: it stays.
    assert api.put("/sync/schedule", json=body).json()["period"] == dates
    assert api.get("/sync/schedule").json()["period"] == dates


def test_a_bad_period_answers_400(api):
    body = {"enabled": False, "days": [0], "times": ["08:00"]}
    for period in ({}, {"days": 61}, {"days": True}, {"days": "7"}, {"days": 3, "start": "2026-11-01", "end": "2026-11-30"},
                   {"start": "2026-11-30", "end": "2026-11-01"}, {"start": "2026-11-01"}):
        answer = api.put("/sync/schedule", json={**body, "period": period})
        assert (answer.status_code, answer.json()["error"]["code"]) == (400, "invalid_input"), period
    assert api.get("/sync/schedule").json()["period"] == {"days": 7}


def test_reading_the_schedule_is_not_written_in_the_journal(api, cfg):
    from efactura import journal

    api.get("/sync/schedule")
    api.put("/sync/schedule", json={"enabled": False, "days": [0], "times": ["08:00"]})

    lines = journal.events(cfg.db_path, details=True, text="/sync/schedule")["events"]
    requests = [line["message"] for line in lines if line["event"] == "page.request"]
    assert requests == ["PUT /sync/schedule answered 200."]
