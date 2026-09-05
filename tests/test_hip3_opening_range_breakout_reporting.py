"""Tests for opening-range development-only disposition rules."""

import json
from types import SimpleNamespace

import pandas as pd

from hypervector.research.hip3_opening_range_breakout_reporting import (
    _strategy_identity,
    opening_range_development_disposition,
)
from hypervector.research.hip3_opening_range_breakout_signals import (
    Hip3OpeningRangeBreakoutConfig,
)
from hypervector.research.mu_hip3_candidate import MuPartitionResult
from hypervector.research.shared_portfolio_models import SharedPortfolioReport


def _empty_report() -> SharedPortfolioReport:
    return SharedPortfolioReport(
        initial_equity=5000.0,
        final_equity=5000.0,
        net_pnl_usd=0.0,
        return_pct=0.0,
        maximum_drawdown_pct=0.0,
        completed_trades=0,
        wins=0,
        losses=0,
        gross_profit_usd=0.0,
        gross_loss_usd=0.0,
        profit_factor=None,
        liquidations=0,
        total_fees_usd=0.0,
        funding_cashflow_usd=0.0,
        conflicting_entry_signals=0,
        maximum_concurrent_positions=0,
        forced_end_exits=0,
        barrier_invalidated_entries=0,
        insolvent=False,
        monthly_net_pnl_usd={},
        limitations=(),
        trades=(),
    )


def test_zero_trade_development_cannot_be_success_shaped() -> None:
    start = pd.Timestamp("2026-06-08T08:00:00Z")
    end = pd.Timestamp("2026-07-16T16:15:00Z")
    report = _empty_report()
    partition = MuPartitionResult("development", start, end, report, report)
    folds = tuple(
        MuPartitionResult(f"development_fold_{index}", start, end, report, report)
        for index in range(1, 4)
    )

    disposition = opening_range_development_disposition(
        partition, folds, {"status": "resolved"}
    )

    assert disposition["status"] == "NOT_SUITABLE_DEVELOPMENT_ECONOMICS"
    assert disposition["checks"]["nominal_profit_factor_above_one"] is False
    assert disposition["checks"]["both_directions_observed"] is False
    assert disposition["live_change_proposed"] is False


def test_strategy_identity_serializes_frozen_holidays_as_iso_dates() -> None:
    """Immutable evidence cannot retain Python-only date objects."""
    result = SimpleNamespace(
        proposed_provider_id="provider",
        proposed_profile_id="profile",
        signal=Hip3OpeningRangeBreakoutConfig(clearance_bps=20.0),
    )

    identity = _strategy_identity(result)

    json.dumps(identity)
    assert identity["config"]["closed_session_dates"] == [
        "2026-06-19",
        "2026-07-03",
    ]
