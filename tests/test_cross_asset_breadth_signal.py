"""Causality and labeling tests for cross-sectional breadth signals."""

import numpy as np
import pandas as pd
import pytest

from hypervector.research.cross_asset_breadth_models import (
    CrossAssetBreadthConfig,
)
from hypervector.research.cross_asset_breadth_signal import (
    _strictly_prior_cross,
    build_breadth_states,
    label_breadth_events,
    sample_breadth_events,
)


def _feature_fixture() -> tuple[pd.DataFrame, pd.DataFrame, CrossAssetBreadthConfig]:
    index = pd.date_range("2025-07-20T00:00:00Z", periods=80, freq="15min")
    steps = np.arange(len(index), dtype=float)
    returns = pd.DataFrame(
        {
            "BTC": 0.0010 + 0.0008 * np.sin(steps / 2.0),
            "ETH": 0.0008 + 0.0009 * np.sin(steps / 2.3),
            "SOL": 0.0012 + 0.0011 * np.sin(steps / 1.7),
            "HYPE": 0.0006 + 0.0013 * np.sin(steps / 2.8),
        },
        index=index,
    )
    closes = 100.0 * np.exp(returns.cumsum())
    validity = pd.DataFrame(True, index=index, columns=closes.columns)
    config = CrossAssetBreadthConfig(
        return_bars=2,
        lookback_bars=8,
        minimum_valid_bars=8,
    )
    return closes, validity, config


def test_current_bar_cannot_change_its_strictly_prior_thresholds() -> None:
    closes, validity, config = _feature_fixture()
    baseline = build_breadth_states(closes, validity, config)
    changed = closes.copy()
    changed.loc[changed.index[-1], ["BTC", "ETH", "SOL", "HYPE"]] *= [
        1.1,
        0.9,
        1.2,
        0.8,
    ]

    perturbed = build_breadth_states(changed, validity, config)

    assert perturbed.iloc[-1]["dispersion"] != pytest.approx(
        baseline.iloc[-1]["dispersion"]
    )
    assert perturbed.iloc[-1]["dispersion_threshold"] == pytest.approx(
        baseline.iloc[-1]["dispersion_threshold"]
    )
    assert perturbed.iloc[-1]["btc_momentum_threshold"] == pytest.approx(
        baseline.iloc[-1]["btc_momentum_threshold"]
    )


def test_default_threshold_requires_666_of_672_strictly_prior_values() -> None:
    config = CrossAssetBreadthConfig()
    values = pd.Series(np.linspace(0.0, 1.0, 673))
    six_missing = values.copy()
    six_missing.iloc[:6] = np.nan
    seven_missing = values.copy()
    seven_missing.iloc[:7] = np.nan

    accepted, _ = _strictly_prior_cross(six_missing, config)
    rejected, _ = _strictly_prior_cross(seven_missing, config)

    assert pd.notna(accepted.iloc[-1])
    assert pd.isna(rejected.iloc[-1])


def test_invalid_bar_invalidates_the_full_return_path() -> None:
    closes, validity, config = _feature_fixture()
    invalid_at = validity.index[60]
    validity.loc[invalid_at, "BTC"] = False

    states = build_breadth_states(closes, validity, config)

    affected = validity.index[60:63]
    assert states.loc[affected, "BTC_normalized_return"].isna().all()
    assert not states.loc[affected, "primary_qualifies"].any()


def test_primary_onsets_respect_one_shared_cooldown() -> None:
    config = CrossAssetBreadthConfig()
    opens = pd.date_range("2025-08-01T00:00:00Z", periods=8, freq="15min")
    states = pd.DataFrame(
        {
            "bar_open_at": opens,
            "decision_time_utc": opens + pd.Timedelta(minutes=15),
            "primary_qualifies": [False, True, False, True, False, False, True, False],
            "primary_direction": [
                None,
                "long",
                None,
                "short",
                None,
                None,
                "short",
                None,
            ],
            "BTC_normalized_return": [
                np.nan,
                2.0,
                np.nan,
                -2.0,
                np.nan,
                np.nan,
                -3.0,
                np.nan,
            ],
            "breadth_count": [0, 4, 0, 3, 0, 0, 4, 0],
            "dispersion": [np.nan, 1.2, np.nan, 1.3, np.nan, np.nan, 1.4, np.nan],
            "dispersion_threshold": [
                np.nan,
                1.0,
                np.nan,
                1.0,
                np.nan,
                np.nan,
                1.0,
                np.nan,
            ],
            "valid_symbols": [0, 4, 0, 4, 0, 0, 4, 0],
        }
    )

    events = sample_breadth_events(states, config, signal_variant="primary")

    assert [event.direction for event in events] == ["long", "short"]
    assert [event.decision_time_utc for event in events] == [
        "2025-08-01T00:30:00+00:00",
        "2025-08-01T01:45:00+00:00",
    ]


def test_labels_use_next_open_and_independent_delayed_horizon() -> None:
    config = CrossAssetBreadthConfig()
    opens = pd.date_range("2025-08-01T00:00:00Z", periods=3, freq="15min")
    states = pd.DataFrame(
        {
            "bar_open_at": opens,
            "decision_time_utc": opens + pd.Timedelta(minutes=15),
            "primary_qualifies": [False, True, False],
            "primary_direction": [None, "long", None],
            "BTC_normalized_return": [np.nan, 2.0, np.nan],
            "breadth_count": [0, 4, 0],
            "dispersion": [np.nan, 1.2, np.nan],
            "dispersion_threshold": [np.nan, 1.0, np.nan],
            "valid_symbols": [0, 4, 0],
        }
    )
    event = sample_breadth_events(states, config, signal_variant="primary")
    minutes = pd.date_range("2025-08-01T00:00:00Z", periods=180, freq="1min")
    bars = pd.DataFrame(
        {
            "timestamp": minutes,
            "open": 100.0 + np.arange(len(minutes), dtype=float) * 0.01,
            "source": "hl",
        }
    )

    labels = label_breadth_events(event, bars, config)

    assert len(labels) == 2
    base, delayed = labels
    assert base.anchor == "base"
    assert base.entry_time_utc == "2025-08-01T00:30:00+00:00"
    assert base.exit_time_utc == "2025-08-01T01:30:00+00:00"
    assert delayed.anchor == "delayed"
    assert delayed.entry_time_utc == "2025-08-01T00:31:00+00:00"
    assert delayed.exit_time_utc == "2025-08-01T01:31:00+00:00"
    assert base.status == delayed.status == "resolved"
    assert base.directional_gross_return_bps is not None
    assert delayed.directional_gross_return_bps is not None


def test_gap_at_any_anchor_is_explicit_technical_gap() -> None:
    config = CrossAssetBreadthConfig()
    opens = pd.date_range("2025-08-01T00:00:00Z", periods=3, freq="15min")
    states = pd.DataFrame(
        {
            "bar_open_at": opens,
            "decision_time_utc": opens + pd.Timedelta(minutes=15),
            "primary_qualifies": [False, True, False],
            "primary_direction": [None, "short", None],
            "BTC_normalized_return": [np.nan, -2.0, np.nan],
            "breadth_count": [0, 4, 0],
            "dispersion": [np.nan, 1.2, np.nan],
            "dispersion_threshold": [np.nan, 1.0, np.nan],
            "valid_symbols": [0, 4, 0],
        }
    )
    event = sample_breadth_events(states, config, signal_variant="primary")
    minutes = pd.date_range("2025-08-01T00:00:00Z", periods=180, freq="1min")
    bars = pd.DataFrame({"timestamp": minutes, "open": 100.0, "source": "hl"})
    bars.loc[bars["timestamp"].eq(pd.Timestamp("2025-08-01T01:30:00Z")), "source"] = (
        "hl_gap_fill"
    )

    labels = label_breadth_events(event, bars, config)

    assert labels[0].status == "technical_gap"
    assert labels[0].directional_gross_return_bps is None
    assert labels[1].status == "resolved"
