"""Tests for the read-only official Hyperliquid funding-history reader."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from hypervector.live.hyperliquid_funding_history import (
    HyperliquidFundingHistoryReader,
)


class FakeFundingInfo:
    """Return predeclared funding pages without making network calls."""

    def __init__(self, pages: Sequence[object]) -> None:
        self.pages = list(pages)
        self.calls: list[tuple[str, int, int | None]] = []

    def funding_history(
        self,
        name: str,
        start_time: int,
        end_time: int | None = None,
    ) -> object:
        """Record one SDK-compatible request and return its fake page."""
        self.calls.append((name, start_time, end_time))
        if not self.pages:
            pytest.fail("unexpected funding-history page request")
        return self.pages.pop(0)


def _row(timestamp_ms: int, rate: str = "0.0000125") -> dict[str, object]:
    return {
        "coin": "ETH",
        "fundingRate": rate,
        "premium": "0.0",
        "time": timestamp_ms,
    }


def test_reader_returns_one_complete_bounded_evidence_window() -> None:
    info = FakeFundingInfo([[_row(60_000), _row(120_000, "-0.0000025")]])
    reader = HyperliquidFundingHistoryReader(info)

    evidence = reader.read("ETH", 1, 180_000)

    assert info.calls == [("ETH", 1, 180_000)]
    assert evidence.requested_start_ms == 1
    assert evidence.requested_end_ms == 180_000
    assert [event.timestamp_ms for event in evidence.events] == [60_000, 120_000]
    assert [event.funding_rate for event in evidence.events] == pytest.approx(
        [0.0000125, -0.0000025]
    )


def test_reader_paginates_full_official_pages_without_duplicate_boundaries() -> None:
    first = [_row(timestamp) for timestamp in range(1_000, 501_000, 1_000)]
    second = [_row(501_000)]
    info = FakeFundingInfo([first, second])
    reader = HyperliquidFundingHistoryReader(info)

    evidence = reader.read("ETH", 1, 600_000)

    assert info.calls == [
        ("ETH", 1, 600_000),
        ("ETH", 500_001, 600_000),
    ]
    assert len(evidence.events) == 501
    assert evidence.events[-1].timestamp_ms == 501_000


def test_reader_rejects_success_shaped_non_list_response() -> None:
    reader = HyperliquidFundingHistoryReader(FakeFundingInfo([{"status": "ok"}]))

    with pytest.raises(ValueError, match="must be a list"):
        reader.read("ETH", 1, 180_000)
