import json

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


def test_list_prints_next_cursor_when_not_interactive(configured, api):
    api.get("/workitems/mine").respond(
        json={"workitems": [workitem("TF-2")], "pagination": {"hasMore": True, "nextCursor": "t:id"}}
    )
    result = runner.invoke(app, ["list", "-n", "1"])
    assert result.exit_code == 0, result.output
    assert "TF-2" in result.output
    assert "--cursor 't:id'" in result.output


def test_list_json(configured, api):
    api.get("/workitems/mine").respond(json={"workitems": [workitem("TF-2")], "pagination": {"hasMore": False}})
    result = runner.invoke(app, ["list", "--json"])
    data = json.loads(result.output)
    assert data["workitems"][0]["ref"] == "TF-2"
    assert data["pagination"] == {"hasMore": False, "nextCursor": None}


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
