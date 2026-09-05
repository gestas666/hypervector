"""Report-only HYPE 15-minute adverse-context comparison."""

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
    HypeExitTrade,
)
from hypervector.research.hype_breakout_exit_replay import (
    replay_hype_breakout_exits,
)


def build_hype_native_adverse_context_comparison(
    market: pd.DataFrame,
    *,
    holdout_days: int = 60,
    fold_count: int = 5,
    fee_bps_per_side: float = 4.32,
    slippage_bps_per_side: float = 2.0,
) -> dict[str, object]:
    """Compare long-only native entry authority with one 15m context censor."""
    _validate_fold_count(fold_count)
    config = _config(fee_bps_per_side, slippage_bps_per_side)
    development, opened, split = split_hype_exit_market(
        market,
        config,
        holdout_days,
    )
    development_result = _period(development, config, fold_count)
    opened_result = _period(opened, config, fold_count)
    return {
        "schema_version": 1,
        "mode": "hype_native_v54_adverse_15m_context_report_only",
        "execution_authority": "none",
        "contract": _contract(config),
        "split": split,
        "development": development_result,
        "holdout_already_opened": opened_result,
        "development_comparison": _comparison(development_result),
        "holdout_comparison": _comparison(opened_result),
        "limitations": _limitations(),
    }


def censor_adverse_long_entries(
    market: pd.DataFrame,
) -> tuple[pd.DataFrame, int]:
    """Censor TREND_DOWN long onsets while preserving the native signal stream."""
    required = {"entry_side", "context_15m"}
    missing = sorted(required.difference(market.columns))
    if missing:
        raise ValueError(f"HYPE adverse-context market missing columns: {missing}")
    result = market.copy()
    result["entry_side"] = result["entry_side"].astype(object)
    adverse = result["entry_side"].eq("long") & result["context_15m"].eq("TREND_DOWN")
    result.loc[adverse, "entry_side"] = None
    return result, int(adverse.sum())


def _period(
    market: pd.DataFrame,
    config: HypeExitReplayConfig,
    fold_count: int,
) -> dict[str, dict[str, object]]:
    challenger, censored = censor_adverse_long_entries(market)
    return {
        "control_long_only": _arm(
            market,
            config,
            fold_count,
            0,
            "hype_native_long_control",
        ),
        "censor_trend_down_long": _arm(
            challenger,
            config,
            fold_count,
            censored,
            "hype_native_long_censor_trend_down_15m",
        ),
    }


def _arm(
    market: pd.DataFrame,
    config: HypeExitReplayConfig,
    fold_count: int,
    censored: int,
    policy_id: str,
) -> dict[str, object]:
    report = replay_hype_breakout_exits(
        market,
        HypeExitPolicy(policy_id),
        config,
        entry_sides=("long",),
    )
    payload = asdict(report)
    payload["entry_sides"] = ["long"]
    payload["censored_long_signals"] = censored
    payload["retained_short_signals"] = int(market["entry_side"].eq("short").sum())
    payload["net_excluding_largest_winner_bps"] = _without_largest(report)
    payload["chronological_fold_net_bps"] = _fold_net(
        report.trades,
        market.index,
        fold_count,
    )
    return payload


def _fold_net(
    trades: tuple[HypeExitTrade, ...],
    index: pd.DatetimeIndex,
    fold_count: int,
) -> list[float]:
    start = index[0]
    end = index[-1] + pd.Timedelta(minutes=1)
    step = (end.value - start.value) // fold_count
    boundaries = pd.to_datetime(
        [start.value + step * position for position in range(fold_count)],
        utc=True,
    )
    values = [0.0] * fold_count
    for trade in trades:
        fold = int(boundaries.searchsorted(pd.Timestamp(trade.entry_time_utc))) - 1
        values[min(max(fold, 0), fold_count - 1)] += trade.net_return_bps
    return values


def _config(fee_bps: float, slippage_bps: float) -> HypeExitReplayConfig:
    return HypeExitReplayConfig(
        fee_bps_per_side=fee_bps,
        slippage_bps_per_side=slippage_bps,
        exit_on_opposite_signal=True,
    )


def _without_largest(report: HypeExitReplayReport) -> float:
    winners = [
        trade.net_return_bps for trade in report.trades if trade.net_return_bps > 0
    ]
    return report.net_return_bps - (max(winners) if winners else 0.0)


def _comparison(period: dict[str, dict[str, object]]) -> dict[str, float]:
    control = period["control_long_only"]
    challenger = period["censor_trend_down_long"]
    return {
        "challenger_minus_control_net_bps": (
            float(challenger["net_return_bps"]) - float(control["net_return_bps"])
        ),
        "challenger_minus_control_drawdown_bps": (
            float(challenger["maximum_drawdown_bps"])
            - float(control["maximum_drawdown_bps"])
        ),
        "challenger_minus_control_completed_trades": (
            float(challenger["completed_trades"]) - float(control["completed_trades"])
        ),
    }


def _contract(config: HypeExitReplayConfig) -> dict[str, object]:
    return {
        "report_only": True,
        "performance_gate": False,
        "automatic_promotion": False,
        "same_HYPE_native_signal_stream": True,
        "single_mechanistic_filter": "censor_long_when_context_15m_TREND_DOWN",
        "native_short_onset_remains_exit_authoritative": True,
        "execution": asdict(config) | {"entry_sides": ["long"]},
    }


def _limitations() -> list[str]:
    return [
        "the hypothesis was selected after inspecting fourteen live lifecycles",
        "time, profile generation, direction, and regime are confounded",
        "the final sixty-day block was already opened and is descriptive only",
        "censoring entries changes lifecycle occupancy and later opportunities",
        "one-minute bars do not reproduce private IOC or intrabar event order",
        "no result grants automatic live promotion or execution authority",
    ]


def _validate_fold_count(fold_count: int) -> None:
    if isinstance(fold_count, bool) or fold_count < 2:
        raise ValueError("HYPE adverse-context fold_count must be at least two")
