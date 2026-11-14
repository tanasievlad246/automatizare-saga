from datetime import datetime
from pathlib import Path

import pytest

from efactura.config import load_config
from efactura.errors import EfacturaError


def write_config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(body, encoding="utf-8")
    return path


FULL = """
[anaf]
client_id = "abc"
client_secret = "shh"
redirect_uri = "https://localhost/callback"
environment = "prod"

[storage]
data_dir = "data"
folder_date_format = "DD-MM-YYYY"

[sync]
default_days = 7

[api]
key = "local-key"
port = 9001
"""


def test_reads_values_from_the_file(tmp_path):
    cfg = load_config(write_config(tmp_path, FULL))

    assert cfg.client_id == "abc"
    assert cfg.client_secret == "shh"
    assert cfg.redirect_uri == "https://localhost/callback"
    assert cfg.api_key == "local-key"
    assert cfg.api_port == 9001
    assert cfg.default_days == 7


def test_relative_data_dir_is_resolved_next_to_the_config_file(tmp_path):
    cfg = load_config(write_config(tmp_path, FULL))

    assert cfg.data_dir == tmp_path / "data"
    assert cfg.db_path == tmp_path / "data" / "efactura.db"
    assert cfg.invoices_dir == tmp_path / "data" / "invoices"


def test_missing_file_is_a_config_error(tmp_path):
    with pytest.raises(EfacturaError) as info:
        load_config(tmp_path / "nope.toml")

    assert info.value.code == "config_error"


def test_defaults_apply_when_sections_are_absent(tmp_path):
    cfg = load_config(write_config(tmp_path, ""))

    assert cfg.environment == "prod"
    assert cfg.redirect_uri == "https://localhost/callback"
    assert cfg.default_days == 7
    assert cfg.api_port == 8765
    assert cfg.api_base == "https://api.anaf.ro/prod/FCTEL/rest"


def test_test_environment_changes_the_api_base(tmp_path):
    cfg = load_config(write_config(tmp_path, '[anaf]\nenvironment = "test"\n'))

    assert cfg.api_base == "https://api.anaf.ro/test/FCTEL/rest"


def test_unknown_environment_is_rejected(tmp_path):
    with pytest.raises(EfacturaError) as info:
        load_config(write_config(tmp_path, '[anaf]\nenvironment = "staging"\n'))

    assert info.value.code == "config_error"


@pytest.mark.parametrize(
    "fmt, expected",
    [("DD-MM-YYYY", "11-11-2026"), ("YYYY-MM-DD", "2026-11-11"), ("DD.MM.YYYY", "11.11.2026")],
)
def test_folder_name_follows_the_configured_format(tmp_path, fmt, expected):
    cfg = load_config(write_config(tmp_path, f'[storage]\nfolder_date_format = "{fmt}"\n'))

    assert cfg.folder_name(datetime(2026, 11, 11, 9, 30)) == expected


def test_folder_format_that_could_escape_the_folder_is_rejected(tmp_path):
    with pytest.raises(EfacturaError) as info:
        load_config(write_config(tmp_path, '[storage]\nfolder_date_format = "../YYYY"\n'))

    assert info.value.code == "config_error"


def test_default_days_outside_anaf_range_is_rejected(tmp_path):
    with pytest.raises(EfacturaError) as info:
        load_config(write_config(tmp_path, "[sync]\ndefault_days = 90\n"))

    assert info.value.code == "config_error"


def test_saved_login_defaults_to_a_location_outside_the_data_folder(tmp_path):
    cfg = load_config(write_config(tmp_path, FULL))

    assert cfg.token_file.name == "tokens.json"
    assert tmp_path not in cfg.token_file.parents


def test_token_file_can_be_set_explicitly(tmp_path):
    target = tmp_path / "private" / "tokens.json"
    cfg = load_config(write_config(tmp_path, f"[anaf]\ntoken_file = '{target}'\n"))

    assert cfg.token_file == target


def test_relative_token_file_is_resolved_next_to_the_config_file(tmp_path, monkeypatch):
    settings_folder = tmp_path / "settings"
    settings_folder.mkdir()
    started_from = tmp_path / "elsewhere"
    started_from.mkdir()
    monkeypatch.chdir(started_from)

    cfg = load_config(write_config(settings_folder, '[anaf]\ntoken_file = "private/tokens.json"\n'))

    assert cfg.token_file == settings_folder / "private" / "tokens.json"


def test_require_oauth_names_the_missing_setting(tmp_path):
    cfg = load_config(write_config(tmp_path, '[anaf]\nclient_id = "abc"\n'))

    with pytest.raises(EfacturaError) as info:
        cfg.require_oauth()

    assert info.value.code == "config_error"
    assert "client_secret" in info.value.message


def test_require_api_key_rejects_an_empty_key(tmp_path):
    cfg = load_config(write_config(tmp_path, ""))

    with pytest.raises(EfacturaError) as info:
        cfg.require_api_key()

    assert info.value.code == "config_error"


def test_error_serialises_to_the_failure_shape():
    err = EfacturaError("login_needed", "Plug in the token and log in.")

    assert err.to_dict() == {
        "ok": False,
        "error": {"code": "login_needed", "message": "Plug in the token and log in."},
    }


def test_settings_file_saved_by_notepad_with_a_byte_order_mark_is_read(tmp_path):
    path = tmp_path / "config.toml"
    path.write_bytes(b"\xef\xbb\xbf" + FULL.encode("utf-8"))

    assert load_config(path).client_id == "abc"


# --- classification settings ---------------------------------------------------------


def test_openrouter_settings_are_read(tmp_path):
    cfg = load_config(write_config(
        tmp_path, '[openrouter]\napi_key = " or-key "\nmodel = "typesafe/jev-1.13"\n'
    ))

    assert (cfg.openrouter_api_key, cfg.jev_model) == ("or-key", "typesafe/jev-1.13")


def test_without_an_openrouter_section_there_is_no_key_and_the_model_is_pinned(tmp_path):
    cfg = load_config(write_config(tmp_path, ""))

    assert cfg.openrouter_api_key == ""
    assert cfg.jev_model == "typesafe/jev-1.14"


def test_saga_files_go_to_a_folder_named_saga_import_inside_the_data_folder(tmp_path):
    cfg = load_config(write_config(tmp_path, FULL))

    assert cfg.saga_dir == tmp_path / "data" / "SAGA Import"


def test_saga_folder_can_be_moved(tmp_path):
    elsewhere = tmp_path / "pentru saga"
    cfg = load_config(write_config(tmp_path, f"[saga]\nimport_dir = '{elsewhere}'\n"))
    relative = load_config(write_config(tmp_path, '[saga]\nimport_dir = "saga"\n'))

    assert cfg.saga_dir == elsewhere
    assert relative.saga_dir == tmp_path / "saga"
