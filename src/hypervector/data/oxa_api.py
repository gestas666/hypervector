"""Shared secret-safe REST boundary for 0xArchive market history."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol

import requests

API_ROOT = "https://api.0xarchive.io/v1/hyperliquid"
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._:-]{0,63}$")


class OxaHistoryError(RuntimeError):
    """An actionable 0xArchive transport or HTTP boundary failure."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class HttpResponse(Protocol):
    """Response fields required by the market-history client."""

    status_code: int

    def json(self) -> object: ...


class HttpSession(Protocol):
    """HTTP session surface required for dependency injection."""

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, int | str],
        timeout: float,
    ) -> HttpResponse: ...


class OxaRestClient:
    """Authenticated GET client that never renders credential material."""

    def __init__(self, *, api_key: str, session: HttpSession | None = None) -> None:
        key = api_key.strip()
        if not key:
            raise ValueError("OXA_API_KEY is required")
        self._api_key = key
        self._session = session or requests.Session()

    def get(
        self,
        path: str,
        *,
        params: dict[str, int | str],
        timeout: float,
    ) -> object:
        """Fetch one JSON response or raise a secret-safe boundary error."""
        if not path.startswith("/") or ".." in path:
            raise ValueError("0xArchive API path must be absolute and traversal-free")
        try:
            response = self._session.get(
                f"{API_ROOT}{path}",
                headers={"X-API-Key": self._api_key},
                params=params,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            name = type(exc).__name__
            raise OxaHistoryError(
                f"0xArchive network request failed ({name})"
            ) from None
        if response.status_code != 200:
            raise OxaHistoryError(
                f"0xArchive request failed with HTTP {response.status_code}",
                status_code=response.status_code,
            )
        try:
            return response.json()
        except ValueError:
            raise OxaHistoryError("0xArchive response contained invalid JSON") from None


def validate_symbol(symbol: str) -> None:
    """Reject identifiers that are unsafe or outside core venue syntax."""
    if not _SYMBOL_PATTERN.fullmatch(symbol):
        raise ValueError("symbol must be an uppercase Hyperliquid asset identifier")


def validate_window(start: datetime, end: datetime) -> None:
    """Require an increasing window expressed with canonical UTC tzinfo."""
    if start.tzinfo is not UTC or end.tzinfo is not UTC:
        raise ValueError("start and end must use the UTC timezone")
    if end <= start:
        raise ValueError("end must be after start")


def parse_utc_timestamp_ms(value: str, *, label: str) -> int:
    """Parse one ISO-8601 UTC timestamp into Unix milliseconds."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"invalid {label}: {value!r}") from exc
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError(f"{label} must be UTC")
    return int(parsed.timestamp() * 1000)


def positive_decimal(value: str, *, label: str) -> Decimal:
    """Parse a finite positive decimal string without changing its text."""
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{label} contains an invalid decimal") from exc
    if not number.is_finite() or number <= 0:
        raise ValueError(f"{label} must be positive")
    return number
