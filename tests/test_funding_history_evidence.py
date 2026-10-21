"""Tests for official funding-history evidence and path funding cost."""

from __future__ import annotations

import pytest

import hypervector.live.hyperliquid_funding_history as funding_module
from hypervector.live.hyperliquid_funding_history import (
    FundingHistoryEvidence,
    FundingSettlement,
    covered_funding_bps,
)


def test_official_history_parser_preserves_exact_settlement_rows() -> None:
    """Official string rates become ordered, bounded funding events."""
    parser = getattr(funding_module, "parse_official_funding_history", None)
    if parser is None:
        pytest.fail("official funding-history parser is unavailable")
    rows = [
        {
            "coin": "ETH",
            "fundingRate": "0.0000125",
            "premium": "-0.0003",
            "time": 120_000,
        },
        {
            "coin": "ETH",
            "fundingRate": "-0.0000025",
            "premium": "0.0001",
            "time": 60_000,
        },
    ]

    evidence = parser(
        rows,
        symbol="ETH",
        requested_start_ms=1,
        requested_end_ms=180_000,
    )

    assert [event.timestamp_ms for event in evidence.events] == [60_000, 120_000]
    assert [event.funding_rate for event in evidence.events] == pytest.approx(
        [-0.0000025, 0.0000125]
    )
    assert evidence.symbol == "ETH"


def test_covered_funding_bps_is_signed_by_position_side_and_requires_coverage() -> None:
    """A long pays positive funding; an uncovered window reports no estimate."""
    evidence = FundingHistoryEvidence(
        symbol="ETH",
        requested_start_ms=0,
        requested_end_ms=10_000,
        events=(FundingSettlement(5_000, 0.0001),),
    )
    assert covered_funding_bps(
        evidence, symbol="ETH", side="long", start_ms=0, end_ms=10_000
    ) == pytest.approx(-1.0)
    assert covered_funding_bps(
        evidence, symbol="ETH", side="short", start_ms=0, end_ms=10_000
    ) == pytest.approx(1.0)
    assert (
        covered_funding_bps(
            evidence, symbol="ETH", side="long", start_ms=0, end_ms=20_000
        )
        is None
    )
    with pytest.raises(ValueError, match="symbol"):
        covered_funding_bps(evidence, symbol="BTC", side="long", start_ms=0, end_ms=1)
