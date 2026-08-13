"""Price-only, causal port of the local DAFE Trend State reference.

The TradingView reference optionally uses proprietary footprint bars. This
research port intentionally excludes that unavailable input and reports the
price/volume state engine without changing the Hypervelocity runtime.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from hypervector.strategies.indicators import atr, ema

_REQUIRED = {"open", "high", "low", "close", "volume"}


@dataclass(frozen=True)
class PriceTrendStateConfig:
    """Frozen price-only parameters from ``trend_state.pine``."""

    anchor_length: int = 21
    atr_length: int = 21
    decay_rate: float = 0.80
    impulse_weight: float = 1.20
    structure_weight: float = 1.35
    exhaustion_weight: float = 1.15
    continuation_weight: float = 1.00
    compression_weight: float = 0.90
    enter_net_threshold: float = 12.0
    hold_net_threshold: float = 5.0
    dominance_threshold: float = 0.18
    opposing_pressure_threshold: float = 0.58
    damage_threshold: float = 4.0
    damage_decay_multiplier: float = 1.75
    damage_impulse_retention: float = 0.88
    damage_hold_ease: float = 0.80
    damage_pressure_ease: float = 0.92

    def __post_init__(self) -> None:
        if self.anchor_length < 2 or self.atr_length < 1:
            raise ValueError("trend-state lengths must be positive")
        if not 0.0 < self.decay_rate < 1.0:
            raise ValueError("decay_rate must be within (0, 1)")
        numeric = (
            self.impulse_weight,
            self.structure_weight,
            self.exhaustion_weight,
            self.continuation_weight,
            self.compression_weight,
            self.enter_net_threshold,
            self.hold_net_threshold,
            self.dominance_threshold,
            self.opposing_pressure_threshold,
            self.damage_threshold,
        )
        if not all(math.isfinite(value) and value >= 0.0 for value in numeric):
            raise ValueError("trend-state thresholds and weights must be finite")


@dataclass
class _Buckets:
    impulse_bull: float = 0.0
    impulse_bear: float = 0.0
    structure_bull: float = 0.0
    structure_bear: float = 0.0
    exhaustion_bull: float = 0.0
    exhaustion_bear: float = 0.0
    continuation_bull: float = 0.0
    continuation_bear: float = 0.0
    compression_bull: float = 0.0
    compression_bear: float = 0.0

    def decay(self, rate: float) -> None:
        for name in self.__dataclass_fields__:
            setattr(self, name, float(getattr(self, name)) * rate)

    def clip(self) -> None:
        caps = (25.0, 25.0, 30.0, 30.0, 20.0, 20.0, 20.0, 20.0, 15.0, 15.0)
        for name, cap in zip(self.__dataclass_fields__, caps, strict=True):
            setattr(self, name, min(max(float(getattr(self, name)), 0.0), cap))


@dataclass(frozen=True)
class _Pressure:
    bull: float
    bear: float
    net: float
    dominance: float
    bull_ratio: float
    bear_ratio: float


@dataclass
class _Engine:
    config: PriceTrendStateConfig
    buckets: _Buckets
    state: int = 0
    bull_peak: float = 0.0
    bear_peak: float = 0.0

    def add_evidence(self, row: pd.Series) -> None:
        b = self.buckets
        b.decay(self.config.decay_rate)
        b.impulse_bull += (4.0 + 1.5 * _flag(row, "volume_boost")) * _flag(
            row, "bull_impulse"
        )
        b.impulse_bear += (4.0 + 1.5 * _flag(row, "volume_boost")) * _flag(
            row, "bear_impulse"
        )
        b.structure_bull += 6.0 * _flag(row, "broke_up")
        b.structure_bear += 6.0 * _flag(row, "broke_down")
        b.structure_bull += 5.5 * _flag(row, "reclaim_bull") + 4.0 * _flag(
            row, "sweep_bull"
        )
        b.structure_bear += 5.5 * _flag(row, "reclaim_bear") + 4.0 * _flag(
            row, "sweep_bear"
        )
        b.exhaustion_bull += 2.0 * _flag(row, "reclaim_bull") + 4.5 * _flag(
            row, "bull_exhaustion"
        )
        b.exhaustion_bear += 2.0 * _flag(row, "reclaim_bear") + 4.5 * _flag(
            row, "bear_exhaustion"
        )
        b.continuation_bull += 2.0 * _flag(row, "bull_continuation")
        b.continuation_bear += 2.0 * _flag(row, "bear_continuation")
        self._invalidate_continuation(row)
        b.compression_bull += 1.5 * _flag(row, "bull_compression")
        b.compression_bear += 1.5 * _flag(row, "bear_compression")
        b.clip()

    def _invalidate_continuation(self, row: pd.Series) -> None:
        b = self.buckets
        if _flag(row, "below_anchor") and b.continuation_bull > 0.0:
            b.continuation_bull *= 0.62
        if _flag(row, "above_anchor") and b.continuation_bear > 0.0:
            b.continuation_bear *= 0.62
        if _flag(row, "crossed_below") and b.continuation_bull > 0.0:
            b.continuation_bull *= 0.50
        if _flag(row, "crossed_above") and b.continuation_bear > 0.0:
            b.continuation_bear *= 0.50

    def pressure(self) -> _Pressure:
        b, c = self.buckets, self.config
        bull = b.impulse_bull * c.impulse_weight + b.structure_bull * c.structure_weight
        bull += b.exhaustion_bull * c.exhaustion_weight
        bull += (
            b.continuation_bull * c.continuation_weight
            + b.compression_bull * c.compression_weight
        )
        bear = b.impulse_bear * c.impulse_weight + b.structure_bear * c.structure_weight
        bear += b.exhaustion_bear * c.exhaustion_weight
        bear += (
            b.continuation_bear * c.continuation_weight
            + b.compression_bear * c.compression_weight
        )
        activity = bull + bear
        net = bull - bear
        dominance = net / activity if activity > 0.0 else 0.0
        return _Pressure(
            bull,
            bear,
            net,
            dominance,
            bull / activity if activity else 0.0,
            bear / activity if activity else 0.0,
        )

    def damage(self, row: pd.Series, pressure: _Pressure) -> tuple[float, float]:
        bull = bear = 0.0
        if self.state == 1:
            bull += 1.5 * _flag(row, "below_anchor") + _flag(row, "bear_impulse")
            bull += 0.75 * _flag(row, "upper_wick_damage") + _flag(row, "slope_down")
            bull += _flag_value(pressure.bear_ratio > 0.45) + 0.75 * _flag(
                row, "lower_close_high"
            )
            bull += 1.25 * _flag(row, "crossed_below")
        if self.state == -1:
            bear += 1.5 * _flag(row, "above_anchor") + _flag(row, "bull_impulse")
            bear += 0.75 * _flag(row, "lower_wick_damage") + _flag(row, "slope_up")
            bear += _flag_value(pressure.bull_ratio > 0.45) + 0.75 * _flag(
                row, "higher_close_low"
            )
            bear += 1.25 * _flag(row, "crossed_above")
        return bull, bear

    def apply_damage(self, bull: float, bear: float) -> tuple[bool, bool]:
        c, b = self.config, self.buckets
        bull_hit = self.state == 1 and bull >= c.damage_threshold
        bear_hit = self.state == -1 and bear >= c.damage_threshold
        if bull_hit:
            b.continuation_bull *= max(0.0, 1.0 - 0.25 * c.damage_decay_multiplier)
            b.impulse_bull *= c.damage_impulse_retention
            b.structure_bull *= 0.92
            b.exhaustion_bear += 1.5
            b.impulse_bear += 1.0
        if bear_hit:
            b.continuation_bear *= max(0.0, 1.0 - 0.25 * c.damage_decay_multiplier)
            b.impulse_bear *= c.damage_impulse_retention
            b.structure_bear *= 0.92
            b.exhaustion_bull += 1.5
            b.impulse_bull += 1.0
        b.clip()
        return bull_hit, bear_hit

    def advance(
        self, pressure: _Pressure, bull_damaged: bool, bear_damaged: bool
    ) -> tuple[bool, bool, bool]:
        previous, c = self.state, self.config
        self.bull_peak = (
            pressure.bull if pressure.bull > self.bull_peak else self.bull_peak * 0.985
        )
        self.bear_peak = (
            pressure.bear if pressure.bear > self.bear_peak else self.bear_peak * 0.985
        )
        bull_erosion, bear_erosion = (
            max(0.0, self.bull_peak - pressure.bull),
            max(0.0, self.bear_peak - pressure.bear),
        )
        hold = c.hold_net_threshold * (
            c.damage_hold_ease if bull_damaged or bear_damaged else 1.0
        )
        opposing = c.opposing_pressure_threshold * (
            c.damage_pressure_ease if bull_damaged or bear_damaged else 1.0
        )
        enter_bull = (
            pressure.net > c.enter_net_threshold
            and pressure.dominance > c.dominance_threshold
        )
        enter_bear = (
            pressure.net < -c.enter_net_threshold
            and pressure.dominance < -c.dominance_threshold
        )
        if previous == 1 and (
            pressure.net < hold
            or pressure.bear_ratio > opposing
            or bull_erosion > pressure.bull * 0.35
        ):
            self.state = 0
        elif previous == -1 and (
            pressure.net > -hold
            or pressure.bull_ratio > opposing
            or bear_erosion > pressure.bear * 0.35
        ):
            self.state = 0
        if self.state == 0:
            self.state = 1 if enter_bull else -1 if enter_bear else 0
        return (
            self.state == 1 and previous != 1,
            self.state == -1 and previous != -1,
            self.state == 0 and previous != 0,
        )


def _flag(row: pd.Series, name: str) -> float:
    return _flag_value(bool(row[name]))


def _flag_value(value: bool) -> float:
    return 1.0 if value else 0.0


def _validate_bars(bars: pd.DataFrame) -> pd.DataFrame:
    missing = _REQUIRED.difference(bars.columns)
    if missing:
        raise ValueError(f"trend-state bars missing columns: {sorted(missing)}")
    if not isinstance(bars.index, pd.DatetimeIndex):
        raise ValueError("trend-state bars require a DatetimeIndex")
    if not bars.index.is_monotonic_increasing or bars.index.has_duplicates:
        raise ValueError("trend-state bar index must be unique and increasing")
    frame = bars.loc[:, sorted(_REQUIRED)].astype(float)
    if not np.isfinite(frame.to_numpy()).all():
        raise ValueError("trend-state bars contain non-finite values")
    if (frame[["open", "high", "low", "close"]] <= 0.0).any().any() or (
        frame["volume"] < 0.0
    ).any():
        raise ValueError("trend-state prices must be positive and volume non-negative")
    return frame


def _basic_features(bars: pd.DataFrame, config: PriceTrendStateConfig) -> pd.DataFrame:
    frame = _validate_bars(bars)
    source = frame[["high", "low", "close"]].mean(axis=1)
    anchor = ema(source, config.anchor_length)
    span = frame["high"] - frame["low"]
    body = (frame["close"] - frame["open"]).abs()
    body_average = body.rolling(10).mean().fillna(body)
    span_average = span.rolling(10).mean()
    volume_average = frame["volume"].rolling(20).mean()
    volume_ratio = (
        (frame["volume"] / volume_average).where(volume_average > 0.0, 1.0).fillna(1.0)
    )
    close_position = ((frame["close"] - frame["low"]) / span).where(span > 0.0, 0.5)
    swing_high = frame["high"].rolling(5).max().shift(1)
    swing_low = frame["low"].rolling(5).min().shift(1)
    lower_wick = frame[["open", "close"]].min(axis=1) - frame["low"]
    upper_wick = frame["high"] - frame[["open", "close"]].max(axis=1)
    atr_value = atr(frame["high"], frame["low"], frame["close"], config.atr_length)
    atr_slow = atr_value.rolling(30).mean()
    atr_compression = (atr_value / atr_slow).where(atr_slow > 0.0, 1.0).fillna(1.0)
    return pd.DataFrame(
        {
            "open": frame.open,
            "high": frame.high,
            "low": frame.low,
            "close": frame.close,
            "volume_ratio": volume_ratio,
            "span": span,
            "body": body,
            "body_average": body_average,
            "span_average": span_average,
            "close_position": close_position,
            "anchor": anchor,
            "slope": anchor.diff(),
            "swing_high": swing_high,
            "swing_low": swing_low,
            "lower_wick_ratio": (lower_wick / span).where(span > 0.0, 0.0),
            "upper_wick_ratio": (upper_wick / span).where(span > 0.0, 0.0),
            "atr_compression": atr_compression,
        },
        index=frame.index,
    )


def _conditions(features: pd.DataFrame) -> pd.DataFrame:
    f = features
    bull_body, bear_body = f.close > f.open, f.close < f.open
    above, below = f.close > f.anchor, f.close < f.anchor
    crossed_above = above & f.close.shift(1).le(f.anchor.shift(1))
    crossed_below = below & f.close.shift(1).ge(f.anchor.shift(1))
    broke_up, broke_down = f.close > f.swing_high, f.close < f.swing_low
    reclaim_bull = f.low.lt(f.swing_low) & f.close.gt(f.swing_low) & bull_body
    reclaim_bear = f.high.gt(f.swing_high) & f.close.lt(f.swing_high) & bear_body
    impulse_size = f.body.gt(f.body_average * 1.15) & f.span.gt(f.span_average * 1.05)
    narrow = f.span_average.gt(0.0) & f.span.lt(f.span_average * 0.8)
    return pd.DataFrame(
        {
            "volume_boost": f.volume_ratio > 1.2,
            "bull_impulse": bull_body & impulse_size & f.close_position.gt(0.7),
            "bear_impulse": bear_body & impulse_size & f.close_position.lt(0.3),
            "broke_up": broke_up,
            "broke_down": broke_down,
            "reclaim_bull": reclaim_bull,
            "reclaim_bear": reclaim_bear,
            "sweep_bull": f.low.lt(f.swing_low) & f.close.gt(f.swing_low),
            "sweep_bear": f.high.gt(f.swing_high) & f.close.lt(f.swing_high),
            "bull_exhaustion": bear_body
            & f.lower_wick_ratio.gt(0.45)
            & f.volume_ratio.gt(1.2),
            "bear_exhaustion": bull_body
            & f.upper_wick_ratio.gt(0.45)
            & f.volume_ratio.gt(1.2),
            "bull_continuation": f.slope.gt(0.0) & above & f.close.gt(f.close.shift(1)),
            "bear_continuation": f.slope.lt(0.0) & below & f.close.lt(f.close.shift(1)),
            "bull_compression": narrow & f.atr_compression.lt(0.95) & above,
            "bear_compression": narrow & f.atr_compression.lt(0.95) & below,
            "above_anchor": above,
            "below_anchor": below,
            "crossed_above": crossed_above,
            "crossed_below": crossed_below,
            "upper_wick_damage": f.upper_wick_ratio.gt(0.35),
            "lower_wick_damage": f.lower_wick_ratio.gt(0.35),
            "slope_up": f.slope.gt(0.0),
            "slope_down": f.slope.lt(0.0),
            "lower_close_high": f.close.le(f.close.shift(1))
            & f.high.le(f.high.shift(1)),
            "higher_close_low": f.close.ge(f.close.shift(1)) & f.low.ge(f.low.shift(1)),
        },
        index=f.index,
    ).fillna(False)


def _snapshot(
    engine: _Engine,
    pressure: _Pressure,
    damage: tuple[float, float],
    shifts: tuple[bool, bool, bool],
) -> dict[str, object]:
    return {
        "trend_state": "BULL"
        if engine.state == 1
        else "BEAR"
        if engine.state == -1
        else "TRANSITION",
        "state_code": engine.state,
        "bull_confidence": pressure.bull,
        "bear_confidence": pressure.bear,
        "net_confidence": pressure.net,
        "dominance": pressure.dominance,
        "bull_pressure": pressure.bull_ratio,
        "bear_pressure": pressure.bear_ratio,
        "bull_damage_score": damage[0],
        "bear_damage_score": damage[1],
        "bull_shift": shifts[0],
        "bear_shift": shifts[1],
        "transition_shift": shifts[2],
    }


def classify_price_trend_state(
    bars: pd.DataFrame, config: PriceTrendStateConfig | None = None
) -> pd.DataFrame:
    """Return causal price/volume Trend State annotations for completed bars."""
    cfg = config or PriceTrendStateConfig()
    conditions = _conditions(_basic_features(bars, cfg))
    engine = _Engine(cfg, _Buckets())
    rows: list[dict[str, object]] = []
    for _, row in conditions.iterrows():
        engine.add_evidence(row)
        preliminary = engine.pressure()
        damage = engine.damage(row, preliminary)
        damaged = engine.apply_damage(*damage)
        final = engine.pressure()
        shifts = engine.advance(final, *damaged)
        rows.append(_snapshot(engine, final, damage, shifts))
    return pd.DataFrame(rows, index=bars.index)
