"""Causal descriptive regime evidence for BTC liquidation research."""

from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from hypervector.regime.classifier import RegimeClassifierConfig, classify_timeframe

_INTERVAL = pd.Timedelta(minutes=5)
_BAR_COLUMNS = ("open", "high", "low", "close", "volume")


def build_causal_regime_labels(
    candles: pd.DataFrame,
    *,
    evaluation_start: pd.Timestamp,
    evaluation_end: pd.Timestamp,
    minimum_context_bars: int,
    config: RegimeClassifierConfig | None = None,
) -> pd.DataFrame:
    """Classify complete five-minute bars and timestamp label availability."""
    cfg = config or RegimeClassifierConfig()
    start = _utc_timestamp(evaluation_start, "evaluation start")
    end = _utc_timestamp(evaluation_end, "evaluation end")
    if start >= end:
        raise ValueError("regime evaluation bounds must be ordered")
    if (
        isinstance(minimum_context_bars, bool)
        or not isinstance(minimum_context_bars, int)
        or minimum_context_bars < cfg.structure_lookback
    ):
        raise ValueError("regime context must cover the structure lookback")
    bars = _validated_bars(candles)
    _validate_evaluation_coverage(bars.index, start, end, minimum_context_bars)
    classified = classify_timeframe(bars, cfg)
    output = classified.rename_axis("bar_open_at").reset_index()
    output.insert(1, "available_at", output["bar_open_at"] + _INTERVAL)
    output.insert(
        2,
        "in_evaluation_partition",
        output["bar_open_at"].ge(start) & output["bar_open_at"].lt(end),
    )
    return output


def select_regime_at_decision(
    labels: pd.DataFrame, decision_at: pd.Timestamp
) -> dict[str, object]:
    """Return the latest label whose source candle had closed by a decision."""
    required = {"bar_open_at", "available_at", "primary_regime"}
    if not required.issubset(labels.columns):
        raise ValueError("causal regime labels are missing required columns")
    decision = _utc_timestamp(decision_at, "decision time")
    available = pd.DatetimeIndex(pd.to_datetime(labels["available_at"], utc=True))
    opens = pd.DatetimeIndex(pd.to_datetime(labels["bar_open_at"], utc=True))
    if not available.is_monotonic_increasing or not available.is_unique:
        raise ValueError("regime label availability must be ordered and unique")
    if not available.equals(opens + _INTERVAL):
        raise ValueError("regime label availability violates completed-bar timing")
    eligible = labels.loc[available <= decision]
    if eligible.empty:
        raise ValueError("no completed regime label is available at decision time")
    return dict(eligible.iloc[-1].to_dict())


def regime_config_evidence(
    config: RegimeClassifierConfig | None = None,
) -> dict[str, object]:
    """Return the exact serializable classifier configuration."""
    return dict(asdict(config or RegimeClassifierConfig()))


def _validated_bars(candles: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", *_BAR_COLUMNS}
    missing = required.difference(candles.columns)
    if missing:
        raise ValueError(
            f"regime candle evidence is missing columns: {sorted(missing)}"
        )
    timestamps = pd.DatetimeIndex(pd.to_datetime(candles["timestamp"], utc=True))
    if timestamps.hasnans:
        raise ValueError("regime candle evidence contains invalid timestamps")
    if not timestamps.is_unique or not timestamps.is_monotonic_increasing:
        raise ValueError("regime candle timestamps must be ordered and unique")
    expected = pd.date_range(
        timestamps[0], timestamps[-1] + _INTERVAL, freq=_INTERVAL, inclusive="left"
    )
    if not timestamps.equals(expected):
        raise ValueError(
            "regime candle evidence does not have exact five-minute cadence"
        )
    bars = candles.loc[:, _BAR_COLUMNS].copy()
    bars.index = timestamps
    return bars


def _validate_evaluation_coverage(
    index: pd.DatetimeIndex,
    start: pd.Timestamp,
    end: pd.Timestamp,
    minimum_context_bars: int,
) -> None:
    if start not in index or end > index[-1] + _INTERVAL:
        raise ValueError("regime candles do not cover the evaluation window")
    preceding = int((index < start).sum())
    if preceding < minimum_context_bars:
        raise ValueError("regime candles provide insufficient causal context")
    if index[preceding - 1] + _INTERVAL != start:
        raise ValueError("regime context does not end at the evaluation boundary")


def _utc_timestamp(value: pd.Timestamp, label: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tz is None:
        raise ValueError(f"regime {label} must be timezone-aware")
    return timestamp.tz_convert("UTC")
