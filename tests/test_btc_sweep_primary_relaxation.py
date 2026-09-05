"""Frozen signal contract for the V58 BTC sweep-relaxation replay."""

from __future__ import annotations

import pandas as pd
import pytest

from hypervector.research.btc_sweep_primary_relaxation import (
    BtcSweepPrimaryRelaxationConfig,
    build_btc_sweep_primary_relaxation_signals,
)


def test_frozen_config_rejects_post_preregistration_retuning() -> None:
    """Only the registered primary-predicate removal may be evaluated."""
    config = BtcSweepPrimaryRelaxationConfig()
    assert config.lookback_hours == 20
    assert config.sweep_clearance_bps == pytest.approx(2.0)
    assert config.volume_multiple == pytest.approx(1.2)
    assert config.ema_length_hours == 55
    with pytest.raises(ValueError, match="lookback"):
        BtcSweepPrimaryRelaxationConfig(lookback_hours=19)
    with pytest.raises(ValueError, match="volume multiple"):
        BtcSweepPrimaryRelaxationConfig(volume_multiple=1.1)


def test_candidate_removes_only_sweep_and_preserves_onset_semantics() -> None:
    """A high-volume trend hour enters candidate once but not the control."""
    bars = _minute_market()
    result = build_btc_sweep_primary_relaxation_signals(bars)
    candidate_times = result.candidate.index[result.candidate["long_entry"]]
    control_times = result.control.index[result.control["long_entry"]]

    assert list(candidate_times) == [bars.index[60 * 60 + 59]]
    assert list(control_times) == []
    diagnostics = result.hourly.loc[pd.Timestamp("2025-01-03T12:00:00Z")]
    assert diagnostics["candidate_raw"] == pytest.approx(1.0)
    assert diagnostics["control_raw"] == pytest.approx(0.0)
    assert diagnostics["reclaim"] == pytest.approx(1.0)
    assert diagnostics["volume_ok"] == pytest.approx(1.0)
    assert diagnostics["trend_ok"] == pytest.approx(1.0)
    assert diagnostics["sweep_ok"] == pytest.approx(0.0)
    assert not bool(result.candidate.iloc[60 * 60 + 59 + 60]["long_entry"])


def test_control_and_candidate_share_a_true_sweep_after_reset() -> None:
    """When every frozen predicate passes, both routes emit the same onset."""
    bars = _minute_market()
    hour = pd.Timestamp("2025-01-03T15:00:00Z")
    prior = bars.loc[bars.index < hour].resample("1h").agg(low=("low", "min"))
    prior_low = float(prior.tail(20)["low"].min())
    selected = bars.index.floor("1h") == hour
    bars.loc[selected, "low"] = prior_low * 0.999
    bars.loc[selected, "volume"] = 2.0

    result = build_btc_sweep_primary_relaxation_signals(bars)
    available = hour + pd.Timedelta(minutes=59)
    assert bool(result.control.loc[available, "long_entry"])
    assert bool(result.candidate.loc[available, "long_entry"])


def test_volume_and_trend_predicates_remain_binding() -> None:
    """Removing the sweep cannot silently remove volume or EMA55 filters."""
    bars = _minute_market()
    selected_hours = bars.index.floor("1h").isin(
        pd.DatetimeIndex(["2025-01-03T12:00:00Z", "2025-01-03T13:00:00Z"])
    )
    bars.loc[selected_hours, "volume"] = 0.5
    result = build_btc_sweep_primary_relaxation_signals(bars)
    assert not result.candidate["long_entry"].any()

    falling = _minute_market(direction="down")
    falling_result = build_btc_sweep_primary_relaxation_signals(falling)
    assert not falling_result.candidate["long_entry"].any()


def test_future_rows_cannot_change_prior_signal_bytes() -> None:
    """Appending a completed future hour cannot revise the causal prefix."""
    bars = _minute_market()
    baseline = build_btc_sweep_primary_relaxation_signals(bars)
    future = bars.iloc[-60:].copy()
    future.index += pd.Timedelta(hours=1)
    future.loc[:, ["open", "high", "low", "close"]] *= 0.5
    extended = build_btc_sweep_primary_relaxation_signals(pd.concat([bars, future]))
    pd.testing.assert_frame_equal(
        baseline.control,
        extended.control.loc[baseline.control.index],
        check_freq=False,
    )
    pd.testing.assert_frame_equal(
        baseline.candidate,
        extended.candidate.loc[baseline.candidate.index],
        check_freq=False,
    )


def test_missing_minute_fails_closed() -> None:
    """A cadence hole cannot be bridged into an apparently valid signal."""
    bars = _minute_market().drop(pd.Timestamp("2025-01-03T11:17:00Z"))
    with pytest.raises(ValueError, match="uninterrupted one-minute cadence"):
        build_btc_sweep_primary_relaxation_signals(bars)


def test_authentic_gap_fill_may_have_zero_but_not_negative_volume() -> None:
    """Known zero-trade minutes remain valid while impossible volume fails."""
    bars = _minute_market()
    timestamp = pd.Timestamp("2025-01-02T00:00:00Z")
    bars.loc[timestamp, "volume"] = 0.0
    result = build_btc_sweep_primary_relaxation_signals(bars)
    assert len(result.hourly) == 66
    bars.loc[timestamp, "volume"] = -0.1
    with pytest.raises(ValueError, match="volume must be finite and non-negative"):
        build_btc_sweep_primary_relaxation_signals(bars)


def _minute_market(direction: str = "up") -> pd.DataFrame:
    hours = pd.date_range("2025-01-01", periods=66, freq="1h", tz="UTC")
    step = 0.25 if direction == "up" else -0.25
    closes = pd.Series(
        [120.0 + step * position for position in range(len(hours))],
        index=hours,
    )
    hourly = pd.DataFrame(index=hours)
    hourly["close"] = closes
    hourly["open"] = closes - step / 2.0
    hourly["high"] = hourly[["open", "close"]].max(axis=1) + 0.1
    hourly["low"] = hourly[["open", "close"]].min(axis=1) - 0.1
    hourly["volume"] = 60.0
    hourly.loc[hours[60:62], "volume"] = 120.0
    return _expand_hours(hourly)


def _expand_hours(hourly: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, float]] = []
    index: list[pd.Timestamp] = []
    for timestamp, row in hourly.iterrows():
        for minute in range(60):
            index.append(timestamp + pd.Timedelta(minutes=minute))
            rows.append(
                {
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]) / 60.0,
                }
            )
    return pd.DataFrame(rows, index=pd.DatetimeIndex(index))
