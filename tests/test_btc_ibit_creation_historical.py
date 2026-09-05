"""Tests for chronological IBIT creation experiment orchestration."""

from __future__ import annotations

import pandas as pd
import pytest

from btc_ibit_creation_fixtures import ibit_creation_history, ibit_market
from hypervector.research.btc_ibit_creation_historical import (
    BtcIbitCreationPartition,
    frozen_btc_ibit_creation_partitions,
    run_btc_ibit_creation_historical,
)


def test_frozen_partitions_match_preregistration() -> None:
    """The three half-open windows must retain their exact frozen bounds."""
    partitions = frozen_btc_ibit_creation_partitions()

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
    """Warmup and delay mapping must still publish the complete matrix."""
    result = run_btc_ibit_creation_historical(
        ibit_market(100),
        ibit_creation_history(),
        _short_partitions(),
    )

    assert len(result.report["summary_rows"]) == 45
    assert len(result.report["comparisons"]) == 9
    assert result.report["authority"]["execution_authority"] == "none"
    delayed = [
        row
        for row in result.report["summary_rows"]
        if row["partition"] == "pseudo_holdout"
        and row["scenario"] == "publication_delay_24h"
        and row["arm"] == "ibit_two_creation_persistence_candidate"
    ]
    assert delayed[0]["point_in_time_event_times_utc"] == ["2026-08-04T12:00:00+00:00"]


def test_historical_runner_rejects_market_coverage_drift() -> None:
    """A missing terminal minute must fail before any result is accepted."""
    bars = ibit_market(100)
    end = _short_partitions()[-1].end_utc
    truncated = bars.loc[bars.index < end - pd.Timedelta(minutes=1)]

    with pytest.raises(ValueError, match="source end is incomplete"):
        run_btc_ibit_creation_historical(
            truncated,
            ibit_creation_history(),
            _short_partitions(),
        )


def _short_partitions() -> tuple[BtcIbitCreationPartition, ...]:
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
        BtcIbitCreationPartition(names[index], boundaries[index], boundaries[index + 1])
        for index in range(3)
    )
