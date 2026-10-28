"""Ticket logic that sits between the CLI and the raw API client.

The main job here is hiding API quirks: PUT is a full replace (omitted
description/customFields get wiped), the server ignores filters, and custom
fields are addressed by opaque ids.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass

from .client import MAX_PAGE_SIZE, TicketForgeClient
from .errors import NotFoundError, ValidationError
from .models import STAGES, CustomField, WorkItem

FIELD_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")


@dataclass
class ListResult:
    items: list[WorkItem]
    has_more: bool


def normalize_stage(value: str) -> str:
    stage = value.strip().lower().replace("-", "_").replace(" ", "_")
    if stage not in STAGES:
        raise ValidationError(f"invalid stage '{value}'. Choose one of: {', '.join(STAGES)}")
    return stage


def normalize_ref(value: str) -> str:
    ref = value.strip().upper()
    if ref.isdigit():
        ref = f"TF-{ref}"
    return ref


def parse_field_assignments(pairs: Iterable[str]) -> dict[str, str]:
    """Parse `name=value` pairs. An empty value (`name=`) means unset."""
    result: dict[str, str] = {}
    for pair in pairs:
        name, sep, value = pair.partition("=")
        name = name.strip()
        if not sep or not name:
            raise ValidationError(f"invalid field '{pair}', expected name=value")
        result[name] = value.strip()
    return result


class TicketPager:
    """Page-number access over the cursor API, loading lazily and caching.

    The API only offers forward cursor pagination in chunks of at most 5, with
    no offset and no server-side filtering. The pager fetches chunks only when
    a page beyond what is cached is requested, applies the stage filter
    client-side, and keeps everything loaded so revisiting a page is free.
    """

    def __init__(self, client: TicketForgeClient, *, stage: str | None = None) -> None:
        self.client = client
        self.stage = normalize_stage(stage) if stage else None
        self.loaded: list[WorkItem] = []
        self.exhausted = False
        self.requests = 0
        self._cursor: str | None = None

    def ensure(self, count: int) -> None:
        """Fetch chunks until `count` matching tickets are cached or the list ends."""
        while len(self.loaded) < count and not self.exhausted:
            chunk = self.client.list_page(limit=MAX_PAGE_SIZE, cursor=self._cursor)
            self.requests += 1
            self.loaded.extend(
                w for w in chunk.items if self.stage is None or w.stage == self.stage
            )
            self._cursor = chunk.next_cursor
            self.exhausted = not (chunk.has_more and chunk.next_cursor)

    def is_cached(self, number: int, size: int) -> bool:
        return self.exhausted or len(self.loaded) > number * size

    def page(self, number: int, size: int) -> ListResult:
        if number < 1:
            raise ValidationError("page must be 1 or greater")
        if size < 1:
            raise ValidationError("limit must be 1 or greater")
        end = number * size
        self.ensure(end)
        if len(self.loaded) > end:
            has_more = True
        elif self.exhausted:
            has_more = False
        elif self.stage is None:
            # Unfiltered: the API reported another non-empty chunk.
            has_more = True
        else:
            # Filtered: more chunks don't guarantee more matches, so look ahead.
            self.ensure(end + 1)
            has_more = len(self.loaded) > end
        return ListResult(self.loaded[end - size : end], has_more)

    def load_all(self) -> list[WorkItem]:
        while not self.exhausted:
            self.ensure(len(self.loaded) + MAX_PAGE_SIZE)
        return self.loaded

    def total_pages(self, size: int) -> int | None:
        """Exact page count once the end of the list has been reached, else None."""
        if not self.exhausted:
            return None
        return max(1, math.ceil(len(self.loaded) / size))


class TicketService:
    def __init__(self, client: TicketForgeClient) -> None:
        self.client = client
        self._fields: list[CustomField] | None = None

    # ------------------------------------------------------------ listing

    def pager(self, stage: str | None = None) -> TicketPager:
        return TicketPager(self.client, stage=stage)

    def list_tickets(
        self,
        *,
        page: int = 1,
        limit: int | None = None,
        stage: str | None = None,
    ) -> ListResult:
        """Return page `page` of `limit` tickets, or every ticket if `limit` is None."""
        pager = self.pager(stage)
        if limit is None:
            return ListResult(pager.load_all(), has_more=False)
        return pager.page(page, limit)

    # ------------------------------------------------------------ tickets

    def get_ticket(self, ref: str) -> WorkItem:
        return self.client.get_workitem(normalize_ref(ref))

    def create_ticket(
        self,
        title: str,
        *,
        description: str | None = None,
        depends_on: Iterable[str] = (),
        fields: dict[str, str] | None = None,
    ) -> WorkItem:
        title = title.strip()
        if not title:
            raise ValidationError("title must not be empty")
        payload: dict[str, object] = {
            "title": title,
            "description": (description or "").strip() or None,
            "dependsOn": [normalize_ref(r) for r in depends_on] or None,
        }
        values = {k: v for k, v in (fields or {}).items() if v}
        if values:
            self._check_field_names(values)
            payload["customFields"] = values
        return self.client.create_workitem(payload)

    def update_ticket(
        self,
        ref: str,
        *,
        title: str | None = None,
        description: str | None = None,
        stage: str | None = None,
        depends_on: Iterable[str] | None = None,
        add_deps: Iterable[str] = (),
        remove_deps: Iterable[str] = (),
        fields: dict[str, str] | None = None,
    ) -> WorkItem:
        """Apply only the given changes, preserving everything else.

        `depends_on` replaces the whole list (an empty iterable clears it).
        In `fields`, an empty value removes that field from the ticket.
        """
        add_deps, remove_deps = list(add_deps), list(remove_deps)
        changes = [title, description, stage, depends_on, fields]
        if all(c is None for c in changes) and not add_deps and not remove_deps:
            raise ValidationError("nothing to update; pass at least one option")

        ticket = self.get_ticket(ref)

        if title is not None:
            if not title.strip():
                raise ValidationError("title must not be empty")
            ticket.title = title.strip()
        if description is not None:
            ticket.description = description.strip() or None
        if stage is not None:
            ticket.stage = normalize_stage(stage)

        deps = (
            [normalize_ref(r) for r in depends_on]
            if depends_on is not None
            else list(ticket.depends_on)
        )
        for dep in map(normalize_ref, add_deps):
            if dep not in deps:
                deps.append(dep)
        removing = {normalize_ref(r) for r in remove_deps}
        ticket.depends_on = [d for d in deps if d not in removing]

        if fields:
            self._check_field_names([k for k, v in fields.items() if v])
            for name, value in fields.items():
                if value:
                    ticket.custom_fields[name] = value
                else:
                    ticket.custom_fields.pop(name, None)

        return self.client.update_workitem(ticket.ref, ticket.to_update_payload())

    def delete_ticket(self, ref: str) -> None:
        self.client.delete_workitem(normalize_ref(ref))

    # ------------------------------------------------------- custom fields

    def list_fields(self, *, refresh: bool = False) -> list[CustomField]:
        if self._fields is None or refresh:
            self._fields = self.client.list_custom_fields()
        return self._fields

    def add_field(self, name: str, label: str | None = None) -> CustomField:
        name = name.strip()
        if not FIELD_NAME_RE.match(name):
            raise ValidationError("field name may only contain letters, digits and underscores")
        label = (label or "").strip() or name.replace("_", " ").title()
        field = self.client.create_custom_field(name, label)
        self._fields = None
        return field

    def relabel_field(self, name_or_id: str, label: str) -> CustomField:
        if not label.strip():
            raise ValidationError("label must not be empty")
        field = self._resolve_field(name_or_id)
        updated = self.client.update_custom_field(field.id, label.strip())
        self._fields = None
        return updated

    def delete_field(self, name_or_id: str) -> CustomField:
        field = self._resolve_field(name_or_id)
        self.client.delete_custom_field(field.id)
        self._fields = None
        return field

    def _resolve_field(self, name_or_id: str) -> CustomField:
        for field in self.list_fields():
            if name_or_id in (field.name, field.id):
                return field
        raise NotFoundError(f"custom field '{name_or_id}' not found")

    def _check_field_names(self, names: Iterable[str]) -> None:
        known = {f.name for f in self.list_fields()}
        unknown = sorted(set(names) - known)
        if unknown:
            hint = f"available: {', '.join(sorted(known))}" if known else "no custom fields defined"
            raise ValidationError(
                f"unknown custom field(s): {', '.join(unknown)} ({hint}). "
                "Create one with `tforge fields add NAME`."
            )
