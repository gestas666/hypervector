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


def test_timer_journal_scores_report_only_regime_aware_extension() -> None:
    """Support extends while mixed context matches the authoritative timer exit."""
    trades = [
        _trade(
            "maximum_hold_seconds",
            "still_directionally_supported",
            1.0,
            "continued_original_direction",
            directional_close_return_bps=100.0,
            exit_price=100.0,
            exit_size=2.0,
        ),
        _trade(
            "maximum_hold_seconds",
            "mixed_or_transition",
            0.5,
            "reversed_against_original_direction",
            directional_close_return_bps=-50.0,
            exit_price=50.0,
            exit_size=1.0,
        ),
    ]

    journal = build_maximum_hold_context_journal(trades, [5])

    challenger = journal["regime_aware_extension_challenger"]
    assert challenger["contract"]["execution_authority"] == "none"
    assert challenger["policy"] == {
        "still_directionally_supported": "extend",
        "directionally_opposed": "exit",
        "mixed_or_transition": "exit",
        "unavailable": "abstain",
    }
    assert challenger["decisions"] == {"extend": 1, "exit": 1, "abstain": 0}
    assert challenger["horizons"]["5"] == {
        "eligible_extensions": 1,
        "resolved": 1,
        "positive": 1,
        "negative": 0,
        "unchanged": 0,
        "protective_stop_hits": 0,
        "censored": 0,
        "missing_data": 0,
        "missing_protection": 0,
        "incremental_gross_pnl_usd": pytest.approx(2.0),
    }


def test_timer_journal_keeps_provider_symbol_exit_evidence_separate() -> None:
    """A strong provider cannot conceal a weak provider in pooled evidence."""
    trades = [
        _trade(
            "maximum_hold_seconds",
            "still_directionally_supported",
            1.0,
            "continued_original_direction",
            strategy_id="hype_breakout",
            symbol="HYPE",
        ),
        _trade(
            "maximum_hold_seconds",
            "mixed_or_transition",
            -0.5,
            "reversed_against_original_direction",
            strategy_id="source_follow",
            symbol="BTC",
        ),
    ]

    journal = build_maximum_hold_context_journal(trades, [5])

    providers = journal["provider_symbols"]
    assert [(row["strategy_id"], row["symbol"]) for row in providers] == [
        ("hype_breakout", "HYPE"),
        ("source_follow", "BTC"),
    ]
    hype = providers[0]
    assert hype["timer_exits"] == 1
    assert hype["contexts"]["still_directionally_supported"]["net_pnl_usd"] == 1.0
    assert hype["regime_aware_extension_challenger"]["decisions"] == {
        "extend": 1,
        "exit": 0,
        "abstain": 0,
    }
    btc = providers[1]
    assert btc["timer_exits"] == 1
    assert btc["contexts"]["mixed_or_transition"]["net_pnl_usd"] == -0.5
    assert btc["regime_aware_extension_challenger"]["decisions"] == {
        "extend": 0,
        "exit": 1,
        "abstain": 0,
    }


def test_timer_extension_challenger_counts_unresolved_paths() -> None:
    """Unavailable future candles remain visible rather than becoming zero PnL."""
    trade = _trade(
        "maximum_hold_seconds",
        "still_directionally_supported",
        1.0,
        "continued_original_direction",
    )
    trade["post_exit_path"]["5"] = {"status": "censored"}

    challenger = build_maximum_hold_context_journal([trade], [5])[
        "regime_aware_extension_challenger"
    ]

    assert challenger["horizons"]["5"]["eligible_extensions"] == 1
    assert challenger["horizons"]["5"]["resolved"] == 0
    assert challenger["horizons"]["5"]["censored"] == 1
    assert challenger["horizons"]["5"]["incremental_gross_pnl_usd"] == 0.0


def test_timer_extension_challenger_honors_original_protective_stop() -> None:
    """A later close cannot claim gains after the retained venue stop was touched."""
    trade = _trade(
        "maximum_hold_seconds",
        "still_directionally_supported",
        1.0,
        "continued_original_direction",
        directional_close_return_bps=1_000.0,
        exit_price=110.0,
        exit_size=2.0,
        stop_price=99.0,
        lowest_price=98.0,
        highest_price=122.0,
    )

    horizon = build_maximum_hold_context_journal([trade], [5])[
        "regime_aware_extension_challenger"
    ]["horizons"]["5"]

    assert horizon["protective_stop_hits"] == 1
    assert horizon["negative"] == 1
    assert horizon["positive"] == 0
    assert horizon["incremental_gross_pnl_usd"] == pytest.approx(-22.0)


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
