import json
import stat

import pytest

from ticketforge_cli.config import DEFAULT_BASE_URL, Config, config_path, load_config, save_config
from ticketforge_cli.errors import ConfigError


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ("TFORGE_BASE_URL", "TFORGE_USERNAME", "TFORGE_PASSWORD", "TFORGE_CONFIG"):
        monkeypatch.delenv(var, raising=False)


def test_defaults_when_no_file(tmp_path):
    cfg = load_config(tmp_path / "missing.json")
    assert cfg.base_url == DEFAULT_BASE_URL
    assert not cfg.is_complete


def test_save_and_load_roundtrip_with_private_permissions(tmp_path):
    path = tmp_path / "sub" / "config.json"
    save_config(Config(base_url="https://x", username="u", password="p"), path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    cfg = load_config(path)
    assert (cfg.base_url, cfg.username, cfg.password) == ("https://x", "u", "p")


def test_env_overrides_file(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"username": "file-user", "password": "file-pw"}))
    monkeypatch.setenv("TFORGE_USERNAME", "env-user")
    cfg = load_config(path)
    assert cfg.username == "env-user"
    assert cfg.password == "file-pw"


def test_corrupt_file_raises_config_error(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not json")
    with pytest.raises(ConfigError):
        load_config(path)


def test_config_path_respects_xdg_config_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert config_path() == tmp_path / "ticketforge" / "config.json"


def test_config_path_override_expands_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("TFORGE_CONFIG", "~/tf.json")
    assert config_path() == tmp_path / "tf.json"


def test_empty_base_url_in_file_falls_back_to_default(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"base_url": "", "username": "u", "password": "p"}))
    assert load_config(path).base_url == DEFAULT_BASE_URL


def test_save_tightens_permissions_of_an_existing_file(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{}")
    path.chmod(0o644)
    save_config(Config(username="u", password="p"), path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
