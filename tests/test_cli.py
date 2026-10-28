import json

import httpx
import pytest
from typer.testing import CliRunner

from ticketforge_cli import __version__
from ticketforge_cli.cli import app
from ticketforge_cli.client import TicketForgeClient

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


@pytest.mark.parametrize("flag", ["--version", "-V"])
def test_version(flag):
    result = runner.invoke(app, [flag])
    assert result.exit_code == 0
    assert result.output.strip() == f"tforge {__version__}"


def test_unconfigured_cli_points_to_setup(tmp_path, monkeypatch):
    monkeypatch.setenv("TFORGE_CONFIG", str(tmp_path / "none.json"))
    for var in ("TFORGE_USERNAME", "TFORGE_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 2
    assert "tforge setup" in result.output
    assert "TFORGE_USERNAME" in result.output


def test_status_shows_credentials_from_env(tmp_path, monkeypatch, api):
    monkeypatch.setenv("TFORGE_CONFIG", str(tmp_path / "none.json"))
    monkeypatch.setenv("TFORGE_USERNAME", "alice")
    monkeypatch.setenv("TFORGE_PASSWORD", "pw")
    monkeypatch.setenv("TFORGE_BASE_URL", BASE)
    api.get("/workitems/mine").respond(json={"workitems": [], "pagination": {}})
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    assert "alice (from environment)" in result.output
    assert "Credentials OK" in result.output


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
    api.get("/workitems/mine").respond(
        401, json={"err": "unauthorized", "message": "valid basic auth required"}
    )
    result = runner.invoke(app, ["setup", "-u", "alice", "-p", "bad", "--base-url", BASE])
    assert result.exit_code == 2
    assert not path.exists()


def test_setup_refuses_a_url_that_is_not_ticketforge(tmp_path, monkeypatch, api):
    path = tmp_path / "cfg.json"
    monkeypatch.setenv("TFORGE_CONFIG", str(path))
    api.get("/workitems/mine").respond(200, text="<html>some web app</html>")
    result = runner.invoke(app, ["setup", "-u", "alice", "-p", "pw", "--base-url", BASE])
    assert result.exit_code == 1
    assert "unexpected response" in result.output
    assert not path.exists()


def test_list_footer_suggests_next_page(configured, api):
    api.get("/workitems/mine").respond(
        json={
            "workitems": [workitem("TF-3"), workitem("TF-2")],
            "pagination": {"hasMore": True, "nextCursor": "c"},
        }
    )
    result = runner.invoke(app, ["list", "--limit", "2"])
    assert result.exit_code == 0, result.output
    assert "TF-3" in result.output
    assert "Page 1 · tickets 1–2 · next: tforge list --page 2 --limit 2" in result.output


def test_list_json(configured, api):
    api.get("/workitems/mine").respond(
        json={"workitems": [workitem("TF-2")], "pagination": {"hasMore": False}}
    )
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
            200,
            json={
                "workitems": chunk,
                "pagination": {"hasMore": more, **({"nextCursor": "5"} if more else {})},
            },
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
        ["TF-1"],  # n on the last page does nothing
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
    api.get("/workitem/TF-1").respond(
        400, json={"err": "not_found", "message": "workitem TF-1 does not exist"}
    )
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


def test_create_rejects_bad_stage_before_creating(configured, api):
    post = api.post("/workitem/publish")
    result = runner.invoke(app, ["create", "Hello", "--stage", "done"])
    assert result.exit_code == 1
    assert "invalid stage 'done'" in result.output
    assert not post.called


def test_create_with_open_stage_makes_a_single_request(configured, api):
    api.post("/workitem/publish").respond(json={"workitem": workitem("TF-3")})
    put = api.put("/workitem/TF-3")
    result = runner.invoke(app, ["create", "Hello", "--stage", "Open"])
    assert result.exit_code == 0, result.output
    assert not put.called


def test_create_prompts_for_title_and_prints_json(configured, api):
    post = api.post("/workitem/publish").respond(
        json={"workitem": workitem("TF-3", title="From prompt")}
    )
    api.get("/custom-fields").respond(json={"customFields": []})
    result = runner.invoke(app, ["create", "--json"], input="From prompt\n\n\n\n")
    assert result.exit_code == 0, result.output
    assert json.loads(post.calls.last.request.content)["title"] == "From prompt"
    # Prompts go to stderr, so stdout holds only the JSON (plus the runner's echo of the input).
    assert "Title" not in result.stdout
    assert json.loads(result.stdout[result.stdout.index("{") :])["ref"] == "TF-3"


# ------------------------------------------------------------------ setup / register / status


def test_setup_prompts_only_for_credentials(tmp_path, monkeypatch, api):
    path = tmp_path / "cfg.json"
    monkeypatch.setenv("TFORGE_CONFIG", str(path))
    monkeypatch.setenv("TFORGE_BASE_URL", BASE)
    api.get("/workitems/mine").respond(json={"workitems": [], "pagination": {}})
    result = runner.invoke(app, ["setup"], input="alice\npw\n")
    assert result.exit_code == 0, result.output
    assert "URL" not in result.output.split("Connected")[0]
    assert json.loads(path.read_text()) == {"base_url": BASE, "username": "alice", "password": "pw"}


def test_setup_strips_trailing_slash(tmp_path, monkeypatch, api):
    path = tmp_path / "cfg.json"
    monkeypatch.setenv("TFORGE_CONFIG", str(path))
    api.get("/workitems/mine").respond(json={"workitems": [], "pagination": {}})
    result = runner.invoke(app, ["setup", "-u", "alice", "-p", "pw", "--base-url", f"{BASE}/"])
    assert result.exit_code == 0, result.output
    assert json.loads(path.read_text())["base_url"] == BASE


UNAUTHORIZED = httpx.Response(401, json={"err": "unauthorized", "message": "bad auth"})
EMPTY_PAGE = httpx.Response(200, json={"workitems": [], "pagination": {}})


def test_setup_offers_to_register_unknown_user(tmp_path, monkeypatch, api):
    path = tmp_path / "cfg.json"
    monkeypatch.setenv("TFORGE_CONFIG", str(path))
    api.get("/workitems/mine").mock(side_effect=[UNAUTHORIZED, EMPTY_PAGE])
    route = api.post("/user/register").respond(json={"ok": True})
    result = runner.invoke(app, ["setup", "--base-url", BASE], input="carol\npw\ny\npw\n")
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls.last.request.content) == {"username": "carol", "password": "pw"}
    assert "Account carol created" in result.output
    assert json.loads(path.read_text())["username"] == "carol"


def test_setup_register_password_mismatch(tmp_path, monkeypatch, api):
    path = tmp_path / "cfg.json"
    monkeypatch.setenv("TFORGE_CONFIG", str(path))
    api.get("/workitems/mine").mock(return_value=UNAUTHORIZED)
    route = api.post("/user/register")
    result = runner.invoke(app, ["setup", "--base-url", BASE], input="carol\npw\ny\npx\n")
    assert result.exit_code == 1
    assert "Passwords do not match" in result.output
    assert not route.called
    assert not path.exists()


def test_setup_register_existing_user_means_wrong_password(tmp_path, monkeypatch, api):
    path = tmp_path / "cfg.json"
    monkeypatch.setenv("TFORGE_CONFIG", str(path))
    api.get("/workitems/mine").mock(return_value=UNAUTHORIZED)
    api.post("/user/register").respond(
        400, json={"err": "duplicate", "message": "username already taken"}
    )
    result = runner.invoke(
        app, ["setup", "-u", "alice", "-p", "bad", "--base-url", BASE], input="y\n"
    )
    assert result.exit_code == 2
    assert "the password is wrong" in result.output
    assert not path.exists()


def test_register_saves_config_by_default(tmp_path, monkeypatch, api):
    path = tmp_path / "cfg.json"
    monkeypatch.setenv("TFORGE_CONFIG", str(path))
    route = api.post("/user/register").respond(json={"ok": True})
    result = runner.invoke(app, ["register", "-u", "bob", "-p", "pw", "--base-url", BASE])
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls.last.request.content) == {"username": "bob", "password": "pw"}
    assert "authorization" not in route.calls.last.request.headers
    assert json.loads(path.read_text())["username"] == "bob"


def test_register_no_save(tmp_path, monkeypatch, api):
    path = tmp_path / "cfg.json"
    monkeypatch.setenv("TFORGE_CONFIG", str(path))
    api.post("/user/register").respond(json={"ok": True})
    result = runner.invoke(
        app, ["register", "-u", "bob", "-p", "pw", "--base-url", BASE, "--no-save"]
    )
    assert result.exit_code == 0, result.output
    assert not path.exists()


def test_register_duplicate_username(tmp_path, monkeypatch, api):
    monkeypatch.setenv("TFORGE_CONFIG", str(tmp_path / "cfg.json"))
    api.post("/user/register").respond(
        400, json={"err": "duplicate", "message": "username already taken"}
    )
    result = runner.invoke(app, ["register", "-u", "bob", "-p", "pw", "--base-url", BASE])
    assert result.exit_code == 1
    assert "username already taken" in result.output


def test_status_reports_rate_limit(configured, api):
    api.get("/workitems/mine").respond(
        json={"workitems": [], "pagination": {}},
        headers={"x-ratelimit-limit": "50", "x-ratelimit-remaining": "42"},
    )
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    assert "alice" in result.output
    assert "Credentials OK" in result.output
    assert "42/50 requests left" in result.output


def test_status_without_rate_headers(configured, api):
    api.get("/workitems/mine").respond(json={"workitems": [], "pagination": {}})
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    assert "Rate limit:  unknown" in result.output


def test_status_unconfigured(tmp_path, monkeypatch):
    monkeypatch.setenv("TFORGE_CONFIG", str(tmp_path / "none.json"))
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 2
    assert "not set" in result.output


# ------------------------------------------------------------------ error mapping


def test_rejected_credentials_exit_2(configured, api):
    api.get("/workitems/mine").respond(
        401, json={"err": "unauthorized", "message": "valid basic auth required"}
    )
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 2
    assert "Check your credentials" in result.output


def test_corrupt_config_exits_2(configured):
    configured.write_text("{not json")
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 2
    assert "could not read config file" in result.output


def test_rate_limit_wait_is_reported(configured, api):
    api.get("/workitems/mine").mock(
        side_effect=[
            httpx.Response(429, json={"err": "rate_limited"}, headers={"retry-after": "0"}),
            httpx.Response(200, json={"workitems": [], "pagination": {}}),
        ]
    )
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0, result.output
    assert "rate limited; waiting 0.0s" in result.output


# ------------------------------------------------------------------ list


def test_list_all_footer_counts_tickets(configured, api):
    api.get("/workitems/mine").respond(
        json={"workitems": [workitem("TF-2"), workitem("TF-1")], "pagination": {"hasMore": False}}
    )
    result = runner.invoke(app, ["list", "--all"])
    assert result.exit_code == 0, result.output
    assert "2 tickets" in result.output
    assert "next:" not in result.output


def test_list_next_hint_keeps_stage_filter(configured, api):
    api.get("/workitems/mine").respond(
        json={
            "workitems": [workitem(f"TF-{i}", stage="review") for i in range(5, 0, -1)],
            "pagination": {"hasMore": False},
        }
    )
    result = runner.invoke(app, ["list", "--stage", "review", "-n", "1"])
    assert result.exit_code == 0, result.output
    assert (
        "Page 1 · ticket 1 · next: tforge list --page 2 --limit 1 --stage review" in result.output
    )


def test_list_empty_messages(configured, api):
    api.get("/workitems/mine").respond(json={"workitems": [], "pagination": {"hasMore": False}})
    assert "No tickets found." in runner.invoke(app, ["list"]).output
    assert "No tickets on page 3." in runner.invoke(app, ["list", "--page", "3"]).output


def test_list_bad_stage(configured, api):
    route = api.get("/workitems/mine")
    result = runner.invoke(app, ["list", "--stage", "done"])
    assert result.exit_code == 1
    assert not route.called


def test_interactive_needs_a_terminal(configured):
    result = runner.invoke(app, ["list", "-i"])
    assert result.exit_code == 1
    assert "needs a terminal" in result.output


def test_interactive_rejects_json(configured):
    assert runner.invoke(app, ["list", "-i", "--json"]).exit_code != 0


def test_interactive_starts_browser_on_a_terminal(configured, monkeypatch):
    from types import SimpleNamespace

    from ticketforge_cli import cli

    tty = SimpleNamespace(isatty=lambda: True)
    monkeypatch.setattr(cli, "sys", SimpleNamespace(stdin=tty, stdout=tty))
    calls = []
    monkeypatch.setattr(
        cli, "browse", lambda pager, limit, page: calls.append((pager.stage, limit, page))
    )
    result = runner.invoke(app, ["list", "-i", "-n", "4", "-p", "2", "--stage", "In Progress"])
    assert result.exit_code == 0, result.output
    assert calls == [("in_progress", 4, 2)]


# ------------------------------------------------------------------ browse keys


@pytest.fixture
def screen(monkeypatch):
    from ticketforge_cli import views

    out = []
    monkeypatch.setattr(views.console, "clear", lambda: None)
    monkeypatch.setattr(views, "ticket_table", lambda items, title=None: [w.ref for w in items])
    monkeypatch.setattr(views.console, "print", lambda *a, **k: out.append(a[0] if a else ""))
    return out


def seven_tickets(api):
    from .test_services import serve

    api.get("/workitems/mine").mock(
        side_effect=serve([(f"TF-{i}", "open") for i in range(7, 0, -1)])
    )


def tables(screen):
    return [x for x in screen if isinstance(x, list)]


def test_browse_arrow_keys_and_escape(screen, client, api):
    from ticketforge_cli import cli
    from ticketforge_cli.services import TicketService

    seven_tickets(api)
    keys = iter(["\x1b[C", "\x1b[B", "\x1b[D", "\x1b"])
    cli.browse(TicketService(client).pager(), limit=3, read_key=lambda: next(keys))
    assert tables(screen) == [
        ["TF-7", "TF-6", "TF-5"],
        ["TF-4", "TF-3", "TF-2"],
        ["TF-1"],
        ["TF-4", "TF-3", "TF-2"],
    ]


def test_browse_ctrl_c_quits(screen, client, api):
    from ticketforge_cli import cli
    from ticketforge_cli.services import TicketService

    seven_tickets(api)

    def interrupt():
        raise KeyboardInterrupt

    cli.browse(TicketService(client).pager(), limit=3, read_key=interrupt)
    assert tables(screen) == [["TF-7", "TF-6", "TF-5"]]


def test_browse_start_page_past_the_end_shows_last_page(screen, client, api):
    from ticketforge_cli import cli
    from ticketforge_cli.services import TicketService

    seven_tickets(api)
    cli.browse(TicketService(client).pager(), limit=3, page=9, read_key=lambda: "q")
    assert tables(screen) == [["TF-1"]]
    assert any(isinstance(x, str) and x.startswith("Page 3/3") for x in screen)


# ------------------------------------------------------------------ show / update / delete

FIELDS = {"customFields": [{"id": "f1", "name": "priority", "label": "Priority", "type": "text"}]}


def test_show_uses_field_labels(configured, api):
    api.get("/workitem/TF-4").respond(
        json={
            "workitem": workitem(
                "TF-4", customFields={"priority": "high"}, owner={"username": "alice"}
            )
        }
    )
    api.get("/custom-fields").respond(json=FIELDS)
    result = runner.invoke(app, ["show", "tf-4"])
    assert result.exit_code == 0, result.output
    assert "Priority" in result.output and "high" in result.output
    assert "Owner" in result.output


def test_show_json_is_the_raw_ticket(configured, api):
    raw = workitem("TF-4", extra="kept")
    api.get("/workitem/TF-4").respond(json={"workitem": raw})
    result = runner.invoke(app, ["show", "4", "--json"])
    assert json.loads(result.output) == raw


def test_update_wires_options_into_a_full_put(configured, api):
    api.get("/custom-fields").respond(json=FIELDS)
    api.get("/workitem/TF-5").respond(
        json={
            "workitem": workitem(
                "TF-5", description="keep", dependsOn=["TF-1"], customFields={"priority": "low"}
            )
        }
    )
    put = api.put("/workitem/TF-5").respond(json={"workitem": workitem("TF-5")})
    result = runner.invoke(
        app, ["update", "5", "--clear-deps", "-f", "priority=", "--title", "New"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(put.calls.last.request.content) == {
        "title": "New",
        "description": "keep",
        "stage": "open",
        "dependsOn": None,
        "customFields": {},
    }


def test_update_json(configured, api):
    api.get("/workitem/TF-5").respond(json={"workitem": workitem("TF-5")})
    api.put("/workitem/TF-5").respond(json={"workitem": workitem("TF-5", stage="closed")})
    result = runner.invoke(app, ["update", "TF-5", "--stage", "closed", "--json"])
    assert json.loads(result.output)["stage"] == "closed"


def test_update_without_options_asks_and_sends_nothing_on_eof(configured, api):
    api.get("/workitem/TF-5").respond(json={"workitem": workitem("TF-5")})
    put = api.put("/workitem/TF-5")
    result = runner.invoke(app, ["update", "TF-5"])  # no input: EOF at the first prompt
    assert result.exit_code == 1
    assert "Title [Ticket TF-5]" in result.output
    assert not put.called


def test_update_bad_field_syntax(configured, api):
    result = runner.invoke(app, ["update", "TF-5", "-f", "novalue"])
    assert result.exit_code == 1
    assert "expected name=value" in result.output


@pytest.mark.parametrize(
    ("args", "answer", "deleted"), [([], "n\n", False), ([], "y\n", True), (["--yes"], "", True)]
)
def test_delete_confirmation(configured, api, args, answer, deleted):
    api.get("/workitem/TF-5").respond(json={"workitem": workitem("TF-5")})
    route = api.delete("/workitem/TF-5").respond(json={})
    result = runner.invoke(app, ["delete", "5", *args], input=answer)
    assert route.called is deleted
    assert result.exit_code == (0 if deleted else 1)
    if deleted:
        assert "Deleted TF-5" in result.output


def test_delete_missing_ticket_sends_no_delete(configured, api):
    api.get("/workitem/TF-9").respond(
        400, json={"err": "not_found", "message": "workitem TF-9 does not exist"}
    )
    route = api.delete("/workitem/TF-9")
    result = runner.invoke(app, ["delete", "TF-9", "--yes"])
    assert result.exit_code == 1
    assert not route.called


# ------------------------------------------------------------------ fields


def test_fields_list_table_json_and_empty(configured, api):
    route = api.get("/custom-fields").respond(json=FIELDS)
    table = runner.invoke(app, ["fields", "list"])
    assert "priority" in table.output and "Priority" in table.output
    assert (
        json.loads(runner.invoke(app, ["fields", "list", "--json"]).output)[0]["name"] == "priority"
    )

    route.respond(json={"customFields": []})
    assert "No custom fields defined" in runner.invoke(app, ["fields", "list"]).output


def test_fields_add(configured, api):
    post = api.post("/custom-fields").respond(
        json={"customField": {"id": "f2", "name": "team", "label": "Squad"}}
    )
    result = runner.invoke(app, ["fields", "add", "team", "--label", "Squad"])
    assert result.exit_code == 0, result.output
    assert json.loads(post.calls.last.request.content) == {"name": "team", "label": "Squad"}
    assert "Added field team (Squad)" in result.output


def test_fields_relabel(configured, api):
    api.get("/custom-fields").respond(json=FIELDS)
    api.put("/custom-fields/f1").respond(
        json={"customField": {"id": "f1", "name": "priority", "label": "Urgency"}}
    )
    result = runner.invoke(app, ["fields", "relabel", "priority", "Urgency"])
    assert result.exit_code == 0, result.output
    assert 'now labelled "Urgency"' in result.output


@pytest.mark.parametrize(("args", "answer", "deleted"), [([], "n\n", False), (["--yes"], "", True)])
def test_fields_delete_confirmation(configured, api, args, answer, deleted):
    api.get("/custom-fields").respond(json=FIELDS)
    route = api.delete("/custom-fields/f1").respond(json={})
    result = runner.invoke(app, ["fields", "delete", "priority", *args], input=answer)
    assert route.called is deleted
    assert result.exit_code == (0 if deleted else 1)


def test_fields_delete_unknown(configured, api):
    api.get("/custom-fields").respond(json=FIELDS)
    result = runner.invoke(app, ["fields", "delete", "nope", "--yes"])
    assert result.exit_code == 1
    assert "custom field 'nope' not found" in result.output


MARKUP = "fix [/] bug [red]x"


def test_markup_in_ticket_text_is_shown_literally(configured, api):
    item = workitem("TF-1", title=MARKUP, description=MARKUP)
    api.get("/workitems/mine").respond(json={"workitems": [item], "pagination": {}})
    api.get("/workitem/TF-1").respond(json={"workitem": item})
    for args in (["list"], ["show", "1"]):
        result = runner.invoke(app, args)
        assert result.exit_code == 0, result.output
        assert MARKUP in result.output


def test_markup_in_server_error_is_shown_literally(configured, api):
    api.get("/workitem/TF-1").respond(400, json={"err": "not_found", "message": MARKUP})
    result = runner.invoke(app, ["show", "1"])
    assert result.exit_code == 1
    assert MARKUP in result.output


def test_markup_in_username_is_shown_literally(tmp_path, monkeypatch, api):
    monkeypatch.setenv("TFORGE_CONFIG", str(tmp_path / "cfg.json"))
    api.get("/workitems/mine").respond(json={"workitems": [], "pagination": {}})
    result = runner.invoke(app, ["setup", "-u", "a[/]b", "-p", "pw", "--base-url", BASE])
    assert result.exit_code == 0, result.output
    assert "as a[/]b." in result.output


def test_bad_ref_is_rejected_before_any_request(configured, api):
    result = runner.invoke(app, ["show", "1/../../custom-fields"])
    assert result.exit_code == 1
    assert "invalid ref" in result.output
    assert not api.calls


def test_bad_dep_is_rejected_before_any_request(configured, api):
    result = runner.invoke(app, ["create", "Hello", "--dep", "nope"])
    assert result.exit_code == 1
    assert "invalid ref 'nope'" in result.output
    assert not api.calls


def test_setup_rejects_bad_url_and_blank_username(tmp_path, monkeypatch, api):
    monkeypatch.setenv("TFORGE_CONFIG", str(tmp_path / "cfg.json"))
    result = runner.invoke(app, ["setup", "--base-url", "example.com", "-u", "a", "-p", "b"])
    assert result.exit_code == 1
    assert "invalid URL 'example.com'" in result.output
    result = runner.invoke(app, ["setup", "--base-url", BASE, "-u", "  ", "-p", "b"])
    assert result.exit_code == 1
    assert "username must not be empty" in result.output
    assert not api.calls


def test_setup_repairs_a_malformed_config(tmp_path, monkeypatch, api):
    path = tmp_path / "cfg.json"
    path.write_text("[]")
    monkeypatch.setenv("TFORGE_CONFIG", str(path))
    assert runner.invoke(app, ["status"]).exit_code == 2
    api.get("/workitems/mine").respond(json={"workitems": [], "pagination": {}})
    result = runner.invoke(app, ["setup", "--base-url", BASE, "-u", "alice", "-p", "pw"])
    assert result.exit_code == 0, result.output
    assert json.loads(path.read_text())["username"] == "alice"


def _interrupt(*args, **kwargs):
    raise KeyboardInterrupt


def test_ctrl_c_mid_request_exits_130(configured, monkeypatch):
    monkeypatch.setattr(TicketForgeClient, "get_workitem", _interrupt)
    result = runner.invoke(app, ["show", "1"])
    assert result.exit_code == 130
    assert "Interrupted" in result.output


def test_service_client_is_closed_after_the_command(configured, monkeypatch):
    from ticketforge_cli import cli

    closed = []
    monkeypatch.setattr(TicketForgeClient, "close", lambda self: closed.append(self))
    monkeypatch.setattr(TicketForgeClient, "get_workitem", _interrupt)
    runner.invoke(app, ["show", "1"])
    assert len(closed) == 1
    assert not cli._open_clients


@pytest.mark.parametrize("interrupted", [True, False])
def test_create_reports_ticket_when_stage_update_fails(configured, api, monkeypatch, interrupted):
    api.post("/workitem/publish").respond(json={"workitem": workitem("TF-3")})
    api.get("/workitem/TF-3").respond(json={"workitem": workitem("TF-3")})
    if interrupted:
        monkeypatch.setattr(TicketForgeClient, "update_workitem", _interrupt)
    else:
        api.put("/workitem/TF-3").respond(400, json={"err": "invalid_input", "message": "nope"})
    result = runner.invoke(app, ["create", "Hello", "-s", "review"])
    assert result.exit_code == (130 if interrupted else 1)
    assert "Created TF-3, but its stage wasn't set" in result.output
    assert "tforge update TF-3 -s review" in result.output


def test_create_guided_asks_for_each_field(configured, api):
    api.get("/custom-fields").respond(json=FIELDS)
    post = api.post("/workitem/publish").respond(json={"workitem": workitem("TF-3")})
    api.get("/workitem/TF-3").respond(json={"workitem": workitem("TF-3")})
    put = api.put("/workitem/TF-3").respond(json={"workitem": workitem("TF-3", stage="review")})
    answers = ["Ship v2", "Release notes", "nope", "review", "TF-1, x", "1, 2", "high"]
    result = runner.invoke(app, ["create"], input="\n".join(answers) + "\n")
    assert result.exit_code == 0, result.output
    for prompt in ("Title", "Description (optional)", "Stage [open]", "Depends on", "Priority"):
        assert prompt in result.output
    assert "invalid stage 'nope'" in result.output
    assert "invalid ref 'x'" in result.output
    assert json.loads(post.calls.last.request.content) == {
        "title": "Ship v2",
        "description": "Release notes",
        "dependsOn": ["TF-1", "TF-2"],
        "customFields": {"priority": "high"},
    }
    assert json.loads(put.calls.last.request.content)["stage"] == "review"


def test_create_guided_skips_prompts_for_given_options(configured, api):
    api.get("/custom-fields").respond(json={"customFields": []})
    post = api.post("/workitem/publish").respond(json={"workitem": workitem("TF-3")})
    result = runner.invoke(app, ["create", "-d", "Given", "--dep", "TF-1"], input="T\n\n")
    assert result.exit_code == 0, result.output
    assert "Description (optional)" not in result.output
    assert "Depends on (refs" not in result.output
    assert json.loads(post.calls.last.request.content)["description"] == "Given"


def test_create_guided_requires_a_title(configured, api):
    api.get("/custom-fields").respond(json={"customFields": []})
    api.post("/workitem/publish").respond(json={"workitem": workitem("TF-3")})
    result = runner.invoke(app, ["create"], input="  \nReal\n\n\n\n")
    assert result.exit_code == 0, result.output
    assert "a value is required" in result.output


def test_update_guided_sends_only_what_changed(configured, api):
    current = workitem(
        "TF-5",
        title="Old",
        description="Keep me",
        dependsOn=["TF-1"],
        customFields={"priority": "high"},
    )
    api.get("/workitem/TF-5").respond(json={"workitem": current})
    api.get("/custom-fields").respond(json=FIELDS)
    put = api.put("/workitem/TF-5").respond(json={"workitem": current})
    # title: keep, description: clear, stage: "-" refused then review, deps: change, priority: keep
    answers = ["", "-", "-", "review", "TF-2, 3", ""]
    result = runner.invoke(app, ["update", "5"], input="\n".join(answers) + "\n")
    assert result.exit_code == 0, result.output
    assert "Title [Old]" in result.output
    assert "the stage can't be cleared" in result.output
    assert json.loads(put.calls.last.request.content) == {
        "title": "Old",
        "description": None,
        "stage": "review",
        "dependsOn": ["TF-2", "TF-3"],
        "customFields": {"priority": "high"},
    }


def test_update_guided_without_changes_sends_nothing(configured, api):
    api.get("/workitem/TF-5").respond(json={"workitem": workitem("TF-5")})
    api.get("/custom-fields").respond(json={"customFields": []})
    put = api.put("/workitem/TF-5")
    result = runner.invoke(app, ["update", "5"], input="\n\n\n\n")
    assert result.exit_code == 0, result.output
    assert "No changes" in result.output
    assert not put.called
