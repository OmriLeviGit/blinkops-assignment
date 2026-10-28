"""Lenient data models.

The API omits empty fields (e.g. `dependsOn`, `customFields`) and returns
different subsets of fields from different endpoints, so every field except
`ref`/`title` is optional and unknown keys are ignored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

STAGES = ("open", "in_progress", "review", "closed")


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class WorkItem:
    ref: str
    title: str
    description: str | None = None
    stage: str = "open"
    depends_on: list[str] = field(default_factory=list)
    custom_fields: dict[str, str] = field(default_factory=dict)
    owner: str | None = None
    created: datetime | None = None
    updated: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> WorkItem:
        owner = data.get("owner")
        created = _parse_time(data.get("created"))
        return cls(
            ref=str(data.get("ref", "")),
            title=str(data.get("title", "")),
            description=data.get("description"),
            stage=data.get("stage") or "open",
            depends_on=list(data.get("dependsOn") or []),
            custom_fields=dict(data.get("customFields") or {}),
            owner=owner.get("username") if isinstance(owner, dict) else None,
            created=created,
            # The create endpoint omits `updated`; a new ticket was last updated when created.
            updated=_parse_time(data.get("updated")) or created,
            raw=data,
        )

    def to_update_payload(self) -> dict[str, Any]:
        """Full PUT body. The API wipes omitted description/customFields."""
        return {
            "title": self.title,
            "description": self.description or None,
            "stage": self.stage,
            "dependsOn": self.depends_on or None,
            "customFields": self.custom_fields,
        }


@dataclass
class CustomField:
    id: str
    name: str
    label: str
    type: str = "text"
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> CustomField:
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            label=str(data.get("label", "")),
            type=data.get("type") or "text",
            raw=data,
        )


@dataclass
class Page:
    items: list[WorkItem]
    has_more: bool = False
    next_cursor: str | None = None
