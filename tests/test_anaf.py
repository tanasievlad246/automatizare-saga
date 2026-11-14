from datetime import datetime, timedelta, timezone

import httpx
import pytest

from efactura.anaf import AnafService, normalize_cui, parse_created_at, type_slug
from efactura.config import load_config
from efactura.errors import EfacturaError

from helpers import VALID_CUI, FakeAnaf

END = datetime(2026, 11, 11, 9, 0, tzinfo=timezone(timedelta(hours=2)))
START = END - timedelta(days=7)


@pytest.fixture
def cfg(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("", encoding="utf-8")
    return load_config(path)


@pytest.fixture
def anaf():
    return FakeAnaf()


def anaf_service_for(cfg, anaf, tokens=("access-1",)):
    """An AnafService whose token source hands out `tokens` in order, recording forced renewals."""
    forced = []
    supply = list(tokens)

    def get_token(force_refresh: bool) -> str:
        forced.append(force_refresh)
        if force_refresh and len(supply) > 1:
            supply.pop(0)
        return supply[0]

    return AnafService(cfg, anaf.client(), get_token), forced


# --- CUI ---------------------------------------------------------------------


@pytest.mark.parametrize("given", ["12345674", "RO12345674", " ro 12345674 ", "RO 1234 5674"])
def test_cui_is_reduced_to_digits(given):
    assert normalize_cui(given) == "12345674"


@pytest.mark.parametrize("given", ["", "RO", "ABC", "1234567x", "12345678901"])
def test_malformed_cui_is_rejected(given):
    with pytest.raises(EfacturaError) as info:
        normalize_cui(given)

    assert info.value.code == "invalid_cui"


def test_cui_with_a_wrong_check_digit_is_rejected():
    with pytest.raises(EfacturaError) as info:
        normalize_cui("12345678")

    assert info.value.code == "invalid_cui"
    assert "check digit" in info.value.message


def test_personal_code_with_a_valid_check_digit_is_accepted():
    assert normalize_cui("1860101123451") == "1860101123451"


def test_personal_code_with_a_wrong_check_digit_is_rejected():
    with pytest.raises(EfacturaError) as info:
        normalize_cui("1860101123459")

    assert info.value.code == "invalid_cui"


# --- small conversions -------------------------------------------------------


@pytest.mark.parametrize(
    "tip, slug",
    [
        ("FACTURA PRIMITA", "primita"),
        ("FACTURA TRIMISA", "trimisa"),
        ("ERORI FACTURA", "erori"),
        ("MESAJ CUMPARATOR PRIMIT / MESAJ CUMPARATOR TRANSMIS", "mesaj"),
        ("SOMETHING NEW", "alt"),
    ],
)
def test_message_type_maps_to_a_file_name_part(tip, slug):
    assert type_slug(tip) == slug


def test_anaf_timestamp_becomes_iso():
    assert parse_created_at("202211011336") == "2022-11-01T13:36"


def test_unexpected_timestamp_is_none():
    assert parse_created_at("yesterday") is None


# --- listing -----------------------------------------------------------------


def test_list_asks_for_the_company_and_window_with_the_token(cfg, anaf):
    anaf.add("3001")
    anaf_service, _ = anaf_service_for(cfg, anaf)

    anaf_service.list_messages(VALID_CUI, START, END)

    (params,) = anaf.list_requests
    assert params == {
        "startTime": str(int(START.timestamp() * 1000)),
        "endTime": str(int(END.timestamp() * 1000)),
        "cif": VALID_CUI,
        "pagina": "1",
    }


def test_list_returns_anafs_entries(cfg, anaf):
    anaf.add("3001", tip="FACTURA PRIMITA")
    anaf.add("3002", tip="ERORI FACTURA")
    anaf_service, _ = anaf_service_for(cfg, anaf)

    entries = anaf_service.list_messages(VALID_CUI, START, END)

    assert [(e["id"], e["tip"]) for e in entries] == [
        ("3001", "FACTURA PRIMITA"),
        ("3002", "ERORI FACTURA"),
    ]


def test_list_follows_every_page(cfg, anaf):
    for n in range(5):
        anaf.add(f"30{n}")
    anaf.page_size = 2
    anaf_service, _ = anaf_service_for(cfg, anaf)

    entries = anaf_service.list_messages(VALID_CUI, START, END)

    assert [e["id"] for e in entries] == ["300", "301", "302", "303", "304"]
    assert [p["pagina"] for p in anaf.list_requests] == ["1", "2", "3"]


def test_an_id_repeated_across_pages_is_listed_once(cfg, anaf):
    anaf.add("3001")
    anaf.add("3001")
    anaf_service, _ = anaf_service_for(cfg, anaf)

    assert [e["id"] for e in anaf_service.list_messages(VALID_CUI, START, END)] == ["3001"]


def test_no_messages_is_an_empty_list_not_a_failure(cfg, anaf):
    anaf_service, _ = anaf_service_for(cfg, anaf)

    assert anaf_service.list_messages(VALID_CUI, START, END) == []


def test_no_spv_rights_is_reported_as_such(cfg, anaf):
    anaf.list_error = f"Nu aveti drept in SPV pentru CIF={VALID_CUI}"
    anaf_service, _ = anaf_service_for(cfg, anaf)

    with pytest.raises(EfacturaError) as info:
        anaf_service.list_messages(VALID_CUI, START, END)

    assert info.value.code == "no_spv_rights"


def test_daily_limit_is_reported_as_such(cfg, anaf):
    anaf.list_error = "S-au facut deja 100000 interogari de lista mesaje de catre utilizator in cursul zilei"
    anaf_service, _ = anaf_service_for(cfg, anaf)

    with pytest.raises(EfacturaError) as info:
        anaf_service.list_messages(VALID_CUI, START, END)

    assert info.value.code == "anaf_limit_reached"


def test_any_other_anaf_refusal_carries_anafs_text(cfg, anaf):
    anaf.list_error = "startTime = 2020 nu poate fi mai vechi de 60 de zile"
    anaf_service, _ = anaf_service_for(cfg, anaf)

    with pytest.raises(EfacturaError) as info:
        anaf_service.list_messages(VALID_CUI, START, END)

    assert info.value.code == "anaf_error"
    assert "60 de zile" in info.value.message


def test_rejected_token_is_renewed_once_and_the_call_repeated(cfg, anaf):
    anaf.add("3001")
    anaf.valid_access = {"access-2"}
    anaf_service, forced = anaf_service_for(cfg, anaf, tokens=("stale", "access-2"))

    entries = anaf_service.list_messages(VALID_CUI, START, END)

    assert [e["id"] for e in entries] == ["3001"]
    assert forced == [False, True]


def test_token_still_rejected_after_renewal_means_login_needed(cfg, anaf):
    anaf.valid_access = set()
    anaf_service, _ = anaf_service_for(cfg, anaf, tokens=("stale", "also-stale"))

    with pytest.raises(EfacturaError) as info:
        anaf_service.list_messages(VALID_CUI, START, END)

    assert info.value.code == "login_needed"


def test_anaf_server_failure_is_an_anaf_error(cfg):
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503, text="down")))
    anaf_service = AnafService(cfg, http, lambda force: "access-1")

    with pytest.raises(EfacturaError) as info:
        anaf_service.list_messages(VALID_CUI, START, END)

    assert info.value.code == "anaf_error"


def test_unreachable_anaf_is_a_network_error(cfg):
    def refuse(request):
        raise httpx.ConnectTimeout("timed out", request=request)

    anaf_service = AnafService(cfg, httpx.Client(transport=httpx.MockTransport(refuse)), lambda f: "t")

    with pytest.raises(EfacturaError) as info:
        anaf_service.list_messages(VALID_CUI, START, END)

    assert info.value.code == "network_error"


def test_reply_that_is_not_json_is_an_anaf_error(cfg):
    http = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text="<html>maintenance</html>"))
    )
    anaf_service = AnafService(cfg, http, lambda force: "access-1")

    with pytest.raises(EfacturaError) as info:
        anaf_service.list_messages(VALID_CUI, START, END)

    assert info.value.code == "anaf_error"


# --- download ----------------------------------------------------------------


def test_download_returns_the_zip(cfg, anaf):
    anaf.add("3001")
    anaf_service, _ = anaf_service_for(cfg, anaf)

    assert anaf_service.download("3001") == anaf.zips["3001"]
    assert anaf.downloads == ["3001"]


def test_download_refusal_arrives_as_json_and_becomes_an_error(cfg, anaf):
    anaf_service, _ = anaf_service_for(cfg, anaf)

    with pytest.raises(EfacturaError) as info:
        anaf_service.download("21")

    assert info.value.code == "anaf_error"
    assert "id=21" in info.value.message


def test_download_limit_is_reported_as_such(cfg, anaf):
    anaf.download_errors["3001"] = "S-au facut deja 10 descarcari de mesaj in cursul zilei"
    anaf_service, _ = anaf_service_for(cfg, anaf)

    with pytest.raises(EfacturaError) as info:
        anaf_service.download("3001")

    assert info.value.code == "anaf_limit_reached"


def test_download_without_rights_is_reported_as_such(cfg, anaf):
    anaf.download_errors["3001"] = "Nu aveti dreptul sa descarcati acesta factura"
    anaf_service, _ = anaf_service_for(cfg, anaf)

    with pytest.raises(EfacturaError) as info:
        anaf_service.download("3001")

    assert info.value.code == "no_spv_rights"


def test_download_that_is_neither_zip_nor_json_is_an_anaf_error(cfg):
    http = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"\x00\x01garbage"))
    )
    anaf_service = AnafService(cfg, http, lambda force: "access-1")

    with pytest.raises(EfacturaError) as info:
        anaf_service.download("3001")

    assert info.value.code == "anaf_error"
