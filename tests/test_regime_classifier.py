"""Causal regime classifier and multi-timeframe composition tests."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from hypervector.data.hl import bars_from_hl_payload
from hypervector.regime.classifier import RegimeClassifierConfig, classify_timeframe
from hypervector.regime.composite import (
    _completed_supplied_context,
    _resample_bars,
    classify_multitimeframe,
    compose_regimes,
)
from hypervector.regime.ultimate import detect_ultimate_regime
from hypervector.regime.classifier import hyperliquid_native_regime_config


def _bars(close: np.ndarray, volume: np.ndarray | None = None) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=len(close), freq="1min", tz="UTC")
    values = close.astype(float)
    volumes = np.full(len(values), 100.0) if volume is None else volume.astype(float)
    return pd.DataFrame(
        {
            "open": values,
            "high": values + 0.02,
            "low": values - 0.02,
            "close": values,
            "volume": volumes,
        },
        index=index,
    )


def _config() -> RegimeClassifierConfig:
    return RegimeClassifierConfig(
        ema_fast=3,
        ema_slow=8,
        warmup_bars=10,
        structure_lookback=10,
        trend_strength_percentile=50.0,
        range_strength_percentile=20.0,
        minimum_trend_gap_bps=1.0,
        bbwp_length=5,
        bbwp_lookback=10,
        bbwp_compression_threshold=25.0,
        rsi_length=5,
        rsi_signal_length=3,
        breakout_lookback=5,
        breakout_clearance_bps=1.0,
        breakout_volume_lookback=5,
        breakout_volume_multiple=1.5,
    )


def test_resample_uses_complete_venue_aligned_5m_buckets() -> None:
    bars = _bars(np.arange(16, dtype=float))

    result = _resample_bars(bars, 5)

    expected_index = bars.index[[4, 9, 14]]
    assert result.index.equals(expected_index)
    assert result["open"].tolist() == [0.0, 5.0, 10.0]
    assert result["close"].tolist() == [4.0, 9.0, 14.0]
    assert result["volume"].tolist() == [500.0, 500.0, 500.0]


def test_resample_uses_complete_venue_aligned_15m_bucket() -> None:
    bars = _bars(np.arange(16, dtype=float))

    result = _resample_bars(bars, 15)

    assert result.index.equals(bars.index[[14]])
    assert result.iloc[0]["open"] == 0.0
    assert result.iloc[0]["close"] == 14.0
    assert result.iloc[0]["volume"] == 1500.0


def test_resample_matches_native_hyperliquid_5m_candle() -> None:
    fixtures = Path(__file__).parent / "fixtures"
    raw_1m = json.loads((fixtures / "hl_candle_sample.json").read_text())
    raw_5m = json.loads((fixtures / "hl_5m_candle_sample.json").read_text())
    bars_1m = bars_from_hl_payload(raw_1m).set_index("timestamp")
    native_5m = bars_from_hl_payload(raw_5m).set_index("timestamp")

    actual = _resample_bars(bars_1m, 5).iloc[0]
    expected = native_5m.iloc[0]

    assert actual.name == expected.name + pd.Timedelta(minutes=4)
    for column in ("open", "high", "low", "close", "volume"):
        assert actual[column] == pytest.approx(expected[column])


def test_resample_is_invariant_to_incomplete_trailing_bucket() -> None:
    complete = _bars(np.arange(15, dtype=float))
    with_partial = _bars(np.arange(17, dtype=float))

    expected = _resample_bars(complete, 5)
    actual = _resample_bars(with_partial, 5)

    pd.testing.assert_frame_equal(actual, expected)


def test_supplied_open_timestamped_5m_state_is_available_at_last_constituent() -> None:
    index_5m = pd.date_range("2026-01-01", periods=12, freq="5min", tz="UTC")
    values = np.linspace(100.0, 112.0, len(index_5m))
    bars_5m = pd.DataFrame(
        {
            "open": values,
            "high": values + 0.02,
            "low": values - 0.02,
            "close": values,
            "volume": 100.0,
        },
        index=index_5m,
    )
    index_1m = pd.date_range("2026-01-01", periods=60, freq="1min", tz="UTC")

    result = _completed_supplied_context(bars_5m, index_1m, _config(), minutes=5)

    assert result.loc[index_1m[48], "primary_regime"] == "UNKNOWN"
    assert result.loc[index_1m[49], "primary_regime"] == "TREND_UP"


def test_classifier_emits_trend_up_and_down() -> None:
    upward = classify_timeframe(_bars(np.linspace(100.0, 110.0, 80)), _config())
    downward = classify_timeframe(_bars(np.linspace(110.0, 100.0, 80)), _config())

    assert upward.iloc[-1].primary_regime == "TREND_UP"
    assert downward.iloc[-1].primary_regime == "TREND_DOWN"


def test_classifier_emits_range_for_flat_structure() -> None:
    close = 100.0 + np.sin(np.arange(80) * np.pi / 2.0) * 0.002

    result = classify_timeframe(_bars(close), _config())

    assert result.iloc[-1].primary_regime == "RANGE"
    assert bool(result.iloc[-1].coiling) is True


def test_compression_alone_is_not_a_breakout() -> None:
    result = classify_timeframe(_bars(np.full(80, 100.0)), _config())

    assert "BREAKOUT" not in set(result.primary_regime.iloc[-20:])


def test_classifier_requires_directional_prior_range_break() -> None:
    base = np.full(30, 100.0)
    high_volume = np.full(30, 100.0)
    high_volume[-1] = 500.0
    upward = base.copy()
    upward[-1] = 100.25
    downward = base.copy()
    downward[-1] = 99.75

    up_result = classify_timeframe(_bars(upward, high_volume), _config())
    down_result = classify_timeframe(_bars(downward, high_volume), _config())

    assert up_result.iloc[-1].primary_regime == "BREAKOUT"
    assert up_result.iloc[-1].breakout_direction == "BK_UPWARD"
    assert down_result.iloc[-1].primary_regime == "BREAKOUT"
    assert down_result.iloc[-1].breakout_direction == "BK_DOWNWARD"


def test_classifier_warmup_is_unknown() -> None:
    result = classify_timeframe(_bars(np.linspace(100.0, 101.0, 20)), _config())

    assert set(result.primary_regime.iloc[:9]) == {"UNKNOWN"}


def test_classifier_labels_technical_score_as_non_model_telemetry() -> None:
    result = classify_timeframe(_bars(np.linspace(100.0, 110.0, 80)), _config())
    latest = result.iloc[-1]

    assert latest.regime_strength_score == pytest.approx(latest.confidence)
    assert latest.regime_strength_percentile == pytest.approx(
        latest.regime_strength_score * 100.0
    )
    assert latest.regime_score_source == "ema_gap_strength_percentile_rank"


def test_classifier_reports_causal_bbwp_momentum_and_structure_evidence() -> None:
    close = 100.0 + np.sin(np.arange(80) / 2.0) * np.linspace(2.0, 0.001, 80)

    result = classify_timeframe(_bars(close), _config())

    expected = {
        "bbwp_percentile",
        "compression_ready",
        "ema_gap_bps_signed",
        "rsi",
        "rsi_ema",
        "rsi_cross_direction",
        "tactical_breakout_direction",
        "breakout_volume_ratio",
        "prior_range_high",
        "prior_range_low",
    }
    assert expected.issubset(result.columns)
    assert result.bbwp_percentile.iloc[-1] < 25.0
    assert bool(result.compression_ready.iloc[-1]) is True


def test_classifier_reports_exact_range_cause_inputs_without_changing_state() -> None:
    close = 100.0 + np.sin(np.arange(80) * np.pi / 2.0) * 0.002

    result = classify_timeframe(_bars(close), _config())
    latest = result.iloc[-1]

    assert latest.primary_regime == "RANGE"
    assert bool(latest.range_cause_coiling) is True
    assert bool(latest.range_cause_gap) is True
    assert bool(latest.range_cause_filter) is bool(latest.bbwp_percentile < 25.0)
    assert latest.range_filter_name == "bbwp"
    assert latest.bbwp_compression_threshold == pytest.approx(25.0)
    assert latest.minimum_trend_gap_bps == pytest.approx(1.0)
    assert latest.range_strength_threshold == pytest.approx(20.0)
    assert latest.trend_strength_threshold == pytest.approx(50.0)


def test_breakout_requires_eight_bps_clearance_and_two_point_five_x_volume() -> None:
    base = np.full(40, 100.0)
    config = replace(
        _config(),
        breakout_clearance_bps=8.0,
        breakout_volume_multiple=2.5,
    )
    insufficient_clearance = base.copy()
    insufficient_clearance[-1] = 100.08
    insufficient_volume = base.copy()
    insufficient_volume[-1] = 100.20
    confirmed = insufficient_volume.copy()
    low_volume = np.full(40, 100.0)
    high_volume = low_volume.copy()
    high_volume[-1] = 250.0

    clearance_result = classify_timeframe(
        _bars(insufficient_clearance, high_volume), config
    )
    volume_result = classify_timeframe(_bars(insufficient_volume, low_volume), config)
    confirmed_result = classify_timeframe(_bars(confirmed, high_volume), config)

    assert clearance_result.iloc[-1].primary_regime != "BREAKOUT"
    assert volume_result.iloc[-1].primary_regime != "BREAKOUT"
    assert confirmed_result.iloc[-1].primary_regime == "BREAKOUT"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("structure_lookback", 4, "structure_lookback"),
        ("trend_strength_percentile", 101.0, "trend_strength_percentile"),
        ("range_strength_percentile", -1.0, "range_strength_percentile"),
        ("minimum_trend_gap_bps", -0.1, "minimum_trend_gap_bps"),
        ("bbwp_length", 1, "bbwp_length"),
        ("bbwp_lookback", 4, "bbwp_lookback"),
        ("bbwp_compression_threshold", 101.0, "bbwp_compression_threshold"),
        ("rsi_length", 1, "rsi_length"),
        ("rsi_signal_length", 1, "rsi_signal_length"),
        ("coiling_width_bps", -0.1, "coiling_width_bps"),
        ("breakout_clearance_bps", -0.1, "breakout_clearance_bps"),
        ("breakout_volume_lookback", 0, "breakout_volume_lookback"),
        ("breakout_volume_multiple", float("nan"), "breakout_volume_multiple"),
    ],
)
def test_classifier_config_rejects_invalid_thresholds(
    field: str,
    value: int | float,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_config(), **{field: value})


def test_classifier_config_requires_ordered_strength_percentiles() -> None:
    with pytest.raises(ValueError, match="range_strength_percentile"):
        replace(
            _config(),
            range_strength_percentile=60.0,
            trend_strength_percentile=50.0,
        )


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("close", float("nan"), "non-finite"),
        ("open", 0.0, "positive"),
        ("volume", -1.0, "non-negative"),
        ("high", 90.0, "OHLC"),
        ("low", 110.0, "OHLC"),
    ],
)
def test_classifier_rejects_malformed_ohlcv(
    column: str,
    value: float,
    message: str,
) -> None:
    bars = _bars(np.linspace(100.0, 101.0, 20))
    bars.loc[bars.index[7], column] = value

    with pytest.raises(ValueError, match=message):
        classify_timeframe(bars, _config())


def test_multitimeframe_rejects_missing_1m_interval() -> None:
    bars = _bars(np.linspace(100.0, 101.0, 20)).drop(
        pd.Timestamp("2026-01-01 00:07:00+00:00")
    )

    with pytest.raises(ValueError, match="1m.*cadence"):
        classify_multitimeframe(bars, _config())


def test_classifier_is_prefix_invariant() -> None:
    bars = _bars(100.0 + np.sin(np.arange(100) / 7.0))

    prefix = classify_timeframe(bars.iloc[:70], _config())
    full = classify_timeframe(bars, _config())

    pd.testing.assert_frame_equal(prefix, full.iloc[:70])


def _state_frame(
    index: pd.DatetimeIndex,
    primary: str,
    breakout: str | None = None,
    tactical: str | None = None,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "primary_regime": primary,
            "breakout_direction": breakout,
            "tactical_breakout_direction": tactical,
            "confidence": 1.0,
            "reason": "fixture",
            "coiling": False,
        },
        index=index,
    )


def test_composite_uses_5m_as_primary_without_15m_hard_veto() -> None:
    index = pd.date_range("2026-01-01", periods=3, freq="1min", tz="UTC")

    result = compose_regimes(
        _state_frame(index, "TREND_UP"),
        _state_frame(index, "TREND_UP"),
        _state_frame(index, "TREND_DOWN"),
    )

    assert set(result.primary_regime) == {"TREND_UP"}
    assert set(result.context_15m) == {"TREND_DOWN"}
    assert set(result.reason) == {"5m_primary_trend"}


def test_confirmed_1m_and_5m_breakout_overrides_stale_15m() -> None:
    index = pd.date_range("2026-01-01", periods=3, freq="1min", tz="UTC")

    result = compose_regimes(
        _state_frame(index, "BREAKOUT", "BK_UPWARD", "BK_UPWARD"),
        _state_frame(index, "BREAKOUT", "BK_UPWARD"),
        _state_frame(index, "TREND_DOWN"),
    )

    assert set(result.primary_regime) == {"BREAKOUT"}
    assert set(result.breakout_direction) == {"BK_UPWARD"}
    assert set(result.reason) == {"confirmed_1m_5m_breakout"}


def test_5m_trend_remains_eligible_without_tactical_overgate() -> None:
    index = pd.date_range("2026-01-01", periods=3, freq="1min", tz="UTC")

    waiting = compose_regimes(
        _state_frame(index, "TREND_UP"),
        _state_frame(index, "TREND_UP"),
        _state_frame(index, "TREND_DOWN"),
    )
    triggered = compose_regimes(
        _state_frame(index, "BREAKOUT", "BK_UPWARD", "BK_UPWARD"),
        _state_frame(index, "TREND_UP"),
        _state_frame(index, "TREND_DOWN"),
    )

    assert set(waiting.structural_direction) == {"long"}
    assert set(waiting.entry_direction) == {"long"}
    assert set(triggered.structural_direction) == {"long"}
    assert set(triggered.entry_direction) == {"long"}


def test_opposite_1m_tactical_annotation_cannot_reverse_5m_structure() -> None:
    index = pd.date_range("2026-01-01", periods=3, freq="1min", tz="UTC")

    result = compose_regimes(
        _state_frame(index, "BREAKOUT", "BK_DOWNWARD", "BK_DOWNWARD"),
        _state_frame(index, "TREND_UP"),
        _state_frame(index, "TREND_UP"),
    )

    assert set(result.structural_direction) == {"long"}
    assert set(result.entry_direction) == {"long"}


def test_real_features_emit_long_trigger_only_after_full_tactical_alignment() -> None:
    count = 1_800
    compression_bars = 140
    close = np.linspace(100.0, 110.0, count)
    start = count - compression_bars
    center = close[start]
    phase = np.arange(compression_bars) / 2.0 + 2.5
    close[start:] = center + np.sin(phase) * np.linspace(0.5, 0.001, compression_bars)
    close[-1] = center + 1.0
    volume = np.full(count, 100.0)
    volume[-1] = 300.0

    result = classify_multitimeframe(
        _bars(close, volume),
        hyperliquid_native_regime_config(),
    )
    latest = result.iloc[-1]

    assert latest.state_5m == "TREND_UP"
    assert latest.structural_direction == "long"
    assert latest.compression_ready
    assert latest.rsi_cross_direction == "BK_UPWARD"
    assert latest.breakout_volume_ratio == pytest.approx(3.0)
    assert latest.tactical_breakout_direction == "BK_UPWARD"
    assert latest.entry_direction == "long"


def test_ultimate_policy_weights_backend_canonical_entry_direction(monkeypatch) -> None:
    bars = _bars(np.array([100.0, 100.1]))
    classified = pd.DataFrame(
        {
            "primary_regime": ["TREND_UP", "TREND_UP"],
            "breakout_direction": [None, "BK_UPWARD"],
            "structural_direction": ["long", "long"],
            "entry_direction": ["long", "long"],
            "state_1m": ["TREND_UP", "BREAKOUT"],
            "state_5m": ["TREND_UP", "TREND_UP"],
            "context_15m": ["TREND_UP", "TREND_UP"],
            "reason": ["5m_primary_trend", "5m_primary_trend"],
            "confidence": [0.5, 0.6],
            "bbwp_percentile": [30.0, 20.0],
            "compression_ready": [False, True],
            "ema_gap_bps_signed": [1.5, 2.0],
            "rsi": [55.0, 62.0],
            "rsi_ema": [54.0, 60.0],
            "rsi_cross_direction": [None, "BK_UPWARD"],
            "tactical_breakout_direction": [None, "BK_UPWARD"],
            "breakout_volume_ratio": [1.0, 2.7],
            "prior_range_high": [100.0, 100.0],
            "prior_range_low": [99.0, 99.0],
        },
        index=bars.index,
    )
    monkeypatch.setattr(
        "hypervector.regime.ultimate.classify_multitimeframe",
        lambda *_args, **_kwargs: classified,
    )

    result = detect_ultimate_regime(bars)

    assert result.long_weight.tolist() == [1.0, 1.0]
    assert result.short_weight.tolist() == [0.0, 0.0]


def test_5m_breakout_without_1m_confirmation_is_not_directional() -> None:
    index = pd.date_range("2026-01-01", periods=3, freq="1min", tz="UTC")

    result = compose_regimes(
        _state_frame(index, "RANGE"),
        _state_frame(index, "BREAKOUT", "BK_UPWARD"),
        _state_frame(index, "TREND_UP"),
    )

    assert set(result.primary_regime) == {"BREAKOUT"}
    assert result.breakout_direction.isna().all()
    assert set(result.reason) == {"5m_breakout_awaiting_1m_confirmation"}


@pytest.mark.parametrize("state_5m", ["RANGE", "TRANSITION", "UNKNOWN"])
def test_1m_direction_cannot_override_authoritative_5m_state(state_5m: str) -> None:
    index = pd.date_range("2026-01-01", periods=3, freq="1min", tz="UTC")

    result = compose_regimes(
        _state_frame(index, "TREND_UP"),
        _state_frame(index, state_5m),
        _state_frame(index, "TREND_UP"),
    )

    assert set(result.primary_regime) == {state_5m}
    assert set(result.reason) == {"5m_primary_state"}


def test_range_remains_when_1m_and_5m_are_non_directional() -> None:
    index = pd.date_range("2026-01-01", periods=3, freq="1min", tz="UTC")

    result = compose_regimes(
        _state_frame(index, "RANGE"),
        _state_frame(index, "RANGE"),
        _state_frame(index, "TREND_UP"),
    )

    assert set(result.primary_regime) == {"RANGE"}


def test_multitimeframe_context_uses_only_completed_htf_bars() -> None:
    bars = _bars(np.linspace(100.0, 110.0, 121))
    changed = bars.copy()
    changed.iloc[-1, changed.columns.get_loc("close")] = 80.0
    changed.iloc[-1, changed.columns.get_loc("low")] = 79.9

    original = classify_multitimeframe(bars, _config())
    mutated = classify_multitimeframe(changed, _config())

    assert original.iloc[-1].state_5m == mutated.iloc[-1].state_5m
    assert original.iloc[-1].context_15m == mutated.iloc[-1].context_15m


def test_multitimeframe_reports_prefixed_range_anatomy_for_each_causal_frame() -> None:
    bars = _bars(100.0 + np.sin(np.arange(180) / 7.0))

    result = classify_multitimeframe(bars, _config())

    expected = {
        f"regime_{timeframe}_{metric}"
        for timeframe in ("1m", "5m", "15m")
        for metric in (
            "reason",
            "strength_percentile",
            "bbwp_percentile",
            "ema_gap_bps",
            "rsi",
            "rsi_ema",
            "rsi_cross_direction",
            "coiling",
            "range_cause_coiling",
            "range_cause_strength",
            "range_cause_gap",
            "range_cause_filter",
            "breakout_volume_ratio",
        )
    }
    assert expected.issubset(result.columns)
    assert result["regime_5m_reason"].notna().all()
    assert result["regime_5m_strength_percentile"].between(0.0, 100.0).all()


def test_multitimeframe_score_counts_unavailable_context_as_zero() -> None:
    bars = _bars(np.linspace(100.0, 110.0, 41))

    result = classify_multitimeframe(bars, _config())
    row = result.iloc[3]

    assert row.state_5m == "UNKNOWN"
    assert row.context_15m == "UNKNOWN"
    one_minute = classify_timeframe(bars, _config()).iloc[3]
    assert row.regime_strength_score == pytest.approx(
        one_minute.regime_strength_score / 3.0
    )
