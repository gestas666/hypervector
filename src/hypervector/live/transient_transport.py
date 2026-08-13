"""Explicit classification for retry-exhausted read-only venue failures."""

from __future__ import annotations

from hyperliquid.utils.error import ClientError, ServerError  # type: ignore[import-untyped]
from requests import ConnectionError, HTTPError, RequestException, Timeout


def transient_read_failure_reason(exc: Exception) -> str | None:
    """Return a retry reason only for transport failures safe to retry later."""
    if isinstance(exc, HTTPError):
        response = exc.response
        return (
            "http_429_retry_exhausted"
            if response is not None and response.status_code == 429
            else None
        )
    if isinstance(exc, Timeout):
        return "transport_timeout_retry_exhausted"
    if isinstance(exc, ConnectionError):
        return "transport_connection_retry_exhausted"
    if isinstance(exc, RequestException):
        return "transport_request_retry_exhausted"
    if isinstance(exc, ClientError):
        return "http_429_retry_exhausted" if exc.status_code == 429 else None
    if isinstance(exc, ServerError) and exc.status_code >= 500:
        return "http_server_retry_exhausted"
    return None
