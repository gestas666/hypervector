from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hypervector.research.hip3_liquidity_snapshot import (
    build_hip3_liquidity_snapshot,
)


def test_snapshot_ranks_active_markets_and_preserves_exclusions() -> None:
    metadata = {
        "universe": [
            {"name": "xyz:LOW", "maxLeverage": 10},
            {"name": "xyz:HIGH", "maxLeverage": 20},
            {"name": "xyz:OLD", "maxLeverage": 5, "isDelisted": True},
        ]
    }
    contexts = [
        {"dayNtlVlm": "10", "markPx": "2", "openInterest": "3"},
        {"dayNtlVlm": "30", "markPx": "4", "openInterest": "5"},
        {"dayNtlVlm": "100", "markPx": "8", "openInterest": "9"},
    ]

    report = build_hip3_liquidity_snapshot(
        dex="xyz",
        metadata=metadata,
        contexts=contexts,
        observed_at_utc=datetime(2026, 8, 17, tzinfo=UTC),
    )

    assert report["status"] == "observed"
    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "credentials_loaded": False,
        "execution_client_constructed": False,
        "automatic_live_change": False,
    }
    assert [row["symbol"] for row in report["markets"]] == [
        "xyz:HIGH",
        "xyz:LOW",
    ]
    assert [row["volume_rank"] for row in report["markets"]] == [1, 2]
    assert report["markets"][0]["open_interest_notional_usd"] == 20.0
    assert report["excluded_delisted_symbols"] == ["xyz:OLD"]


def test_snapshot_rejects_misaligned_market_contexts() -> None:
    with pytest.raises(ValueError, match="lengths differ"):
        build_hip3_liquidity_snapshot(
            dex="xyz",
            metadata={"universe": [{"name": "xyz:ONE", "maxLeverage": 10}]},
            contexts=[],
            observed_at_utc=datetime(2026, 8, 17, tzinfo=UTC),
        )
