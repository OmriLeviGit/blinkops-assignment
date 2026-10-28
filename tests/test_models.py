from datetime import datetime, timezone

from ticketforge_cli.models import CustomField, WorkItem

from .conftest import workitem


def test_from_api_tolerates_missing_and_extra_keys():
    item = WorkItem.from_api(
        {"ref": "TF-1", "title": "t", "somethingNew": 1, "dependsOn": None, "customFields": None}
    )
    assert item.stage == "open"
    assert item.depends_on == [] and item.custom_fields == {}
    assert item.owner is None and item.created is None and item.updated is None
    assert item.raw["somethingNew"] == 1


def test_from_api_reads_owner_and_times():
    item = WorkItem.from_api(
        workitem("TF-1", owner={"id": "u1", "username": "alice"}, dependsOn=["TF-0"])
    )
    assert item.owner == "alice"
    assert item.depends_on == ["TF-0"]
    assert item.created == datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


def test_updated_falls_back_to_created():
    # The create endpoint returns no `updated`.
    data = workitem("TF-1")
    del data["updated"]
    item = WorkItem.from_api(data)
    assert item.updated == item.created


def test_bad_timestamps_become_none():
    item = WorkItem.from_api(workitem("TF-1", created="yesterday", updated=12345))
    assert item.created is None and item.updated is None


def test_update_payload_always_sends_every_field():
    # PUT is a full replace: an omitted description or customFields is wiped server-side.
    item = WorkItem(ref="TF-1", title="t", description="", depends_on=[], custom_fields={})
    assert item.to_update_payload() == {
        "title": "t",
        "description": None,
        "stage": "open",
        "dependsOn": None,
        "customFields": {},
    }


def test_custom_field_defaults():
    field = CustomField.from_api({"id": "f1", "name": "team"})
    assert (field.label, field.type) == ("", "text")
