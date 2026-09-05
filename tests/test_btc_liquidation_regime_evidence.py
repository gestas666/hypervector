"""Tests for causal descriptive regime evidence in BTC liquidation research."""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from hypervector.regime.classifier import RegimeClassifierConfig, classify_timeframe
from hypervector.research.btc_liquidation_regime_evidence import (
    build_causal_regime_labels,
    select_regime_at_decision,
)


def _candles(rows: int = 360) -> pd.DataFrame:
    index = pd.date_range("2025-11-30", periods=rows, freq="5min", tz="UTC")
    close = np.linspace(90_000.0, 92_000.0, rows)
    return pd.DataFrame(
        {
            "timestamp": index,
            "open": close - 1.0,
            "high": close + 2.0,
            "low": close - 2.0,
            "close": close,
            "volume": np.linspace(10.0, 30.0, rows),
        }
    )


def test_regime_labels_are_available_only_after_completed_bar() -> None:
    """The first evaluation label cannot describe its still-open candle."""
    candles = _candles()
    evaluation_start = pd.Timestamp("2025-12-01T00:00:00Z")
    evaluation_end = pd.Timestamp("2025-12-01T06:00:00Z")

    labels = build_causal_regime_labels(
        candles,
        evaluation_start=evaluation_start,
        evaluation_end=evaluation_end,
        minimum_context_bars=288,
    )
    selected = select_regime_at_decision(labels, evaluation_start)

    assert labels.iloc[0]["available_at"] == labels.iloc[0]["bar_open_at"] + timedelta(
        minutes=5
    )
    assert selected["bar_open_at"] == evaluation_start - timedelta(minutes=5)
    assert selected["available_at"] == evaluation_start
    assert int(labels["in_evaluation_partition"].sum()) == 72


def test_regime_label_matches_same_prefix_classifier_result() -> None:
    """A retained label equals classification from data available through that bar."""
    candles = _candles()
    evaluation_start = pd.Timestamp("2025-12-01T00:00:00Z")
    target = evaluation_start + timedelta(minutes=30)
    config = RegimeClassifierConfig()

    labels = build_causal_regime_labels(
        candles,
        evaluation_start=evaluation_start,
        evaluation_end=pd.Timestamp("2025-12-01T06:00:00Z"),
        minimum_context_bars=288,
        config=config,
    )
    prefix = candles.loc[pd.to_datetime(candles["timestamp"], utc=True).le(target)]
    source = prefix.set_index("timestamp")[["open", "high", "low", "close", "volume"]]
    expected = classify_timeframe(source, config).iloc[-1]
    observed = labels.loc[labels["bar_open_at"].eq(target)].iloc[0]

    assert observed["primary_regime"] == expected["primary_regime"]
    assert observed["regime_strength_score"] == expected["regime_strength_score"]


def test_regime_evidence_rejects_gap_or_insufficient_context() -> None:
    """Missing source bars and under-warmed evaluation windows fail closed."""
    candles = _candles()
    evaluation_start = pd.Timestamp("2025-12-01T00:00:00Z")
    evaluation_end = pd.Timestamp("2025-12-01T06:00:00Z")
    gapped = candles.drop(index=100).reset_index(drop=True)

    for frame, context in ((gapped, 288), (candles, 289)):
        try:
            build_causal_regime_labels(
                frame,
                evaluation_start=evaluation_start,
                evaluation_end=evaluation_end,
                minimum_context_bars=context,
            )
        except ValueError as exc:
            assert "cadence" in str(exc) or "context" in str(exc)
        else:
            raise AssertionError("invalid causal regime evidence was accepted")
