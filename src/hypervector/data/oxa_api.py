"""Shared secret-safe REST boundary for 0xArchive market history."""

from __future__ import annotations

import math
import random
import re
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Literal, Protocol

import requests

API_ROOT = "https://api.0xarchive.io/v1/hyperliquid"
DEFAULT_MAX_ATTEMPTS = 5
_BACKOFF_BASE_SECONDS = 0.5
_BACKOFF_CAP_SECONDS = 8.0
_RETRY_AFTER_CAP_SECONDS = 60.0
_RETRYABLE_TRANSPORT_ERRORS = (
    requests.ConnectionError,
    requests.Timeout,
    requests.exceptions.ChunkedEncodingError,
)
MarketFamily = Literal["core", "hip3"]
# Core perps are uppercase venue names, except HL's case-sensitive 1000x
# contracts: one lowercase "k" then an uppercase asset (kPEPE, kSHIB, kBONK).
_CORE_SYMBOL = r"k?[A-Z0-9][A-Z0-9._-]{0,63}"
# HIP-3 builder perps: exact lowercase dex, colon, uppercase asset (xyz:TSLA).
_HIP3_SYMBOL = (
    r"(?P<dex>[a-z0-9][a-z0-9._-]{0,31}):"
    r"(?P<asset>[A-Z0-9][A-Z0-9._-]{0,63})"
)
_CORE_SYMBOL_PATTERN = re.compile(rf"^{_CORE_SYMBOL}$")
_HIP3_SYMBOL_PATTERN = re.compile(rf"^{_HIP3_SYMBOL}$")
#: Any exact Hyperliquid perp identity: core (incl. k-prefixed) or HIP-3.
_SYMBOL_PATTERN = re.compile(rf"^(?:{_CORE_SYMBOL}|{_HIP3_SYMBOL})$")
_CORE_SYMBOL_ERROR = (
    "symbol must be an uppercase Hyperliquid asset identifier "
    "(or a k-prefixed 1000x coin such as kPEPE)"
)


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


class JitterSource(Protocol):
    """Random source used for full-jitter retry backoff."""

    def uniform(self, a: float, b: float) -> float: ...


class OxaRestClient:
    """Authenticated GET client that never renders credential material.

    Transient failures (HTTP 429, HTTP 5xx, connection errors, timeouts and
    truncated bodies) are retried in place with bounded full-jitter backoff
    that honours a numeric ``Retry-After``, so one blip does not discard every
    page already fetched. Other statuses and request errors fail immediately.
    """

    def __init__(
        self,
        *,
        api_key: str,
        session: HttpSession | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        sleep: Callable[[float], None] | None = None,
        rng: JitterSource | None = None,
    ) -> None:
        key = api_key.strip()
        if not key:
            raise ValueError("OXA_API_KEY is required")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._api_key = key
        self._session = session or requests.Session()
        self._max_attempts = max_attempts
        self._sleep = sleep
        self._rng: JitterSource = rng or random.Random()

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
        for attempt in range(1, self._max_attempts + 1):
            retry_after: float | None = None
            try:
                response = self._session.get(
                    f"{API_ROOT}{path}",
                    headers={"X-API-Key": self._api_key},
                    params=params,
                    timeout=timeout,
                )
            except _RETRYABLE_TRANSPORT_ERRORS as exc:
                failure = _network_failure(exc)
            except requests.RequestException as exc:
                raise _network_failure(exc) from None
            else:
                status = response.status_code
                if status == 200:
                    try:
                        return response.json()
                    except ValueError:
                        raise OxaHistoryError(
                            "0xArchive response contained invalid JSON"
                        ) from None
                failure = OxaHistoryError(
                    f"0xArchive request failed with HTTP {status}",
                    status_code=status,
                )
                if not _retryable_status(status):
                    raise failure
                retry_after = _retry_after_seconds(response)
            if attempt == self._max_attempts:
                raise failure
            self._pause(attempt, retry_after)
        raise RuntimeError("unreachable 0xArchive retry state")

    def _pause(self, attempt: int, retry_after: float | None) -> None:
        ceiling = min(
            _BACKOFF_CAP_SECONDS, _BACKOFF_BASE_SECONDS * 2 ** (attempt - 1)
        )
        delay = self._rng.uniform(0.0, ceiling)
        if retry_after is not None:
            delay = max(min(retry_after, _RETRY_AFTER_CAP_SECONDS), delay)
        sleep = self._sleep if self._sleep is not None else time.sleep
        sleep(delay)


def _network_failure(exc: BaseException) -> OxaHistoryError:
    return OxaHistoryError(f"0xArchive network request failed ({type(exc).__name__})")


def _retryable_status(status: int) -> bool:
    return status == 429 or status >= 500


def _retry_after_seconds(response: object) -> float | None:
    """Return a finite, non-negative numeric Retry-After, ignoring dates."""
    headers = getattr(response, "headers", None) or {}
    if not isinstance(headers, Mapping):
        return None
    value = headers.get("Retry-After", headers.get("retry-after"))
    if value is None:
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(seconds) or seconds < 0:
        return None
    return seconds


def validate_symbol(symbol: str) -> None:
    """Reject identifiers that are unsafe or not an exact Hyperliquid perp name.

    Accepts uppercase core names, HL's case-sensitive k-prefixed 1000x coins
    (``kPEPE``) and HIP-3 ``dex:ASSET`` identities (``xyz:TSLA``). Lowercase or
    mixed-case core names, a capitalised dex or a lowercase asset are refused.
    """
    if not isinstance(symbol, str) or not _SYMBOL_PATTERN.fullmatch(symbol):
        raise ValueError(
            "symbol must be an uppercase Hyperliquid asset identifier, a "
            "k-prefixed 1000x coin (kPEPE) or a HIP-3 lower-dex:UPPER-ASSET"
        )


def validate_core_symbol(symbol: str) -> None:
    """Require a core-perp identity (uppercase, or k-prefixed); never ``dex:ASSET``."""
    if not isinstance(symbol, str) or not _CORE_SYMBOL_PATTERN.fullmatch(symbol):
        raise ValueError(_CORE_SYMBOL_ERROR)


def validate_hip3_symbol(symbol: str) -> tuple[str, str]:
    """Validate and split one exact builder-deployed ``dex:ASSET`` identity."""
    match = _HIP3_SYMBOL_PATTERN.fullmatch(symbol)
    if match is None:
        raise ValueError("HIP-3 symbol must use exact lower-dex:UPPER-ASSET identity")
    return match.group("dex"), match.group("asset")


def validate_market_symbol(symbol: str, market_family: MarketFamily) -> None:
    """Require a symbol whose syntax matches its explicit venue family."""
    if market_family == "core":
        validate_core_symbol(symbol)
        return
    if market_family == "hip3":
        validate_hip3_symbol(symbol)
        return
    raise ValueError(f"unsupported 0xArchive market family: {market_family!r}")


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
