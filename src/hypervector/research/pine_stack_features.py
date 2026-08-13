"""Aligned backend feature frame for the causal four-Pine stack."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from hypervector.research.pine_stack_adaptive_supertrend import (
    AdaptiveSupertrendConfig,
    build_adaptive_supertrend,
)
from hypervector.research.pine_stack_market_sentiment import (
    MarketSentimentConfig,
    build_market_sentiment,
)
from hypervector.research.pine_stack_native_bars import validated_native_bars
from hypervector.research.pine_stack_tp_dimensions import (
    TpDimensionsConfig,
    build_tp_dimensions,
)
from hypervector.research.pine_stack_trend_levels import (
    TrendLevelsConfig,
    build_trend_levels,
)


@dataclass(frozen=True)
class PineStackFeatureConfig:
    """Immutable configurations for all four causal backend layers."""

    adaptive_supertrend: AdaptiveSupertrendConfig = field(
        default_factory=AdaptiveSupertrendConfig
    )
    trend_levels: TrendLevelsConfig = field(default_factory=TrendLevelsConfig)
    market_sentiment: MarketSentimentConfig = field(
        default_factory=MarketSentimentConfig
    )
    tp_dimensions: TpDimensionsConfig = field(default_factory=TpDimensionsConfig)


def build_pine_stack_features(
    bars: pd.DataFrame,
    *,
    bar_minutes: int,
    config: PineStackFeatureConfig | None = None,
) -> pd.DataFrame:
    """Return one aligned, completed-bar, report-only feature frame."""
    cfg = config or PineStackFeatureConfig()
    native = validated_native_bars(bars, bar_minutes=bar_minutes)
    adaptive = _adaptive_columns(
        build_adaptive_supertrend(
            native, bar_minutes=bar_minutes, config=cfg.adaptive_supertrend
        )
    )
    levels = _trend_level_columns(
        build_trend_levels(native, bar_minutes=bar_minutes, config=cfg.trend_levels)
    )
    sentiment = _drop_identity(
        build_market_sentiment(
            native, bar_minutes=bar_minutes, config=cfg.market_sentiment
        )
    )
    dimensions = _prefixed_columns(
        build_tp_dimensions(native, bar_minutes=bar_minutes, config=cfg.tp_dimensions),
        "tp_",
    )
    _validate_alignment(adaptive, levels, sentiment, dimensions)
    output = native.copy()
    output["decision_time_utc"] = adaptive["decision_time_utc"]
    for component in (adaptive, levels, sentiment, dimensions):
        values = component.drop(columns="decision_time_utc", errors="ignore")
        output = pd.concat([output, values], axis=1)
    if output.columns.has_duplicates:
        duplicates = output.columns[output.columns.duplicated()].tolist()
        raise RuntimeError(f"Pine stack feature columns collide: {duplicates}")
    output["bar_minutes"] = bar_minutes
    output["execution_authority"] = "none"
    return output


def _adaptive_columns(frame: pd.DataFrame) -> pd.DataFrame:
    mapping = {
        "atr": "cs_atr",
        "selected_factor": "cs_selected_factor",
        "trailing_stop": "cs_trailing_stop",
        "trend_state": "cs_trend_state",
        "long_onset": "cs_long_onset",
        "short_onset": "cs_short_onset",
        "source_translation": "cs_source_translation",
    }
    return _drop_bar_open(frame).rename(columns=mapping)


def _prefixed_columns(frame: pd.DataFrame, prefix: str) -> pd.DataFrame:
    values = _drop_bar_open(frame)
    mapping = {
        column: f"{prefix}{column}"
        for column in values.columns
        if column != "decision_time_utc"
    }
    return values.rename(columns=mapping)


def _trend_level_columns(frame: pd.DataFrame) -> pd.DataFrame:
    values = _prefixed_columns(frame, "trend_levels_")
    return values.rename(columns={"trend_levels_trend_state": "trend_levels_state"})


def _drop_identity(frame: pd.DataFrame) -> pd.DataFrame:
    return _drop_bar_open(frame).drop(columns="source_translation", errors="ignore")


def _drop_bar_open(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.drop(columns="bar_open_at").reset_index(drop=True)


def _validate_alignment(*frames: pd.DataFrame) -> None:
    expected = frames[0]["decision_time_utc"]
    if any(
        len(frame) != len(expected) or not frame["decision_time_utc"].equals(expected)
        for frame in frames[1:]
    ):
        raise RuntimeError("Pine stack component decision timestamps are misaligned")
