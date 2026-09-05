"""Complete report-only exit comparison for the HYPE-native v54 contract."""

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
)
from hypervector.research.hype_breakout_exit_replay import (
    replay_hype_breakout_exits,
)


def build_hype_native_exit_comparison(
    market: pd.DataFrame,
    *,
    holdout_days: int = 60,
    fee_bps_per_side: float = 4.32,
    slippage_bps_per_side: float = 2.0,
) -> dict[str, object]:
    """Compare fixed and supported holds with the native opposite-onset exit."""
    common = {
        "fee_bps_per_side": fee_bps_per_side,
        "slippage_bps_per_side": slippage_bps_per_side,
        "exit_on_opposite_signal": True,
    }
    fixed = HypeExitReplayConfig(**common)
    extension = HypeExitReplayConfig(
        maximum_hold_policy="extend_while_regime_supported",
        hard_maximum_hold_minutes=1_440,
        **common,
    )
    development, holdout, split = split_hype_exit_market(
        market,
        extension,
        holdout_days,
    )
    developed = _period(development, fixed, extension)
    held_out = _period(holdout, fixed, extension)
    return {
        "schema_version": 1,
        "mode": "hype_native_v54_exit_contract_report_only",
        "execution_authority": "none",
        "contract": _contract(fixed, extension),
        "split": split,
        "trial_accounting": {"policy_partition_trials": 4},
        "development": developed,
        "holdout_already_opened": held_out,
        "development_comparison": _delta(developed),
        "holdout_comparison": _delta(held_out),
        "limitations": _limitations(),
    }


def _period(
    market: pd.DataFrame,
    fixed: HypeExitReplayConfig,
    extension: HypeExitReplayConfig,
) -> dict[str, dict[str, object]]:
    policy = HypeExitPolicy("hype_native_entry_control")
    return {
        "fixed_8h": _report(market, policy, fixed),
        "supported_extension": _report(market, policy, extension),
    }


def _report(
    market: pd.DataFrame,
    policy: HypeExitPolicy,
    config: HypeExitReplayConfig,
) -> dict[str, object]:
    report = replay_hype_breakout_exits(market, policy, config)
    return _serialized_report(report)


def _serialized_report(report: HypeExitReplayReport) -> dict[str, object]:
    payload = asdict(report)
    payload["trades"] = [asdict(trade) for trade in report.trades]
    return payload


def _delta(values: dict[str, dict[str, object]]) -> dict[str, float]:
    fixed = values["fixed_8h"]
    extension = values["supported_extension"]
    return {
        "extension_minus_fixed_net_bps": float(extension["net_return_bps"])
        - float(fixed["net_return_bps"]),
        "extension_minus_fixed_drawdown_bps": float(extension["maximum_drawdown_bps"])
        - float(fixed["maximum_drawdown_bps"]),
    }


def _contract(
    fixed: HypeExitReplayConfig,
    extension: HypeExitReplayConfig,
) -> dict[str, object]:
    return {
        "report_only": True,
        "performance_gate": False,
        "automatic_promotion": False,
        "same_signal_stream": True,
        "opposite_native_onset_exit": True,
        "fixed": asdict(fixed),
        "supported_extension": asdict(extension),
    }


def _limitations() -> list[str]:
    return [
        "the final 60-day block was previously opened and is descriptive only",
        "legacy bars approximate current native onset and private IOC execution",
        "one-minute bars cannot establish intrabar event order",
        "different hold occupancy can change later available entries",
        "neither exit policy can establish a profitable entry edge by itself",
    ]
