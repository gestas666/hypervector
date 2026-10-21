"""Causal contracts for the backend regime-component telemetry bank."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hypervector.live.canonical_regime_components import build_regime_component_frame


def _bars(rows: int = 900) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=rows, freq="1min", tz="UTC")
    phase = np.arange(rows, dtype=float)
    close = 100.0 + phase * 0.01 + np.sin(phase / 17.0) * 0.4
    opening = close - np.sin(phase / 9.0) * 0.08
    return pd.DataFrame(
        {
            "open": opening,
            "high": np.maximum(opening, close) + 0.12,
            "low": np.minimum(opening, close) - 0.12,
            "close": close,
            "volume": 100.0 + (phase % 23.0) * 3.0,
        },
        index=index,
    )


def test_component_bank_contains_every_requested_observe_only_family() -> None:
    result = build_regime_component_frame(_bars())

    assert {
        "ema_21_55_gap_bps",
        "sma_100_200_gap_bps",
        "ema_11_34_direction",
        "harsi_direction",
        "harsi_smoothed_rsi",
        "choppiness_14",
        "mtf_5m_bias",
        "mtf_15m_bias",
        "trend_slope_bps",
        "trend_r2",
        "self_aware_tqi",
    }.issubset(result.columns)
    latest = result.iloc[-1]
    assert (
        latest[["ema_21_55_gap_bps", "choppiness_14", "trend_r2", "self_aware_tqi"]]
        .notna()
        .all()
    )
    assert int(latest["ema_11_34_direction"]) in {-1, 0, 1}
    assert int(latest["harsi_direction"]) in {-1, 0, 1}
    assert 0.0 <= float(latest["trend_r2"]) <= 1.0
    assert 0.0 <= float(latest["self_aware_tqi"]) <= 1.0


def test_component_bank_is_prefix_invariant_and_uses_no_future_bars() -> None:
    bars = _bars()
    prefix = build_regime_component_frame(bars.iloc[:700])
    full = build_regime_component_frame(bars)

    pd.testing.assert_series_equal(prefix.iloc[-1], full.loc[prefix.index[-1]])
