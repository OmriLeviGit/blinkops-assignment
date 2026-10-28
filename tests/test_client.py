import base64
import json
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest

from ticketforge_cli.client import MAX_WAIT_SECONDS, TicketForgeClient
from ticketforge_cli.errors import (
    AuthError,
    ForbiddenError,
    NotFoundError,
    RateLimitError,
    ServerError,
    TicketForgeError,
    ValidationError,
)

from .conftest import BASE, workitem


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


def test_list_page_sends_the_cursor(client, api):
    route = api.get("/workitems/mine").respond(json={"workitems": [], "pagination": {}})
    client.list_page(cursor="c1")
    assert route.calls.last.request.url.params["cursor"] == "c1"


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


# ------------------------------------------------------------------ error fallbacks


def test_500_with_non_json_body(client, api, sleeps):
    api.get("/custom-fields").mock(return_value=httpx.Response(500, text="<html>oops</html>"))
    with pytest.raises(ServerError, match="HTTP 500"):
        client.list_custom_fields()
    assert len(sleeps) == client.max_retries  # 5xx on a GET is transient


def test_unknown_err_code_falls_back_to_base_error(client, api):
    api.get("/custom-fields").mock(return_value=httpx.Response(400, json={"err": "teapot"}))
    with pytest.raises(TicketForgeError) as info:
        client.list_custom_fields()
    assert type(info.value) is TicketForgeError
    assert info.value.message == "teapot" and info.value.status == 400


def test_network_error_on_post_is_not_retried(client, api, sleeps):
    route = api.post("/workitem/publish").mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(TicketForgeError, match="could not reach TicketForge"):
        client.create_workitem({"title": "x"})
    assert route.call_count == 1 and sleeps == []


def test_network_error_gives_up_after_max_retries(client, api, sleeps):
    api.get("/custom-fields").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(TicketForgeError, match="could not reach"):
        client.list_custom_fields()
    assert len(sleeps) == client.max_retries


# ------------------------------------------------------------------ waits


def test_retry_after_as_http_date(client, api, sleeps):
    when = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=10), usegmt=True)
    api.get("/custom-fields").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": when}),
            httpx.Response(200, json={"customFields": []}),
        ]
    )
    client.list_custom_fields()
    assert len(sleeps) == 1 and 8 < sleeps[0] <= 10


def test_waits_are_capped(client, api, sleeps):
    api.get("/custom-fields").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "3600"}),
            httpx.Response(200, json={"customFields": []}),
        ]
    )
    client.list_custom_fields()
    assert sleeps == [MAX_WAIT_SECONDS]


def test_unparseable_retry_after_falls_back_to_backoff(client, api, sleeps):
    api.get("/custom-fields").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "soon"}),
            httpx.Response(200, json={"customFields": []}),
        ]
    )
    client.list_custom_fields()
    assert len(sleeps) == 1 and 0.5 <= sleeps[0] <= 0.75


def test_malformed_rate_headers_are_ignored(client, api):
    api.get("/custom-fields").respond(
        json={"customFields": []},
        headers={"x-ratelimit-remaining": "lots", "x-ratelimit-reset": "later"},
    )
    client.list_custom_fields()
    assert client.rate_remaining is None


def test_on_wait_is_told_why(api):
    waits = []
    c = TicketForgeClient(
        BASE, "alice", "pw", sleep=lambda s: None, on_wait=lambda s, why: waits.append(why)
    )
    api.get("/custom-fields").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(200, json={"customFields": []}),
        ]
    )
    c.list_custom_fields()
    c.close()
    assert waits == ["rate limited"]


# ------------------------------------------------------------------ endpoints


def test_get_workitem_asks_for_the_deep_view(client, api):
    route = api.get("/workitem/TF-1").respond(json={"workitem": workitem("TF-1")})
    client.get_workitem("TF-1")
    assert route.calls.last.request.url.params["view"] == "deep"


def test_custom_field_endpoints(client, api):
    created = api.post("/custom-fields").respond(
        json={"customField": {"id": "f1", "name": "team", "label": "Team"}}
    )
    updated = api.put("/custom-fields/f1").respond(
        json={"customField": {"id": "f1", "name": "team", "label": "Squad"}}
    )
    deleted = api.delete("/custom-fields/f1").respond(json={})

    assert client.create_custom_field("team", "Team").id == "f1"
    assert json.loads(created.calls.last.request.content) == {"name": "team", "label": "Team"}
    assert client.update_custom_field("f1", "Squad").label == "Squad"
    assert json.loads(updated.calls.last.request.content) == {"label": "Squad"}
    client.delete_custom_field("f1")
    assert deleted.called


def test_delete_workitem_with_empty_response(client, api):
    route = api.delete("/workitem/TF-1").respond(204)
    client.delete_workitem("TF-1")
    assert route.called


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="<html>not the API</html>"),
        httpx.Response(200, json=[1, 2]),
        httpx.Response(200, json={"something": "else"}),
    ],
    ids=["html", "list", "missing-key"],
)
def test_unexpected_success_body_is_an_error(client, api, response):
    api.get("/workitem/TF-1").mock(return_value=response)
    with pytest.raises(TicketForgeError, match="unexpected response"):
        client.get_workitem("TF-1")


def test_verify_credentials_rejects_a_page_that_is_not_the_api(client, api):
    api.get("/workitems/mine").respond(200, text="<html>a web app</html>")
    with pytest.raises(TicketForgeError, match="is the base URL right"):
        client.verify_credentials()
