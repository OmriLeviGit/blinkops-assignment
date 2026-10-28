import os

# rich reads these when `views.console` is created at import time, before any fixture runs.
for _var in ("FORCE_COLOR", "NO_COLOR", "TTY_COMPATIBLE"):
    os.environ.pop(_var, None)
os.environ["COLUMNS"] = "200"

import pytest
import respx

from ticketforge_cli.client import TicketForgeClient

BASE = "https://tf.test"
API = BASE + "/api/tforge"


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    """Keep the caller's TicketForge settings (env vars and ./.env) out of the tests."""
    for var in ("TFORGE_BASE_URL", "TFORGE_USERNAME", "TFORGE_PASSWORD", "TFORGE_CONFIG"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def sleeps():
    return []


@pytest.fixture
def client(sleeps):
    c = TicketForgeClient(BASE, "alice", "pw", sleep=sleeps.append)
    yield c
    c.close()


@pytest.fixture
def api():
    with respx.mock(base_url=API, assert_all_called=False) as mock:
        yield mock


def workitem(ref="TF-1", **overrides):
    data = {
        "ref": ref,
        "title": f"Ticket {ref}",
        "description": None,
        "stage": "open",
        "created": "2026-10-28T12:00:00.000Z",
        "updated": "2026-10-28T12:00:00.000Z",
    }
    data.update(overrides)
    return data
