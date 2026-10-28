"""Saved configuration with environment-variable overrides.

Precedence: environment variables > config file > defaults.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from .errors import ConfigError

DEFAULT_BASE_URL = "https://integrations-assignment-ticketforge.vercel.app"

ENV_BASE_URL = "TFORGE_BASE_URL"
ENV_USERNAME = "TFORGE_USERNAME"
ENV_PASSWORD = "TFORGE_PASSWORD"
ENV_CONFIG_PATH = "TFORGE_CONFIG"


@dataclass
class Config:
    base_url: str = DEFAULT_BASE_URL
    username: str | None = None
    password: str | None = None

    @property
    def is_complete(self) -> bool:
        return bool(self.base_url and self.username and self.password)


def config_path() -> Path:
    if override := os.environ.get(ENV_CONFIG_PATH):
        return Path(override).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "ticketforge" / "config.json"


def load_config(path: Path | None = None) -> Config:
    path = path or config_path()
    cfg = Config()
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"could not read config file {path}: {exc}") from exc
        cfg = Config(
            base_url=data.get("base_url") or DEFAULT_BASE_URL,
            username=data.get("username"),
            password=data.get("password"),
        )

    cfg.base_url = os.environ.get(ENV_BASE_URL) or cfg.base_url
    cfg.username = os.environ.get(ENV_USERNAME) or cfg.username
    cfg.password = os.environ.get(ENV_PASSWORD) or cfg.password
    return cfg


def save_config(cfg: Config, path: Path | None = None) -> Path:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Create the file with 0600 from the start so the password is never world-readable.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(asdict(cfg), fh, indent=2)
    os.chmod(path, 0o600)
    return path
