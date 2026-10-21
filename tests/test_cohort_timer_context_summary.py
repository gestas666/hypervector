"""Maximum-hold regime-context journal tests."""

from __future__ import annotations

import pytest

from hypervector.research.cohort_trade_reflection_summary import (
    build_maximum_hold_context_journal,
)


def test_timer_journal_groups_only_timer_exits_by_causal_context() -> None:
    """Timer evidence remains separate from stops and preserves later paths."""
    trades = [
        _trade(
            "maximum_hold_seconds",
            "still_directionally_supported",
            1.0,
            "continued_original_direction",
        ),
        _trade(
            "maximum_hold",
            "mixed_or_transition",
            -0.5,
            "reversed_against_original_direction",
        ),
        _trade(
            "protective_stop",
            "directionally_opposed",
            -2.0,
            "continued_original_direction",
        ),
    ]

    journal = build_maximum_hold_context_journal(trades, [5])

    assert journal["contract"]["execution_authority"] == "none"
    assert journal["timer_exits"] == 2
    assert journal["non_timer_exits"] == 1
    supportive = journal["contexts"]["still_directionally_supported"]
    assert supportive["closed_trades"] == 1
    assert supportive["net_pnl_usd"] == pytest.approx(1.0)
    assert supportive["horizons"]["5"]["continued_original_direction"] == 1
    mixed = journal["contexts"]["mixed_or_transition"]
    assert mixed["closed_trades"] == 1
    assert mixed["horizons"]["5"]["reversed_against_original_direction"] == 1
    assert journal["contexts"]["directionally_opposed"]["closed_trades"] == 0
    assert journal["contexts"]["unavailable"]["closed_trades"] == 0


def test_timer_journal_keeps_provider_symbol_exit_evidence_separate() -> None:
    """A strong provider cannot conceal a weak provider in pooled evidence."""
    trades = [
        _trade(
            "maximum_hold_seconds",
            "still_directionally_supported",
            1.0,
            "continued_original_direction",
            strategy_id="test_fade_1m",
            symbol="HYPE",
        ),
        _trade(
            "maximum_hold_seconds",
            "mixed_or_transition",
            -0.5,
            "reversed_against_original_direction",
            strategy_id="test_mirror_1m",
            symbol="BTC",
        ),
    ]

    journal = build_maximum_hold_context_journal(trades, [5])

    providers = journal["provider_symbols"]
    assert [(row["strategy_id"], row["symbol"]) for row in providers] == [
        ("test_fade_1m", "HYPE"),
        ("test_mirror_1m", "BTC"),
    ]
    hype = providers[0]
    assert hype["timer_exits"] == 1
    assert hype["contexts"]["still_directionally_supported"]["net_pnl_usd"] == 1.0
    assert "regime_aware_extension_challenger" not in hype
    btc = providers[1]
    assert btc["timer_exits"] == 1
    assert btc["contexts"]["mixed_or_transition"]["net_pnl_usd"] == -0.5


def test_timer_journal_rejects_unknown_context() -> None:
    """Unknown policy labels cannot disappear into an aggregate bucket."""
    trade = _trade("maximum_hold_seconds", "mystery", 0.0, "unchanged")

    with pytest.raises(ValueError, match="maximum-hold context"):
        build_maximum_hold_context_journal([trade], [5])


def _trade(
    reason: str,
    context: str,
    net_pnl_usd: float,
    interpretation: str,
    *,
    directional_close_return_bps: float = 10.0,
    exit_price: float = 100.0,
    exit_size: float = 1.0,
    stop_price: float = 90.0,
    lowest_price: float = 99.0,
    highest_price: float = 101.0,
    strategy_id: str = "test_strategy",
    symbol: str = "BTC",
) -> dict[str, object]:
    return {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "exit_reason": reason,
        "net_pnl_usd": net_pnl_usd,
        "side": "long",
        "exit": {"price": exit_price, "size": exit_size},
        "protective_stop": {"oid": 202, "trigger_price": stop_price},
        "exit_regime_assessment": {"maximum_hold_context": context},
        "post_exit_path": {
            "5": {
                "status": "resolved",
                "interpretation": interpretation,
                "directional_close_return_bps": directional_close_return_bps,
                "lowest_price": lowest_price,
                "highest_price": highest_price,
            }
        },
    }
