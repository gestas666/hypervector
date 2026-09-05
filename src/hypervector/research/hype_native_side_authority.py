"""Report-only directional authority comparison for HYPE-native v54."""

from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from hypervector.research.hype_breakout_exit_experiment import (
    split_hype_exit_market,
)
from hypervector.research.hype_breakout_exit_models import (
    HypeExitPolicy,
    HypeExitReplayConfig,
    HypeExitReplayReport,
    HypeSide,
)
from hypervector.research.hype_breakout_exit_replay import (
    replay_hype_breakout_exits,
)


def build_hype_native_side_authority_comparison(
    market: pd.DataFrame,
    *,
    holdout_days: int = 60,
    fee_bps_per_side: float = 4.32,
    slippage_bps_per_side: float = 2.0,
) -> dict[str, object]:
    """Compare bidirectional, long-only, and short-only entry authority."""
    base = _config(fee_bps_per_side, slippage_bps_per_side)
    development, holdout, split = split_hype_exit_market(
        market,
        base,
        holdout_days,
    )
    developed = _period(development, fee_bps_per_side, slippage_bps_per_side)
    held_out = _period(holdout, fee_bps_per_side, slippage_bps_per_side)
    return {
        "schema_version": 1,
        "mode": "hype_native_v54_side_authority_report_only",
        "execution_authority": "none",
        "contract": _contract(base),
        "split": split,
        "trial_accounting": {"predeclared_directional_arms": 3},
        "development": developed,
        "holdout_already_opened": held_out,
        "development_comparison": _comparison(developed),
        "holdout_comparison": _comparison(held_out),
        "limitations": _limitations(),
    }


def _period(
    market: pd.DataFrame,
    fee_bps: float,
    slippage_bps: float,
) -> dict[str, dict[str, object]]:
    arms: tuple[tuple[str, tuple[HypeSide, ...]], ...] = (
        ("bidirectional", ("long", "short")),
        ("long_only", ("long",)),
        ("short_only", ("short",)),
    )
    return {
        name: _report(market, name, sides, fee_bps, slippage_bps)
        for name, sides in arms
    }


def _report(
    market: pd.DataFrame,
    name: str,
    sides: tuple[HypeSide, ...],
    fee_bps: float,
    slippage_bps: float,
) -> dict[str, object]:
    config = _config(fee_bps, slippage_bps)
    result = replay_hype_breakout_exits(
        market,
        HypeExitPolicy(f"hype_native_{name}"),
        config,
        entry_sides=sides,
    )
    payload = asdict(result)
    payload["entry_sides"] = list(sides)
    payload["side_counts"] = _side_counts(result)
    payload["net_excluding_largest_winner_bps"] = _without_largest(result)
    return payload


def _config(
    fee_bps: float,
    slippage_bps: float,
) -> HypeExitReplayConfig:
    return HypeExitReplayConfig(
        fee_bps_per_side=fee_bps,
        slippage_bps_per_side=slippage_bps,
        exit_on_opposite_signal=True,
    )


def _side_counts(report: HypeExitReplayReport) -> dict[str, int]:
    counts: dict[str, int] = {}
    for trade in report.trades:
        counts[trade.side] = counts.get(trade.side, 0) + 1
    return counts


def _without_largest(report: HypeExitReplayReport) -> float:
    winners = [
        trade.net_return_bps for trade in report.trades if trade.net_return_bps > 0
    ]
    return report.net_return_bps - (max(winners) if winners else 0.0)


def _comparison(values: dict[str, dict[str, object]]) -> dict[str, float]:
    control = float(values["bidirectional"]["net_return_bps"])
    return {
        "long_only_minus_bidirectional_net_bps": (
            float(values["long_only"]["net_return_bps"]) - control
        ),
        "short_only_minus_bidirectional_net_bps": (
            float(values["short_only"]["net_return_bps"]) - control
        ),
    }


def _contract(config: HypeExitReplayConfig) -> dict[str, object]:
    execution = asdict(config)
    execution["entry_sides"] = ["long", "short"]
    return {
        "report_only": True,
        "performance_gate": False,
        "automatic_promotion": False,
        "same_native_signal_stream": True,
        "opposite_disabled_side_remains_exit_authoritative": True,
        "execution": execution,
    }


def _limitations() -> list[str]:
    return [
        "this side comparison was opened after observing directional asymmetry",
        "the final 60-day block was already opened and is descriptive only",
        "legacy bars approximate current native onset and private IOC execution",
        "one-minute bars cannot establish intrabar event order",
        "directional authority changes lifecycle occupancy and later entries",
        "no arm is eligible for automatic live promotion",
    ]
