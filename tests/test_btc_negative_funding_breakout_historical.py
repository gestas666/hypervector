from __future__ import annotations

import pandas as pd

from hypervector.research.btc_negative_funding_breakout_historical import (
    BtcNegativeFundingBreakoutPartition,
    frozen_btc_negative_funding_breakout_partitions,
    run_btc_negative_funding_breakout_historical,
)

from btc_negative_funding_breakout_fixtures import (
    partitioned_negative_funding_breakout_bars,
)


def test_frozen_partitions_match_preregistration() -> None:
    """Retain the exact opened development, validation, and pseudo-holdout bounds."""
    partitions = frozen_btc_negative_funding_breakout_partitions()
    assert [value.name for value in partitions] == [
        "development",
        "validation",
        "pseudo_holdout",
    ]
    assert partitions[0].start_utc == pd.Timestamp("2025-07-28T00:00:00Z")
    assert partitions[-1].end_utc == pd.Timestamp("2026-07-28T00:00:00Z")


def test_historical_runner_publishes_all_scenarios_without_abort() -> None:
    """Run the full matrix even when its tiny fixture cannot pass acceptance."""
    bars, funding = partitioned_negative_funding_breakout_bars()
    start = bars.index[0]
    partitions = tuple(
        BtcNegativeFundingBreakoutPartition(
            name,
            start + pd.Timedelta(hours=63 * offset),
            start + pd.Timedelta(hours=63 * (offset + 1)),
        )
        for offset, name in enumerate(("development", "validation", "pseudo_holdout"))
    )
    result = run_btc_negative_funding_breakout_historical(
        bars,
        funding,
        partitions,
    )
    assert len(result.report["summary_rows"]) == 27
    assert len(result.report["comparisons"]) == 9
    assert result.report["authority"]["execution_authority"] == "none"
    assert not result.report["acceptance"]["candidate_supported"]
