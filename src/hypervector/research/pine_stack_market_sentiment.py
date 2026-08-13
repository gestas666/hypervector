"""Causal backend translation of LuxAlgo Market Sentiment Technicals."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from hypervector.research.pine_stack_native_bars import validated_native_bars
from hypervector.research.pine_stack_sentiment_indicators import (
    VwapAnchor,
    anchored_vwap_bands,
    bull_bear_power_sentiment,
    cci_sentiment,
    classic_supertrend_line,
    confirmed_market_structure_events,
    oscillator_sentiment,
    pine_rsi,
    state_normalized_sentiment,
    stochastic_sentiment,
)

MARKET_SENTIMENT_COMPONENTS: tuple[str, ...] = (
    "sentiment_rsi",
    "sentiment_stochastic",
    "sentiment_stochastic_rsi",
    "sentiment_cci",
    "sentiment_bull_bear_power",
    "sentiment_moving_average",
    "sentiment_vwap",
    "sentiment_bollinger",
    "sentiment_supertrend",
    "sentiment_linear_regression",
    "sentiment_market_structure",
)


@dataclass(frozen=True)
class MarketSentimentConfig:
    """Source-default lengths with an explicit comparable VWAP anchor."""

    normalization_smooth: int = 3
    vwap_anchor: VwapAnchor = "day"
    vwap_standard_deviations: float = 2.0
    supertrend_atr_period: int = 10
    supertrend_factor: float = 3.0
    market_structure_width: int = 5

    def __post_init__(self) -> None:
        """Reject invalid Market Sentiment source parameters."""
        integers = (
            self.normalization_smooth,
            self.supertrend_atr_period,
            self.market_structure_width,
        )
        if any(isinstance(value, bool) or value < 1 for value in integers):
            raise ValueError("Market Sentiment lengths must be positive")
        numbers = (self.vwap_standard_deviations, self.supertrend_factor)
        if any(not math.isfinite(value) or value <= 0.0 for value in numbers):
            raise ValueError("Market Sentiment factors must be positive and finite")
        if self.vwap_anchor not in {"day", "week"}:
            raise ValueError("Market Sentiment VWAP anchor must be day or week")


def build_market_sentiment(
    bars: pd.DataFrame,
    *,
    bar_minutes: int,
    config: MarketSentimentConfig | None = None,
) -> pd.DataFrame:
    """Return all eleven causal components and their fully supported mean."""
    cfg = config or MarketSentimentConfig()
    frame = validated_native_bars(bars, bar_minutes=bar_minutes)
    close, high, low = frame["close"], frame["high"], frame["low"]
    result = frame.loc[:, ["bar_open_at"]].copy()
    result["decision_time_utc"] = result["bar_open_at"] + pd.Timedelta(
        minutes=bar_minutes
    )
    result["sentiment_rsi"] = oscillator_sentiment(
        pine_rsi(close, 14), bands=(30.0, 70.0)
    )
    result["sentiment_stochastic"] = stochastic_sentiment(
        close, high, low, length=14, smooth=3
    )
    rsi = pine_rsi(close, 14)
    result["sentiment_stochastic_rsi"] = stochastic_sentiment(
        rsi, rsi, rsi, length=14, smooth=3
    )
    result["sentiment_cci"] = cci_sentiment((high + low + close) / 3.0, length=20)
    result["sentiment_bull_bear_power"] = bull_bear_power_sentiment(
        high, low, close, ema_length=13
    )
    result = _attach_state_components(result, frame, cfg)
    result["sentiment_linear_regression"] = _linear_regression_sentiment(close, 25)
    result["sentiment_market_structure"] = _market_structure_sentiment(frame, cfg)
    result["component_support"] = (
        result.loc[:, list(MARKET_SENTIMENT_COMPONENTS)].notna().sum(axis=1)
    )
    complete = result["component_support"].eq(len(MARKET_SENTIMENT_COMPONENTS))
    result["sentiment_score"] = (
        result.loc[:, list(MARKET_SENTIMENT_COMPONENTS)].mean(axis=1).where(complete)
    )
    result["vwap_anchor"] = cfg.vwap_anchor
    result["source_translation"] = "market_sentiment_causal"
    return result


def _attach_state_components(
    result: pd.DataFrame,
    frame: pd.DataFrame,
    config: MarketSentimentConfig,
) -> pd.DataFrame:
    output = result.copy()
    close, high, low = frame["close"], frame["high"], frame["low"]
    smooth = config.normalization_smooth
    average = close.rolling(20, min_periods=20).mean()
    output["sentiment_moving_average"] = state_normalized_sentiment(
        close, close > average, close < average, smooth=smooth
    )
    vwap_upper, vwap_lower = anchored_vwap_bands(
        frame,
        anchor=config.vwap_anchor,
        standard_deviations=config.vwap_standard_deviations,
    )
    output["sentiment_vwap"] = state_normalized_sentiment(
        close, close > vwap_upper, close < vwap_lower, smooth=smooth
    )
    deviation = close.rolling(20, min_periods=20).std(ddof=0) * 2.0
    output["sentiment_bollinger"] = state_normalized_sentiment(
        close,
        close > average + deviation,
        close < average - deviation,
        smooth=smooth,
    )
    line = classic_supertrend_line(
        high,
        low,
        close,
        atr_period=config.supertrend_atr_period,
        factor=config.supertrend_factor,
    )
    output["sentiment_supertrend"] = state_normalized_sentiment(
        close, close > line, close < line, smooth=smooth
    )
    return output


def _linear_regression_sentiment(close: pd.Series, length: int) -> pd.Series:
    positions = pd.Series(np.arange(len(close), dtype=float), index=close.index)
    return close.rolling(length, min_periods=length).corr(positions) * 50.0 + 50.0


def _market_structure_sentiment(
    frame: pd.DataFrame,
    config: MarketSentimentConfig,
) -> pd.Series:
    bullish, bearish = confirmed_market_structure_events(
        frame["high"],
        frame["low"],
        frame["close"],
        pivot_width=config.market_structure_width,
    )
    return state_normalized_sentiment(
        frame["close"],
        bullish,
        bearish,
        smooth=config.normalization_smooth,
    )
