"""Read-only pagination for official Hyperliquid funding history."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from hypervector.research.cohort_eligible_policy_funding import (
    EligiblePolicyFundingEvidence,
    EligiblePolicyFundingEvent,
    parse_official_funding_history,
)

_OFFICIAL_PAGE_SIZE = 500


class HyperliquidFundingInfo(Protocol):
    """Minimal public SDK boundary used by the funding observer."""

    def funding_history(
        self,
        name: str,
        start_time: int,
        end_time: int | None = None,
    ) -> object:
        """Return official funding settlements for one bounded interval."""


class HyperliquidFundingHistoryReader:
    """Collect one complete bounded funding window with no execution authority."""

    def __init__(self, info: HyperliquidFundingInfo) -> None:
        self._info = info

    def read(
        self,
        symbol: str,
        requested_start_ms: int,
        requested_end_ms: int,
    ) -> EligiblePolicyFundingEvidence:
        """Read and validate every official page in the requested window."""
        _validate_request(symbol, requested_start_ms, requested_end_ms)
        cursor = requested_start_ms
        events: list[EligiblePolicyFundingEvent] = []
        while cursor <= requested_end_ms:
            raw = self._info.funding_history(
                symbol,
                cursor,
                requested_end_ms,
            )
            rows = _funding_rows(raw)
            page = parse_official_funding_history(
                rows,
                symbol=symbol,
                requested_start_ms=requested_start_ms,
                requested_end_ms=requested_end_ms,
            )
            events.extend(page.events)
            if len(rows) < _OFFICIAL_PAGE_SIZE:
                break
            cursor = page.events[-1].timestamp_ms + 1
        return EligiblePolicyFundingEvidence(
            symbol=symbol,
            requested_start_ms=requested_start_ms,
            requested_end_ms=requested_end_ms,
            events=tuple(events),
        )


def _funding_rows(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list):
        raise ValueError("official funding-history response must be a list")
    if not all(isinstance(row, Mapping) for row in value):
        raise ValueError("official funding-history rows must be objects")
    return tuple(row for row in value if isinstance(row, Mapping))


def _validate_request(symbol: str, start_ms: int, end_ms: int) -> None:
    if not symbol.strip():
        raise ValueError("funding-history symbol must be non-empty")
    if (
        type(start_ms) is not int
        or type(end_ms) is not int
        or start_ms < 0
        or end_ms < start_ms
    ):
        raise ValueError("funding-history bounds are invalid")
