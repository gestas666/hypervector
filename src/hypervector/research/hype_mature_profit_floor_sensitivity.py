"""Fixed-entry HYPE sensitivity for one predeclared mature profit floor."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict
import math

import pandas as pd

from hypervector.research.cohort_profit_lock_policy import (
    ProfitLockPathState,
    ProfitLockPolicy,
    evaluate_profit_lock_path,
    policy_declaration,
)
from hypervector.research.cohort_trade_reflection_index import Candle
from hypervector.research.hype_breakout_exit_models import HypeExitReplayConfig

Record = Mapping[str, object]
_BPS_DENOMINATOR = 10_000.0
_MINUTE = pd.Timedelta(minutes=1)


def build_fixed_entry_profit_floor_period(
    market: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    policy: ProfitLockPolicy,
    config: HypeExitReplayConfig,
    fold_count: int,
) -> dict[str, object]:
    """Compare one floor with native exits on an unchanged lifecycle cohort."""
    _validate_market(market)
    _validate_fold_count(fold_count)
    outcomes = tuple(
        _evaluate_trade(market, row, policy, config)
        for row in trades.to_dict(orient="records")
    )
    if not outcomes:
        raise ValueError("fixed-entry profit-floor sensitivity requires trades")
    native = _summary(outcomes, "actual_net_return_bps", count_triggers=False)
    challenger = _summary(outcomes, "estimated_net_return_bps", count_triggers=True)
    return {
        "policy": policy_declaration(policy),
        "fixed_entry_cohort": True,
        "native": native,
        "challenger": challenger,
        "challenger_minus_native_net_bps": (
            challenger["net_return_bps"] - native["net_return_bps"]
        ),
        "folds": _fold_summary(market.index, outcomes, fold_count),
        "outcomes": list(outcomes),
    }


def combine_fixed_entry_profit_floor_periods(
    periods: tuple[Record, ...],
) -> dict[str, object]:
    """Combine disjoint confirmation segments and recompute robustness globally."""
    if not periods:
        raise ValueError("profit-floor combination requires at least one period")
    policies = [period.get("policy") for period in periods]
    if any(policy != policies[0] for policy in policies[1:]):
        raise ValueError("profit-floor periods must share one policy")
    outcomes = tuple(
        outcome
        for period in periods
        for outcome in _outcome_records(period.get("outcomes"))
    )
    native = _summary(outcomes, "actual_net_return_bps", count_triggers=False)
    challenger = _summary(outcomes, "estimated_net_return_bps", count_triggers=True)
    return {
        "policy": policies[0],
        "periods": len(periods),
        "native": native,
        "challenger": challenger,
        "challenger_minus_native_net_bps": (
            challenger["net_return_bps"] - native["net_return_bps"]
        ),
        "outcomes": list(outcomes),
    }


def build_hype_mature_profit_floor_report(
    development_market: pd.DataFrame,
    development_trades: pd.DataFrame,
    confirmation_periods: tuple[tuple[pd.DataFrame, pd.DataFrame], ...],
    *,
    policy: ProfitLockPolicy,
    config: HypeExitReplayConfig,
    development_fold_count: int,
) -> dict[str, object]:
    """Build separated development and later-confirmation floor evidence."""
    development = build_fixed_entry_profit_floor_period(
        development_market,
        development_trades,
        policy=policy,
        config=config,
        fold_count=development_fold_count,
    )
    confirmation = combine_fixed_entry_profit_floor_periods(
        tuple(
            build_fixed_entry_profit_floor_period(
                market,
                trades,
                policy=policy,
                config=config,
                fold_count=1,
            )
            for market, trades in confirmation_periods
        )
    )
    triggers = confirmation["challenger"]["triggered_lifecycles"]
    return {
        "schema_version": 1,
        "mode": "hype_mature_profit_floor_fixed_entry_sensitivity_v1",
        "contract": _report_contract(),
        "execution_contract": asdict(config),
        "hypothesis": "preserve at least 25 gross bps only after 100 bps MFE",
        "policy_origin": "post_hoc_spcx_open_winner_hypothesis_20260813",
        "selection_performed": False,
        "development": development,
        "later_confirmation": confirmation,
        "disposition": (
            "defer_until_independent_trigger_evidence"
            if triggers == 0
            else "report_only_trigger_evidence_requires_review"
        ),
        "limitations": _report_limitations(),
    }


def _evaluate_trade(
    market: pd.DataFrame,
    trade: Record,
    policy: ProfitLockPolicy,
    config: HypeExitReplayConfig,
) -> dict[str, object]:
    side = _side(trade.get("side"))
    entry = _timestamp(trade.get("entry_time_utc"), "entry")
    exit_time = _timestamp(trade.get("exit_time_utc"), "exit")
    if exit_time <= entry:
        raise ValueError("fixed-entry lifecycle exit must follow entry")
    entry_price = _positive(trade.get("entry_price"), "entry price")
    actual = _number(trade.get("net_return_bps"), "native net return")
    path = _completed_path(market, entry, exit_time)
    state = evaluate_profit_lock_path(policy, side, path, entry_price)
    if state.trigger is None:
        return _unchanged_outcome(trade, side, entry, actual, state)
    estimated = _triggered_net(market, side, entry, entry_price, state, config)
    return {
        "entry_timestamp_utc": entry.isoformat(),
        "side": side,
        "status": "triggered",
        "native_exit_reason": str(trade.get("exit_reason")),
        "estimated_exit_reason": "profit_protection",
        "activation_timestamp_utc": _utc_iso(state.activation_timestamp_ms),
        "trigger_timestamp_utc": _utc_iso(state.trigger.trigger_timestamp_ms),
        "trigger_reference_price": state.trigger.reference_price,
        "actual_net_return_bps": actual,
        "estimated_net_return_bps": estimated,
        "estimated_minus_actual_net_bps": estimated - actual,
    }


def _unchanged_outcome(
    trade: Record,
    side: str,
    entry: pd.Timestamp,
    actual: float,
    state: ProfitLockPathState,
) -> dict[str, object]:
    reason = str(trade.get("exit_reason"))
    return {
        "entry_timestamp_utc": entry.isoformat(),
        "side": side,
        "status": "not_triggered",
        "native_exit_reason": reason,
        "estimated_exit_reason": reason,
        "activation_timestamp_utc": _utc_iso(state.activation_timestamp_ms),
        "trigger_timestamp_utc": None,
        "trigger_reference_price": None,
        "actual_net_return_bps": actual,
        "estimated_net_return_bps": actual,
        "estimated_minus_actual_net_bps": 0.0,
    }


def _triggered_net(
    market: pd.DataFrame,
    side: str,
    entry: pd.Timestamp,
    entry_price: float,
    state: ProfitLockPathState,
    config: HypeExitReplayConfig,
) -> float:
    trigger = state.trigger
    if trigger is None:
        raise RuntimeError("triggered HYPE floor result lacks trigger evidence")
    trigger_ms = int(trigger.trigger_timestamp_ms)
    trigger_time = pd.to_datetime(trigger_ms, unit="ms", utc=True)
    raw_exit = float(trigger.reference_price)
    slip = config.slippage_bps_per_side / _BPS_DENOMINATOR
    exit_price = raw_exit * (1.0 - slip if side == "long" else 1.0 + slip)
    direction = 1.0 if side == "long" else -1.0
    gross = direction * (exit_price / entry_price - 1.0) * _BPS_DENOMINATOR
    fees = config.fee_bps_per_side * (1.0 + exit_price / entry_price)
    funding = _funding_bps(market, side, entry, trigger_time, entry_price)
    return gross - fees + funding


def _funding_bps(
    market: pd.DataFrame,
    side: str,
    entry: pd.Timestamp,
    exit_time: pd.Timestamp,
    entry_price: float,
) -> float:
    rows = market.loc[(market.index > entry) & (market.index <= exit_time)]
    direction = 1.0 if side == "long" else -1.0
    return sum(
        -direction
        * float(row.funding_rate)
        * (float(row.open) / entry_price)
        * _BPS_DENOMINATOR
        for row in rows.itertuples()
    )


def _completed_path(
    market: pd.DataFrame,
    entry: pd.Timestamp,
    exit_time: pd.Timestamp,
) -> tuple[Candle, ...]:
    expected = pd.date_range(entry, exit_time - _MINUTE, freq="1min", tz="UTC")
    observed = market.loc[(market.index >= entry) & (market.index < exit_time)]
    if not observed.index.equals(expected):
        raise ValueError("profit floor requires a continuous completed one-minute path")
    return tuple(
        Candle(
            int(timestamp.timestamp() * 1_000),
            float(row.open),
            float(row.high),
            float(row.low),
            float(row.close),
        )
        for timestamp, row in observed.iterrows()
    )


def _summary(
    outcomes: tuple[Record, ...], field: str, *, count_triggers: bool
) -> dict[str, object]:
    ordered = sorted(outcomes, key=lambda row: str(row["entry_timestamp_utc"]))
    values = [_number(row[field], field) for row in ordered]
    gains = sum(value for value in values if value > 0.0)
    losses = -sum(value for value in values if value < 0.0)
    largest = max((value for value in values if value > 0.0), default=0.0)
    return {
        "trades": len(values),
        "wins": sum(value > 0.0 for value in values),
        "losses": sum(value < 0.0 for value in values),
        "net_return_bps": sum(values),
        "profit_factor": gains / losses if losses else None,
        "without_largest_winner_net_bps": sum(values) - largest,
        "maximum_drawdown_bps": _maximum_drawdown(values),
        "triggered_lifecycles": (
            sum(row["status"] == "triggered" for row in ordered)
            if count_triggers
            else 0
        ),
        "long_net_return_bps": _side_net(ordered, values, "long"),
        "short_net_return_bps": _side_net(ordered, values, "short"),
    }


def _fold_summary(
    index: pd.DatetimeIndex,
    outcomes: tuple[Record, ...],
    fold_count: int,
) -> dict[str, object]:
    end = index[-1] + _MINUTE
    step = (end.value - index[0].value) // fold_count
    bounds = pd.to_datetime(
        [index[0].value + step * fold for fold in range(fold_count)] + [end.value],
        utc=True,
    )
    native = [0.0] * fold_count
    challenger = [0.0] * fold_count
    for row in outcomes:
        stamp = pd.Timestamp(str(row["entry_timestamp_utc"]))
        fold = min(
            max(int(bounds.searchsorted(stamp, side="right") - 1), 0), fold_count - 1
        )
        native[fold] += _number(row["actual_net_return_bps"], "native fold")
        challenger[fold] += _number(row["estimated_net_return_bps"], "challenger fold")
    return {
        "native_net_bps": native,
        "challenger_net_bps": challenger,
        "native_positive_folds": sum(value > 0.0 for value in native),
        "challenger_positive_folds": sum(value > 0.0 for value in challenger),
    }


def _maximum_drawdown(values: list[float]) -> float:
    equity = peak = drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def _side_net(rows: list[Record], values: list[float], side: str) -> float:
    return sum(
        value for row, value in zip(rows, values, strict=True) if row["side"] == side
    )


def _validate_market(market: pd.DataFrame) -> None:
    required = {"open", "high", "low", "close", "funding_rate"}
    if required - set(market.columns):
        raise ValueError("profit-floor market is missing required columns")
    index = market.index
    if not isinstance(index, pd.DatetimeIndex) or index.tz is None:
        raise ValueError("profit-floor market requires timezone-aware timestamps")
    if index.empty or index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError("profit-floor market timestamps must be ordered and unique")


def _outcome_records(value: object) -> tuple[Record, ...]:
    if not isinstance(value, list) or not all(
        isinstance(row, Mapping) for row in value
    ):
        raise ValueError("profit-floor period outcomes must be objects")
    return tuple(value)


def _validate_fold_count(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("profit-floor fold_count must be positive")


def _timestamp(value: object, label: str) -> pd.Timestamp:
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is None:
        raise ValueError(f"profit-floor {label} timestamp must be timezone-aware")
    return parsed.tz_convert("UTC")


def _side(value: object) -> str:
    if value not in {"long", "short"}:
        raise ValueError("profit-floor trade side must be long or short")
    return str(value)


def _positive(value: object, label: str) -> float:
    parsed = _number(value, label)
    if parsed <= 0.0:
        raise ValueError(f"profit-floor {label} must be positive")
    return parsed


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"profit-floor {label} must be numeric")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"profit-floor {label} must be finite")
    return parsed


def _utc_iso(value: int | None) -> str | None:
    if value is None:
        return None
    return pd.to_datetime(value, unit="ms", utc=True).isoformat()


def _report_contract() -> dict[str, object]:
    return {
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "performance_gate": False,
    }


def _report_limitations() -> list[str]:
    return [
        "the policy was declared after observing an unrelated open winner",
        "fixed-entry sensitivity does not model changed re-entry availability",
        "one-minute OHLC cannot reproduce intrabar ordering or private IOC fills",
        "the later confirmation window is sparse and was previously opened",
        "no live strategy, exit, sizing, or routing authority is granted",
    ]
