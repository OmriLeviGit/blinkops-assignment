from __future__ import annotations


class TicketForgeError(Exception):
    """Base error for anything that goes wrong talking to TicketForge."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.retryable = retryable


class ConfigError(TicketForgeError):
    """The CLI is not configured, or the config file is unreadable."""


class AuthError(TicketForgeError):
    """Credentials are missing or rejected."""


class NotFoundError(TicketForgeError):
    pass


class ForbiddenError(TicketForgeError):
    pass


class ValidationError(TicketForgeError):
    """The server (or the CLI, before sending) rejected the input."""


class RateLimitError(TicketForgeError):
    """Rate limit still exceeded after all retries."""


class ServerError(TicketForgeError):
    pass


# TicketForge returns HTTP 400 for nearly every failure, so the `err` field in
# the body is the only reliable way to tell them apart.
_ERR_CODES: dict[str, type[TicketForgeError]] = {
    "unauthorized": AuthError,
    "not_found": NotFoundError,
    "forbidden": ForbiddenError,
    "invalid_input": ValidationError,
    "missing_fields": ValidationError,
    "duplicate": ValidationError,
    "invalid_cursor": ValidationError,
    "server_error": ServerError,
}


def error_from_response(status: int, body: object) -> TicketForgeError:
    code = message = None
    retryable = False
    if isinstance(body, dict):
        code = body.get("err")
        message = body.get("message")
        retryable = bool(body.get("retryable", False))

    if status == 401:
        cls: type[TicketForgeError] = AuthError
    elif status == 429:
        cls = RateLimitError
    elif code in _ERR_CODES:
        cls = _ERR_CODES[code]
    elif status >= 500:
        cls = ServerError
    else:
        cls = TicketForgeError

    if not message:
        message = code or f"HTTP {status}"
    return cls(message, code=code, status=status, retryable=retryable)
