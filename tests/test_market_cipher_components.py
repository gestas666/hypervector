"""Tests for causal Market Cipher decision-time components."""

from __future__ import annotations

from datetime import UTC

import numpy as np
import pandas as pd

from hypervector.research.market_cipher_components import (
    build_market_cipher_components,
)


def _bars(rows: int = 120) -> pd.DataFrame:
    """Return deterministic 15-minute OHLCV bars."""
    close = np.linspace(100.0, 112.0, rows)
    opening = close - 0.5
    return pd.DataFrame(
        {
            "bar_open_at": pd.date_range(
                "2026-01-01", periods=rows, freq="15min", tz=UTC
            ),
            "open": opening,
            "high": close + 0.75,
            "low": opening - 0.75,
            "close": close,
            "volume": np.full(rows, 10.0),
        }
    ).set_index("bar_open_at")


def _indicator_arrays(rows: int) -> dict[str, np.ndarray]:
    """Return aligned synthetic upstream indicator arrays."""
    wt1 = np.linspace(-10.0, 10.0, rows)
    wt2 = wt1 + 1.0
    wt1[80:] = wt2[80:] + 1.0
    return {
        "wt1": wt1,
        "wt2": wt2,
        "ema_11": np.linspace(99.0, 111.0, rows),
        "ema_15": np.linspace(98.5, 110.0, rows),
        "ema_34": np.linspace(98.0, 108.0, rows),
        "rsi_14": np.linspace(40.0, 60.0, rows),
        "stoch_k": np.linspace(10.0, 90.0, rows),
        "stoch_d": np.linspace(12.0, 88.0, rows),
        "krown_rsi": np.linspace(30.0, 75.0, rows),
        "krown_rsi_ema": np.linspace(32.0, 70.0, rows),
        "krown_direction": np.ones(rows, dtype=np.int8),
    }


def test_component_frame_separates_money_flow_vwap_and_volume() -> None:
    """Three distinct confluence concepts must not be conflated."""
    bars = _bars()
    bars.iloc[100, bars.columns.get_loc("volume")] = 20.0

    result = build_market_cipher_components(
        bars, bar_minutes=15, **_indicator_arrays(len(bars))
    )

    assert result.loc[result.index[59], "money_flow_value"] == 35.0
    assert result.loc[result.index[59], "money_flow_direction"] == 1
    assert result.loc[result.index[95], "price_vwap_alignment"] == 1
    assert result.loc[result.index[100], "volume_ratio"] == 2.0
    assert result.loc[result.index[100], "volume_above_average"]
    assert result.loc[result.index[100], "volume_surge"]
    assert "ema_15" in result.columns
    assert result.loc[result.index[100], "krown_direction"] == 1
    assert result.loc[result.index[100], "krown_zone_context"] == 1


def test_component_frame_emits_only_actual_wave_cross_bar() -> None:
    """A WaveTrend cross is an event pulse rather than a persistent state."""
    bars = _bars()

    result = build_market_cipher_components(
        bars, bar_minutes=15, **_indicator_arrays(len(bars))
    )

    cross_rows = result.index[result["wave_cross"].ne(0)]
    assert cross_rows.tolist() == [result.index[80]]
    assert result.loc[result.index[80], "wave_cross"] == 1


def test_component_frame_preserves_unknown_warmup() -> None:
    """Unavailable rolling values must stay unavailable, not gain free points."""
    bars = _bars()

    result = build_market_cipher_components(
        bars, bar_minutes=15, **_indicator_arrays(len(bars))
    )

    assert np.isnan(result.loc[result.index[18], "volume_ratio"])
    assert np.isnan(result.loc[result.index[58], "money_flow_value"])
    assert result.loc[result.index[58], "money_flow_direction"] == 0
    assert np.isnan(result.loc[result.index[94], "price_vwap"])
    assert result.loc[result.index[94], "price_vwap_alignment"] == 0
