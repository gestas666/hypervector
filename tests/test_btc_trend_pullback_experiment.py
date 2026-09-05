from __future__ import annotations

import importlib

import pandas as pd

from btc_trend_pullback_fixtures import partitioned_market


_REGISTERED_METRICS = {
    "raw_signal_count",
    "completed_trades",
    "wins",
    "losses",
    "net_pnl_usd",
    "profit_factor",
    "maximum_drawdown_pct",
    "net_pnl_excluding_largest_winner_usd",
    "fees_usd",
    "funding_usd",
    "liquidations",
    "same_bar_ambiguities",
    "gap_expired_entries",
    "forced_end_exits",
    "median_interarrival_hours",
    "events_per_week",
    "long_route_overlap_and_displacement",
}


def test_report_publishes_every_registered_standalone_metric() -> None:
    """Sparse cells retain explicit cadence, cost, and lifecycle fields."""
    historical = importlib.import_module(
        "hypervector.research.btc_trend_pullback_historical"
    )
    bounds = pd.date_range("2025-01-01", periods=4, freq="72h", tz="UTC")
    partitions = tuple(
        historical.BtcTrendPullbackPartition(name, bounds[index], bounds[index + 1])
        for index, name in enumerate(("development", "validation", "pseudo_holdout"))
    )
    result = historical.run_btc_trend_pullback_historical(
        partitioned_market(), partitions
    )
    assert len(result.report["summary_rows"]) == 18
    for row in result.report["summary_rows"]:
        assert _REGISTERED_METRICS <= set(row)


def test_all_winner_profit_factor_satisfies_above_one_predicate() -> None:
    """An undefined ratio with wins and no losses represents infinite PF."""
    module = importlib.import_module(
        "hypervector.research.btc_trend_pullback_experiment"
    )
    assert module._profit_factor_above_one(
        {"profit_factor": None, "wins": 2, "losses": 0}
    )
    assert not module._profit_factor_above_one(
        {"profit_factor": None, "wins": 0, "losses": 0}
    )
