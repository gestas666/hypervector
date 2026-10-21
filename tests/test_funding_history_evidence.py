"""Tests for official eligible-policy funding evidence."""

from __future__ import annotations

import pytest

import hypervector.research.cohort_eligible_policy_funding as funding_module


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
