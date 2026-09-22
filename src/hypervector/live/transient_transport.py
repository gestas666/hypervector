"""Explicit classification for retry-exhausted read-only venue failures."""

from __future__ import annotations

from hyperliquid.utils.error import ClientError, ServerError  # type: ignore[import-untyped]
from requests import ConnectionError, HTTPError, RequestException, Timeout

from hypervector.live.multi_asset_market_bars import TransientCohortMarketDataError

_RECOVERABLE_HTTP_SERVER_STATUSES = frozenset({500, 502, 503, 504})


def transient_read_failure_reason(exc: Exception) -> str | None:
    """Return a retry reason only for transport failures safe to retry later."""
    if isinstance(exc, HTTPError):
        response = exc.response
        if response is None:
            return None
        if response.status_code == 429:
            return "http_429_retry_exhausted"
        if response.status_code in _RECOVERABLE_HTTP_SERVER_STATUSES:
            return "http_server_retry_exhausted"
        return None
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


def raise_if_transient_read_failure(error: Exception, source: str) -> None:
    """Classify an exhausted transport failure anywhere in its cause chain."""
    current: BaseException | None = error
    visited: set[int] = set()
    while isinstance(current, Exception) and id(current) not in visited:
        visited.add(id(current))
        reason = transient_read_failure_reason(current)
        if reason is not None:
            raise TransientCohortMarketDataError(
                source=source,
                reason=reason,
            ) from error
        current = current.__cause__ or current.__context__
