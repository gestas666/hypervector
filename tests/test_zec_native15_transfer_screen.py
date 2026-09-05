"""Fixed contracts for the V81 native fifteen-minute ZEC screen."""

from __future__ import annotations

from hypervector.research.fixed_risk_signal_screen import FrictionProfile
from hypervector.research.zec_native15_transfer_screen import (
    CandidateContract,
    candidate_contracts,
    portfolio_config,
    profile_supported,
    resolve_candidates,
)


def test_candidate_inventory_is_the_preregistered_eight_family_sides() -> None:
    """The screen must not add, remove, or retune candidates after returns open."""
    expected = (
        "squeeze_breakout_long",
        "squeeze_breakout_short",
        "liquidity_sweep_long",
        "liquidity_sweep_short",
        "zero_lag_reclaim_long",
        "zero_lag_reclaim_short",
        "regime_trend_router_long",
        "regime_trend_router_short",
    )
    assert tuple(row.candidate_id for row in candidate_contracts()) == expected
    assert all(isinstance(row, CandidateContract) for row in candidate_contracts())


def test_resolve_candidates_preserves_preregistered_order() -> None:
    """An explicit survivor subset must retain the frozen inventory order."""
    selected = resolve_candidates(
        ("regime_trend_router_short", "squeeze_breakout_long")
    )
    assert tuple(row.candidate_id for row in selected) == (
        "squeeze_breakout_long",
        "regime_trend_router_short",
    )


def test_resolve_candidates_rejects_unknown_or_duplicate_ids() -> None:
    """Posthoc aliases and repeated trials must fail rather than be ignored."""
    for values in (("unknown",), ("squeeze_breakout_long",) * 2):
        try:
            resolve_candidates(values)
        except ValueError as error:
            assert "candidate" in str(error)
        else:
            raise AssertionError("invalid candidate selection was accepted")


def test_portfolio_config_matches_v79_probation_size_and_v81_costs() -> None:
    """Research risk must not exceed the proposed live ZEC probation contract."""
    config = portfolio_config(FrictionProfile("stress_20bps_rt", 5.5))
    assert config.symbol == "ZEC"
    assert config.initial_equity == 5_000.0
    assert config.margin_fraction == 0.02
    assert config.leverage == 5.0
    assert config.venue_max_leverage == 10.0
    assert config.maximum_notional_usd == 500.0
    assert config.stop_margin_pct == 3.0
    assert config.max_hold_bars == 192
    assert config.entry_fee_rate == 0.00045
    assert config.market_exit_fee_rate == 0.00045
    assert config.entry_slippage_bps == 5.5
    assert config.market_exit_slippage_bps == 5.5
    assert config.close_on_opposite_signal is True
    assert config.reverse_on_opposite_signal is False


def test_profile_support_requires_every_preregistered_metric() -> None:
    """Positive headline PnL alone must not promote a sparse or tail-driven route."""
    passing: dict[str, object] = {
        "completed_trades": 12,
        "net_pnl_usd": 10.0,
        "profit_factor": 1.1,
        "net_excluding_largest_winner_usd": 1.0,
        "maximum_drawdown_pct": -4.9,
        "liquidations": 0,
        "insolvent": False,
    }
    assert profile_supported(passing) is True
    for key, value in (
        ("completed_trades", 11),
        ("net_pnl_usd", 0.0),
        ("profit_factor", 1.0),
        ("net_excluding_largest_winner_usd", 0.0),
        ("maximum_drawdown_pct", -5.1),
        ("liquidations", 1),
        ("insolvent", True),
    ):
        failing = {**passing, key: value}
        assert profile_supported(failing) is False


def test_profile_support_rejects_null_profit_factor_without_crashing() -> None:
    """A no-loss or no-trade report is insufficient rather than malformed."""
    metrics: dict[str, object] = {
        "completed_trades": 0,
        "net_pnl_usd": 0.0,
        "profit_factor": None,
        "net_excluding_largest_winner_usd": 0.0,
        "maximum_drawdown_pct": 0.0,
        "liquidations": 0,
        "insolvent": False,
    }
    assert profile_supported(metrics) is False
