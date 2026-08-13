"""Report-only HT structural/breakout agreement comparison."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict

import pandas as pd

from hypervector.research.hype_breakout_exit_experiment import split_hype_exit_market
from hypervector.research.hype_breakout_exit_models import (
    HypeExitPolicy,
    HypeExitReplayConfig,
    HypeExitReplayReport,
)
from hypervector.research.hype_breakout_exit_replay import replay_hype_breakout_exits

_SYMBOLS = frozenset({"BTC", "ETH", "SOL"})
_INVARIANT_COLUMNS = (
    "open",
    "high",
    "low",
    "close",
    "state_5m",
    "structural_direction",
    "funding_rate",
)
_CONTROL = "v39_structural_side_control"
_CHALLENGER = "structural_breakout_agree_only"


def build_ht_agree_only_market(
    structural: pd.DataFrame,
    breakout: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Censor structural onsets unless the completed-5m side agrees."""
    _validate_markets(structural, breakout)
    structural_side = structural["entry_side"].astype(object)
    breakout_side = breakout["entry_side"].astype(object)
    present = structural_side.isin(("long", "short"))
    available = breakout_side.isin(("long", "short"))
    aligned = present & available & structural_side.eq(breakout_side)
    opposed = present & available & structural_side.ne(breakout_side)
    unavailable = present & ~available
    market = structural.copy()
    market["entry_side"] = structural_side.where(aligned, None)
    accounting = {
        "structural_onsets": int(present.sum()),
        "aligned_onsets": int(aligned.sum()),
        "opposed_onsets": int(opposed.sum()),
        "unavailable_onsets": int(unavailable.sum()),
        "censored_onsets": int((present & ~aligned).sum()),
    }
    return market, accounting


def build_ht_agree_only_comparison(
    structural: pd.DataFrame,
    breakout: pd.DataFrame,
    *,
    symbol: str,
    holdout_days: int = 60,
) -> dict[str, object]:
    """Compare v39 structural entries with the frozen agree-only challenger."""
    if symbol not in _SYMBOLS:
        raise ValueError(f"v39 HT agree-only symbol is unsupported: {symbol}")
    agree, full_accounting = build_ht_agree_only_market(structural, breakout)
    config = _v39_config()
    control_dev, control_holdout, split = split_hype_exit_market(
        structural, config, holdout_days
    )
    agree_dev, agree_holdout, agree_split = split_hype_exit_market(
        agree, config, holdout_days
    )
    breakout_dev, breakout_holdout, breakout_split = split_hype_exit_market(
        breakout, config, holdout_days
    )
    if split != agree_split or split != breakout_split:
        raise ValueError("HT agree-only comparison split mismatch")
    development = _period(control_dev, breakout_dev, agree_dev, config)
    holdout = _period(control_holdout, breakout_holdout, agree_holdout, config)
    return _artifact(symbol, config, split, full_accounting, development, holdout)


def _period(
    control: pd.DataFrame,
    breakout: pd.DataFrame,
    challenger: pd.DataFrame,
    config: HypeExitReplayConfig,
) -> dict[str, object]:
    policy = HypeExitPolicy("common_v39_entry_exit_contract")
    control_report = replay_hype_breakout_exits(control, policy, config)
    challenger_report = replay_hype_breakout_exits(challenger, policy, config)
    _, accounting = build_ht_agree_only_market(control, breakout)
    return {
        "entry_accounting": accounting,
        _CONTROL: _report(control_report, control.index),
        _CHALLENGER: _report(challenger_report, challenger.index),
        "challenger_minus_control": _delta(control_report, challenger_report),
        "control_profit_lock_surface": _profit_lock_surface(
            control, config, control_report
        ),
    }


def _report(
    report: HypeExitReplayReport,
    index: pd.DatetimeIndex,
) -> dict[str, object]:
    values = asdict(report)
    trade_net = tuple(trade.net_return_bps for trade in report.trades)
    values["net_return_excluding_largest_winner_bps"] = _without_largest(trade_net)
    values["chronological_fold_net_bps"] = _fold_net(report, index, 5)
    values["side_summary"] = {
        side: _side_summary(report, side) for side in ("long", "short")
    }
    return values


def _side_summary(report: HypeExitReplayReport, side: str) -> dict[str, object]:
    trades = tuple(trade for trade in report.trades if trade.side == side)
    values = tuple(trade.net_return_bps for trade in trades)
    profit = sum(value for value in values if value > 0.0)
    loss = -sum(value for value in values if value < 0.0)
    return {
        "completed_trades": len(trades),
        "wins": sum(value > 0.0 for value in values),
        "losses": sum(value < 0.0 for value in values),
        "net_return_bps": sum(values),
        "profit_factor": profit / loss if loss > 0.0 else None,
        "net_return_excluding_largest_winner_bps": _without_largest(values),
    }


def _fold_net(
    report: HypeExitReplayReport,
    index: pd.DatetimeIndex,
    count: int,
) -> list[float]:
    boundaries = pd.date_range(index[0], index[-1], periods=count + 1)
    output = [0.0] * count
    for trade in report.trades:
        stamp = pd.Timestamp(trade.entry_time_utc)
        fold = min(int(boundaries.searchsorted(stamp, side="right") - 1), count - 1)
        output[max(fold, 0)] += trade.net_return_bps
    return output


def _delta(
    control: HypeExitReplayReport,
    challenger: HypeExitReplayReport,
) -> dict[str, float | int]:
    return {
        "net_return_bps": challenger.net_return_bps - control.net_return_bps,
        "maximum_drawdown_bps": (
            challenger.maximum_drawdown_bps - control.maximum_drawdown_bps
        ),
        "completed_trades": challenger.completed_trades - control.completed_trades,
    }


def _profit_lock_surface(
    market: pd.DataFrame,
    config: HypeExitReplayConfig,
    control: HypeExitReplayReport,
) -> dict[str, object]:
    output: dict[str, object] = {}
    for policy in _profit_lock_policies():
        report = replay_hype_breakout_exits(market, policy, config)
        output[policy.policy_id] = {
            **_summary_report(report, market.index),
            "automatic_promotion": False,
            "challenger_minus_control": _delta(control, report),
        }
    return output


def _profit_lock_policies() -> tuple[HypeExitPolicy, ...]:
    return (
        _profit_policy("a25_floor15_trail10", 25.0, 10.0),
        _profit_policy("a25_floor15_trail10_reset", 25.0, 10.0, reset=True),
        _profit_policy("a40_floor15_trail20", 40.0, 20.0),
        _profit_policy("a40_floor15_trail20_reset", 40.0, 20.0, reset=True),
        _profit_policy("a60_floor15_trail30", 60.0, 30.0),
        _profit_policy("a60_floor15_trail30_reset", 60.0, 30.0, reset=True),
    )


def _profit_policy(
    policy_id: str,
    activation_bps: float,
    giveback_bps: float,
    *,
    reset: bool = False,
) -> HypeExitPolicy:
    return HypeExitPolicy(
        policy_id,
        profit_activation_bps=activation_bps,
        profit_floor_bps=15.0,
        trailing_giveback_bps=giveback_bps,
        reentry_requires_structural_reset=reset,
    )


def _summary_report(
    report: HypeExitReplayReport,
    index: pd.DatetimeIndex,
) -> dict[str, object]:
    values = tuple(trade.net_return_bps for trade in report.trades)
    return {
        "completed_trades": report.completed_trades,
        "wins": report.wins,
        "losses": report.losses,
        "net_return_bps": report.net_return_bps,
        "profit_factor": report.profit_factor,
        "maximum_drawdown_bps": report.maximum_drawdown_bps,
        "net_return_excluding_largest_winner_bps": _without_largest(values),
        "chronological_fold_net_bps": _fold_net(report, index, 5),
        "side_summary": {
            side: _side_summary(report, side) for side in ("long", "short")
        },
        "occupied_signals": report.occupied_signals,
        "reset_blocked_signals": report.reset_blocked_signals,
        "exit_reasons": report.exit_reasons,
    }


def _artifact(
    symbol: str,
    config: HypeExitReplayConfig,
    split: Mapping[str, object],
    accounting: Mapping[str, int],
    development: Mapping[str, object],
    holdout: Mapping[str, object],
) -> dict[str, object]:
    return {
        "schema_version": "ht_agree_only_comparison_v1",
        "mode": "frozen_report_only_entry_authority_comparison",
        "source": {
            "symbol": symbol,
            "strategy_id": "hype_breakout_onset_bidirectional_v1",
        },
        "contract": _contract(config),
        "split": dict(split),
        "full_window_entry_accounting": dict(accounting),
        "development": dict(development),
        "holdout_already_opened": dict(holdout),
        "disposition": "REPORT_ONLY_COMPARISON_NO_PROMOTION",
        "limitations": _limitations(),
    }


def _contract(config: HypeExitReplayConfig) -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "control_side": "completed_hourly_sma_structural_direction",
        "challenger_rule": "enter_only_when_completed_5m_breakout_side_agrees",
        "execution": asdict(config),
    }


def _v39_config() -> HypeExitReplayConfig:
    return HypeExitReplayConfig(
        stop_bps=80.0,
        maximum_hold_minutes=480,
        maximum_hold_policy="extend_while_regime_supported",
        hard_maximum_hold_minutes=1_440,
        fee_bps_per_side=4.5,
        slippage_bps_per_side=2.0,
    )


def _without_largest(values: tuple[float, ...]) -> float | None:
    winners = tuple(value for value in values if value > 0.0)
    return sum(values) - max(winners) if winners else None


def _validate_markets(structural: pd.DataFrame, breakout: pd.DataFrame) -> None:
    if structural.empty or not structural.index.equals(breakout.index):
        raise ValueError("HT comparison markets must share one non-empty index")
    required = {*_INVARIANT_COLUMNS, "entry_side"}
    for label, market in (("structural", structural), ("breakout", breakout)):
        missing = sorted(required.difference(market.columns))
        if missing:
            raise ValueError(f"HT {label} market missing columns: {missing}")
    if not structural.loc[:, _INVARIANT_COLUMNS].equals(
        breakout.loc[:, _INVARIANT_COLUMNS]
    ):
        raise ValueError("HT comparison market evidence differs beyond entry side")
    for market in (structural, breakout):
        invalid = market["entry_side"].notna() & ~market["entry_side"].isin(
            ("long", "short")
        )
        if invalid.any():
            raise ValueError("HT comparison entry side must be long, short, or null")


def _limitations() -> list[str]:
    return [
        "the final chronological block was previously opened and is descriptive only",
        "one-minute bars cannot reproduce every intrabar fill ordering outcome",
        "fixed slippage is a venue-friction approximation rather than private fills",
        "different entry censorship changes later per-asset occupancy",
        "per-asset comparisons do not model cross-asset loss-wave dependence",
        "no performance result grants live execution authority",
    ]
