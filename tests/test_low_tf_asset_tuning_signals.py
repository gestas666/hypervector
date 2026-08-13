from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.low_tf_asset_tuning_models import (
    TrendEntryShape,
    TrendExitShape,
)
from hypervector.research.low_tf_asset_tuning_signals import (
    build_tuned_trend_signals,
)


def _features(side: str) -> pd.DataFrame:
    times = pd.date_range("2026-01-01", periods=4, freq="5min", tz="UTC")
    long = side == "long"
    close = [100.0, 100.0, 100.0, 101.0 if long else 99.0]
    return pd.DataFrame(
        {
            "bar_open_at": times,
            "close": close,
            "breakout_high_120": [100.0] * 4,
            "breakout_low_120": [100.0] * 4,
            "ema_fast_5m": [100.0, 100.0, 100.0, 100.5 if long else 99.5],
            "ema_slow_5m": [100.0, 100.0, 100.0, 100.0],
            "bbwp_percentile": [50.0, 50.0, 10.0, 40.0],
            "bbwp_signal": [30.0, 30.0, 20.0, 25.0],
            "context_direction": [0, 0, 0, 1 if long else -1],
            "context_fast_slope_bps": [0.0, 0.0, 0.0, 1.0 if long else -1.0],
        }
    )


@pytest.mark.parametrize("side", ["long", "short"])
def test_signal_requires_aligned_release_and_binds_fixed_execution_shape(
    side: str,
) -> None:
    entry = TrendEntryShape(48, 13, 34, 20.0, 8.0)
    exit_shape = TrendExitShape(80.0, 2.0, 24)

    signals = build_tuned_trend_signals(
        _features(side),
        symbol="ETH",
        side=side,
        entry_shape=entry,
        exit_shape=exit_shape,
    )

    assert len(signals) == 1
    row = signals.iloc[0]
    assert row["decision_time_utc"] == "2026-01-01T00:20:00+00:00"
    assert row["family"] == "low_tf_trend_impulse_bidirectional_v1"
    assert row["exit_variant"] == "fixed_rr_max_hold"
    assert row["max_hold_bars"] == 24
    assert row["execution_authority"] == "none"
    reference = 101.0 if side == "long" else 99.0
    stop_sign = -1.0 if side == "long" else 1.0
    target_sign = 1.0 if side == "long" else -1.0
    stop = reference * (1.0 + stop_sign * 80.0 / 10_000.0)
    target = reference + target_sign * abs(reference - stop) * 2.0
    assert row["stop_anchor_price"] == pytest.approx(stop)
    assert row["target_anchor_price"] == pytest.approx(target)


def test_signal_is_withheld_when_five_minute_direction_disagrees() -> None:
    features = _features("long")
    features.loc[3, "ema_fast_5m"] = 99.5

    signals = build_tuned_trend_signals(
        features,
        symbol="SOL",
        side="long",
        entry_shape=TrendEntryShape(48, 13, 34, 20.0, 8.0),
        exit_shape=TrendExitShape(80.0, 2.0, 24),
    )

    assert signals.empty


def test_signal_history_is_append_invariant() -> None:
    features = _features("short")
    future = features.iloc[[-1]].copy()
    future["bar_open_at"] = pd.Timestamp("2026-01-01T00:20:00Z")
    future["close"] = 120.0
    base = build_tuned_trend_signals(
        features,
        symbol="SOL",
        side="short",
        entry_shape=TrendEntryShape(48, 13, 34, 20.0, 8.0),
        exit_shape=TrendExitShape(80.0, 2.0, 24),
    )
    extended = build_tuned_trend_signals(
        pd.concat([features, future], ignore_index=True),
        symbol="SOL",
        side="short",
        entry_shape=TrendEntryShape(48, 13, 34, 20.0, 8.0),
        exit_shape=TrendExitShape(80.0, 2.0, 24),
    )

    pd.testing.assert_frame_equal(
        base, extended.iloc[: len(base)].reset_index(drop=True)
    )
