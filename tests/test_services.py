import json

import httpx
import pytest

from ticketforge_cli.errors import NotFoundError, ValidationError
from ticketforge_cli.services import (
    TicketService,
    normalize_ref,
    normalize_stage,
    parse_field_assignments,
)

from .conftest import workitem

FIELDS = {"customFields": [{"id": "f1", "name": "priority", "label": "Priority", "type": "text"}]}


@pytest.fixture
def svc(client):
    return TicketService(client)


def body(route):
    return json.loads(route.calls.last.request.content)


# ------------------------------------------------------------------ helpers


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("open", "open"), ("In Progress", "in_progress"), ("in-progress", "in_progress"), ("CLOSED", "closed")],
)
def test_normalize_stage(raw, expected):
    assert normalize_stage(raw) == expected


def test_normalize_stage_rejects_unknown():
    with pytest.raises(ValidationError, match="open, in_progress, review, closed"):
        normalize_stage("done")


def test_normalize_ref():
    assert normalize_ref("tf-12") == "TF-12"
    assert normalize_ref("12") == "TF-12"


def test_parse_field_assignments():
    assert parse_field_assignments(["priority=high", "team = core ", "old="]) == {
        "priority": "high",
        "team": "core",
        "old": "",
    }
    with pytest.raises(ValidationError):
        parse_field_assignments(["novalue"])


# ------------------------------------------------------------------ update


def test_update_preserves_fields_the_api_would_wipe(svc, api):
    api.get("/workitem/TF-5").respond(
        json={
            "workitem": workitem(
                "TF-5",
                description="keep me",
                dependsOn=["TF-1"],
                customFields={"priority": "high"},
            )
        }
    )
    put = api.put("/workitem/TF-5").respond(json={"workitem": workitem("TF-5", stage="review")})

    svc.update_ticket("tf-5", stage="review")

    assert body(put) == {
        "title": "Ticket TF-5",
        "description": "keep me",
        "stage": "review",
        "dependsOn": ["TF-1"],
        "customFields": {"priority": "high"},
    }


def test_update_dependency_add_remove_and_clear(svc, api):
    api.get("/workitem/TF-5").respond(json={"workitem": workitem("TF-5", dependsOn=["TF-1", "TF-2"])})
    put = api.put("/workitem/TF-5").respond(json={"workitem": workitem("TF-5")})

    svc.update_ticket("TF-5", add_deps=["tf-3", "TF-1"], remove_deps=["TF-2"])
    assert body(put)["dependsOn"] == ["TF-1", "TF-3"]

    svc.update_ticket("TF-5", depends_on=[])
    assert body(put)["dependsOn"] is None


def test_update_sets_and_unsets_custom_fields(svc, api):
    api.get("/custom-fields").respond(json=FIELDS)
    api.get("/workitem/TF-5").respond(
        json={"workitem": workitem("TF-5", customFields={"priority": "low", "gone": "x"})}
    )
    put = api.put("/workitem/TF-5").respond(json={"workitem": workitem("TF-5")})

    svc.update_ticket("TF-5", fields={"priority": "high", "gone": ""})
    assert body(put)["customFields"] == {"priority": "high"}


def test_update_rejects_unknown_custom_field_before_put(svc, api):
    api.get("/custom-fields").respond(json=FIELDS)
    api.get("/workitem/TF-5").respond(json={"workitem": workitem("TF-5")})
    put = api.put("/workitem/TF-5")
    with pytest.raises(ValidationError, match="available: priority"):
        svc.update_ticket("TF-5", fields={"severity": "x"})
    assert not put.called


def test_update_requires_a_change(svc):
    with pytest.raises(ValidationError, match="nothing to update"):
        svc.update_ticket("TF-5")


def test_update_rejects_bad_stage(svc, api):
    api.get("/workitem/TF-5").respond(json={"workitem": workitem("TF-5")})
    with pytest.raises(ValidationError):
        svc.update_ticket("TF-5", stage="done")


# ------------------------------------------------------------------ create


def test_create_builds_payload(svc, api):
    api.get("/custom-fields").respond(json=FIELDS)
    post = api.post("/workitem/publish").respond(json={"workitem": workitem("TF-9")})
    svc.create_ticket(" New ", description="", depends_on=["tf-1"], fields={"priority": "high"})
    assert body(post) == {
        "title": "New",
        "description": None,
        "dependsOn": ["TF-1"],
        "customFields": {"priority": "high"},
    }


def test_create_requires_title(svc):
    with pytest.raises(ValidationError):
        svc.create_ticket("   ")


# ------------------------------------------------------------------ listing


def pages(*batches):
    """Mock /workitems/mine serving `batches` in order, honoring `limit`."""
    flat = [ref for batch in batches for ref in batch]

    def handler(request):
        limit = int(request.url.params.get("limit", 5))
        start = int(request.url.params.get("cursor", 0))
        chunk = flat[start : start + limit]
        nxt = start + len(chunk)
        has_more = nxt < len(flat)
        return httpx.Response(
            200,
            json={
                "workitems": [workitem(r, stage=s) for r, s in chunk],
                "pagination": {"hasMore": has_more, **({"nextCursor": str(nxt)} if has_more else {})},
            },
        )

    return handler


def test_list_with_limit_returns_exact_resume_cursor(svc, api):
    data = [(f"TF-{i}", "open") for i in range(12, 0, -1)]
    api.get("/workitems/mine").mock(side_effect=pages(data))

    first = svc.list_tickets(limit=7)
    assert [w.ref for w in first.items] == [f"TF-{i}" for i in range(12, 5, -1)]
    assert first.has_more and first.next_cursor == "7"

    rest = svc.list_tickets(cursor=first.next_cursor)
    assert [w.ref for w in rest.items] == [f"TF-{i}" for i in range(5, 0, -1)]
    assert not rest.has_more and rest.next_cursor is None


def test_list_filters_stage_client_side(svc, api):
    data = [("TF-6", "open"), ("TF-5", "closed"), ("TF-4", "open"), ("TF-3", "closed"),
            ("TF-2", "closed"), ("TF-1", "open")]
    api.get("/workitems/mine").mock(side_effect=pages(data))

    result = svc.list_tickets(stage="closed")
    assert [w.ref for w in result.items] == ["TF-5", "TF-3", "TF-2"]


def test_list_with_stage_and_limit_never_skips_rows(svc, api):
    data = [(f"TF-{i}", "open") for i in range(8, 0, -1)]
    api.get("/workitems/mine").mock(side_effect=pages(data))

    first = svc.list_tickets(limit=3, stage="open")
    assert [w.ref for w in first.items] == ["TF-8", "TF-7", "TF-6"]
    rest = svc.list_tickets(cursor=first.next_cursor, stage="open")
    assert "TF-5" in [w.ref for w in rest.items]


# ------------------------------------------------------------------ fields


def test_field_resolution_by_name(svc, api):
    api.get("/custom-fields").respond(json=FIELDS)
    put = api.put("/custom-fields/f1").respond(
        json={"customField": {"id": "f1", "name": "priority", "label": "Prio"}}
    )
    assert svc.relabel_field("priority", "Prio").label == "Prio"
    assert body(put) == {"label": "Prio"}

    with pytest.raises(NotFoundError):
        svc.delete_field("nope")


def test_add_field_validates_name_and_defaults_label(svc, api):
    post = api.post("/custom-fields").respond(
        json={"customField": {"id": "f2", "name": "due_date", "label": "Due Date"}}
    )
    with pytest.raises(ValidationError):
        svc.add_field("bad name")
    svc.add_field("due_date")
    assert body(post) == {"name": "due_date", "label": "Due Date"}
