"""Exact entry-component telemetry for the BTC liquidity-sweep long route."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from hypervector.live.provider_readiness import SignalReadiness
from hypervector.research.liquidity_sweep_long import (
    LIQUIDITY_SWEEP_CLEARANCE_BPS,
    LIQUIDITY_SWEEP_EMA_LENGTH,
    LIQUIDITY_SWEEP_LOOKBACK,
    LIQUIDITY_SWEEP_VOLUME_MULTIPLE,
)
from hypervector.strategies.indicators import ema


@dataclass(frozen=True)
class _SweepMeasurements:
    prior_low: float
    current_low: float
    close: float
    ema_value: float
    volume_multiple: float

    @property
    def clearance_bps(self) -> float:
        return (self.prior_low - self.current_low) / self.prior_low * 10_000.0


def liquidity_sweep_long_readiness(
    hourly_bars: pd.DataFrame,
    decision_hour: pd.Timestamp,
) -> SignalReadiness:
    """Measure the four exact registered long-entry prerequisites."""
    values = _measure(hourly_bars, decision_hour)
    conditions = _conditions(values)
    blockers = tuple(name for name, met in conditions if not met)
    return SignalReadiness(
        side="long" if not blockers else None,
        conditions_met=sum(met for _, met in conditions),
        conditions_required=len(conditions),
        blockers=blockers,
        indicators=_indicators(values),
        metrics=_metrics(values),
    )


def _measure(bars: pd.DataFrame, decision_hour: pd.Timestamp) -> _SweepMeasurements:
    required = {"high", "low", "close", "volume"}
    missing = sorted(required.difference(bars.columns))
    if missing:
        raise ValueError(f"liquidity-sweep readiness missing columns: {missing}")
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("liquidity-sweep readiness requires aware hourly bars")
    timestamp = pd.Timestamp(decision_hour).tz_convert("UTC")
    if timestamp not in bars.index:
        raise ValueError("liquidity-sweep decision hour is absent from hourly bars")
    location = bars.index.get_loc(timestamp)
    if not isinstance(location, int) or location < LIQUIDITY_SWEEP_EMA_LENGTH:
        raise ValueError("liquidity-sweep readiness requires 55 prior hourly bars")
    prior = bars.iloc[location - LIQUIDITY_SWEEP_LOOKBACK : location]
    current = bars.iloc[location]
    return _SweepMeasurements(
        prior_low=float(prior["low"].min()),
        current_low=float(current["low"]),
        close=float(current["close"]),
        ema_value=float(ema(bars["close"].iloc[: location + 1], 55).iloc[-1]),
        volume_multiple=float(current["volume"] / prior["volume"].mean()),
    )


def _conditions(values: _SweepMeasurements) -> tuple[tuple[str, bool], ...]:
    return (
        (
            "sweep_below_prior_low_absent",
            values.clearance_bps > LIQUIDITY_SWEEP_CLEARANCE_BPS,
        ),
        ("close_reclaim_absent", values.close > values.prior_low),
        (
            "volume_below_1.20x",
            values.volume_multiple >= LIQUIDITY_SWEEP_VOLUME_MULTIPLE,
        ),
        ("close_below_ema55", values.close >= values.ema_value),
    )


def _indicators(values: _SweepMeasurements) -> tuple[str, ...]:
    ema_gap = (values.close - values.ema_value) / values.close * 10_000.0
    reclaim = (values.close - values.prior_low) / values.prior_low * 10_000.0
    return (
        f"SWEEP {values.clearance_bps:+.1f}/{LIQUIDITY_SWEEP_CLEARANCE_BPS:.1f}bps",
        f"RECLAIM {reclaim:+.1f}bps",
        f"VOLUME {values.volume_multiple:.2f}/{LIQUIDITY_SWEEP_VOLUME_MULTIPLE:.2f}x",
        f"EMA55 GAP {ema_gap:+.1f}bps",
    )


def _metrics(values: _SweepMeasurements) -> dict[str, object]:
    return {
        "signal_timeframe": "1h",
        "entry_side": "long",
        "prior_20h_low": values.prior_low,
        "sweep_low": values.current_low,
        "clearance_bps": values.clearance_bps,
        "reclaim_close": values.close,
        "volume_multiple": values.volume_multiple,
        "volume_multiple_required": LIQUIDITY_SWEEP_VOLUME_MULTIPLE,
        "ema55": values.ema_value,
        "close_above_ema55": values.close >= values.ema_value,
    }
