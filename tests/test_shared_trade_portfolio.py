"""Chronological shared-capital replay tests for completed trade evidence."""

from __future__ import annotations

import pytest

from hypervector.research.shared_trade_portfolio import (
    SharedTradeOutcome,
    SharedTradeReplayConfig,
    replay_shared_trade_outcomes,
)


def _trade(
    trade_id: str,
    symbol: str,
    entry_ms: int,
    exit_ms: int,
    *,
    net_pnl: float,
    entry_fee: float = 0.0,
    source_equity: float = 100.0,
    margin_fraction: float = 0.10,
) -> SharedTradeOutcome:
    """Build one deterministic completed outcome."""
    return SharedTradeOutcome(
        trade_id=trade_id,
        symbol=symbol,
        entry_time_ms=entry_ms,
        exit_time_ms=exit_ms,
        source_equity_usd=source_equity,
        margin_fraction=margin_fraction,
        entry_fee_usd=entry_fee,
        net_pnl_usd=net_pnl,
        outcome="target",
    )


def test_shared_replay_scales_sequential_outcomes_with_current_equity() -> None:
    """Uncapped outcomes must compound from the equity available at entry."""
    trades = (
        _trade("btc-1", "BTC", 1_000, 2_000, net_pnl=10.0),
        _trade("sol-1", "SOL", 3_000, 4_000, net_pnl=5.0),
    )

    report = replay_shared_trade_outcomes(
        trades,
        SharedTradeReplayConfig(initial_equity_usd=100.0),
    )

    assert report.final_equity_usd == pytest.approx(115.5)
    assert [trade.scaling_base_usd for trade in report.trades] == [100.0, 110.0]
    assert report.maximum_concurrent_positions == 1


def test_shared_replay_allows_unique_symbols_and_applies_entry_fees_now() -> None:
    """Concurrent assets share fee-adjusted equity and reserve separate margin."""
    trades = (
        _trade(
            "btc-1",
            "BTC",
            1_000,
            4_000,
            net_pnl=10.0,
            entry_fee=1.0,
            margin_fraction=0.35,
        ),
        _trade(
            "sol-1",
            "SOL",
            2_000,
            3_000,
            net_pnl=5.0,
            entry_fee=0.5,
            margin_fraction=0.03,
        ),
    )

    report = replay_shared_trade_outcomes(
        trades,
        SharedTradeReplayConfig(initial_equity_usd=100.0),
    )

    assert report.maximum_concurrent_positions == 2
    assert report.peak_reserved_margin_usd == pytest.approx(37.97)
    assert report.final_equity_usd == pytest.approx(114.95)


def test_shared_replay_caps_only_the_configured_symbol_scaling_base() -> None:
    """An absolute SOL capacity cap must not suppress BTC compounding."""
    trades = (
        _trade("btc-1", "BTC", 1_000, 2_000, net_pnl=100.0),
        _trade("sol-1", "SOL", 3_000, 4_000, net_pnl=10.0),
    )
    config = SharedTradeReplayConfig(
        initial_equity_usd=100.0,
        capital_base_caps_usd={"SOL": 100.0},
    )

    report = replay_shared_trade_outcomes(trades, config)

    assert report.final_equity_usd == pytest.approx(210.0)
    assert report.trades[-1].scaling_base_usd == pytest.approx(100.0)


def test_shared_replay_can_cap_each_trade_at_its_source_equity() -> None:
    """Evidence-preserving mode must not exceed historically matched quantity."""
    trades = (
        _trade("btc-1", "BTC", 1_000, 2_000, net_pnl=100.0),
        _trade("btc-2", "BTC", 3_000, 4_000, net_pnl=10.0),
    )
    config = SharedTradeReplayConfig(
        initial_equity_usd=100.0,
        cap_at_source_equity=True,
    )

    report = replay_shared_trade_outcomes(trades, config)

    assert report.final_equity_usd == pytest.approx(210.0)
    assert report.trades[-1].scaling_base_usd == pytest.approx(100.0)


def test_shared_replay_rejects_overlapping_positions_for_one_symbol() -> None:
    """One coin cannot have two simultaneous positions."""
    trades = (
        _trade("btc-1", "BTC", 1_000, 4_000, net_pnl=10.0),
        _trade("btc-2", "BTC", 2_000, 3_000, net_pnl=5.0),
    )

    with pytest.raises(ValueError, match="overlapping BTC"):
        replay_shared_trade_outcomes(trades, SharedTradeReplayConfig())


def test_shared_replay_fails_when_reserved_margin_exceeds_equity() -> None:
    """A technical shared-capital shortfall must fail rather than skip a trade."""
    trades = (
        _trade(
            "btc-1",
            "BTC",
            1_000,
            4_000,
            net_pnl=10.0,
            margin_fraction=0.70,
        ),
        _trade(
            "sol-1",
            "SOL",
            2_000,
            3_000,
            net_pnl=5.0,
            margin_fraction=0.40,
        ),
    )

    with pytest.raises(ValueError, match="shared margin"):
        replay_shared_trade_outcomes(trades, SharedTradeReplayConfig())
