"""Causal tests for the LuxAlgo Market Sentiment translation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hypervector.research.pine_stack_market_sentiment import (
    MARKET_SENTIMENT_COMPONENTS,
    MarketSentimentConfig,
    build_market_sentiment,
)


def _bars(rows: int = 900, minutes: int = 15) -> pd.DataFrame:
    """Return oscillating native bars that exercise both normalization states."""
    positions = np.arange(rows, dtype=float)
    close = 100.0 + 0.015 * positions + 7.0 * np.sin(positions / 9.0)
    open_ = np.concatenate(([close[0]], close[:-1]))
    return pd.DataFrame(
        {
            "bar_open_at": pd.date_range(
                "2026-01-01", periods=rows, freq=f"{minutes}min", tz="UTC"
            ),
            "open": open_,
            "high": np.maximum(open_, close) + 0.8,
            "low": np.minimum(open_, close) - 0.8,
            "close": close,
            "volume": 500.0 + 100.0 * np.cos(positions / 7.0),
        }
    )


def test_market_sentiment_exposes_all_components_and_exact_mean() -> None:
    """The aggregate must remain attributable to all eleven source components."""
    result = build_market_sentiment(_bars(), bar_minutes=15)
    ready = result.dropna(subset=["sentiment_score"])

    assert not ready.empty
    assert set(MARKET_SENTIMENT_COMPONENTS).issubset(result.columns)
    expected = ready.loc[:, list(MARKET_SENTIMENT_COMPONENTS)].mean(axis=1)
    pd.testing.assert_series_equal(
        ready["sentiment_score"], expected, check_names=False
    )
    assert ready["sentiment_score"].between(0.0, 100.0).all()
    assert ready["component_support"].eq(11).all()


def test_market_sentiment_is_append_invariant() -> None:
    """Future native bars must not revise historical components or aggregate."""
    bars = _bars()
    config = MarketSentimentConfig(vwap_anchor="day")
    before = build_market_sentiment(bars.iloc[:700], bar_minutes=15, config=config)
    after = build_market_sentiment(bars, bar_minutes=15, config=config).iloc[:700]

    pd.testing.assert_frame_equal(before, after.reset_index(drop=True))


def test_market_sentiment_uses_completed_native_bar_timestamp() -> None:
    """The backend decision timestamp must be the close of the source bar."""
    result = build_market_sentiment(_bars(200, 30), bar_minutes=30)

    assert (
        result["decision_time_utc"] == result["bar_open_at"] + pd.Timedelta(minutes=30)
    ).all()
    assert result["vwap_anchor"].eq("day").all()
