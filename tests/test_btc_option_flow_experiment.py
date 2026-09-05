"""Tests for complete frozen BTC option-flow experiment orchestration."""

from __future__ import annotations

import pandas as pd

from hypervector.research.btc_option_flow_experiment import (
    OptionFlowPartition,
    run_frozen_option_flow_experiment,
)


def test_experiment_runs_all_arms_scenarios_partitions_and_folds() -> None:
    """The report must be complete, trade-level, and unable to authorize live use."""
    bars = _bars()
    flow = pd.DataFrame(
        {
            "available_at": pd.to_datetime(
                ["2025-01-03T01:01:00Z", "2025-01-03T03:01:00Z"]
            ),
            "long_onset": [True, False],
            "opposing_onset": [False, True],
        }
    )
    partitions = (
        OptionFlowPartition(
            "development",
            pd.Timestamp("2025-01-02T00:00:00Z"),
            pd.Timestamp("2025-01-03T00:00:00Z"),
        ),
        OptionFlowPartition(
            "validation",
            pd.Timestamp("2025-01-03T00:00:00Z"),
            pd.Timestamp("2025-01-04T00:00:00Z"),
        ),
        OptionFlowPartition(
            "pseudo_holdout",
            pd.Timestamp("2025-01-04T00:00:00Z"),
            pd.Timestamp("2025-01-05T00:00:00Z"),
        ),
    )
    fold_hours = (0, 5, 10, 15, 20, 24)
    folds = tuple(
        OptionFlowPartition(
            f"development_fold_{index}",
            pd.Timestamp("2025-01-02T00:00:00Z")
            + pd.Timedelta(hours=fold_hours[index]),
            pd.Timestamp("2025-01-02T00:00:00Z")
            + pd.Timedelta(hours=fold_hours[index + 1]),
        )
        for index in range(5)
    )

    result = run_frozen_option_flow_experiment(
        bars,
        bars.drop(columns=["funding_rate", "gap_before_bars"]),
        flow,
        partitions=partitions,
        development_folds=folds,
        bootstrap_resamples=100,
        bootstrap_seed=58,
    )

    assert len(result.report["summary_rows"]) == 36
    assert len(result.report["development_fold_rows"]) == 5
    assert result.report["authority"]["execution_authority"] == "none"
    assert result.report["acceptance"]["live_promotion_authorized"] is False
    assert (
        result.report["acceptance"]["candidate_supported_for_future_only_capture"]
        is False
    )
    assert all(row["arm"] != "no_action" for row in result.trade_rows)
    assert {row["scenario"] for row in result.trade_rows} <= {
        "nominal",
        "stress",
        "delayed",
    }


def _bars() -> pd.DataFrame:
    index = pd.date_range("2025-01-01T00:00:00Z", periods=7_200, freq="1min")
    return pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "volume": 1.0,
            "source": "hl",
            "funding_rate": 0.0,
            "gap_before_bars": 0,
        },
        index=index,
    )
