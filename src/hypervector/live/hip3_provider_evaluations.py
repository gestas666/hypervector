"""Typed readiness and recipe-exit evaluation for HIP-3 providers."""

from __future__ import annotations

from decimal import Decimal
from numbers import Real
from typing import Literal

import math
import pandas as pd

from hypervector.live.hip3_ledger_pressure import Hip3PressureObservation
from hypervector.live.hip3_provider_inputs import decision_time_ms
from hypervector.live.multi_asset_signal_source import ProviderEvaluation
from hypervector.live.provider_readiness import SignalReadiness
from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)
from hypervector.research.swing_ha_signals import SwingHaSignalConfig

Hip3PressureStatus = Literal[
    "available",
    "no_candidate",
    "stale_candidate",
    "decision_not_observed",
    "post_decision_candidate",
    "not_evaluated_for_prior_decision",
]


def swing_evaluation(
    *,
    strategy_id: str,
    symbol: str,
    timestamp: pd.Timestamp,
    bar: pd.Series,
    signal: pd.Series,
    config: SwingHaSignalConfig,
) -> ProviderEvaluation:
    """Project one completed Swing/HA entry and recipe-exit decision."""
    entry_side = _entry_side(signal)
    side = entry_side or _ema_side(signal)
    confirmations, confirmation_labels = _swing_conditions(signal, side, config)
    conditions = (entry_side is not None, *confirmations)
    labels = (_entry_trigger_blocker(config), *confirmation_labels)
    eligible = all(conditions)
    exit_sides = _swing_exit_sides(signal)
    exit_reason = _swing_exit_reason(signal, config, exit_sides)
    blockers = tuple(label for value, label in zip(conditions, labels) if not value)
    readiness = SignalReadiness(
        side=side,
        conditions_met=sum(conditions),
        conditions_required=len(conditions),
        blockers=() if eligible else blockers,
        indicators=_swing_indicators(signal, side),
        metrics=_swing_metrics(signal, config, exit_sides, exit_reason),
    )
    return _evaluation(
        strategy_id,
        symbol,
        timestamp,
        bar,
        side,
        eligible,
        "swing_ha_alignment" if eligible else exit_reason or readiness.blockers[0],
        readiness,
        "swing_ha_buy_green_or_sell_red" if eligible else exit_reason or "none",
        exit_sides=exit_sides,
        exit_reason=exit_reason,
    )


def _entry_trigger_blocker(config: SwingHaSignalConfig) -> str:
    """Name the exact missing entry event without implying indicator warmup."""
    if config.entry_mode == "onset":
        return "fresh_entry_onset_absent"
    return "entry_state_absent"


def breakout_evaluation(
    *,
    strategy_id: str,
    symbol: str,
    timestamp: pd.Timestamp,
    bar: pd.Series,
    signal: pd.Series,
    config: Hip3BreakoutPressureConfig,
    pressure: Hip3PressureObservation | None,
    pressure_status: Hip3PressureStatus,
    pressure_cutoff_ms: int,
    maximum_pressure_age_ms: int,
) -> ProviderEvaluation:
    """Project one completed breakout-pressure entry decision."""
    side = _entry_side(signal) or _breakout_side(bar, signal) or _ema_side(signal)
    conditions, labels = _breakout_conditions(bar, signal, side, pressure, config)
    eligible = _entry_side(signal) is not None and all(conditions)
    blockers = tuple(label for value, label in zip(conditions, labels) if not value)
    age = (
        None
        if pressure is None
        else (pressure_cutoff_ms - pressure.recv_ts_ms) / 1_000.0
    )
    readiness = SignalReadiness(
        side=side,
        conditions_met=sum(conditions),
        conditions_required=4,
        blockers=() if eligible else blockers or ("breakout_not_active",),
        indicators=_breakout_indicators(signal, side, pressure, pressure_status),
        metrics=_breakout_metrics(
            bar,
            signal,
            side,
            config,
            pressure,
            age,
            pressure_status,
            maximum_pressure_age_ms,
        ),
    )
    return _evaluation(
        strategy_id,
        symbol,
        timestamp,
        bar,
        side,
        eligible,
        "breakout_pressure_confirmed" if eligible else readiness.blockers[0],
        readiness,
        "breakout_ema_depth10_pressure" if eligible else "none",
    )


def _swing_metrics(
    signal: pd.Series,
    config: SwingHaSignalConfig,
    exit_sides: frozenset[str],
    exit_reason: str | None,
) -> dict[str, object]:
    return {
        "ema_fast": _finite_or_none(signal.get("ema_fast")),
        "ema_slow": _finite_or_none(signal.get("ema_slow")),
        "ha_color": _finite_or_none(signal.get("ha_color")),
        "active_order_block_direction": _finite_or_none(
            signal.get("active_ob_direction")
        ),
        "entry_mode": config.entry_mode,
        "exit_mode": config.exit_mode,
        "long_exit": "long" in exit_sides,
        "short_exit": "short" in exit_sides,
        "exit_reason": exit_reason,
        "source_timeframe": "15m",
    }


def _swing_exit_sides(signal: pd.Series) -> frozenset[str]:
    return frozenset(
        side
        for side, field in (("long", "long_exit"), ("short", "short_exit"))
        if bool(signal.get(field, False))
    )


def _swing_exit_reason(
    signal: pd.Series,
    config: SwingHaSignalConfig,
    exit_sides: frozenset[str],
) -> str | None:
    if not exit_sides:
        return None
    if bool(signal.get("gap_recovery_exit", False)):
        return "hip3_swing_gap_recovery"
    return f"hip3_swing_{config.exit_mode}"


def _swing_conditions(
    signal: pd.Series,
    side: str | None,
    config: SwingHaSignalConfig,
) -> tuple[tuple[bool, ...], tuple[str, ...]]:
    long = side == "long"
    ema = _comparison(signal, "ema_fast", "ema_slow", greater=long)
    state = (
        bool(signal.get("buy_state" if long else "sell_state", False))
        if side
        else False
    )
    color = int(signal.get("ha_color", 0)) == (1 if long else -1) if side else False
    block = (
        True
        if config.order_block_role == "none"
        else int(signal.get("active_ob_direction", 0)) == (1 if long else -1)
        if side
        else False
    )
    return (ema, state, color, block), (
        "ema_alignment_missing",
        "pivot_break_state_missing",
        "heikin_ashi_color_mismatch",
        "order_block_agreement_missing",
    )


def _swing_indicators(signal: pd.Series, side: str | None) -> tuple[str, ...]:
    state_field = "buy_state" if side == "long" else "sell_state"
    return (
        f"SIDE {(side or 'NONE').upper()}",
        f"EMA {_display(signal.get('ema_fast'))} / {_display(signal.get('ema_slow'))}",
        f"HA COLOR {_display(signal.get('ha_color'))}",
        f"PIVOT STATE {'YES' if bool(signal.get(state_field, False)) else 'NO'}",
        f"ORDER BLOCK {_display(signal.get('active_ob_direction'))}",
    )


def _breakout_conditions(
    bar: pd.Series,
    signal: pd.Series,
    side: str | None,
    pressure: Hip3PressureObservation | None,
    config: Hip3BreakoutPressureConfig,
) -> tuple[tuple[bool, ...], tuple[str, ...]]:
    long = side == "long"
    level = signal.get("prior_breakout_high" if long else "prior_breakout_low")
    level_ready = _finite_or_none(level) is not None
    close = float(bar["close"])
    breakout = level_ready and (close > float(level) if long else close < float(level))
    ema = _comparison(signal, "fast_ema", "slow_ema", greater=long)
    aligned = pressure is not None and (
        pressure.imbalance_10 >= config.minimum_abs_imbalance
        if long
        else pressure.imbalance_10 <= -config.minimum_abs_imbalance
    )
    return (level_ready, breakout, ema, aligned), (
        "breakout_history_warmup",
        "breakout_level_not_crossed",
        "ema_alignment_missing",
        "order_pressure_unavailable" if pressure is None else "order_pressure_opposed",
    )


def _breakout_indicators(
    signal: pd.Series,
    side: str | None,
    pressure: Hip3PressureObservation | None,
    pressure_status: Hip3PressureStatus,
) -> tuple[str, ...]:
    return (
        f"SIDE {(side or 'NONE').upper()}",
        f"PRIOR HIGH {_display(signal.get('prior_breakout_high'))}",
        f"PRIOR LOW {_display(signal.get('prior_breakout_low'))}",
        f"EMA {_display(signal.get('fast_ema'))} / {_display(signal.get('slow_ema'))}",
        f"L2 IMB10 {_display(None if pressure is None else pressure.imbalance_10)}",
        f"L2 STATUS {pressure_status.upper()}",
    )


def _breakout_metrics(
    bar: pd.Series,
    signal: pd.Series,
    side: str | None,
    config: Hip3BreakoutPressureConfig,
    pressure: Hip3PressureObservation | None,
    age: float | None,
    pressure_status: Hip3PressureStatus,
    maximum_pressure_age_ms: int,
) -> dict[str, object]:
    metrics: dict[str, object] = {
        "imbalance_10": None if pressure is None else pressure.imbalance_10,
        "pressure_age_seconds": age,
        "pressure_status": pressure_status,
        "maximum_pressure_age_seconds": maximum_pressure_age_ms / 1_000,
        "minimum_abs_imbalance": config.minimum_abs_imbalance,
        "breakout_lookback_bars": config.breakout_lookback_bars,
        "source_timeframe": "15m",
    }
    metrics.update(_breakout_geometry(bar, signal, side, config))
    return metrics


def _breakout_geometry(
    bar: pd.Series,
    signal: pd.Series,
    side: str | None,
    config: Hip3BreakoutPressureConfig,
) -> dict[str, object]:
    close = float(bar["close"])
    high = _finite_or_none(signal.get("prior_breakout_high"))
    low = _finite_or_none(signal.get("prior_breakout_low"))
    level = high if side == "long" else low if side == "short" else None
    distance = _directional_breakout_distance_bps(close, level, side)
    return {
        "prior_breakout_high": high,
        "prior_breakout_low": low,
        "ema_fast": _finite_or_none(signal.get("fast_ema")),
        "ema_slow": _finite_or_none(signal.get("slow_ema")),
        "ema_fast_period": config.fast_ema,
        "ema_slow_period": config.slow_ema,
        "breakout_level": level,
        "reference_close": close,
        "directional_breakout_distance_bps": distance,
        "breakout_distance_semantics": "positive_beyond_side_level_v1",
    }


def _directional_breakout_distance_bps(
    close: float,
    level: float | None,
    side: str | None,
) -> float | None:
    if level is None or side not in {"long", "short"}:
        return None
    direction = 1.0 if side == "long" else -1.0
    return direction * (close - level) / level * 10_000.0


def _evaluation(
    strategy_id: str,
    symbol: str,
    timestamp: pd.Timestamp,
    bar: pd.Series,
    side: str | None,
    eligible: bool,
    reason: str,
    readiness: SignalReadiness,
    trigger: str,
    *,
    exit_sides: frozenset[str] = frozenset(),
    exit_reason: str | None = None,
) -> ProviderEvaluation:
    return ProviderEvaluation(
        strategy_id=strategy_id,
        symbol=symbol,
        decision_time_ms=decision_time_ms(timestamp),
        reference_price=float(bar["close"]),
        decision_action=f"enter_{side}" if eligible else _exit_action(exit_sides),
        eligible=eligible,
        reason=reason,
        side=side,
        readiness=readiness,
        trigger=trigger,
        confidence=readiness.fraction,
        exit_sides=exit_sides,
        exit_reason=exit_reason,
    )


def _exit_action(exit_sides: frozenset[str]) -> str:
    if len(exit_sides) == 1:
        return f"close_{next(iter(exit_sides))}"
    return "close_open_position" if exit_sides else "hold"


def _entry_side(signal: pd.Series) -> str | None:
    if bool(signal.get("long_entry", False)):
        return "long"
    if bool(signal.get("short_entry", False)):
        return "short"
    return None


def _ema_side(signal: pd.Series) -> str | None:
    fast = _finite_or_none(signal.get("ema_fast", signal.get("fast_ema")))
    slow = _finite_or_none(signal.get("ema_slow", signal.get("slow_ema")))
    if fast is None or slow is None or fast == slow:
        return None
    return "long" if fast > slow else "short"


def _breakout_side(bar: pd.Series, signal: pd.Series) -> str | None:
    close = float(bar["close"])
    high = _finite_or_none(signal.get("prior_breakout_high"))
    low = _finite_or_none(signal.get("prior_breakout_low"))
    if high is not None and close > high:
        return "long"
    if low is not None and close < low:
        return "short"
    return None


def _comparison(
    row: pd.Series,
    left: str,
    right: str,
    *,
    greater: bool,
) -> bool:
    first = _finite_or_none(row.get(left))
    second = _finite_or_none(row.get(right))
    if first is None or second is None:
        return False
    return first > second if greater else first < second


def _finite_or_none(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (Real, Decimal)):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _display(value: object) -> str:
    numeric = _finite_or_none(value)
    return "N/A" if numeric is None else f"{numeric:.4g}"
