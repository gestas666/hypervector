"""Contracts for the frozen ETH side-mechanism decision."""

from __future__ import annotations

from copy import deepcopy

import pytest

from hypervector.research.eth_side_mechanism_decision import (
    build_eth_side_mechanism_decision,
)


def test_partition_rotation_requires_new_side_mechanism_identity() -> None:
    """No side/relation arm may survive by pooling opposing partitions."""
    attribution = _attribution()
    duration = _duration(attribution)

    report = build_eth_side_mechanism_decision(attribution, duration)

    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "model_authority": "none",
        "automatic_promotion": False,
        "automatic_retuning": False,
        "runtime_strategy_changed": False,
    }
    assert report["assessment"] == {
        "tested_side_arms": 2,
        "stable_side_arms": [],
        "tested_side_relation_arms": 4,
        "stable_side_relation_arms": [],
        "retained_maximum_hold_minutes": 720,
        "holdout_claimed": False,
    }
    assert report["decision"] == (
        "tested_side_relation_set_falsified_requires_new_mechanism_identity"
    )
    assert report["side_relation_arms"]["long|aligned"]["stable"] is False
    assert report["side_relation_arms"]["long|aligned"]["failed_partitions"] == [
        "opened_final_60d"
    ]
    assert report["side_arms"]["short"]["failed_partitions"] == ["opened_final_60d"]


def test_duration_source_must_reproduce_exact_side_economics() -> None:
    """The 12-hour control cannot drift from the attributed lifecycle set."""
    attribution = _attribution()
    duration = _duration(attribution)
    duration["duration_comparison"]["development"]["fixed_720m"]["by_side"]["long"][
        "net_return_bps"
    ] = 999.0

    with pytest.raises(ValueError, match="720-minute side economics mismatch"):
        build_eth_side_mechanism_decision(attribution, duration)


def _attribution() -> dict[str, object]:
    development = {
        "by_side": {
            "long": _cell(2, 1, 1, 4.0, 2.0, -1.0),
            "short": _cell(2, 1, 1, 3.0, 1.8, 1.0),
        },
        "by_side_relation": {
            "long|aligned": _cell(2, 1, 1, 4.0, 2.0, 1.0),
            "long|opposed": _cell(1, 0, 1, -2.0, 0.0, -2.0),
            "short|aligned": _cell(1, 0, 1, -2.0, 0.0, -2.0),
            "short|opposed": _cell(2, 1, 1, 3.0, 1.8, 1.0),
        },
    }
    final = {
        "by_side": {
            "long": _cell(2, 1, 1, 2.0, 1.5, 0.5),
            "short": _cell(2, 0, 2, -3.0, 0.0, -3.0),
        },
        "by_side_relation": {
            "long|aligned": _cell(1, 0, 1, -2.0, 0.0, -2.0),
            "long|opposed": _cell(2, 1, 1, 3.0, 1.8, 1.0),
            "short|aligned": _cell(2, 1, 1, 2.0, 1.5, 0.5),
            "short|opposed": _cell(1, 0, 1, -2.0, 0.0, -2.0),
        },
    }
    return {
        "schema_version": 1,
        "mode": "eth_pullback_side_breakout_relation_attribution_v1",
        "contract": _contract(),
        "strategy_id": "eth_breakout_precompression_pullback_bidirectional_v1",
        "symbol": "ETH",
        "split": _split(),
        "coverage": {
            "input_trades": 8,
            "development_trades": 4,
            "opened_final_trades": 4,
            "purge_or_out_of_window_trades": 0,
        },
        "segments": {
            "development": development,
            "opened_final_60d": final,
        },
    }


def _duration(attribution: dict[str, object]) -> dict[str, object]:
    segments = attribution["segments"]
    return {
        "schema_version": 1,
        "mode": "eth_pullback_side_breakout_relation_attribution_v1",
        "contract": _contract(),
        "strategy_id": attribution["strategy_id"],
        "symbol": attribution["symbol"],
        "split": attribution["split"],
        "coverage": attribution["coverage"],
        "duration_comparison": {
            phase: {"fixed_720m": {"by_side": deepcopy(segments[phase]["by_side"])}}
            for phase in ("development", "opened_final_60d")
        },
    }


def _cell(
    trades: int,
    wins: int,
    losses: int,
    net: float,
    profit_factor: float,
    repeatable_net: float,
) -> dict[str, object]:
    return {
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "net_return_bps": net,
        "profit_factor": profit_factor,
        "net_excluding_largest_winner_bps": repeatable_net,
    }


def _contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "entry_gate": False,
        "portfolio_pnl_claimed": False,
    }


def _split() -> dict[str, object]:
    return {
        "development_end_exclusive_utc": "2026-05-28T12:00:00+00:00",
        "opened_final_start_utc": "2026-05-29T00:00:00+00:00",
        "opened_final_end_exclusive_utc": "2026-07-28T00:00:00+00:00",
    }
