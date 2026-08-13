"""Auditable long and short signal tests for the low-timeframe cohort."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from hypervector.research.low_tf_multi_asset_cells import declared_low_tf_cells
from hypervector.research.low_tf_multi_asset_signals import (
    LowTfSignalConfig,
    build_low_tf_signals,
)


def _neutral_features(rows: int = 4) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "bar_open_at": pd.date_range(
                "2026-01-01", periods=rows, freq="5min", tz="UTC"
            ),
            "open": [100.0] * rows,
            "high": [100.5] * rows,
            "low": [99.5] * rows,
            "close": [100.0] * rows,
            "range_high_240": [110.0] * rows,
            "range_low_240": [90.0] * rows,
            "range_midpoint_240": [100.0] * rows,
            "range_width_bps": [2_000.0] * rows,
            "breakout_high_120": [110.0] * rows,
            "breakout_low_120": [90.0] * rows,
            "ema_fast_5m": [100.0] * rows,
            "ema_slow_5m": [100.0] * rows,
            "bbwp_percentile": [50.0] * rows,
            "bbwp_signal": [50.0] * rows,
            "rsi": [50.0] * rows,
            "rsi_signal": [50.0] * rows,
            "rsi_bearish_divergence": [False] * rows,
            "rsi_bullish_divergence": [False] * rows,
            "pmarp": [50.0] * rows,
            "pmarp_signal": [50.0] * rows,
            "atr": [1.0] * rows,
            "context_direction": [0] * rows,
            "context_fast_slope_bps": [0.0] * rows,
        }
    )


def _identities(signals: pd.DataFrame) -> set[tuple[str, str, str]]:
    return set(
        zip(
            signals["family"],
            signals["side"],
            signals["exit_variant"],
            strict=True,
        )
    )


def test_range_reclaim_emits_real_long_and_short_variants() -> None:
    long_frame = _neutral_features()
    long_frame.loc[3, ["low", "close"]] = [89.8, 95.0]
    long_signals = build_low_tf_signals(long_frame, symbol="BTC")

    short_frame = _neutral_features()
    short_frame.loc[3, ["high", "close"]] = [110.3, 105.0]
    short_signals = build_low_tf_signals(short_frame, symbol="BTC")

    assert _identities(long_signals) == {
        ("range_reclaim_v1", "long", "range_close_invalidation"),
        ("range_reclaim_v1", "long", "range_wick_atr_stop"),
    }
    assert _identities(short_signals) == {
        ("range_reclaim_v1", "short", "range_close_invalidation"),
        ("range_reclaim_v1", "short", "range_wick_atr_stop"),
    }
    assert set(long_signals["target_anchor_price"]) == {100.0}
    assert set(short_signals["target_anchor_price"]) == {100.0}


def test_range_reclaim_requires_clearance_width_and_favorable_midpoint() -> None:
    frame = _neutral_features()
    frame.loc[3, ["low", "close", "range_width_bps"]] = [89.95, 95.0, 99.0]

    assert build_low_tf_signals(frame, symbol="BTC").empty


def test_trend_expansion_is_bidirectional_and_requires_completed_context() -> None:
    long_frame = _neutral_features()
    long_frame.loc[2, "bbwp_percentile"] = 10.0
    long_frame.loc[3, ["close", "bbwp_percentile", "bbwp_signal"]] = [
        111.0,
        30.0,
        20.0,
    ]
    long_frame.loc[3, ["context_direction", "context_fast_slope_bps"]] = [1, 2.0]

    short_frame = _neutral_features()
    short_frame.loc[2, "bbwp_percentile"] = 10.0
    short_frame.loc[3, ["close", "bbwp_percentile", "bbwp_signal"]] = [
        89.0,
        30.0,
        20.0,
    ]
    short_frame.loc[3, ["context_direction", "context_fast_slope_bps"]] = [-1, -2.0]

    assert _identities(build_low_tf_signals(long_frame, symbol="ETH")) == {
        ("trend_expansion_v1", "long", "rsi_reversal_exit"),
        ("trend_expansion_v1", "long", "ema_alignment_exit"),
    }
    assert _identities(build_low_tf_signals(short_frame, symbol="ETH")) == {
        ("trend_expansion_v1", "short", "rsi_reversal_exit"),
        ("trend_expansion_v1", "short", "ema_alignment_exit"),
    }
    long_frame.loc[3, "context_direction"] = 0
    assert build_low_tf_signals(long_frame, symbol="ETH").empty


def test_pmarp_reversal_cross_emits_both_declared_exit_variants() -> None:
    long_frame = _neutral_features()
    long_frame.loc[2, ["pmarp", "pmarp_signal"]] = [10.0, 12.0]
    long_frame.loc[3, ["close", "pmarp", "pmarp_signal", "bbwp_percentile"]] = [
        98.0,
        25.0,
        20.0,
        90.0,
    ]
    long_frame.loc[3, "ema_fast_5m"] = 100.0

    short_frame = _neutral_features()
    short_frame.loc[2, ["pmarp", "pmarp_signal"]] = [90.0, 88.0]
    short_frame.loc[3, ["close", "pmarp", "pmarp_signal", "bbwp_percentile"]] = [
        102.0,
        75.0,
        80.0,
        90.0,
    ]
    short_frame.loc[3, "ema_fast_5m"] = 100.0

    assert _identities(build_low_tf_signals(long_frame, symbol="SOL")) == {
        ("pmarp_exhaustion_v1", "long", "ema_mean_exit"),
        ("pmarp_exhaustion_v1", "long", "pmarp_opposite_extreme_exit"),
    }
    assert _identities(build_low_tf_signals(short_frame, symbol="SOL")) == {
        ("pmarp_exhaustion_v1", "short", "ema_mean_exit"),
        ("pmarp_exhaustion_v1", "short", "pmarp_opposite_extreme_exit"),
    }


def test_krown_pullback_emits_long_only_on_fresh_state_onset() -> None:
    frame = _neutral_features(5)
    frame.loc[1:3, "bbwp_percentile"] = 30.0
    frame.loc[1:3, ["ema_fast_5m", "ema_slow_5m"]] = [101.0, 100.0]
    frame.loc[2:3, "pmarp"] = 20.0
    frame.loc[1, "low"] = 98.0
    frame.loc[2, "low"] = 99.0

    signals = build_low_tf_signals(frame, symbol="BTC")
    krown = signals.loc[signals["family"].eq("krown_pullback_long_v1")]

    assert _identities(krown) == {
        (
            "krown_pullback_long_v1",
            "long",
            "krown_close_stop_pmarp80",
        ),
        (
            "krown_pullback_long_v1",
            "long",
            "krown_hard_stop_pmarp80",
        ),
    }
    assert krown["decision_position"].tolist() == [2, 2]
    assert set(krown["stop_anchor_price"]) == {98.0}
    assert set(krown["invalidation_mode"]) == {
        "completed_bar_close",
        "intrabar_stop",
    }


def test_krown_pullback_requires_trend_compression_and_pmarp_states() -> None:
    frame = _neutral_features()
    frame.loc[3, ["ema_fast_5m", "ema_slow_5m"]] = [101.0, 100.0]
    frame.loc[3, ["bbwp_percentile", "pmarp"]] = [36.0, 20.0]

    signals = build_low_tf_signals(frame, symbol="BTC")

    assert "krown_pullback_long_v1" not in set(signals["family"])


def test_krown_touch_reclaim_emits_bidirectional_stop_variants() -> None:
    long_frame = _neutral_features(5)
    long_frame.loc[1:3, "bbwp_percentile"] = 20.0
    long_frame.loc[3, ["low", "high", "close"]] = [99.0, 101.0, 100.5]
    long_frame.loc[3, ["ema_fast_5m", "ema_slow_5m"]] = [101.0, 100.0]

    short_frame = _neutral_features(5)
    short_frame.loc[1:3, "bbwp_percentile"] = 20.0
    short_frame.loc[3, ["low", "high", "close"]] = [99.0, 101.0, 99.5]
    short_frame.loc[3, ["ema_fast_5m", "ema_slow_5m"]] = [99.0, 100.0]

    long_signals = build_low_tf_signals(long_frame, symbol="BTC")
    short_signals = build_low_tf_signals(short_frame, symbol="BTC")
    long_touch = long_signals.loc[long_signals["family"].eq("krown_ema55_touch_v1")]
    short_touch = short_signals.loc[short_signals["family"].eq("krown_ema55_touch_v1")]

    assert _identities(long_touch) == {
        ("krown_ema55_touch_v1", "long", "krown_touch_close_stop_rsi_div"),
        ("krown_ema55_touch_v1", "long", "krown_touch_hard_stop_rsi_div"),
    }
    assert _identities(short_touch) == {
        ("krown_ema55_touch_v1", "short", "krown_touch_close_stop_rsi_div"),
        ("krown_ema55_touch_v1", "short", "krown_touch_hard_stop_rsi_div"),
    }
    assert set(long_touch["stop_anchor_price"]) == {99.0}
    assert set(short_touch["stop_anchor_price"]) == {101.0}


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("bbwp_percentile", 25.0),
        ("low", 100.1),
        ("close", 99.9),
        ("ema_fast_5m", 99.0),
    ],
)
def test_krown_long_touch_requires_every_completed_entry_predicate(
    column: str, value: float
) -> None:
    frame = _neutral_features(5)
    frame.loc[1:3, "bbwp_percentile"] = 20.0
    frame.loc[3, ["low", "high", "close"]] = [99.0, 101.0, 100.5]
    frame.loc[3, ["ema_fast_5m", "ema_slow_5m"]] = [101.0, 100.0]
    frame.loc[3, column] = value

    signals = build_low_tf_signals(frame, symbol="BTC")

    assert "krown_ema55_touch_v1" not in set(signals["family"])


def test_contradictory_families_are_preserved_for_portfolio_attribution() -> None:
    frame = _neutral_features()
    frame.loc[2, "bbwp_percentile"] = 10.0
    frame.loc[3, ["high", "close", "range_midpoint_240"]] = [110.3, 105.0, 100.0]
    frame.loc[3, ["breakout_high_120", "bbwp_percentile", "bbwp_signal"]] = [
        104.0,
        30.0,
        20.0,
    ]
    frame.loc[3, ["context_direction", "context_fast_slope_bps"]] = [1, 2.0]

    signals = build_low_tf_signals(frame, symbol="HYPE")

    assert set(zip(signals["family"], signals["side"], strict=True)) == {
        ("range_reclaim_v1", "short"),
        ("trend_expansion_v1", "long"),
    }


def test_signal_generation_is_append_invariant() -> None:
    frame = _neutral_features(5)
    frame.loc[2, "bbwp_percentile"] = 10.0
    frame.loc[3, ["close", "bbwp_percentile", "bbwp_signal"]] = [111.0, 30.0, 20.0]
    frame.loc[3, ["context_direction", "context_fast_slope_bps"]] = [1, 2.0]

    before = build_low_tf_signals(frame.iloc[:4], symbol="BTC")
    after = build_low_tf_signals(frame, symbol="BTC")

    pd.testing.assert_frame_equal(before, after.loc[after["decision_position"].lt(4)])


def test_signal_evidence_separates_sources_from_hypotheses() -> None:
    frame = _neutral_features()
    frame.loc[3, ["low", "close"]] = [89.8, 95.0]

    signal = build_low_tf_signals(frame, symbol="BTC").iloc[0]

    assert "range_midpoint" in signal["source_backed_facts"]
    assert "240_bar_boundary" in signal["hypothesis_facts"]
    assert signal["execution_authority"] == "none"
    assert signal["decision_time_utc"] == "2026-01-01T00:20:00+00:00"


def test_signal_validation_rejects_missing_and_nonfinite_decision_inputs() -> None:
    missing = _neutral_features().drop(columns="atr")
    with pytest.raises(ValueError, match="missing columns"):
        build_low_tf_signals(missing, symbol="BTC")

    nonfinite = _neutral_features()
    nonfinite.loc[3, "close"] = math.inf
    with pytest.raises(ValueError, match="finite"):
        build_low_tf_signals(nonfinite, symbol="BTC")


def test_signal_config_rejects_inverted_extremes() -> None:
    with pytest.raises(ValueError, match="PMARP"):
        LowTfSignalConfig(pmarp_low=90.0, pmarp_high=80.0)


def test_declared_cell_catalog_retains_zero_signal_trial_identities() -> None:
    cells = declared_low_tf_cells()

    assert len(cells) == 18
    assert len(set(cells)) == len(cells)
    assert {
        ("krown_ema55_touch_v1", "long", "krown_touch_hard_stop_rsi_div"),
        ("krown_ema55_touch_v1", "short", "krown_touch_hard_stop_rsi_div"),
    }.issubset(set(cells))
