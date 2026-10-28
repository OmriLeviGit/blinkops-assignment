import pytest
import respx

from ticketforge_cli.client import TicketForgeClient

BASE = "https://tf.test"
API = BASE + "/api/tforge"


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
