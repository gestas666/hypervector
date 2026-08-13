"""Bounded causal signal builders for independent low-timeframe challengers."""

from __future__ import annotations

import pandas as pd

from hypervector.research.low_tf_rsi_divergence import (
    confirmed_three_drive_rsi_divergence,
)

_THREE_DRIVE_COLUMNS = {
    "bar_open_at",
    "high",
    "low",
    "close",
    "rsi",
    "ema_fast_5m",
}
_ABSORPTION_COLUMNS = {
    "bar_open_at",
    "high",
    "low",
    "close",
    "return_1_bps",
    "trade_flow_imbalance",
    "imbalance_5_last",
    "imbalance_5_delta_60s",
    "spread_bps_last",
    "micro_price_delta_bps",
}
_ABSORPTION_LOOKBACK = 12
_MINIMUM_FLOW_IMBALANCE = 0.25
_MINIMUM_BOOK_IMBALANCE = 0.10
_ABSORPTION_TARGET_BPS = 25.0


def build_three_drive_signals(
    features: pd.DataFrame,
    *,
    symbol: str,
) -> pd.DataFrame:
    """Return symmetric confirmed three-drive entries with no live authority."""
    missing = sorted(_THREE_DRIVE_COLUMNS.difference(features.columns))
    if missing:
        raise ValueError(f"three-drive features missing columns: {missing}")
    divergence = _three_drive_divergence(features)
    records: list[dict[str, object]] = []
    mappings = (
        ("short", "rsi_three_drive_bearish", "bearish_stop_anchor"),
        ("long", "rsi_three_drive_bullish", "bullish_stop_anchor"),
    )
    for side, signal_column, stop_column in mappings:
        for position in divergence.index[divergence[signal_column]]:
            row = features.loc[position]
            records.append(
                _three_drive_record(
                    row, symbol, side, float(divergence.loc[position, stop_column])
                )
            )
    return pd.DataFrame(records)


def _three_drive_divergence(features: pd.DataFrame) -> pd.DataFrame:
    """Calculate divergence after a leading-only RSI warmup."""
    valid = features["rsi"].notna()
    if not valid.any():
        return pd.DataFrame(index=features.index)
    first = int(valid.to_numpy().argmax())
    if not valid.iloc[first:].all():
        raise ValueError("three-drive RSI contains a non-leading missing value")
    ready = features.loc[valid]
    return confirmed_three_drive_rsi_divergence(
        ready["high"], ready["low"], ready["rsi"]
    )


def _three_drive_record(
    row: pd.Series,
    symbol: str,
    side: str,
    stop: float,
) -> dict[str, object]:
    """Return one replay-compatible immutable three-drive decision."""
    decision = pd.Timestamp(row["bar_open_at"]) + pd.Timedelta(minutes=5)
    return {
        "decision_time_utc": decision.isoformat(),
        "symbol": symbol.strip().upper(),
        "family": "three_drive_rsi_reversal_v1",
        "side": side,
        "exit_variant": "ema21_target",
        "trigger_price": float(row["close"]),
        "stop_anchor_price": stop,
        "target_anchor_price": float(row["ema_fast_5m"]),
        "invalidation_mode": "intrabar_stop",
        "max_hold_bars": 12,
        "source_backed_facts": "confirmed_three_drive_rsi|ema21_mean",
        "hypothesis_facts": "next_bar_entry|prior_pivot_hard_stop",
        "reason": f"three_drive_rsi_reversal_v1:{side}:ema21_target",
        "execution_authority": "none",
    }


def build_absorption_signals(
    features: pd.DataFrame,
    *,
    symbol: str,
) -> pd.DataFrame:
    """Return completed-bar sell-flow absorption reversals at local lows."""
    missing = sorted(_ABSORPTION_COLUMNS.difference(features.columns))
    if missing:
        raise ValueError(f"absorption features missing columns: {missing}")
    prior_low = features["low"].shift(1).rolling(_ABSORPTION_LOOKBACK).min()
    prior_high = features["high"].shift(1).rolling(_ABSORPTION_LOOKBACK).max()
    prior_spread = (
        features["spread_bps_last"].shift(1).rolling(_ABSORPTION_LOOKBACK).median()
    )
    long = (
        features["low"].lt(prior_low)
        & features["return_1_bps"].lt(0.0)
        & features["trade_flow_imbalance"].le(-_MINIMUM_FLOW_IMBALANCE)
        & features["imbalance_5_last"].ge(_MINIMUM_BOOK_IMBALANCE)
        & features["imbalance_5_delta_60s"].gt(0.0)
        & features["micro_price_delta_bps"].gt(0.0)
        & features["spread_bps_last"].le(prior_spread)
    )
    short = (
        features["high"].gt(prior_high)
        & features["return_1_bps"].gt(0.0)
        & features["trade_flow_imbalance"].ge(_MINIMUM_FLOW_IMBALANCE)
        & features["imbalance_5_last"].le(-_MINIMUM_BOOK_IMBALANCE)
        & features["imbalance_5_delta_60s"].lt(0.0)
        & features["micro_price_delta_bps"].lt(0.0)
        & features["spread_bps_last"].le(prior_spread)
    )
    records = []
    for side, mask in (("long", long), ("short", short)):
        records.extend(
            _absorption_record(features.iloc[position], symbol, side)
            for position in range(len(features))
            if bool(mask.iloc[position])
        )
    return pd.DataFrame(records)


def _absorption_record(
    row: pd.Series,
    symbol: str,
    side: str,
) -> dict[str, object]:
    """Return one replay-compatible L2 absorption decision."""
    long = side == "long"
    close = float(row["close"])
    target_sign = 1.0 if long else -1.0
    decision = pd.Timestamp(row["bar_open_at"]) + pd.Timedelta(minutes=5)
    return {
        "decision_time_utc": decision.isoformat(),
        "symbol": symbol.strip().upper(),
        "family": "l2_absorption_reversal_v1",
        "side": side,
        "exit_variant": "fixed25_wick_stop",
        "trigger_price": close,
        "stop_anchor_price": float(row["low" if long else "high"]),
        "target_anchor_price": close
        * (1.0 + target_sign * _ABSORPTION_TARGET_BPS / 10_000.0),
        "invalidation_mode": "intrabar_stop",
        "max_hold_bars": 12,
        "source_backed_facts": "local_extreme|opposed_trade_and_l2_flow",
        "hypothesis_facts": "spread_compressed|microprice_confirms_absorption",
        "reason": f"l2_absorption_reversal_v1:{side}:fixed25_wick_stop",
        "execution_authority": "none",
    }
