from __future__ import annotations

from dataclasses import replace
import importlib

import numpy as np
import pandas as pd


def test_route_priority_and_occupancy_preserve_one_btc_position() -> None:
    """Higher-priority baseline wins conflicts and open BTC displaces later entries."""
    module = importlib.import_module(
        "hypervector.research.btc_trend_pullback_route_competition"
    )
    bars = _bars()
    first = bars.index[10]
    later = bars.index[12]
    events = (
        module.BtcRouteEvent.fixed("sweep", "long", 10, first),
        module.BtcRouteEvent.structural("robust", 20, first, 101.0),
        module.BtcRouteEvent.fixed("candidate", "long", 9, later),
    )
    result = module.evaluate_btc_route_case(bars, events, 2.0)
    assert result.report.maximum_concurrent_positions == 1
    assert result.report.trades[0].signal_name == "robust"
    assert result.same_minute_priority_displacements == 1
    assert result.occupancy_displacements == 1


def test_candidate_case_reconciles_exact_increment_against_baseline() -> None:
    """The candidate delta must equal the two independently reported cases."""
    module = importlib.import_module(
        "hypervector.research.btc_trend_pullback_route_competition"
    )
    bars = _bars()
    baseline = (module.BtcRouteEvent.fixed("sweep", "long", 10, bars.index[10]),)
    candidate = replace(
        baseline[0], strategy_id="candidate", priority=9, signal_time=bars.index[40]
    )
    comparison = module.compare_btc_route_cases(bars, baseline, (candidate,), 2.0)
    expected = (
        comparison.candidate.report.net_pnl_usd - comparison.baseline.report.net_pnl_usd
    )
    assert comparison.incremental_net_pnl_usd == expected
    assert comparison.candidate.report.maximum_concurrent_positions == 1


def test_missing_exact_short_identity_is_explicitly_unavailable() -> None:
    """A missing V58 dependency cannot silently substitute another Hulk route."""
    module = importlib.import_module(
        "hypervector.research.btc_trend_pullback_route_competition"
    )
    result = module.identity_unavailable(("hulk_expansion_short_tuned_v2",))
    assert result == {
        "status": "identity_unavailable",
        "missing_dependencies": ["hulk_expansion_short_tuned_v2"],
        "substitute_profile_used": False,
    }


def _bars() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=90, freq="1min", tz="UTC")
    close = 100.0 + np.linspace(0.0, 0.2, len(index))
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.05,
            "low": close - 0.05,
            "close": close,
            "volume": 1.0,
            "funding_rate": 0.0,
        },
        index=index,
    )
