"""Complete bounded unsigned user-funding reads with inclusive-page deduplication."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from hypervector.live.hyperliquid_parsing import (
    HyperliquidAdapterError,
    mapping,
    nonnegative_integer,
    sequence,
    text,
)

_PAGE_SIZE = 500
_FundingIdentity = tuple[str, int, str]


class UserFundingInfo(Protocol):
    """Unsigned SDK boundary for account-wide funding pagination."""

    def user_funding_history(
        self, user: str, startTime: int, endTime: int | None = None
    ) -> object:
        """Return one account funding page at inclusive millisecond bounds."""


def read_user_funding_history(
    info: UserFundingInfo, address: str, start_ms: int, end_ms: int
) -> tuple[Mapping[str, object], ...]:
    """Read every page before a caller filters funding records by symbol."""
    start = nonnegative_integer(start_ms, "funding start_time_ms")
    end = nonnegative_integer(end_ms, "funding end_time_ms")
    if end < start:
        raise HyperliquidAdapterError("funding end must not precede start")
    cursor = start
    retained: dict[_FundingIdentity, Mapping[str, object]] = {}
    while True:
        response = info.user_funding_history(address, startTime=cursor, endTime=end)
        rows = sequence(response, "user funding history")
        timestamps = _retain_page(rows, cursor, end, retained)
        if len(rows) < _PAGE_SIZE:
            break
        latest = max(timestamps)
        if latest <= cursor:
            raise HyperliquidAdapterError(
                "full funding page cannot advance its timestamp"
            )
        cursor = latest
    return tuple(retained.values())


def _retain_page(
    rows: Sequence[object],
    cursor: int,
    end: int,
    retained: dict[_FundingIdentity, Mapping[str, object]],
) -> list[int]:
    timestamps = []
    for value in rows:
        row = mapping(value, "funding record")
        timestamp = nonnegative_integer(row.get("time"), "funding time")
        if not cursor <= timestamp <= end:
            raise HyperliquidAdapterError(
                "funding timestamp lies outside requested window"
            )
        delta = mapping(row.get("delta"), "funding delta")
        identity = (
            text(row.get("hash"), "funding hash"),
            timestamp,
            text(delta.get("coin"), "funding coin"),
        )
        if identity in retained and retained[identity] != row:
            raise HyperliquidAdapterError(
                "conflicting funding rows share a native identity"
            )
        retained[identity] = row
        timestamps.append(timestamp)
    if timestamps != sorted(timestamps):
        raise HyperliquidAdapterError("funding page timestamps must be nondecreasing")
    return timestamps
