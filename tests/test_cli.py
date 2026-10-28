import json

import httpx

import pytest
from typer.testing import CliRunner

from ticketforge_cli.cli import app

from .conftest import BASE, workitem

runner = CliRunner()


@pytest.fixture
def configured(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"base_url": BASE, "username": "alice", "password": "pw"}))
    monkeypatch.setenv("TFORGE_CONFIG", str(path))
    for var in ("TFORGE_BASE_URL", "TFORGE_USERNAME", "TFORGE_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    return path


def test_unconfigured_cli_points_to_setup(tmp_path, monkeypatch):
    monkeypatch.setenv("TFORGE_CONFIG", str(tmp_path / "none.json"))
    for var in ("TFORGE_USERNAME", "TFORGE_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 2
    assert "tforge setup" in result.output


def test_setup_verifies_and_saves(tmp_path, monkeypatch, api):
    path = tmp_path / "cfg.json"
    monkeypatch.setenv("TFORGE_CONFIG", str(path))
    api.get("/workitems/mine").respond(json={"workitems": [], "pagination": {}})
    result = runner.invoke(app, ["setup", "-u", "alice", "-p", "pw", "--base-url", BASE])
    assert result.exit_code == 0, result.output
    assert json.loads(path.read_text())["username"] == "alice"


def test_setup_rejects_bad_credentials_without_saving(tmp_path, monkeypatch, api):
    path = tmp_path / "cfg.json"
    monkeypatch.setenv("TFORGE_CONFIG", str(path))
    api.get("/workitems/mine").respond(401, json={"err": "unauthorized", "message": "valid basic auth required"})
    result = runner.invoke(app, ["setup", "-u", "alice", "-p", "bad", "--base-url", BASE])
    assert result.exit_code == 2
    assert not path.exists()


def test_list_footer_suggests_next_page(configured, api):
    api.get("/workitems/mine").respond(
        json={"workitems": [workitem("TF-3"), workitem("TF-2")], "pagination": {"hasMore": True, "nextCursor": "c"}}
    )
    result = runner.invoke(app, ["list", "--limit", "2"])
    assert result.exit_code == 0, result.output
    assert "TF-3" in result.output
    assert "Page 1 · tickets 1–2 · next: tforge list --page 2 --limit 2" in result.output


def test_list_json(configured, api):
    api.get("/workitems/mine").respond(json={"workitems": [workitem("TF-2")], "pagination": {"hasMore": False}})
    result = runner.invoke(app, ["list", "--json"])
    data = json.loads(result.output)
    assert data["workitems"][0]["ref"] == "TF-2"
    assert data["pagination"] == {"page": 1, "limit": 10, "hasMore": False}


def test_interactive_rejects_all(configured):
    result = runner.invoke(app, ["list", "-i", "--all"])
    assert result.exit_code != 0


def test_browse_lazy_navigation(monkeypatch, client, api):
    from ticketforge_cli import cli, views
    from ticketforge_cli.services import TicketService

    data = [workitem(f"TF-{i}") for i in range(7, 0, -1)]

    def handler(request):
        start = int(request.url.params.get("cursor", 0))
        chunk = data[start : start + 5]
        more = start + 5 < len(data)
        return httpx.Response(
            200, json={"workitems": chunk, "pagination": {"hasMore": more, **({"nextCursor": "5"} if more else {})}}
        )

    route = api.get("/workitems/mine").mock(side_effect=handler)
    screens = []
    monkeypatch.setattr(views.console, "clear", lambda: None)
    monkeypatch.setattr(views, "ticket_table", lambda items, title=None: [w.ref for w in items])
    monkeypatch.setattr(views.console, "print", lambda *a, **k: screens.append(a[0] if a else ""))

    calls_after = []
    keys = iter(["n", "n", "n", "p", "p", "q"])

    def read_key():
        calls_after.append(route.call_count)
        return next(keys)

    cli.browse(TicketService(client).pager(), limit=3, read_key=read_key)

    tables = [x for x in screens if isinstance(x, list)]
    prompts = [x for x in screens if isinstance(x, str) and x.startswith("Page")]
    assert tables == [
        ["TF-7", "TF-6", "TF-5"],
        ["TF-4", "TF-3", "TF-2"],
        ["TF-1"],
        ["TF-1"],                  # n on the last page does nothing
        ["TF-4", "TF-3", "TF-2"],
        ["TF-7", "TF-6", "TF-5"],
    ]
    assert prompts[0].startswith("Page 1 · 5 loaded") and "\\[n]" in prompts[0]
    assert prompts[2].startswith("Page 3/3 · 7 tickets") and "\\[n]" not in prompts[2]
    assert calls_after == [1, 2, 2, 2, 2, 2]  # going back never fetches


def test_browse_empty(monkeypatch, client, api):
    from ticketforge_cli import cli, views
    from ticketforge_cli.services import TicketService

    api.get("/workitems/mine").respond(json={"workitems": [], "pagination": {"hasMore": False}})
    out = []
    monkeypatch.setattr(views.console, "print", lambda *a, **k: out.append(a[0] if a else ""))
    cli.browse(TicketService(client).pager(), limit=3, read_key=lambda: "q")
    assert out == ["No tickets found."]


def test_api_error_exits_nonzero(configured, api):
    api.get("/workitem/TF-1").respond(400, json={"err": "not_found", "message": "workitem TF-1 does not exist"})
    result = runner.invoke(app, ["show", "1"])
    assert result.exit_code == 1
    assert "workitem TF-1 does not exist" in result.output


def test_create_with_stage_creates_then_updates(configured, api):
    api.post("/workitem/publish").respond(json={"workitem": workitem("TF-3")})
    api.get("/workitem/TF-3").respond(json={"workitem": workitem("TF-3")})
    put = api.put("/workitem/TF-3").respond(json={"workitem": workitem("TF-3", stage="review")})
    result = runner.invoke(app, ["create", "Hello", "--stage", "review"])
    assert result.exit_code == 0, result.output
    assert json.loads(put.calls.last.request.content)["stage"] == "review"
