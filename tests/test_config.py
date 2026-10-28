import json
import stat

import pytest

from ticketforge_cli.config import DEFAULT_BASE_URL, Config, load_config, save_config
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
