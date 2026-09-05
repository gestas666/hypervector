"""Frozen contracts for the V82 two-R ZEC challenger."""

from __future__ import annotations

from hypervector.research.fixed_risk_signal_screen import FrictionProfile
from hypervector.research.zec_two_r_challenger import (
    candidate_ids,
    portfolio_config,
)


def test_candidate_ids_match_the_preregistered_development_survivor_rule() -> None:
    """V82 must not rank in new candidates after opening target outcomes."""
    assert candidate_ids() == (
        "zero_lag_reclaim_long",
        "zero_lag_reclaim_short",
        "regime_trend_router_long",
    )


def test_two_r_config_changes_only_the_bounded_target_contract() -> None:
    """Sizing, stop, holding time, and all-taker stress remain frozen from V81."""
    config = portfolio_config(FrictionProfile("stress_20bps_rt", 5.5))
    assert config.symbol == "ZEC"
    assert config.initial_equity == 5_000.0
    assert config.margin_fraction == 0.02
    assert config.leverage == 5.0
    assert config.maximum_notional_usd == 500.0
    assert config.stop_margin_pct == 3.0
    assert config.target_margin_pct == 6.0
    assert config.max_hold_bars == 192
    assert config.entry_fee_rate == 0.00045
    assert config.target_fee_rate == 0.00045
    assert config.market_exit_fee_rate == 0.00045
    assert config.entry_slippage_bps == 5.5
    assert config.market_exit_slippage_bps == 5.5
    assert config.close_on_opposite_signal is True
    assert config.reverse_on_opposite_signal is False
