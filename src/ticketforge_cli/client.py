"""Low-level HTTP client for the TicketForge API.

Handles auth, error mapping, rate limits and retries. It knows nothing about
CLI concerns; business rules live in `services.py`.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from . import __version__
from .errors import RateLimitError, ServerError, TicketForgeError, error_from_response
from .models import CustomField, Page, WorkItem

API_PREFIX = "/api/tforge"
MAX_PAGE_SIZE = 5  # server clamps `limit` to 1..5

IDEMPOTENT_METHODS = {"GET", "HEAD", "PUT", "DELETE", "OPTIONS"}
MAX_WAIT_SECONDS = 60.0


class TicketForgeClient:
    def __init__(
        self,
        base_url: str,
        username: str | None = None,
        password: str | None = None,
        *,
        max_retries: int = 3,
        timeout: float = 15.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        on_wait: Callable[[float, str], None] | None = None,
    ) -> None:
        auth = (username, password) if username and password else None
        self._http = httpx.Client(
            base_url=base_url.rstrip("/") + API_PREFIX,
            auth=auth,
            timeout=timeout,
            transport=transport,
            headers={"User-Agent": f"ticketforge-cli/{__version__}"},
        )
        self.max_retries = max_retries
        self._sleep = sleep
        self._on_wait = on_wait
        self.rate_limit: int | None = None
        self.rate_remaining: int | None = None
        self.rate_reset: datetime | None = None

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> TicketForgeClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------ core

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        method = method.upper()
        attempt = 0
        while True:
            self._wait_if_exhausted()
            try:
                response = self._http.request(method, path, **kwargs)
            except httpx.TransportError as exc:
                if method in IDEMPOTENT_METHODS and attempt < self.max_retries:
                    attempt += 1
                    self._wait(self._backoff(attempt), f"network error ({exc.__class__.__name__})")
                    continue
                raise TicketForgeError(f"could not reach TicketForge: {exc}") from exc

            self._record_rate_limit(response)
            if response.is_success:
                return _json(response)

            error = error_from_response(response.status_code, _json(response))
            if attempt < self.max_retries and self._should_retry(method, response, error):
                attempt += 1
                reason = "rate limited" if response.status_code == 429 else "transient server error"
                self._wait(self._retry_delay(response, attempt), reason)
                continue
            if response.status_code == 429 and not isinstance(error, RateLimitError):
                error = RateLimitError(error.message, code=error.code, status=429)
            raise error

    @staticmethod
    def _should_retry(method: str, response: httpx.Response, error: TicketForgeError) -> bool:
        if response.status_code == 429:
            # Rejected before processing, so retrying is safe for any method.
            return True
        transient = error.retryable or response.status_code >= 500 or isinstance(error, ServerError)
        # Retrying a POST could create a duplicate ticket.
        return transient and method in IDEMPOTENT_METHODS

    def _record_rate_limit(self, response: httpx.Response) -> None:
        headers = response.headers
        if "x-ratelimit-remaining" not in headers:
            return
        try:
            self.rate_limit = int(headers.get("x-ratelimit-limit", 0)) or None
            self.rate_remaining = int(headers["x-ratelimit-remaining"])
        except ValueError:
            return
        self.rate_reset = _parse_reset(headers.get("x-ratelimit-reset"))

    def _wait_if_exhausted(self) -> None:
        if self.rate_remaining is None or self.rate_remaining > 0 or self.rate_reset is None:
            return
        delay = (self.rate_reset - datetime.now(timezone.utc)).total_seconds()
        if delay > 0:
            self._wait(min(delay, MAX_WAIT_SECONDS), "rate limit reached")
        self.rate_remaining = None

    def _retry_delay(self, response: httpx.Response, attempt: int) -> float:
        retry_after = _parse_retry_after(response.headers.get("retry-after"))
        if retry_after is not None:
            return min(retry_after, MAX_WAIT_SECONDS)
        reset = _parse_reset(response.headers.get("x-ratelimit-reset"))
        if reset is not None:
            delay = (reset - datetime.now(timezone.utc)).total_seconds()
            if delay > 0:
                return min(delay, MAX_WAIT_SECONDS)
        return self._backoff(attempt)

    @staticmethod
    def _backoff(attempt: int) -> float:
        return min(0.5 * 2.0 ** (attempt - 1) + random.uniform(0, 0.25), MAX_WAIT_SECONDS)

    def _wait(self, seconds: float, reason: str) -> None:
        if self._on_wait:
            self._on_wait(seconds, reason)
        self._sleep(seconds)

    # ------------------------------------------------------------- endpoints

    def register(self, username: str, password: str) -> Any:
        return self.request(
            "POST", "/user/register", json={"username": username, "password": password}
        )

    def verify_credentials(self) -> None:
        self.request("GET", "/workitems/mine", params={"limit": 1})

    def list_page(self, *, limit: int = MAX_PAGE_SIZE, cursor: str | None = None) -> Page:
        params: dict[str, Any] = {"limit": max(1, min(int(limit), MAX_PAGE_SIZE))}
        if cursor:
            params["cursor"] = cursor
        data = self.request("GET", "/workitems/mine", params=params)
        pagination = data.get("pagination") or {}
        return Page(
            items=[WorkItem.from_api(w) for w in data.get("workitems") or []],
            has_more=bool(pagination.get("hasMore")),
            next_cursor=pagination.get("nextCursor"),
        )

    def iter_workitems(self, *, cursor: str | None = None) -> Iterator[WorkItem]:
        while True:
            page = self.list_page(cursor=cursor)
            yield from page.items
            if not page.has_more or not page.next_cursor:
                return
            cursor = page.next_cursor

    def get_workitem(self, ref: str, *, deep: bool = True) -> WorkItem:
        params = {"view": "deep"} if deep else None
        data = self.request("GET", f"/workitem/{ref}", params=params)
        return WorkItem.from_api(data["workitem"])

    def create_workitem(self, payload: dict[str, Any]) -> WorkItem:
        data = self.request("POST", "/workitem/publish", json=payload)
        return WorkItem.from_api(data["workitem"])

    def update_workitem(self, ref: str, payload: dict[str, Any]) -> WorkItem:
        data = self.request("PUT", f"/workitem/{ref}", json=payload)
        return WorkItem.from_api(data["workitem"])

    def delete_workitem(self, ref: str) -> None:
        self.request("DELETE", f"/workitem/{ref}")

    def list_custom_fields(self) -> list[CustomField]:
        data = self.request("GET", "/custom-fields")
        return [CustomField.from_api(f) for f in data.get("customFields") or []]

    def create_custom_field(self, name: str, label: str) -> CustomField:
        data = self.request("POST", "/custom-fields", json={"name": name, "label": label})
        return CustomField.from_api(data["customField"])

    def update_custom_field(self, field_id: str, label: str) -> CustomField:
        data = self.request("PUT", f"/custom-fields/{field_id}", json={"label": label})
        return CustomField.from_api(data["customField"])

    def delete_custom_field(self, field_id: str) -> None:
        self.request("DELETE", f"/custom-fields/{field_id}")


def _json(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {}


def _parse_reset(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max((when - datetime.now(timezone.utc)).total_seconds(), 0.0)
