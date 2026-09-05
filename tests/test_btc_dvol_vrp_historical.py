"""Tests for chronological BTC DVOL-VRP experiment orchestration."""

from __future__ import annotations

import pandas as pd
import pytest

from btc_dvol_vrp_fixtures import dvol_vrp_dvol, dvol_vrp_market
from hypervector.research.btc_dvol_vrp_historical import (
    BtcDvolVrpPartition,
    frozen_btc_dvol_vrp_partitions,
    run_btc_dvol_vrp_historical,
)


def test_frozen_partitions_match_preregistration() -> None:
    """The three half-open windows must retain exact frozen bounds."""
    partitions = frozen_btc_dvol_vrp_partitions()

    assert [value.name for value in partitions] == [
        "development",
        "validation",
        "pseudo_holdout",
    ]
    assert partitions[0].start_utc == pd.Timestamp("2025-07-28T00:00:00Z")
    assert partitions[0].end_utc == pd.Timestamp("2026-01-28T00:00:00Z")
    assert partitions[1].end_utc == pd.Timestamp("2026-04-28T00:00:00Z")
    assert partitions[2].end_utc == pd.Timestamp("2026-07-28T00:00:00Z")


def test_historical_runner_keeps_every_scenario_and_arm() -> None:
    """Causal warmup and partition masks must preserve the 54-cell matrix."""
    bars = dvol_vrp_market(150)
    result = run_btc_dvol_vrp_historical(
        bars,
        dvol_vrp_dvol(bars),
        _short_partitions(),
    )

    assert len(result.report["summary_rows"]) == 54
    assert len(result.report["comparisons"]) == 9
    assert result.report["authority"]["execution_authority"] == "none"


def test_historical_runner_rejects_market_or_dvol_coverage_drift() -> None:
    """Missing terminal market or hourly DVOL evidence must fail closed."""
    bars = dvol_vrp_market(150)
    dvol = dvol_vrp_dvol(bars)
    end = _short_partitions()[-1].end_utc
    truncated = bars.loc[bars.index < end - pd.Timedelta(minutes=1)]

    with pytest.raises(ValueError, match="source end is incomplete"):
        run_btc_dvol_vrp_historical(truncated, dvol, _short_partitions())
    with pytest.raises(ValueError, match="DVOL coverage"):
        run_btc_dvol_vrp_historical(bars, dvol.iloc[:-1], _short_partitions())


def _short_partitions() -> tuple[BtcDvolVrpPartition, ...]:
    boundaries = pd.to_datetime(
        [
            "2026-08-03T12:00:00Z",
            "2026-08-04T00:00:00Z",
            "2026-08-04T12:00:00Z",
            "2026-08-05T00:00:00Z",
        ],
        utc=True,
    )
    names = ("development", "validation", "pseudo_holdout")
    return tuple(
        BtcDvolVrpPartition(names[index], boundaries[index], boundaries[index + 1])
        for index in range(3)
    )
