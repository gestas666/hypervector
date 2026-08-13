"""Causal source-regime feature alignment tests."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.hypervelocity_source_features import (
    source_regime_features,
)


def _labels() -> pd.DataFrame:
    index = pd.date_range("2026-01-01T00:00:00Z", periods=3, freq="5min")
    return pd.DataFrame(
        {
            "available_at": index + pd.Timedelta(minutes=5),
            "primary_code": ["TREND_UP", "TREND_UP", "BREAKOUT"],
            "secondary_code": [
                "TU_STRONG_HIGH_VOL",
                "TU_STRONG_HIGH_VOL",
                "BK_DOWNWARD",
            ],
            "confidence": [0.8, 0.9, 0.7],
            "raw_primary_code": ["TREND_UP", "TREND_UP", "BREAKOUT"],
            "raw_secondary_code": [
                "TU_STRONG_HIGH_VOL",
                "TU_WEAK_CHOPPY",
                "BK_DOWNWARD",
            ],
            "volume_ratio": [1.2, 1.3, 2.5],
        },
        index=index,
    )


def test_source_features_use_only_labels_available_by_signal_time() -> None:
    """A later source label cannot alter an earlier decision feature row."""
    labels = _labels()
    signals = pd.DatetimeIndex(
        pd.to_datetime(
            ["2026-01-01T00:04:00Z", "2026-01-01T00:07:00Z", "2026-01-01T00:12:00Z"]
        )
    )

    observed = source_regime_features(labels, signals)
    mutated = labels.copy()
    mutated.iloc[2, mutated.columns.get_loc("confidence")] = 0.01
    after_future_change = source_regime_features(mutated, signals)

    assert observed.iloc[0].isna().all()
    assert observed.iloc[1]["source_confidence"] == pytest.approx(0.8)
    assert observed.iloc[1]["source_state_age_minutes"] == pytest.approx(2.0)
    assert observed.iloc[1]["source_is_strong"] == 1.0
    assert observed.iloc[1]["source_is_high_vol"] == 1.0
    pd.testing.assert_series_equal(observed.iloc[1], after_future_change.iloc[1])


def test_source_features_capture_stabilized_raw_disagreement_and_state_age() -> None:
    """Subtype persistence and raw/stabilized disagreement remain numeric evidence."""
    signals = pd.DatetimeIndex(
        pd.to_datetime(["2026-01-01T00:10:00Z", "2026-01-01T00:16:00Z"])
    )

    observed = source_regime_features(_labels(), signals)

    assert observed.iloc[0]["source_state_age_minutes"] == pytest.approx(5.0)
    assert observed.iloc[0]["source_raw_primary_agreement"] == 1.0
    assert observed.iloc[0]["source_raw_secondary_agreement"] == 0.0
    assert observed.iloc[1]["source_is_breakout"] == 1.0
    assert observed.iloc[1]["source_state_age_minutes"] == pytest.approx(1.0)
