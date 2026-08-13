"""Walk-forward attribution tests for HYPE breakout entry features."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.hype_breakout_entry_attribution import (
    analyze_hype_entry_attribution,
)


def _outcomes() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=20, freq="1h", tz="UTC")
    feature = [float(value) for value in range(20)]
    gross = [value * 10.0 for value in feature]
    return pd.DataFrame(
        {
            "feature": feature,
            "flat_feature": [1.0] * 20,
            "gross_return_bps": gross,
            "net_return_bps": [value - 13.0 for value in gross],
        },
        index=index,
    )


def test_attribution_reports_fold_stability_and_cost_spread() -> None:
    """Monotonic signal quality remains visible separately in each time fold."""
    report = analyze_hype_entry_attribution(
        _outcomes(),
        feature_names=("feature",),
        fold_count=2,
        modeled_round_trip_bps=13.0,
    )

    result = report["features"]["feature"]
    assert result["median_spearman_ic"] == pytest.approx(1.0)
    assert result["ic_sign_consistent_folds"] == 2
    assert result["absolute_median_gross_tail_spread_bps"] > 26.0
    assert result["gross_spread_clears_2x_cost"] is True
    assert len(result["folds"]) == 2


def test_attribution_marks_constant_features_without_fabricated_ic() -> None:
    """A constant feature becomes insufficient evidence instead of zero alpha."""
    report = analyze_hype_entry_attribution(
        _outcomes(),
        feature_names=("flat_feature",),
        fold_count=2,
        modeled_round_trip_bps=13.0,
    )

    result = report["features"]["flat_feature"]
    assert result["valid_ic_folds"] == 0
    assert result["median_spearman_ic"] is None
    assert result["gross_spread_clears_2x_cost"] is False


def test_attribution_rejects_unknown_features() -> None:
    """A misspelled feature cannot become an empty successful diagnostic."""
    with pytest.raises(ValueError, match="missing feature columns"):
        analyze_hype_entry_attribution(
            _outcomes(),
            feature_names=("unknown",),
            fold_count=2,
            modeled_round_trip_bps=13.0,
        )
