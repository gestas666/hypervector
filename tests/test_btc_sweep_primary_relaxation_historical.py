"""Chronological orchestration tests for the frozen BTC replay."""

from __future__ import annotations

import pandas as pd

from hypervector.research.btc_sweep_primary_relaxation_historical import (
    BtcSweepHistoricalPartition,
    run_btc_sweep_primary_relaxation_historical,
)


def test_historical_runner_builds_all_frozen_partition_scenario_cells() -> None:
    """Warmup must not prevent complete three-partition comparative output."""
    bars = _market(hours=216)
    boundaries = pd.date_range("2025-01-01", periods=4, freq="72h", tz="UTC")
    partitions = tuple(
        BtcSweepHistoricalPartition(name, boundaries[index], boundaries[index + 1])
        for index, name in enumerate(("development", "validation", "pseudo_holdout"))
    )
    result = run_btc_sweep_primary_relaxation_historical(bars, partitions)
    rows = result.report["summary_rows"]
    identities = {(row["partition"], row["scenario"], row["arm"]) for row in rows}
    assert len(identities) == 18
    assert result.report["authority"]["execution_authority"] == "none"
    assert result.report["acceptance"]["accepted_for_next_validation_stage"] is False


def test_partition_rejects_naive_or_reversed_bounds() -> None:
    """Chronology is a hard input contract rather than a silent normalization."""
    start = pd.Timestamp("2025-01-01T00:00:00Z")
    try:
        BtcSweepHistoricalPartition("development", start.tz_localize(None), start)
    except ValueError as error:
        assert "timezone-aware" in str(error)
    else:
        raise AssertionError("naive partition boundary was accepted")
    try:
        BtcSweepHistoricalPartition("development", start, start)
    except ValueError as error:
        assert "precede" in str(error)
    else:
        raise AssertionError("reversed partition boundary was accepted")


def _market(hours: int) -> pd.DataFrame:
    hourly_index = pd.date_range("2025-01-01", periods=hours, freq="1h", tz="UTC")
    hourly = pd.DataFrame(index=hourly_index)
    hourly["close"] = [120.0 + 0.05 * position for position in range(hours)]
    hourly["open"] = hourly["close"] - 0.025
    hourly["high"] = hourly["close"] + 0.1
    hourly["low"] = hourly["open"] - 0.1
    hourly["volume"] = 60.0
    for position in (60, 132, 204):
        hourly.iloc[position, hourly.columns.get_loc("volume")] = 120.0
    bars = _expand_hours(hourly)
    bars["funding_rate"] = 0.0
    return bars


def _expand_hours(hourly: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, float]] = []
    timestamps: list[pd.Timestamp] = []
    for timestamp, row in hourly.iterrows():
        for minute in range(60):
            timestamps.append(timestamp + pd.Timedelta(minutes=minute))
            records.append(
                {
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]) / 60.0,
                }
            )
    return pd.DataFrame(records, index=pd.DatetimeIndex(timestamps))
