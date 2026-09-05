"""Exact completed-bar condition telemetry for HIP-3 fresh-onset routes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math

import pandas as pd

from hypervector.research.hip3_breakout_pressure_signals import (
    Hip3BreakoutPressureConfig,
)


@dataclass(frozen=True)
class Hip3Fresh15ConditionTelemetry:
    """Price and EMA facts used by one completed-bar breakout decision."""

    close: float
    prior_breakout_high: float
    prior_breakout_low: float
    fast_ema: float
    slow_ema: float
    long_raw: bool
    short_raw: bool

    def __post_init__(self) -> None:
        """Reject non-finite or internally inconsistent market geometry."""
        prices = (
            self.close,
            self.prior_breakout_high,
            self.prior_breakout_low,
            self.fast_ema,
            self.slow_ema,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in prices):
            raise ValueError("HIP-3 condition prices must be finite and positive")
        if self.prior_breakout_low > self.prior_breakout_high:
            raise ValueError("HIP-3 condition breakout levels are inverted")


def build_condition_telemetry(
    bar: pd.Series,
    signal: pd.Series,
    config: Hip3BreakoutPressureConfig,
) -> Hip3Fresh15ConditionTelemetry | None:
    """Build condition facts, returning unavailable during indicator warmup."""
    fields = (
        float(bar["close"]),
        float(signal["prior_breakout_high"]),
        float(signal["prior_breakout_low"]),
        float(signal["fast_ema"]),
        float(signal["slow_ema"]),
    )
    if any(not math.isfinite(value) for value in fields):
        return None
    close, high, low, fast, slow = fields
    pressure = float(signal["decision_imbalance_10"])
    long_raw, short_raw = _raw_conditions(
        close, high, low, fast, slow, pressure, config
    )
    return Hip3Fresh15ConditionTelemetry(
        close, high, low, fast, slow, long_raw, short_raw
    )


def parse_condition_telemetry(
    raw: object,
    config: Hip3BreakoutPressureConfig,
    pressure: float,
) -> Hip3Fresh15ConditionTelemetry | None:
    """Parse optional journal telemetry and verify its exact signal semantics."""
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) != _FIELD_NAMES:
        raise ValueError("HIP-3 condition anatomy must contain the exact fields")
    value = Hip3Fresh15ConditionTelemetry(
        _number(raw, "close"),
        _number(raw, "prior_breakout_high"),
        _number(raw, "prior_breakout_low"),
        _number(raw, "fast_ema"),
        _number(raw, "slow_ema"),
        _boolean(raw, "long_raw"),
        _boolean(raw, "short_raw"),
    )
    expected = _raw_conditions(
        value.close,
        value.prior_breakout_high,
        value.prior_breakout_low,
        value.fast_ema,
        value.slow_ema,
        pressure,
        config,
    )
    if (value.long_raw, value.short_raw) != expected:
        raise ValueError("HIP-3 condition anatomy contradicts the frozen signal")
    return value


def condition_readiness_metrics(
    value: Hip3Fresh15ConditionTelemetry | None,
    config: Hip3BreakoutPressureConfig,
    pressure: float,
) -> dict[str, object]:
    """Return both-side condition and proximity metrics for TUI telemetry."""
    if value is None:
        return {"condition_anatomy_status": "legacy_or_warmup_unavailable"}
    long = _side_metrics(value, config, pressure, "long")
    short = _side_metrics(value, config, pressure, "short")
    return {
        "condition_anatomy_status": "available",
        "close": value.close,
        "prior_breakout_high": value.prior_breakout_high,
        "prior_breakout_low": value.prior_breakout_low,
        "fast_ema": value.fast_ema,
        "slow_ema": value.slow_ema,
        "ema_fast_period": config.fast_ema,
        "ema_slow_period": config.slow_ema,
        "ema_gap_bps": (value.fast_ema - value.slow_ema) / value.slow_ema * 10_000.0,
        **long,
        **short,
    }


def condition_readiness_indicators(
    value: Hip3Fresh15ConditionTelemetry | None,
    config: Hip3BreakoutPressureConfig,
) -> tuple[str, ...]:
    """Render concise exact condition geometry for the Screen 2 detail view."""
    if value is None:
        return ("PRICE/EMA ANATOMY UNAVAILABLE (LEGACY OR WARMUP)",)
    long_distance = _long_distance_bps(value)
    short_distance = _short_distance_bps(value)
    return (
        f"PX {value.close:.4f} / {config.breakout_lookback_bars}H "
        f"{value.prior_breakout_high:.4f} / {config.breakout_lookback_bars}L "
        f"{value.prior_breakout_low:.4f}",
        f"EMA{config.fast_ema}/{config.slow_ema} {value.fast_ema:.4f} / "
        f"{value.slow_ema:.4f}",
        f"TO HIGH {long_distance:+.2f}bps / TO LOW {short_distance:+.2f}bps",
    )


def canonical_pressure_status(
    pressure_fresh: bool,
    snapshot_count: int,
    exchange_ts_ms: int | None,
) -> str:
    """Normalize raw pressure availability for readiness consumers."""
    if pressure_fresh:
        return "available"
    if snapshot_count == 0 or exchange_ts_ms is None:
        return "no_candidate"
    return "stale_candidate"


def _side_metrics(
    value: Hip3Fresh15ConditionTelemetry,
    config: Hip3BreakoutPressureConfig,
    pressure: float,
    side: str,
) -> dict[str, object]:
    long = side == "long"
    price = (
        value.close > value.prior_breakout_high
        if long
        else value.close < value.prior_breakout_low
    )
    ema = value.fast_ema > value.slow_ema if long else value.fast_ema < value.slow_ema
    confirmed = (
        pressure >= config.minimum_abs_imbalance
        if long
        else pressure <= -config.minimum_abs_imbalance
    )
    return {
        f"{side}_price_breakout": price,
        f"{side}_ema_alignment": ema,
        f"{side}_pressure_confirmation": confirmed,
        f"{side}_raw_condition": value.long_raw if long else value.short_raw,
        f"{side}_breakout_distance_bps": _long_distance_bps(value)
        if long
        else _short_distance_bps(value),
    }


def _raw_conditions(
    close: float,
    high: float,
    low: float,
    fast: float,
    slow: float,
    pressure: float,
    config: Hip3BreakoutPressureConfig,
) -> tuple[bool, bool]:
    long = close > high and fast > slow and pressure >= config.minimum_abs_imbalance
    short = close < low and fast < slow and pressure <= -config.minimum_abs_imbalance
    return long, short


def _long_distance_bps(value: Hip3Fresh15ConditionTelemetry) -> float:
    return (value.prior_breakout_high - value.close) / value.close * 10_000.0


def _short_distance_bps(value: Hip3Fresh15ConditionTelemetry) -> float:
    return (value.close - value.prior_breakout_low) / value.close * 10_000.0


def _number(raw: Mapping[str, object], field: str) -> float:
    value = raw.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"HIP-3 condition {field} must be numeric")
    return float(value)


def _boolean(raw: Mapping[str, object], field: str) -> bool:
    value = raw.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"HIP-3 condition {field} must be boolean")
    return value


_FIELD_NAMES = {
    "close",
    "prior_breakout_high",
    "prior_breakout_low",
    "fast_ema",
    "slow_ema",
    "long_raw",
    "short_raw",
}
