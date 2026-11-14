import pytest

from efactura import demo, standins
from efactura.config import load_config
from efactura.errors import EfacturaError
from efactura.service import Service


def test_the_demo_is_built_with_settings_that_say_demo_and_a_filled_database(tmp_path):
    cfg = demo.build(tmp_path / "demo")

    assert cfg.demo is True and cfg.path == tmp_path / "demo" / "config.toml"
    assert cfg.api_port == 8770 and (cfg.data_dir / demo.MARKER).is_file()
    desk = Service(cfg, http=standins.FakeAnaf().client())
    assert len(desk.clients()["clients"]) == 3
    assert len(desk.invoices()["invoices"]) >= 5
    assert desk.rule_suggestions()["count"] >= 1
    assert desk.auth_status()["state"] == "valid"


def test_building_again_starts_from_nothing(tmp_path):
    cfg = demo.build(tmp_path / "demo")
    (cfg.data_dir / "left-over.txt").write_text("x")

    demo.build(tmp_path / "demo")

    assert not (cfg.data_dir / "left-over.txt").exists()


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
