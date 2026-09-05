"""Tests for fixed-entry ETH opposing-breakout economic assessment."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pandas as pd
import pytest

from hypervector.research.eth_opposing_breakout_assessment import (
    assess_eth_opposing_breakout,
    build_eth_opposing_breakout_segment,
)
from hypervector.research.hype_breakout_exit_models import HypeExitTrade


def test_assessment_requires_delay_robustness_in_both_windows() -> None:
    """A baseline pass cannot conceal a failed delayed validation block."""
    passing = _segment()
    failed_delay = _segment(delay_delta=-80.0)

    accepted = assess_eth_opposing_breakout(passing, passing)
    rejected = assess_eth_opposing_breakout(passing, failed_delay)

    assert accepted["status"] == "eligible_for_future_report_only_observer"
    assert accepted["proposed_live_change"] == "none"
    assert rejected["status"] == "rejected_historical_candidate"
    assert "delay_stress_opened_final" in rejected["failed_conditions"]


def test_segment_reconciles_adapter_exits_to_causal_triggers() -> None:
    """More adapter exits than trigger rows must fail technical validation."""
    control = _trades(5)
    changed = tuple(
        replace(trade, exit_reason="structural_reversal") for trade in control
    )
    candidate = _replay(changed, trigger_count=0)

    with pytest.raises(ValueError, match="exceed causal triggers"):
        build_eth_opposing_breakout_segment(
            control,
            candidate,
            candidate,
            include_folds=False,
        )


def test_segment_preserves_entries_and_builds_five_folds() -> None:
    """Economic comparisons must retain every fixed entry identity."""
    control = _trades(10)
    improved = tuple(
        replace(trade, net_return_bps=trade.net_return_bps + 5.0) for trade in control
    )

    segment = build_eth_opposing_breakout_segment(
        control,
        _replay(improved, trigger_count=10),
        _replay(improved, trigger_count=10),
        include_folds=True,
    )

    assert segment["entry_parity"] is True
    assert len(segment["chronological_folds"]) == 5


def _segment(*, delay_delta: float = 20.0) -> dict[str, object]:
    """Return a synthetic segment satisfying every baseline criterion."""
    summary = {
        "trades": 10,
        "net_return_bps": 100.0,
        "profit_factor": 2.0,
        "maximum_drawdown_bps": 20.0,
        "net_excluding_largest_winner_bps": 50.0,
        "by_side": {
            "long": {"net_return_bps": 60.0},
            "short": {"net_return_bps": 40.0},
        },
    }
    control = summary | {
        "net_return_bps": 50.0,
        "profit_factor": 1.2,
        "maximum_drawdown_bps": 25.0,
    }
    delayed = summary | {
        "net_return_bps": 50.0 + delay_delta,
        "profit_factor": 1.5 if delay_delta > 0.0 else 0.8,
    }
    folds = [
        {"candidate": {"net_return_bps": 10.0}, "delta_net_return_bps": 5.0}
        for _ in range(5)
    ]
    return {
        "technical_status": "resolved",
        "control": control,
        "candidate": summary,
        "delay_stress": delayed,
        "chronological_folds": folds,
    }


def _replay(
    trades: tuple[HypeExitTrade, ...], *, trigger_count: int
) -> SimpleNamespace:
    """Build a minimal candidate replay result."""
    triggers = tuple(SimpleNamespace() for _ in range(trigger_count))
    return SimpleNamespace(
        report=SimpleNamespace(trades=trades),
        triggers=triggers,
        unavailable_direction_rows=(),
        technical_status="resolved",
    )


def _trades(count: int) -> tuple[HypeExitTrade, ...]:
    """Build alternating deterministic fixed-entry trades."""
    base = pd.Timestamp("2026-01-01", tz="UTC")
    return tuple(
        _trade(base + pd.Timedelta(minutes=3 * index), index) for index in range(count)
    )


def _trade(timestamp: pd.Timestamp, index: int) -> HypeExitTrade:
    """Return one fully specified synthetic ETH lifecycle."""
    side = "long" if index % 2 == 0 else "short"
    return HypeExitTrade(
        side,
        timestamp.isoformat(),
        (timestamp + pd.Timedelta(minutes=1)).isoformat(),
        (timestamp + pd.Timedelta(minutes=2)).isoformat(),
        100.0,
        100.2,
        99.4,
        19.0,
        9.0,
        0.0,
        10.0,
        1,
        20.0,
        2.0,
        "maximum_hold",
    )
