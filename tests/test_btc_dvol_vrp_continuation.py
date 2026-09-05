"""Tests for preregistered BTC DVOL-VRP long and control signals."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hypervector.research.btc_dvol_vrp_continuation import (
    build_btc_dvol_vrp_signals,
)


def test_primary_emits_one_entry_per_state_onset_and_rearms() -> None:
    """Persistent qualifying states cannot repeatedly enter without reset."""
    features = _features(6)
    features["high_vrp"] = [False, True, True, False, True, True]
    features["bullish_structure"] = [True, True, True, True, True, True]

    signals = build_btc_dvol_vrp_signals(features)

    assert signals.primary["long_entry"].tolist() == [
        False,
        True,
        False,
        False,
        True,
        False,
    ]
    assert not signals.primary["short_entry"].any()
    assert not signals.primary["short_exit"].any()
    assert signals.primary["signal_name"].eq("dvol_vrp_bullish_breakout_long").all()


def test_controls_preserve_only_their_preregistered_mechanisms() -> None:
    """Each control must remove exactly the intended primary condition."""
    features = _features(6)
    features["high_vrp"] = [False, True, True, False, True, False]
    features["low_vrp"] = [False, False, False, True, True, False]
    features["bullish_structure"] = [False, False, True, True, True, False]

    signals = build_btc_dvol_vrp_signals(features)

    assert signals.primary["long_entry"].tolist() == [
        False,
        False,
        True,
        False,
        True,
        False,
    ]
    assert signals.price_only["long_entry"].tolist() == [
        False,
        False,
        True,
        False,
        False,
        False,
    ]
    assert signals.high_vrp_only["long_entry"].tolist() == [
        False,
        True,
        False,
        False,
        True,
        False,
    ]
    assert signals.low_vrp_placebo["long_entry"].tolist() == [
        False,
        False,
        False,
        True,
        False,
        False,
    ]


def test_strategic_exits_are_completed_hour_conditions_for_every_arm() -> None:
    """EMA loss or VRP median loss must request a long exit at event time."""
    features = _features(5)
    features.loc[1, "btc_close"] = 99.0
    features.loc[1, "ema24"] = 100.0
    features.loc[3, "vrp"] = 0.1
    features.loc[3, "vrp_median"] = 0.2

    signals = build_btc_dvol_vrp_signals(features)

    expected = [False, True, False, True, False]
    for frame in (
        signals.primary,
        signals.price_only,
        signals.high_vrp_only,
        signals.low_vrp_placebo,
    ):
        assert frame["long_exit"].tolist() == expected


def test_event_time_is_hour_close_and_never_claims_same_minute_execution() -> None:
    """A labeled source hour can only emit an event one hour later."""
    features = _features(4)

    signals = build_btc_dvol_vrp_signals(features)

    for frame in signals.frames():
        assert frame["event_time"].equals(features["decision_time"])
        assert (
            frame["event_time"] == features["source_timestamp"] + pd.Timedelta(hours=1)
        ).all()
        assert "execution_time" not in frame.columns
        assert (
            frame.attrs["execution_semantics"]
            == "next_minute_open_strictly_after_event"
        )


def test_missing_feature_values_cannot_emit_entry_or_exit() -> None:
    """Incomplete derived inputs must yield no success-shaped signal."""
    features = _features(4)
    features.loc[1, ["vrp", "vrp_median"]] = np.nan
    features.loc[1, ["high_vrp", "bullish_structure"]] = [True, True]
    features.loc[2, ["btc_close", "ema24"]] = np.nan

    signals = build_btc_dvol_vrp_signals(features)

    assert not signals.primary.loc[1, "long_entry"]
    assert not signals.primary.loc[1, "long_exit"]
    assert not signals.primary.loc[2, "long_exit"]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing", "lacks columns"),
        ("naive", "timezone-aware UTC"),
        ("misavailable", "exactly one hour"),
        ("duplicate", "ordered and unique"),
    ],
)
def test_signal_builder_rejects_incomplete_or_invalid_event_contract(
    mutation: str,
    message: str,
) -> None:
    """Invalid point-in-time identity must fail before signal construction."""
    features = _features(4)
    if mutation == "missing":
        features.drop(columns="high_vrp", inplace=True)
    elif mutation == "naive":
        features["decision_time"] = features["decision_time"].dt.tz_localize(None)
    elif mutation == "misavailable":
        features.loc[2, "decision_time"] += pd.Timedelta(minutes=1)
    elif mutation == "duplicate":
        features.loc[2, "decision_time"] = features.loc[1, "decision_time"]
    else:
        raise AssertionError(f"unknown mutation: {mutation}")

    with pytest.raises(ValueError, match=message):
        build_btc_dvol_vrp_signals(features)


def _features(rows: int) -> pd.DataFrame:
    source = pd.date_range("2026-01-01T00:00:00Z", periods=rows, freq="h")
    return pd.DataFrame(
        {
            "source_timestamp": source,
            "decision_time": source + pd.Timedelta(hours=1),
            "btc_close": np.full(rows, 101.0),
            "ema24": np.full(rows, 100.0),
            "vrp": np.full(rows, 0.3),
            "vrp_median": np.full(rows, 0.2),
            "high_vrp": np.full(rows, False),
            "low_vrp": np.full(rows, False),
            "bullish_structure": np.full(rows, False),
        }
    )
