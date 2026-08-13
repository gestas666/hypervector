"""Tests for causal, report-only regime component attribution."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hypervector.research.regime_component_attribution import (
    AttributionSegment,
    build_component_attribution,
    build_component_feature_frame,
    resolve_forward_paths,
    summarize_resolved_paths,
)


def _bars(rows: int = 420) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=rows, freq="1min", tz="UTC")
    phase = np.arange(rows, dtype=np.float64)
    close = 100.0 + phase * 0.02 + np.sin(phase / 9.0) * 0.2
    return pd.DataFrame(
        {
            "open": close - 0.01,
            "high": close + 0.08,
            "low": close - 0.08,
            "close": close,
            "volume": 10.0 + phase % 7.0,
            "source": "hl",
        },
        index=index,
    )


def _segment(
    frame: pd.DataFrame, start: int = 0, end: int | None = None
) -> AttributionSegment:
    stop = len(frame) if end is None else end
    return AttributionSegment(
        "development",
        frame.index[start],
        frame.index[stop - 1] + pd.Timedelta(minutes=1),
    )


def test_forward_paths_begin_after_completed_decision_bar() -> None:
    bars = _bars()
    features = build_component_feature_frame(bars)

    paths = resolve_forward_paths(bars, features, _segment(bars), horizon_minutes=5)
    observed = paths.loc[bars.index[250]]

    assert observed["reference_close"] == bars.iloc[250]["close"]
    assert observed["future_start"] == bars.index[251]
    assert observed["future_end"] == bars.index[255]
    assert observed["future_close_return"] == pytest.approx(
        bars.iloc[255]["close"] / bars.iloc[250]["close"] - 1.0
    )
    assert bool(observed["usable"])


def test_forward_paths_do_not_cross_segment_boundary() -> None:
    bars = _bars()
    segment = _segment(bars, start=100, end=310)
    features = build_component_feature_frame(bars)

    paths = resolve_forward_paths(bars, features, segment, horizon_minutes=15)
    tail = paths.loc[bars.index[295] : bars.index[309]]

    assert tail["usable"].sum() == 0
    assert set(tail["exclusion_reason"]) == {"right_censored"}
    assert paths.loc[paths["usable"], "future_end"].max() < segment.end


def test_gap_fill_decision_or_label_path_is_excluded_and_counted() -> None:
    bars = _bars()
    bars.loc[bars.index[250], "source"] = "hl_gap_fill"
    features = build_component_feature_frame(bars)
    paths = resolve_forward_paths(bars, features, _segment(bars), horizon_minutes=5)

    assert paths.loc[bars.index[250], "exclusion_reason"] == "gap_decision"
    assert paths.loc[bars.index[247], "exclusion_reason"] == "gap_label_path"
    report = build_component_attribution(
        bars,
        symbol="BTC",
        segments=(_segment(bars),),
        horizons_minutes=(5,),
    )
    counts = report["segments"]["development"]["horizons"]["5"]["observations"]
    assert counts["gap_decision"] == 1
    assert counts["gap_label_path"] == 5


def test_post_gap_feature_quarantine_is_explicit_and_bounded() -> None:
    bars = _bars()
    bars.loc[bars.index[250], "source"] = "hl_gap_fill"
    features = build_component_feature_frame(bars)

    paths = resolve_forward_paths(
        bars,
        features,
        _segment(bars),
        horizon_minutes=5,
        gap_quarantine_minutes=30,
    )

    assert paths.loc[bars.index[251], "exclusion_reason"] == "gap_feature_quarantine"
    assert paths.loc[bars.index[280], "exclusion_reason"] == "gap_feature_quarantine"
    assert paths.loc[bars.index[281], "exclusion_reason"] == "usable"


def test_component_features_are_append_invariant() -> None:
    bars = _bars()
    prefix = build_component_feature_frame(bars.iloc[:350])
    extended = build_component_feature_frame(bars)

    pd.testing.assert_frame_equal(prefix, extended.loc[prefix.index])


def test_signed_strength_components_have_explicit_absolute_magnitudes() -> None:
    features = build_component_feature_frame(_bars())

    for signed, magnitude in (
        ("ema_21_55_gap_bps", "ema_21_55_gap_abs_bps"),
        ("sma_100_200_gap_bps", "sma_100_200_gap_abs_bps"),
        ("harsi_smoothed_rsi", "harsi_smoothed_rsi_abs"),
        ("trend_slope_bps", "trend_slope_abs_bps"),
    ):
        pd.testing.assert_series_equal(
            features[magnitude],
            features[signed].abs().rename(magnitude),
        )


@pytest.mark.parametrize(
    "segments",
    [
        (
            AttributionSegment(
                "a",
                pd.Timestamp("2026-01-01", tz="UTC"),
                pd.Timestamp("2026-01-03", tz="UTC"),
            ),
            AttributionSegment(
                "b",
                pd.Timestamp("2026-01-02", tz="UTC"),
                pd.Timestamp("2026-01-04", tz="UTC"),
            ),
        ),
        (
            AttributionSegment(
                "a",
                pd.Timestamp("2026-01-03", tz="UTC"),
                pd.Timestamp("2026-01-04", tz="UTC"),
            ),
            AttributionSegment(
                "b",
                pd.Timestamp("2026-01-01", tz="UTC"),
                pd.Timestamp("2026-01-02", tz="UTC"),
            ),
        ),
    ],
)
def test_segment_contract_rejects_overlap_or_bad_order(
    segments: tuple[AttributionSegment, ...],
) -> None:
    bars = _bars()

    with pytest.raises(ValueError, match="ordered and non-overlapping"):
        build_component_attribution(bars, symbol="BTC", segments=segments)


def test_report_explicitly_has_no_runtime_or_pnl_authority() -> None:
    bars = _bars()

    report = build_component_attribution(
        bars,
        symbol="BTC",
        segments=(_segment(bars),),
        horizons_minutes=(5,),
    )

    assert report["mode"] == "regime_component_attribution_report_only"
    assert report["execution_authority"] == "none"
    assert report["model_authority"] == "none"
    assert report["thresholds_selected"] is False
    assert report["fills_assumed"] is False
    assert report["pnl_claimed"] is False


def _resolved_paths() -> pd.DataFrame:
    days = [
        pd.date_range(f"2026-01-0{day} 00:00", periods=12, freq="1min", tz="UTC")
        for day in (1, 2, 3)
    ]
    index = days[0].append(days[1:])
    within_day = np.tile(np.arange(12, dtype=np.float64), 3)
    direction = np.tile(np.array([-1, 0, 1, -1, 0, 1], dtype=np.int64), 6)
    primary = np.where(within_day < 6, "RANGE", "TREND_UP")
    close_return = np.where(within_day < 6, within_day * 0.0001, within_day * 0.001)
    frame = pd.DataFrame(
        {
            "usable": True,
            "exclusion_reason": "usable",
            "reference_close": 100.0,
            "future_close_return": close_return,
            "future_high_return": np.abs(close_return) + 0.001,
            "future_low_return": -(np.abs(close_return) / 2.0 + 0.0005),
            "primary_regime": primary,
            "state_1m": primary,
            "state_5m": primary,
            "context_15m": "TREND_UP",
            "structural_direction": np.where(within_day < 6, None, "long"),
            "entry_direction": np.where(within_day < 6, None, "long"),
            "ema_21_55_direction": direction,
            "sma_100_200_direction": direction,
            "cipher_a_direction": direction,
            "harsi_direction": direction,
            "mtf_5m_bias": direction * 3,
            "mtf_15m_bias": direction * 2,
            "trend_r2": within_day,
            "choppiness_14": within_day[::-1],
        },
        index=index,
    )
    return frame


def test_summary_reports_range_direction_categorical_and_effective_counts() -> None:
    summary = summarize_resolved_paths(_resolved_paths(), horizon_minutes=5)

    assert summary["observations"]["usable"] == 36
    assert summary["observations"]["non_overlapping"] == 9
    assert summary["canonical"]["state_counts"] == {"RANGE": 18, "TREND_UP": 18}
    assert summary["canonical"]["state_onset_counts"] == {
        "RANGE": 3,
        "TREND_UP": 3,
    }
    range_move = summary["range_quality"]["RANGE"]["absolute_close_return"]["mean"]
    trend_move = summary["range_quality"]["NON_RANGE"]["absolute_close_return"]["mean"]
    assert range_move < trend_move
    assert summary["directional_calls"]["long"]["count"] == 18
    states = summary["categorical_components"]["ema_21_55_direction"]["states"]
    assert set(states) == {"-1", "0", "1"}
    assert "state_onsets" in summary["categorical_components"]["mtf_5m_bias"]


def test_numeric_components_use_daily_not_pooled_spearman_ic() -> None:
    summary = summarize_resolved_paths(_resolved_paths(), horizon_minutes=5)
    metrics = summary["numeric_components"]["trend_r2"]

    assert set(metrics) == {
        "future_close_return",
        "future_absolute_close_return",
        "future_absolute_excursion",
    }
    assert metrics["future_close_return"]["valid_days"] == 3
    assert metrics["future_close_return"]["median_daily_ic"] == pytest.approx(1.0)
    assert "pooled_ic" not in metrics["future_close_return"]


def test_absolute_strength_component_is_retained_in_numeric_summary() -> None:
    paths = _resolved_paths()
    paths["trend_slope_abs_bps"] = paths["trend_r2"]

    summary = summarize_resolved_paths(paths, horizon_minutes=5)

    assert (
        summary["numeric_components"]["trend_slope_abs_bps"][
            "future_absolute_excursion"
        ]["valid_days"]
        == 3
    )
