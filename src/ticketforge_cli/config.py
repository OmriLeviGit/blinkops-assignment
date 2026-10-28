"""Saved configuration with environment-variable overrides.

Precedence: environment variables > config file > defaults.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from .errors import ConfigError, ValidationError

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
    # Settings overridden by an environment variable ("environment"); not saved.
    sources: dict[str, str] = field(default_factory=dict, compare=False)

    @property
    def is_complete(self) -> bool:
        return bool(self.base_url and self.username and self.password)


def config_path() -> Path:
    if override := os.environ.get(ENV_CONFIG_PATH):
        return Path(override).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "ticketforge" / "config.json"


def validate_base_url(url: str) -> str:
    """Return `url` without a trailing slash, or raise if it isn't an http(s) URL."""
    try:
        parsed: httpx.URL | None = httpx.URL(url)
    except httpx.InvalidURL:
        parsed = None
    if parsed is None or parsed.scheme not in ("http", "https") or not parsed.host:
        raise ValidationError(f"invalid URL '{url}', expected http:// or https://")
    return url.rstrip("/")


def load_config(path: Path | None = None) -> Config:
    path = path or config_path()
    cfg = Config()
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"could not read config file {path}: {exc}") from exc
        if not isinstance(data, dict) or not all(
            isinstance(data.get(k), (str, type(None))) for k in ("base_url", "username", "password")
        ):
            raise ConfigError(f"config file {path} is malformed; run `tforge setup` to rewrite it")
        cfg = Config(
            base_url=data.get("base_url") or DEFAULT_BASE_URL,
            username=data.get("username"),
            password=data.get("password"),
        )

    for attr, var in (
        ("base_url", ENV_BASE_URL),
        ("username", ENV_USERNAME),
        ("password", ENV_PASSWORD),
    ):
        if value := os.environ.get(var):
            cfg.sources[attr] = "environment"
            setattr(cfg, attr, value)
    try:
        cfg.base_url = validate_base_url(cfg.base_url)
    except ValidationError as exc:
        where = cfg.sources.get("base_url", f"config file {path}")
        raise ConfigError(f"{exc.message} (from {where})") from None
    return cfg


def save_config(cfg: Config, path: Path | None = None) -> Path:
    path = path or config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write a temp file and rename it over the config, so an interrupted save (Ctrl-C, full
    # disk) leaves the old config intact. mkstemp creates it 0600: the password is never
    # world-readable.
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(
                {"base_url": cfg.base_url, "username": cfg.username, "password": cfg.password},
                fh,
                indent=2,
            )
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path
