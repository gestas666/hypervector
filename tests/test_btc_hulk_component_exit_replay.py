"""Report-only economics for the versioned BTC component exit."""

from __future__ import annotations

import pytest

from hypervector.cohort_profit_lock_policy import ProfitLockTrigger
from hypervector.research.btc_hulk_component_exit_replay import (
    ReplayFriction,
    SourceTrade,
    candidate_net_pnl,
    source_trade_from_record,
    summarize_partition,
)


def test_candidate_exit_reprices_fees_and_prorates_recorded_funding() -> None:
    """An earlier market exit replaces control fees and elapsed funding only."""
    trade = SourceTrade(
        entry_time_ms=0,
        exit_time_ms=600_000,
        entry_price=100.0,
        stop_price=101.0,
        quantity=10.0,
        control_net_pnl=5.0,
        control_funding=2.0,
    )
    friction = ReplayFriction(0.001, 0.002, 10.0)
    trigger = ProfitLockTrigger(60_000, 300_000, 99.0, 99.5, 98.0)

    result = candidate_net_pnl(trade, trigger, friction)

    expected_fill = 99.0 * 1.001
    expected = 10.0 * (100.0 - expected_fill)
    expected -= 10.0 * 100.0 * 0.001
    expected -= 10.0 * expected_fill * 0.002
    expected += 1.0
    assert result == pytest.approx(expected)


def test_partition_summary_reports_leave_largest_and_control_delta() -> None:
    """Robustness metrics cannot hide dependence on the largest winner."""
    summary = summarize_partition((4.0, -2.0, 1.0), control_net=1.0, triggers=2)

    assert summary == {
        "net_pnl_usd": pytest.approx(3.0),
        "improvement_usd": pytest.approx(2.0),
        "net_without_largest_winner_usd": pytest.approx(-1.0),
        "wins": 2,
        "losses": 1,
        "triggers": 2,
    }


def test_component_replay_rejects_non_btc_source_row() -> None:
    """A mixed-symbol artifact cannot silently borrow BTC minute candles."""
    raw: dict[str, object] = {
        "candidate": "hulk_expansion_short_tuned_v2",
        "symbol": "SOL",
        "direction": "short",
        "entry_time_utc": "2026-01-01T00:00:00+00:00",
        "exit_time_utc": "2026-01-01T00:01:00+00:00",
        "entry_price": 100.0,
        "stop_price": 102.0,
        "initial_quantity": 10.0,
        "net_pnl_usd": -25.0,
        "funding_cashflow_usd": 0.0,
    }

    with pytest.raises(ValueError, match="BTC short source rows"):
        source_trade_from_record(raw)
