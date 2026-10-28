import json
from datetime import datetime, timezone

from rich.console import Console

from ticketforge_cli import views
from ticketforge_cli.models import CustomField, WorkItem


def render(renderable):
    console = Console(width=120, color_system=None)
    with console.capture() as cap:
        console.print(renderable)
    return cap.get()


def test_excerpt_collapses_whitespace_and_truncates():
    assert views._excerpt(None) == ""
    assert views._excerpt("a\n  b\tc") == "a b c"
    assert views._excerpt("x" * 60, width=10) == "x" * 9 + "…"


def test_when_handles_missing_time():
    assert views._when(None) == "-"


def test_stage_badge():
    assert views.stage_badge("in_progress").plain == "in progress"
    assert "white" in str(views.stage_badge("weird").style)


def test_ticket_detail_uses_labels_and_shows_owner_only_when_known():
    item = WorkItem(ref="TF-1", title="Hello", custom_fields={"priority": "high"}, depends_on=["TF-0"])
    out = render(views.ticket_detail(item, {"priority": "Urgency"}))
    assert "Urgency" in out and "high" in out and "TF-0" in out
    assert "No description" in out
    assert "Owner" not in out

    item.owner = "alice"
    assert "alice" in render(views.ticket_detail(item))


def test_ticket_table_and_fields_table():
    table = render(views.ticket_table([WorkItem(ref="TF-1", title="Hello", stage="review")]))
    assert "TF-1" in table and "review" in table
    fields = render(views.fields_table([CustomField(id="f1", name="team", label="Team")]))
    assert "team" in fields and "f1" in fields


def test_print_json_prefers_raw_api_data(capsys):
    views.print_json(WorkItem.from_api({"ref": "TF-1", "title": "t", "extra": True}))
    assert json.loads(capsys.readouterr().out) == {"ref": "TF-1", "title": "t", "extra": True}


def test_print_json_serializes_dataclasses_and_datetimes(capsys):
    when = datetime(2026, 1, 2, tzinfo=timezone.utc)
    views.print_json([WorkItem(ref="TF-1", title="t", created=when)])
    data = json.loads(capsys.readouterr().out)
    assert data[0]["created"] == "2026-01-02T00:00:00+00:00"
    assert "raw" not in data[0]
