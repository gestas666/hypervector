"""Tests for report-only HT onset metalabel evidence."""

from __future__ import annotations

import pandas as pd

from hypervector.ml.ht_onset_metalabel import evaluate_ht_onset_metalabel


def test_ht_metalabel_is_purged_report_only_and_keeps_later_data_descriptive() -> None:
    """The model may rank frozen setups but cannot grant execution authority."""
    result = evaluate_ht_onset_metalabel(
        _market(),
        symbol="BTC",
        holdout_days=5,
        n_splits=3,
    )

    report = result.report
    assert report["contract"] == {
        "report_only": True,
        "execution_authority": "none",
        "automatic_promotion": False,
        "runtime_strategy_changed": False,
        "model_installed": False,
    }
    assert report["development"]["used_for_selection"] is True
    assert report["later_already_opened"]["used_for_selection"] is False
    assert report["split"]["purge_minutes"] == 1_440
    assert set(report["later_already_opened"]["by_candidate"]) == {
        "ridge_return",
        "lightgbm_return",
    }
    assert result.later_predictions["candidate"].nunique() == 2


def _market() -> pd.DataFrame:
    rows = 40_000
    index = pd.date_range("2026-01-01", periods=rows, freq="1min", tz="UTC")
    frame = pd.DataFrame(
        {
            "open": 100.0,
            "high": 100.1,
            "low": 99.9,
            "close": 100.0,
            "volume": 10.0,
            "entry_side": None,
            "state_1m": "RANGE",
            "state_5m": "BREAKOUT",
            "context_15m": "RANGE",
            "structural_direction": "long",
            "funding_rate": 0.0,
            "sma_gap_bps": 1.0,
            "regime_strength_score": 50.0,
            "bbwp_percentile": 30.0,
            "ema_gap_bps_signed": 2.0,
            "rsi": 55.0,
            "breakout_volume_ratio": 1.2,
            "regime_5m_strength_percentile": 60.0,
            "regime_5m_bbwp_percentile": 35.0,
            "regime_5m_ema_gap_bps": 3.0,
            "regime_5m_breakout_volume_ratio": 1.3,
        },
        index=index,
    )
    entry_column = frame.columns.get_loc("entry_side")
    direction_column = frame.columns.get_loc("structural_direction")
    for number, position in enumerate(range(100, rows - 1, 500)):
        side = "long" if number % 2 == 0 else "short"
        frame.iloc[position, entry_column] = side
        frame.iloc[position:, direction_column] = side
    return frame
