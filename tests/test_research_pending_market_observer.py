"""Fail-closed tests for data-complete assets without validated entry routes."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.live.research_pending_market_observer import (
    RESEARCH_PENDING_MARKET_OBSERVER_STRATEGY,
    ResearchPendingMarketObserverCollector,
)


def test_observer_advances_completed_bars_without_emitting_entry_intents() -> None:
    """Healthy market data must remain visible while execution stays impossible."""
    collector = ResearchPendingMarketObserverCollector()
    bars = _bars()
    prior = int(pd.Timestamp("2026-09-01T00:15:00Z").timestamp() * 1_000)

    result = collector(
        bars,
        symbol="LTC",
        observed_at=pd.Timestamp("2026-09-01T00:45:00Z"),
        after_decision_time_ms=prior,
    )

    assert result.intents == ()
    assert result.latest_decision_time_ms == int(
        pd.Timestamp("2026-09-01T00:45:00Z").timestamp() * 1_000
    )
    assert len(result.evaluations) == 2
    assert {row.strategy_id for row in result.evaluations} == {
        RESEARCH_PENDING_MARKET_OBSERVER_STRATEGY
    }
    assert {row.symbol for row in result.evaluations} == {"LTC"}
    assert all(not row.eligible for row in result.evaluations)
    assert all(row.decision_action == "observe_only" for row in result.evaluations)
    assert all(
        row.reason == "strategy_validation_pending" for row in result.evaluations
    )
    assert all(
        row.backend_non_action_reason == "execution_authority_none"
        for row in result.evaluations
    )


def test_observer_does_not_invent_a_boundary_without_a_new_completed_bar() -> None:
    """A poll between 15-minute closes must preserve the prior causal cursor."""
    collector = ResearchPendingMarketObserverCollector()
    prior = int(pd.Timestamp("2026-09-01T00:45:00Z").timestamp() * 1_000)

    result = collector(
        _bars(),
        symbol="ETH",
        observed_at=pd.Timestamp("2026-09-01T00:46:00Z"),
        after_decision_time_ms=prior,
    )

    assert result.intents == ()
    assert result.evaluations == ()
    assert result.latest_decision_time_ms == prior


def test_observer_rejects_naive_or_incomplete_market_data() -> None:
    """Malformed input must fail rather than produce success-shaped telemetry."""
    collector = ResearchPendingMarketObserverCollector()
    naive = _bars()
    naive["timestamp"] = naive["timestamp"].dt.tz_localize(None)

    with pytest.raises(ValueError, match="aware, unique, and ordered"):
        collector(
            naive,
            symbol="xyz:BBB",
            observed_at=pd.Timestamp("2026-09-01T00:45:00Z"),
            after_decision_time_ms=0,
        )
    with pytest.raises(ValueError, match="missing columns"):
        collector(
            _bars().drop(columns="volume"),
            symbol="xyz:BBB",
            observed_at=pd.Timestamp("2026-09-01T00:45:00Z"),
            after_decision_time_ms=0,
        )


def _bars() -> pd.DataFrame:
    """Return three complete 15-minute bars with open timestamps."""
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2026-09-01T00:00:00Z",
                periods=3,
                freq="15min",
            ),
            "open": [50.0, 51.0, 52.0],
            "high": [51.0, 52.0, 53.0],
            "low": [49.0, 50.0, 51.0],
            "close": [50.5, 51.5, 52.5],
            "volume": [10.0, 11.0, 12.0],
        }
    )
