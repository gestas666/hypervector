"""Causal and economic tests for the BTC tuned-v2 entry-stop ratchet."""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd
import pytest

from hypervector.live.multi_asset_market_bars import CohortMarketBar
from hypervector.research.btc_hulk_component_exit_replay import (
    ReplayFriction,
    SourceTrade,
)
from hypervector.research.btc_tuned_entry_stop_ratchet_replay import (
    BTC_TUNED_ENTRY_STOP_RATCHET,
    evaluate_entry_stop_ratchet,
    partition_passes_gates,
    ratchet_candidate_net_pnl,
    replay_route_records,
    source_trade_from_record,
    summarize_ratchet_partition,
)


def _bar(
    timestamp_ms: int,
    *,
    open_price: float,
    high: float,
    low: float,
    close: float,
) -> CohortMarketBar:
    return CohortMarketBar("BTC", timestamp_ms, open_price, high, low, close, 1.0)


def _trade(*, exit_time_ms: int = 120_000) -> SourceTrade:
    return SourceTrade(
        entry_time_ms=0,
        exit_time_ms=exit_time_ms,
        entry_price=100.0,
        stop_price=102.0,
        quantity=10.0,
        control_net_pnl=-25.0,
        control_funding=2.0,
    )


def test_activation_close_cannot_trigger_entry_stop_on_same_bar() -> None:
    """An entry-stop crossing inside the activation bar is not tradable."""
    bars = (
        _bar(0, open_price=100.0, high=101.0, low=97.0, close=98.0),
        _bar(60_000, open_price=99.0, high=100.0, low=98.0, close=99.0),
    )

    state = evaluate_entry_stop_ratchet(_trade(), bars)

    assert state.activation_timestamp_ms == 0
    assert state.trigger is not None
    assert state.trigger.trigger_timestamp_ms == 60_000
    assert state.trigger.reference_price == pytest.approx(100.0)


def test_gap_trigger_and_candidate_economics_are_conservative() -> None:
    """A short-side gap uses the worse open plus fees, slippage, and funding."""
    bars = (
        _bar(0, open_price=100.0, high=100.5, low=97.5, close=98.0),
        _bar(60_000, open_price=101.0, high=101.5, low=100.0, close=101.0),
    )
    trade = _trade()
    state = evaluate_entry_stop_ratchet(trade, bars)
    assert state.trigger is not None

    result = ratchet_candidate_net_pnl(
        trade, state.trigger, ReplayFriction(0.001, 0.002, 10.0)
    )

    fill = 101.0 * 1.001
    expected = 10.0 * (100.0 - fill) - 1.0 - 10.0 * fill * 0.002 + 1.0
    assert result == pytest.approx(expected)


def test_structural_stop_has_priority_over_active_candidate() -> None:
    """A source structural boundary preserves control on an ambiguous bar."""
    bars = (
        _bar(0, open_price=100.0, high=100.0, low=97.0, close=98.0),
        _bar(60_000, open_price=99.0, high=102.0, low=98.0, close=101.0),
    )

    state = evaluate_entry_stop_ratchet(_trade(), bars)

    assert state.trigger is None
    assert state.control_boundary_reason == "structural_stop"
    assert state.control_boundary_timestamp_ms == 60_000


def test_no_candidate_trigger_preserves_exact_control_net() -> None:
    """Unchanged lifecycles retain their source outcome without repricing."""
    bars = (
        _bar(0, open_price=100.0, high=100.0, low=99.0, close=99.5),
        _bar(60_000, open_price=99.5, high=99.8, low=98.5, close=99.0),
    )
    trade = _trade()
    state = evaluate_entry_stop_ratchet(trade, bars)

    result = ratchet_candidate_net_pnl(
        trade, state.trigger, ReplayFriction(0.001, 0.002, 10.0)
    )

    assert state.trigger is None
    assert result == trade.control_net_pnl


def test_missing_minute_inside_lifecycle_fails_closed() -> None:
    """A gap cannot be silently bridged during causal path evaluation."""
    bars = (
        _bar(0, open_price=100.0, high=100.0, low=99.0, close=99.5),
        _bar(120_000, open_price=99.0, high=99.5, low=98.0, close=98.5),
    )

    with pytest.raises(ValueError, match="incomplete"):
        evaluate_entry_stop_ratchet(_trade(exit_time_ms=180_000), bars)


def test_non_btc_route_row_fails_before_path_evaluation() -> None:
    """BTC candles cannot be applied to another source symbol."""
    raw: Mapping[str, object] = {
        "candidate": "hulk_expansion_short_tuned_v2",
        "symbol": "SOL",
        "direction": "short",
        "entry_time_utc": "2026-01-01T00:00:00+00:00",
        "exit_time_utc": "2026-01-01T00:01:00+00:00",
        "entry_price": 100.0,
        "stop_price": 102.0,
        "initial_quantity": 10.0,
        "net_pnl_usd": -25.0,
        "funding_cashflow_usd": 2.0,
    }

    with pytest.raises(ValueError, match="exact BTC tuned-v2 short route"):
        source_trade_from_record(raw)


def test_policy_identity_and_fixed_parameters_are_stable() -> None:
    """The preregistered candidate has one immutable natural parameter set."""
    assert BTC_TUNED_ENTRY_STOP_RATCHET.policy_id == (
        "btc_tuned_one_r_entry_stop_ratchet_v1"
    )
    assert BTC_TUNED_ENTRY_STOP_RATCHET.activation_r_multiple == 1.0
    assert BTC_TUNED_ENTRY_STOP_RATCHET.target_r_multiple == 3.0


def test_partition_summary_and_acceptance_require_every_frozen_gate() -> None:
    """Aggregate profit cannot hide degradation, tail reliance, or no exercise."""
    passing = summarize_ratchet_partition(
        (90.0, -5.0),
        (100.0, 1.0),
        triggers=1,
        activations=1,
        structural_boundaries=0,
    )
    degraded = summarize_ratchet_partition(
        (100.0, -10.0),
        (80.0, -5.0),
        triggers=1,
        activations=1,
        structural_boundaries=0,
    )

    assert passing["candidate"]["net_pnl_usd"] == pytest.approx(101.0)
    assert passing["candidate"]["net_without_largest_winner_usd"] == 1.0
    assert partition_passes_gates(passing) is True
    assert partition_passes_gates(degraded) is False


def test_unexercised_candidate_cannot_pass_partition_gates() -> None:
    """An unchanged partition supplies no evidence for candidate mechanics."""
    summary = summarize_ratchet_partition(
        (2.0, 1.0),
        (2.0, 1.0),
        triggers=0,
        activations=0,
        structural_boundaries=0,
    )

    assert partition_passes_gates(summary) is False


def test_route_replay_reports_each_causal_lifecycle() -> None:
    """A partition replay must expose its activation, trigger, and economics."""
    raw: Mapping[str, object] = {
        "candidate": "hulk_expansion_short_tuned_v2",
        "symbol": "BTC",
        "direction": "short",
        "entry_time_utc": "2026-01-01T00:00:00+00:00",
        "exit_time_utc": "2026-01-01T00:02:00+00:00",
        "entry_price": 100.0,
        "stop_price": 102.0,
        "initial_quantity": 10.0,
        "net_pnl_usd": -25.0,
        "funding_cashflow_usd": 2.0,
    }
    candles = pd.DataFrame(
        {
            "open": (100.0, 99.0),
            "high": (101.0, 100.0),
            "low": (97.0, 98.0),
            "close": (98.0, 99.0),
            "volume": (1.0, 1.0),
        },
        index=pd.date_range("2026-01-01", periods=2, freq="1min", tz="UTC"),
    )

    result = replay_route_records((raw,), ReplayFriction(0.001, 0.002, 10.0), candles)

    assert result["triggers"] == 1
    assert result["activations"] == 1
    lifecycle = result["lifecycles"][0]
    assert lifecycle["trigger_timestamp_ms"] == 60_000 + 1_767_225_600_000
    assert lifecycle["candidate_net_pnl_usd"] > raw["net_pnl_usd"]
