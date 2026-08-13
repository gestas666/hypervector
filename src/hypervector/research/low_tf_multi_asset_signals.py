"""Auditable bidirectional signals for the bounded low-timeframe cohort."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

SignalRecord = dict[str, object]

_REQUIRED_COLUMNS = {
    "bar_open_at",
    "open",
    "high",
    "low",
    "close",
    "range_high_240",
    "range_low_240",
    "range_midpoint_240",
    "range_width_bps",
    "breakout_high_120",
    "breakout_low_120",
    "ema_fast_5m",
    "ema_slow_5m",
    "bbwp_percentile",
    "bbwp_signal",
    "rsi",
    "rsi_signal",
    "rsi_bearish_divergence",
    "rsi_bullish_divergence",
    "pmarp",
    "pmarp_signal",
    "atr",
    "context_direction",
    "context_fast_slope_bps",
}
_OUTPUT_COLUMNS = (
    "decision_time_utc",
    "decision_position",
    "symbol",
    "family",
    "side",
    "exit_variant",
    "trigger_price",
    "stop_anchor_price",
    "target_anchor_price",
    "invalidation_mode",
    "max_hold_bars",
    "source_backed_facts",
    "hypothesis_facts",
    "reason",
    "execution_authority",
)


@dataclass(frozen=True)
class LowTfSignalConfig:
    """Frozen mechanical thresholds layered over source-backed concepts."""

    minimum_range_width_bps: float = 100.0
    long_sweep_bps: float = 10.0
    short_sweep_bps: float = 15.0
    range_atr_stop_fraction: float = 0.5
    range_max_hold_bars: int = 24
    compression_percentile: float = 20.0
    long_breakout_clearance_bps: float = 8.0
    short_breakout_clearance_bps: float = 12.0
    trend_atr_stop_multiple: float = 1.0
    trend_max_hold_bars: int = 48
    pmarp_low: float = 20.0
    pmarp_high: float = 80.0
    exhaustion_bbwp_minimum: float = 80.0
    minimum_ema_distance_bps: float = 60.0
    exhaustion_atr_stop_fraction: float = 0.5
    exhaustion_max_hold_bars: int = 12
    krown_bbwp_maximum: float = 35.0
    krown_pmarp_maximum: float = 25.0
    krown_max_hold_bars: int = 48
    krown_touch_bbwp_maximum: float = 25.0
    krown_touch_max_hold_bars: int = 48

    def __post_init__(self) -> None:
        """Reject invalid, inverted, or non-finite signal thresholds."""
        positive = (
            self.minimum_range_width_bps,
            self.long_sweep_bps,
            self.short_sweep_bps,
            self.range_atr_stop_fraction,
            self.long_breakout_clearance_bps,
            self.short_breakout_clearance_bps,
            self.trend_atr_stop_multiple,
            self.minimum_ema_distance_bps,
            self.exhaustion_atr_stop_fraction,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in positive):
            raise ValueError("signal distance thresholds must be positive and finite")
        percentiles = (
            self.compression_percentile,
            self.pmarp_low,
            self.pmarp_high,
            self.exhaustion_bbwp_minimum,
            self.krown_bbwp_maximum,
            self.krown_pmarp_maximum,
            self.krown_touch_bbwp_maximum,
        )
        if any(not 0.0 <= value <= 100.0 for value in percentiles):
            raise ValueError("signal percentiles must be within [0, 100]")
        if self.pmarp_low >= self.pmarp_high:
            raise ValueError("PMARP low must be below PMARP high")
        holds = (
            self.range_max_hold_bars,
            self.trend_max_hold_bars,
            self.exhaustion_max_hold_bars,
            self.krown_max_hold_bars,
            self.krown_touch_max_hold_bars,
        )
        if any(isinstance(value, bool) or value <= 0 for value in holds):
            raise ValueError("signal maximum holds must be positive integers")


def build_low_tf_signals(
    features: pd.DataFrame,
    *,
    symbol: str,
    config: LowTfSignalConfig | None = None,
) -> pd.DataFrame:
    """Emit every eligible long/short variant without portfolio filtering."""
    frame = _validated_features(features)
    normalized_symbol = _validated_symbol(symbol)
    cfg = config or LowTfSignalConfig()
    records = [
        *_range_signals(frame, normalized_symbol, cfg),
        *_trend_signals(frame, normalized_symbol, cfg),
        *_pmarp_signals(frame, normalized_symbol, cfg),
        *_krown_pullback_signals(frame, normalized_symbol, cfg),
        *_krown_touch_signals(frame, normalized_symbol, cfg),
    ]
    result = pd.DataFrame(records, columns=list(_OUTPUT_COLUMNS))
    if result.empty:
        return result
    return result.sort_values(
        ["decision_position", "family", "side", "exit_variant"]
    ).reset_index(drop=True)


def _range_signals(
    frame: pd.DataFrame, symbol: str, config: LowTfSignalConfig
) -> list[SignalRecord]:
    """Return symmetric failed-range-break signals and declared stop variants."""
    low_boundary = frame["range_low_240"]
    high_boundary = frame["range_high_240"]
    long_sweep = (low_boundary - frame["low"]) / low_boundary * 10_000.0
    short_sweep = (frame["high"] - high_boundary) / high_boundary * 10_000.0
    width = frame["range_width_bps"].ge(config.minimum_range_width_bps)
    masks = {
        "long": width
        & long_sweep.ge(config.long_sweep_bps)
        & frame["close"].gt(low_boundary)
        & frame["close"].lt(frame["range_midpoint_240"]),
        "short": width
        & short_sweep.ge(config.short_sweep_bps)
        & frame["close"].lt(high_boundary)
        & frame["close"].gt(frame["range_midpoint_240"]),
    }
    records: list[SignalRecord] = []
    for side, mask in masks.items():
        for position in np.flatnonzero(mask.fillna(False).to_numpy()):
            records.extend(_range_variants(frame, position, symbol, side, config))
    return records


def _range_variants(
    frame: pd.DataFrame,
    position: int,
    symbol: str,
    side: str,
    config: LowTfSignalConfig,
) -> list[SignalRecord]:
    """Build close-invalidation and wick/ATR variants for one reclaim."""
    row = frame.iloc[position]
    boundary = float(row["range_low_240" if side == "long" else "range_high_240"])
    wick = float(row["low" if side == "long" else "high"])
    offset = float(row["atr"]) * config.range_atr_stop_fraction
    wick_stop = wick - offset if side == "long" else wick + offset
    facts = "range_reclaim|range_midpoint|close_based_invalidation"
    hypotheses = "240_bar_boundary|100_bps_width|asymmetric_sweep"
    return [
        _record(
            row,
            position,
            symbol,
            "range_reclaim_v1",
            side,
            "range_close_invalidation",
            boundary,
            float(row["range_midpoint_240"]),
            "completed_bar_close",
            config.range_max_hold_bars,
            facts,
            hypotheses,
        ),
        _record(
            row,
            position,
            symbol,
            "range_reclaim_v1",
            side,
            "range_wick_atr_stop",
            wick_stop,
            float(row["range_midpoint_240"]),
            "intrabar_stop",
            config.range_max_hold_bars,
            facts,
            hypotheses,
        ),
    ]


def _trend_signals(
    frame: pd.DataFrame, symbol: str, config: LowTfSignalConfig
) -> list[SignalRecord]:
    """Return completed-context volatility-expansion signals for both sides."""
    prior_bbwp = frame["bbwp_percentile"].shift(1)
    expansion = (
        prior_bbwp.le(config.compression_percentile)
        & frame["bbwp_percentile"].gt(frame["bbwp_signal"])
        & frame["bbwp_percentile"].gt(prior_bbwp)
    )
    long_clearance = (frame["close"] / frame["breakout_high_120"] - 1.0) * 10_000.0
    short_clearance = (
        (frame["breakout_low_120"] - frame["close"])
        / frame["breakout_low_120"]
        * 10_000.0
    )
    masks = {
        "long": expansion
        & frame["context_direction"].eq(1)
        & frame["context_fast_slope_bps"].gt(0.0)
        & long_clearance.ge(config.long_breakout_clearance_bps),
        "short": expansion
        & frame["context_direction"].eq(-1)
        & frame["context_fast_slope_bps"].lt(0.0)
        & short_clearance.ge(config.short_breakout_clearance_bps),
    }
    records: list[SignalRecord] = []
    for side, mask in masks.items():
        for position in np.flatnonzero(mask.fillna(False).to_numpy()):
            records.extend(_trend_variants(frame, position, symbol, side, config))
    return records


def _trend_variants(
    frame: pd.DataFrame,
    position: int,
    symbol: str,
    side: str,
    config: LowTfSignalConfig,
) -> list[SignalRecord]:
    """Build declared trend exit variants around one structure/ATR stop."""
    row = frame.iloc[position]
    close = float(row["close"])
    offset = float(row["atr"]) * config.trend_atr_stop_multiple
    boundary = float(row["breakout_high_120" if side == "long" else "breakout_low_120"])
    stop = (
        min(boundary, close - offset)
        if side == "long"
        else max(boundary, close + offset)
    )
    facts = "15m_21_55_direction|bbwp_expansion"
    hypotheses = "120_bar_boundary|asymmetric_clearance|prior_compression_20"
    variants = ("rsi_reversal_exit", "ema_alignment_exit")
    return [
        _record(
            row,
            position,
            symbol,
            "trend_expansion_v1",
            side,
            variant,
            stop,
            math.nan,
            "intrabar_stop",
            config.trend_max_hold_bars,
            facts,
            hypotheses,
        )
        for variant in variants
    ]


def _pmarp_signals(
    frame: pd.DataFrame, symbol: str, config: LowTfSignalConfig
) -> list[SignalRecord]:
    """Return high-volatility PMARP reversal signals for both sides."""
    prior = frame["pmarp"].shift(1)
    prior_signal = frame["pmarp_signal"].shift(1)
    long_cross = (
        prior.le(config.pmarp_low)
        & prior.le(prior_signal)
        & frame["pmarp"].gt(frame["pmarp_signal"])
    )
    short_cross = (
        prior.ge(config.pmarp_high)
        & prior.ge(prior_signal)
        & frame["pmarp"].lt(frame["pmarp_signal"])
    )
    high_volatility = frame["bbwp_percentile"].ge(config.exhaustion_bbwp_minimum)
    below_ema = (frame["ema_fast_5m"] / frame["close"] - 1.0) * 10_000.0
    above_ema = (frame["close"] / frame["ema_fast_5m"] - 1.0) * 10_000.0
    masks = {
        "long": long_cross
        & high_volatility
        & below_ema.ge(config.minimum_ema_distance_bps),
        "short": short_cross
        & high_volatility
        & above_ema.ge(config.minimum_ema_distance_bps),
    }
    records: list[SignalRecord] = []
    for side, mask in masks.items():
        for position in np.flatnonzero(mask.fillna(False).to_numpy()):
            records.extend(_pmarp_variants(frame, position, symbol, side, config))
    return records


def _pmarp_variants(
    frame: pd.DataFrame,
    position: int,
    symbol: str,
    side: str,
    config: LowTfSignalConfig,
) -> list[SignalRecord]:
    """Build EMA-mean and opposite-extreme PMARP exit variants."""
    row = frame.iloc[position]
    offset = float(row["atr"]) * config.exhaustion_atr_stop_fraction
    stop = float(row["low"]) - offset if side == "long" else float(row["high"]) + offset
    facts = "pmarp_extreme|high_bbwp_mean_reversion"
    hypotheses = "60_bps_ema_distance|completed_reversal_cross"
    targets = {
        "ema_mean_exit": float(row["ema_fast_5m"]),
        "pmarp_opposite_extreme_exit": math.nan,
    }
    return [
        _record(
            row,
            position,
            symbol,
            "pmarp_exhaustion_v1",
            side,
            variant,
            stop,
            target,
            "intrabar_stop",
            config.exhaustion_max_hold_bars,
            facts,
            hypotheses,
        )
        for variant, target in targets.items()
    ]


def _krown_pullback_signals(
    frame: pd.DataFrame, symbol: str, config: LowTfSignalConfig
) -> list[SignalRecord]:
    """Return canonical Krown long-state onsets with two stop translations."""
    compressed = frame["bbwp_percentile"].lt(config.krown_bbwp_maximum)
    trending = frame["ema_fast_5m"].gt(frame["ema_slow_5m"])
    pulled_back = frame["pmarp"].lt(config.krown_pmarp_maximum)
    ready = compressed & trending & pulled_back
    onset = ready & ~ready.shift(1, fill_value=False)
    episode = compressed.ne(compressed.shift(1, fill_value=False)).cumsum()
    episode_low = frame["low"].where(compressed).groupby(episode).cummin()
    records: list[SignalRecord] = []
    for position in np.flatnonzero(onset.fillna(False).to_numpy()):
        records.extend(
            _krown_pullback_variants(frame, episode_low, position, symbol, config)
        )
    return records


def _krown_pullback_variants(
    frame: pd.DataFrame,
    episode_low: pd.Series,
    position: int,
    symbol: str,
    config: LowTfSignalConfig,
) -> list[SignalRecord]:
    """Build source-faithful PMARP exit with explicit stop interpretations."""
    row = frame.iloc[position]
    stop = float(episode_low.iloc[position])
    facts = "5m_21_55_uptrend|bbwp_below_35|pmarp_below_25|pmarp_80_exit"
    hypotheses = "fresh_state_onset|compression_episode_low|next_bar_entry"
    variants = {
        "krown_close_stop_pmarp80": "completed_bar_close",
        "krown_hard_stop_pmarp80": "intrabar_stop",
    }
    return [
        _record(
            row,
            position,
            symbol,
            "krown_pullback_long_v1",
            "long",
            variant,
            stop,
            math.nan,
            invalidation,
            config.krown_max_hold_bars,
            facts,
            hypotheses,
        )
        for variant, invalidation in variants.items()
    ]


def _krown_touch_signals(
    frame: pd.DataFrame, symbol: str, config: LowTfSignalConfig
) -> list[SignalRecord]:
    """Return symmetric EMA55 wick-touch/reclaim translations."""
    compressed = frame["bbwp_percentile"].lt(config.krown_touch_bbwp_maximum)
    touches = frame["low"].le(frame["ema_slow_5m"]) & frame["high"].ge(
        frame["ema_slow_5m"]
    )
    masks = {
        "long": compressed
        & touches
        & frame["ema_fast_5m"].gt(frame["ema_slow_5m"])
        & frame["close"].gt(frame["ema_slow_5m"]),
        "short": compressed
        & touches
        & frame["ema_fast_5m"].lt(frame["ema_slow_5m"])
        & frame["close"].lt(frame["ema_slow_5m"]),
    }
    episode = compressed.ne(compressed.shift(1, fill_value=False)).cumsum()
    boundaries = {
        "long": frame["low"].where(compressed).groupby(episode).cummin(),
        "short": frame["high"].where(compressed).groupby(episode).cummax(),
    }
    records: list[SignalRecord] = []
    for side, mask in masks.items():
        for position in np.flatnonzero(mask.fillna(False).to_numpy()):
            records.extend(
                _krown_touch_variants(
                    frame, boundaries[side], position, symbol, side, config
                )
            )
    return records


def _krown_touch_variants(
    frame: pd.DataFrame,
    boundary: pd.Series,
    position: int,
    symbol: str,
    side: str,
    config: LowTfSignalConfig,
) -> list[SignalRecord]:
    """Build explicit ideal-close and emergency-hard range-stop variants."""
    row = frame.iloc[position]
    facts = "5m_21_55_bias|bbwp_below_25|ema55_touch|opposing_rsi_div_exit"
    hypotheses = "wick_span_reclaim|compression_episode_stop|next_bar_entry"
    variants = {
        "krown_touch_close_stop_rsi_div": "completed_bar_close",
        "krown_touch_hard_stop_rsi_div": "intrabar_stop",
    }
    return [
        _record(
            row,
            position,
            symbol,
            "krown_ema55_touch_v1",
            side,
            variant,
            float(boundary.iloc[position]),
            math.nan,
            invalidation,
            config.krown_touch_max_hold_bars,
            facts,
            hypotheses,
        )
        for variant, invalidation in variants.items()
    ]


def _record(
    row: pd.Series,
    position: int,
    symbol: str,
    family: str,
    side: str,
    exit_variant: str,
    stop: float,
    target: float,
    invalidation_mode: str,
    max_hold_bars: int,
    source_facts: str,
    hypothesis_facts: str,
) -> SignalRecord:
    """Return one stable signal-ledger row."""
    decision_time = pd.Timestamp(row["bar_open_at"]) + pd.Timedelta(minutes=5)
    return {
        "decision_time_utc": decision_time.isoformat(),
        "decision_position": position,
        "symbol": symbol,
        "family": family,
        "side": side,
        "exit_variant": exit_variant,
        "trigger_price": float(row["close"]),
        "stop_anchor_price": stop,
        "target_anchor_price": target,
        "invalidation_mode": invalidation_mode,
        "max_hold_bars": max_hold_bars,
        "source_backed_facts": source_facts,
        "hypothesis_facts": hypothesis_facts,
        "reason": f"{family}:{side}:{exit_variant}",
        "execution_authority": "none",
    }


def _validated_features(features: pd.DataFrame) -> pd.DataFrame:
    """Validate signal inputs without converting unknown warmup to false data."""
    missing = sorted(_REQUIRED_COLUMNS.difference(features.columns))
    if missing:
        raise ValueError(f"low-timeframe features missing columns: {missing}")
    times = pd.DatetimeIndex(features["bar_open_at"])
    if features.empty or times.tz is None:
        raise ValueError("low-timeframe features require non-empty aware timestamps")
    if not times.is_monotonic_increasing or times.has_duplicates:
        raise ValueError("low-timeframe feature timestamps must be ordered and unique")
    ohlc = features[["open", "high", "low", "close"]].to_numpy(float)
    if not np.isfinite(ohlc).all() or (ohlc <= 0.0).any():
        raise ValueError("low-timeframe decision OHLC must be positive and finite")
    numeric = features[list(_REQUIRED_COLUMNS - {"bar_open_at"})].to_numpy(float)
    if np.isinf(numeric).any():
        raise ValueError(
            "low-timeframe decision features cannot contain non-finite infinity"
        )
    return features.copy()


def _validated_symbol(symbol: str) -> str:
    """Return an uppercase symbol or reject ambiguous identity."""
    value = symbol.strip().upper()
    if not value or value != symbol:
        raise ValueError("signal symbol must be non-empty uppercase text")
    return value
