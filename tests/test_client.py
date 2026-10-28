import base64
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from ticketforge_cli.errors import (
    AuthError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    ServerError,
    ValidationError,
)

from .conftest import workitem


def err(code, message="boom", status=400, retryable=False, headers=None):
    return httpx.Response(
        status, json={"err": code, "message": message, "retryable": retryable}, headers=headers
    )


def test_sends_basic_auth(client, api):
    route = api.get("/workitems/mine").respond(json={"workitems": [], "pagination": {}})
    client.verify_credentials()
    expected = "Basic " + base64.b64encode(b"alice:pw").decode()
    assert route.calls.last.request.headers["authorization"] == expected
    assert route.calls.last.request.url.params["limit"] == "1"


@pytest.mark.parametrize(
    ("status", "code", "exc"),
    [
        (401, "unauthorized", AuthError),
        (400, "not_found", NotFoundError),
        (400, "forbidden", ForbiddenError),
        (400, "invalid_input", ValidationError),
        (400, "duplicate", ValidationError),
        (400, "invalid_cursor", ValidationError),
    ],
)
def test_maps_errors_by_err_code_not_status(client, api, status, code, exc):
    api.get("/workitem/TF-9").mock(return_value=err(code, "nope", status=status))
    with pytest.raises(exc) as info:
        client.get_workitem("TF-9")
    assert info.value.message == "nope"
    assert info.value.code == code


def test_list_page_parses_pagination_and_clamps_limit(client, api):
    route = api.get("/workitems/mine").respond(
        json={
            "workitems": [workitem("TF-2"), workitem("TF-1")],
            "pagination": {"limit": 5, "hasMore": True, "nextCursor": "t:id"},
        }
    )
    page = client.list_page(limit=50)
    assert [w.ref for w in page.items] == ["TF-2", "TF-1"]
    assert page.has_more and page.next_cursor == "t:id"
    assert route.calls.last.request.url.params["limit"] == "5"


def test_iter_workitems_follows_cursor(client, api):
    def handler(request):
        if "cursor" not in request.url.params:
            return httpx.Response(
                200,
                json={
                    "workitems": [workitem("TF-3"), workitem("TF-2")],
                    "pagination": {"hasMore": True, "nextCursor": "c1"},
                },
            )
        assert request.url.params["cursor"] == "c1"
        return httpx.Response(
            200, json={"workitems": [workitem("TF-1")], "pagination": {"hasMore": False}}
        )

    api.get("/workitems/mine").mock(side_effect=handler)
    assert [w.ref for w in client.iter_workitems()] == ["TF-3", "TF-2", "TF-1"]


def test_429_honors_retry_after(client, api, sleeps):
    route = api.get("/custom-fields").mock(
        side_effect=[
            err("rate_limited", status=429, headers={"Retry-After": "3"}),
            httpx.Response(200, json={"customFields": []}),
        ]
    )
    assert client.list_custom_fields() == []
    assert route.call_count == 2
    assert sleeps == [3.0]


def test_429_falls_back_to_reset_header(client, api, sleeps):
    reset = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat()
    api.get("/custom-fields").mock(
        side_effect=[
            httpx.Response(429, headers={"x-ratelimit-reset": reset}),
            httpx.Response(200, json={"customFields": []}),
        ]
    )
    client.list_custom_fields()
    assert len(sleeps) == 1 and 8 < sleeps[0] <= 10


def test_429_is_retried_even_for_post(client, api):
    route = api.post("/workitem/publish").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(200, json={"workitem": workitem("TF-7")}),
        ]
    )
    assert client.create_workitem({"title": "x"}).ref == "TF-7"
    assert route.call_count == 2


def test_gives_up_after_max_retries(client, api, sleeps):
    route = api.get("/custom-fields").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "1"})
    )
    with pytest.raises(RateLimitError):
        client.list_custom_fields()
    assert route.call_count == client.max_retries + 1
    assert len(sleeps) == client.max_retries


def test_retryable_error_is_retried_for_get(client, api, sleeps):
    api.get("/custom-fields").mock(
        side_effect=[
            err("server_error", retryable=True),
            httpx.Response(200, json={"customFields": []}),
        ]
    )
    client.list_custom_fields()
    assert len(sleeps) == 1


def test_retryable_error_is_not_retried_for_post(client, api):
    route = api.post("/workitem/publish").mock(return_value=err("server_error", retryable=True))
    with pytest.raises(ServerError):
        client.create_workitem({"title": "x"})
    assert route.call_count == 1


def test_waits_for_reset_when_quota_exhausted(client, api, sleeps):
    reset = (datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat()
    api.get("/custom-fields").mock(
        return_value=httpx.Response(
            200,
            json={"customFields": []},
            headers={
                "x-ratelimit-limit": "50",
                "x-ratelimit-remaining": "0",
                "x-ratelimit-reset": reset,
            },
        )
    )
    client.list_custom_fields()
    assert sleeps == []
    client.list_custom_fields()
    assert len(sleeps) == 1 and 3 < sleeps[0] <= 5


def test_network_errors_retry_for_get(client, api, sleeps):
    api.get("/custom-fields").mock(
        side_effect=[httpx.ConnectError("down"), httpx.Response(200, json={"customFields": []})]
    )
    client.list_custom_fields()
    assert len(sleeps) == 1
