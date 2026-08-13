"""Causal bidirectional signals for asset-specific low-timeframe tuning."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from hypervector.research.low_tf_asset_tuning_models import (
    TrendEntryShape,
    TrendExitShape,
    TuningSide,
)

TUNED_TREND_STRATEGY = "low_tf_trend_impulse_bidirectional_v1"

_REQUIRED_COLUMNS = frozenset(
    {
        "bar_open_at",
        "close",
        "breakout_high_120",
        "breakout_low_120",
        "ema_fast_5m",
        "ema_slow_5m",
        "bbwp_percentile",
        "bbwp_signal",
        "context_direction",
        "context_fast_slope_bps",
    }
)
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


def build_tuned_trend_signals(
    features: pd.DataFrame,
    *,
    symbol: str,
    side: TuningSide,
    entry_shape: TrendEntryShape,
    exit_shape: TrendExitShape,
) -> pd.DataFrame:
    """Emit causal completed-bar signals for one explicit asset and side."""
    frame = _validated_features(features)
    normalized_symbol = _validated_symbol(symbol)
    _validated_side(side)
    mask = _entry_mask(frame, side, entry_shape)
    records = [
        _signal_record(
            frame.iloc[position],
            position,
            normalized_symbol,
            side,
            entry_shape,
            exit_shape,
        )
        for position in np.flatnonzero(mask.fillna(False).to_numpy())
    ]
    return pd.DataFrame(records, columns=list(_OUTPUT_COLUMNS))


def _entry_mask(
    frame: pd.DataFrame,
    side: TuningSide,
    shape: TrendEntryShape,
) -> pd.Series:
    prior_bbwp = frame["bbwp_percentile"].shift(1)
    release = (
        prior_bbwp.le(shape.compression_percentile)
        & frame["bbwp_percentile"].gt(frame["bbwp_signal"])
        & frame["bbwp_percentile"].gt(prior_bbwp)
    )
    if side == "long":
        clearance = (frame["close"] / frame["breakout_high_120"] - 1.0) * 10_000.0
        aligned = (
            frame["ema_fast_5m"].gt(frame["ema_slow_5m"])
            & frame["context_direction"].eq(1)
            & frame["context_fast_slope_bps"].gt(0.0)
        )
    else:
        clearance = (
            (frame["breakout_low_120"] - frame["close"])
            / frame["breakout_low_120"]
            * 10_000.0
        )
        aligned = (
            frame["ema_fast_5m"].lt(frame["ema_slow_5m"])
            & frame["context_direction"].eq(-1)
            & frame["context_fast_slope_bps"].lt(0.0)
        )
    return release & aligned & clearance.ge(shape.clearance_bps)


def _signal_record(
    row: pd.Series,
    position: int,
    symbol: str,
    side: TuningSide,
    entry_shape: TrendEntryShape,
    exit_shape: TrendExitShape,
) -> dict[str, object]:
    reference = float(row["close"])
    stop = _stop_price(reference, side, exit_shape.stop_bps)
    reward = abs(reference - stop) * exit_shape.target_r_multiple
    target = reference + reward if side == "long" else reference - reward
    decision_time = pd.Timestamp(row["bar_open_at"]) + pd.Timedelta(minutes=5)
    return {
        "decision_time_utc": decision_time.isoformat(),
        "decision_position": position,
        "symbol": symbol,
        "family": TUNED_TREND_STRATEGY,
        "side": side,
        "exit_variant": "fixed_rr_max_hold",
        "trigger_price": reference,
        "stop_anchor_price": stop,
        "target_anchor_price": target,
        "invalidation_mode": "intrabar_stop",
        "max_hold_bars": exit_shape.maximum_hold_bars,
        "source_backed_facts": "5m_ema|15m_ema_context|bbwp_release|prior_breakout",
        "hypothesis_facts": _shape_reason(entry_shape, exit_shape),
        "reason": f"{TUNED_TREND_STRATEGY}:{side}",
        "execution_authority": "none",
    }


def _shape_reason(entry: TrendEntryShape, exit_shape: TrendExitShape) -> str:
    return (
        f"lookback={entry.breakout_lookback}|ema={entry.ema_fast}x{entry.ema_slow}|"
        f"compression={entry.compression_percentile:g}|"
        f"clearance={entry.clearance_bps:g}|stop={exit_shape.stop_bps:g}|"
        f"target_r={exit_shape.target_r_multiple:g}|"
        f"hold={exit_shape.maximum_hold_bars}"
    )


def _stop_price(reference: float, side: TuningSide, stop_bps: float) -> float:
    multiplier = (
        1.0 - stop_bps / 10_000.0 if side == "long" else 1.0 + stop_bps / 10_000.0
    )
    price = reference * multiplier
    if not math.isfinite(price) or price <= 0.0:
        raise ValueError("tuned trend stop price must be positive and finite")
    return price


def _validated_features(features: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(_REQUIRED_COLUMNS.difference(features.columns))
    if missing:
        raise ValueError(f"tuned trend features missing columns: {missing}")
    times = pd.DatetimeIndex(features["bar_open_at"])
    if features.empty or times.tz is None:
        raise ValueError("tuned trend features require aware non-empty timestamps")
    if not times.is_monotonic_increasing or times.has_duplicates:
        raise ValueError("tuned trend feature timestamps must be ordered and unique")
    numeric = features[list(_REQUIRED_COLUMNS - {"bar_open_at"})].to_numpy(float)
    if np.isinf(numeric).any():
        raise ValueError("tuned trend features cannot contain infinity")
    close = features["close"].to_numpy(float)
    if not np.isfinite(close).all() or (close <= 0.0).any():
        raise ValueError("tuned trend closes must be positive and finite")
    return features.copy()


def _validated_symbol(symbol: str) -> str:
    if symbol not in {"ETH", "SOL"}:
        raise ValueError("tuned trend symbol must be ETH or SOL")
    return symbol


def _validated_side(side: str) -> None:
    if side not in {"long", "short"}:
        raise ValueError("tuned trend side must be long or short")
