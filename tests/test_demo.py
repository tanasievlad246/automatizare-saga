import httpx
import pytest
from fastapi.testclient import TestClient

from efactura import demo, standins
from efactura.api import create_app
from efactura.config import load_config
from efactura.errors import EfacturaError
from efactura.service import Service
from efactura.store import Store


def test_the_demo_is_built_with_settings_that_say_demo_and_a_filled_database(tmp_path):
    cfg = demo.build(tmp_path / "demo")

    assert cfg.demo is True and cfg.path == tmp_path / "demo" / "config.toml"
    assert cfg.api_port == 8770 and (cfg.data_dir / demo.MARKER).is_file()
    desk = Service(cfg, http=standins.FakeAnaf().client())
    assert len(desk.clients()["clients"]) == 4
    assert len(desk.invoices()["invoices"]) >= 5
    assert desk.rule_suggestions()["count"] >= 1
    assert desk.auth_status()["state"] == "valid"


def test_building_again_starts_from_nothing(tmp_path):
    cfg = demo.build(tmp_path / "demo")
    (cfg.data_dir / "left-over.txt").write_text("x")

    demo.build(tmp_path / "demo")

    assert not (cfg.data_dir / "left-over.txt").exists()


def test_a_demo_folder_still_in_use_is_a_settings_error_that_says_to_stop_the_demo(tmp_path, monkeypatch):
    demo.build(tmp_path / "demo")

    def held_open(path, ignore_errors=False, **kwargs):  # Windows, with a file a running demo has open
        if not ignore_errors:
            raise PermissionError(13, "The process cannot access the file because it is being used by another process", str(path))

    monkeypatch.setattr(demo.shutil, "rmtree", held_open)
    with pytest.raises(EfacturaError) as refused:
        demo.build(tmp_path / "demo")

    assert refused.value.code == "config_error" and "in use" in refused.value.message
    assert "stop the running demo" in refused.value.message


def test_settings_are_demo_only_when_they_say_so(tmp_path):
    plain = tmp_path / "config.toml"
    plain.write_text('[api]\nkey = "k"\n', encoding="utf-8")
    off = tmp_path / "off.toml"
    off.write_text('[api]\nkey = "k"\n[demo]\nenabled = false\n', encoding="utf-8")

    assert load_config(plain).demo is False and load_config(off).demo is False


def test_settings_that_ask_for_demo_over_a_real_data_folder_are_refused(tmp_path):
    # Made-up invoices must never be written among real ones because of one line in a file.
    real = tmp_path / "config.toml"
    real.write_text('[api]\nkey = "k"\n[demo]\nenabled = true\n', encoding="utf-8")
    (tmp_path / "data").mkdir()

    with pytest.raises(EfacturaError) as refused:
        load_config(real)

    assert refused.value.code == "config_error" and "efactura demo" in refused.value.message


KEY = {"X-API-Key": "EXEMPLU-cheie-locala"}
CLIENT = "12345674"


@pytest.fixture
def cfg(tmp_path):
    return demo.build(tmp_path / "demo")


def test_every_download_brings_one_or_two_new_invoices_and_they_are_remembered(cfg):
    first = demo.service(cfg).sync(CLIENT)
    second = demo.service(cfg).sync(CLIENT)  # a new Service each time, as each request makes one

    assert (first["received_count"], second["received_count"]) == (1, 2)
    assert (cfg.data_dir / "standin.json").is_file()


def test_the_demo_has_invoices_a_client_issued(cfg):
    issued = demo.service(cfg).invoices(cui=CLIENT, message_type="trimisa")["invoices"]

    assert len(issued) == 3
    assert {each["supplier_name"] for each in issued} == {"Alfa Construct SRL"}
    assert [each["customer_name"] for each in issued] == [
        "Gama Imobiliare SA", "Primăria Comunei Valea Mare", "Beta Instal SRL",
    ]
    decided = {each["invoice_number"]: (each["classification_status"], each["cont"]) for each in issued}
    assert decided == {"AC-2029": ("classified", "704"), "AC-2030": ("review", None), "AC-2031": ("classified", "704")}
    assert all(each["is_new"] for each in issued)
    lines = {each["invoice_number"]: each["line_accounts"] for each in issued}
    assert [(entry["cont"], entry["method"]) for entry in lines["AC-2031"]] == [("704", "rules"), ("707", "jev")]
    assert [entry["cont"] for entry in lines["AC-2030"]] == ["704", None]  # Jev is unsure of the bricks


def test_the_demo_has_lines_with_descriptions_decided_by_a_rule_with_stars_on_both_sides(cfg):
    desk = demo.service(cfg)
    listed = {each["invoice_number"]: each for each in desk.invoices(cui=CLIENT)["invoices"]}

    toner = listed["BE-0503"]
    lines = desk.invoice_view(toner["id"])["document"]["lines"]
    assert lines[0]["details"].startswith("Cartuș toner compatibil")
    first = toner["line_accounts"][0]
    assert (first["cont"], first["rule"], first["match"]["found"], first["match"]["in_details"]) == ("302", "consumabile", "*cartus*", True)
    assert toner["line_accounts"][2]["cont"] is None  # Jev is unsure of the coffee
    assert {row["source"] for row in desk.decision_history(toner["id"])["decisions"]} == {"download"}


def test_the_demo_has_an_invoice_with_one_account_and_several_lines_to_split(cfg):
    desk = demo.service(cfg)
    listed = {each["invoice_number"]: each for each in desk.invoices(cui="14399840")["invoices"]}

    whole = listed["BE-0511"]
    assert (whole["cont"], whole["line_accounts"]) == ("302", None)
    split = desk.split_into_lines(whole["id"])["invoice"]
    assert [entry["method"] for entry in split["line_accounts"]] == ["rules", "invoice"]


def test_the_demo_has_invoices_that_ask_for_another_sum_than_they_are_worth(cfg):
    desk = demo.service(cfg)
    listed = {each["invoice_number"]: each for each in desk.invoices(cui="18547290")["invoices"]}

    water, power = listed["CO 1879"], listed["EN 4410"]
    assert (water["total_with_vat"], water["total_payable"]) == ("345.40", "657.80")  # an earlier balance added
    assert (power["total_with_vat"], power["total_payable"]) == ("1190.00", "990.00")  # an advance taken off
    assert desk.invoice_view(water["id"])["document"]["total_prepaid"] == "-312.40"
    assert desk.invoice_view(power["id"])["document"]["total_prepaid"] == "200.00"


def test_every_second_download_also_brings_an_invoice_the_client_issued(cfg):
    first = demo.service(cfg).sync(CLIENT)
    second = demo.service(cfg).sync(CLIENT)

    assert (first["issued_count"], second["issued_count"]) == (0, 1)
    (issued,) = [each for each in second["new"] if each["message_type"] == "FACTURA TRIMISA"]
    assert (issued["supplier_name"], issued["supplier_cui"]) == ("Alfa Construct SRL", CLIENT)
    assert issued["customer_name"] and issued["customer_cui"] != CLIENT


RIDES = "44175209"  # Drum Bun Ride SRL


def test_the_demo_has_a_ride_sharing_client_whose_discounts_get_their_own_account(cfg):
    desk = demo.service(cfg)
    rides = {each["invoice_number"]: each for each in desk.invoices(cui=RIDES, message_type="trimisa")["invoices"]}

    # A fare and a "Reducere" on the whole invoice: Jev is sure of both.
    sure = desk.invoice_view(rides["DB-5848"]["id"])
    assert [(entry["line"], entry["cont"], entry["method"]) for entry in sure["invoice"]["line_accounts"]] == [
        (1, "704", "jev"), (2, "729", "jev"),
    ]
    (fare,), (discount,) = sure["document"]["lines"], sure["document"]["adjustments"]
    assert (fare["description"], fare["unit_name"], fare["value"]) == ("Tarif de călătorie", "SERV", "16.10")
    assert (discount["number"], discount["description"], discount["value"]) == (2, "Reducere", "-4.30")
    assert sure["document"]["customer"]["name"] == "Ana Popescu"
    # A "Cod promoțional" Jev is unsure of: the invoice waits for a person, with Jev's proposal.
    unsure = rides["DB-5849"]
    assert unsure["classification_status"] == "review"
    assert [(entry["cont"], entry["suggested_cont"]) for entry in unsure["line_accounts"]] == [("704", "704"), (None, "729")]
    # A ride without a discount is one line and one account, as before.
    assert (rides["DB-5850"]["cont"], rides["DB-5850"]["line_accounts"]) == ("704", None)
    assert "729" in desk.rules_overview()["issued_accounts"]


def test_the_demo_has_rides_with_more_lines_and_with_several_discounts(cfg):
    desk = demo.service(cfg)
    rides = {each["invoice_number"]: each for each in desk.invoices(cui=RIDES, message_type="trimisa")["invoices"]}

    def rows(number):
        """Each row of the invoice, its lines then its discounts: its name and its account."""
        view = desk.invoice_view(rides[number]["id"])
        names = [row["description"] for row in view["document"]["lines"] + view["document"]["adjustments"]]
        return list(zip(names, [(entry["cont"], entry["method"]) for entry in view["invoice"]["line_accounts"]]))

    # Three lines on two accounts, and one discount on the whole invoice.
    assert rows("DB-5851") == [
        ("Tarif de călătorie", ("704", "jev")), ("Timp de așteptare", ("704", "jev")),
        ("Taxă de aeroport", ("708", "jev")), ("Reducere", ("729", "jev")),
    ]
    # Two discounts with different names: each is its own row and its own question.
    assert rows("DB-5852") == [
        ("Tarif de călătorie", ("704", "jev")), ("Reducere", ("729", "jev")), ("Reducere fidelitate", ("729", "jev")),
    ]
    # Two lines, the same discount twice and one Jev is unsure of: three discounts, one left to a person.
    assert rows("DB-5853") == [
        ("Tarif de călătorie", ("704", "jev")), ("Timp de așteptare", ("704", "jev")),
        ("Reducere", ("729", "jev")), ("Reducere", ("729", "jev")), ("Cod promoțional", (None, None)),
    ]
    assert [rides[number]["classification_status"] for number in ("DB-5851", "DB-5852", "DB-5853")] == [
        "classified", "classified", "review",
    ]
    # The discount written twice is one question to Jev: four questions for five rows.
    store = Store(cfg.db_path)
    try:
        asked = [call for call in store.jev_calls() if call["message_id"] == rides["DB-5853"]["id"]]
    finally:
        store.close()
    assert len(asked) == 4


def test_every_second_download_brings_the_ride_sharing_client_a_ride_with_a_discount(cfg):
    demo.service(cfg).sync(RIDES)
    second = demo.service(cfg).sync(RIDES)

    (ride,) = [each for each in second["new"] if each["message_type"] == "FACTURA TRIMISA"]
    assert (ride["supplier_name"], ride["classification_status"]) == ("Drum Bun Ride SRL", "classified")
    assert [(entry["line"], entry["cont"]) for entry in ride["line_accounts"]] == [(1, "704"), (2, "729")]
    document = demo.service(cfg).invoice_view(ride["id"])["document"]
    assert [row["description"] for row in document["lines"] + document["adjustments"]] == ["Tarif de călătorie", "Reducere"]


def test_the_demo_archive_holds_last_weeks_confirmed_imports(cfg):
    desk = demo.service(cfg)

    imports = {cui: desk.saga_archive(cui)["imports"] for cui in demo.EARLIER}
    first, *others = demo.EARLIER

    assert all(len(entries) == 1 for entries in imports.values())
    assert imports[first][0]["source"] == "api" and all(imports[cui][0]["source"] == "screen" for cui in others)
    for cui, (entry,) in imports.items():
        assert entry["invoices"] > 0 and all(file["present"] for file in entry["files"])
        # Today's invoices wait in a new file; last week's are all marked as imported.
        archived = {invoice["id"] for invoice in desk.saga_archive_entry(entry["id"])["import"]["invoices"]}
        waiting = {message_id for file in desk.saga_files(cui)["files"] for message_id in file["ids"]}
        assert archived and not archived & waiting


@pytest.fixture
def no_network(monkeypatch):
    """A request that would leave this computer fails the test instead of being sent."""
    def refuse(self, request):
        raise AssertionError(f"the real network was reached: {request.url}")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)


def test_any_service_on_demo_settings_talks_to_the_stand_ins_by_itself(cfg, no_network):
    desk = Service(cfg)  # no client given, as any new caller would write it

    assert desk._http.get("https://example.com/").status_code == 404
    assert desk.sync(CLIENT)["received_count"] == 1
    assert demo.service(cfg).sync(CLIENT)["received_count"] == 2  # the old way still works


def test_demo_never_reaches_past_its_three_hosts(cfg):
    with demo.client(cfg) as http:
        assert http.get("https://example.com/").status_code == 404
        assert http.post("https://api.openai.com/v1/chat").status_code == 404


def test_the_demo_login_takes_a_demo_code_and_nothing_else(cfg):
    assert demo.service(cfg).login_finish("https://localhost/callback?code=demo-7")["state"] == "valid"
    with pytest.raises(EfacturaError):
        demo.service(cfg).login_finish("https://localhost/callback?code=abc")


def test_jev_in_the_demo_answers_whatever_key_is_set(cfg):
    demo.service(cfg).sync(CLIENT)  # the new invoices go through the rules and then to the stand-in Jev

    waiting = [each for each in demo.service(cfg).invoices(cui=CLIENT)["invoices"] if each["classification_status"] == "pending"]
    assert waiting == []  # none was left unanswered for want of a real key


def test_the_demo_app_uses_the_stand_ins_and_says_it_is_a_demo(cfg):
    api = TestClient(create_app(cfg))

    assert api.get("/settings", headers=KEY).json()["demo"] is True
    assert api.post("/auth/login/start", headers=KEY).json()["authorize_url"] == "/api/demo/anaf-login"
    sent = api.get("/api/demo/anaf-login", follow_redirects=False)  # no key: the browser opens it in a new tab
    assert sent.status_code == 307 and sent.headers["location"].startswith("https://localhost/callback?code=demo-")
    assert api.post("/sync", headers=KEY, json={"cui": CLIENT}).json()["new_count"] == 1


def test_an_ordinary_app_has_no_demo_address(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(f'[api]\nkey = "k"\n[anaf]\ntoken_file = \'{tmp_path / "tokens.json"}\'\n', encoding="utf-8")
    api = TestClient(create_app(load_config(path)))

    assert api.get("/settings", headers={"X-API-Key": "k"}).json()["demo"] is False
    assert api.get("/api/demo/anaf-login", headers={"X-API-Key": "k"}).status_code == 404


def test_two_words_make_the_demo_jev_decline_or_fail(cfg):
    from efactura import jev

    def asked(word):
        with demo.client(cfg) as http:
            request = {"model": "m", "state": {"linii": [{"descriere": f"Servicii {word}"}]}, "questions": {}}
            return jev.ask(http, "any key", request)

    assert asked("nimic").response["answers"]["cont"]["type"] == "refusal"
    assert asked("eroare").ok is False
