"""Integration tests for the local reviewed Cipher source adapter."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from hypervector.research.backtest_lab_cipher_adapter import (
    compute_cipher_bundle_components,
    compute_cipher_component_states,
    compute_market_cipher_signal_components,
    inspect_backtest_lab_sources,
)


BACKTEST_LAB = Path(__file__).resolve().parents[2] / "backtest-lab" / "backtest_lab"


def _bars(rows: int = 320) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=rows, freq="5min", tz=UTC)
    phase = np.arange(rows, dtype=float)
    close = 100.0 + np.sin(phase / 8.0) + phase * 0.002
    opening = np.concatenate(([close[0]], close[:-1]))
    return pd.DataFrame(
        {
            "bar_open_at": index,
            "open": opening,
            "high": np.maximum(opening, close) + 0.2,
            "low": np.minimum(opening, close) - 0.2,
            "close": close,
            "volume": 10.0 + np.cos(phase / 5.0),
        }
    )


@pytest.mark.skipif(not BACKTEST_LAB.is_dir(), reason="local backtest-lab unavailable")
def test_source_identity_matches_supplied_pine_files() -> None:
    """The adapter must bind to the exact local Pine sources supplied by the user."""
    identity = inspect_backtest_lab_sources(BACKTEST_LAB)

    assert identity["cipher_a_pine_sha256"] == (
        "17c0294b0f815c5e6a889b03c17a3a4136595c1030f8baabce2426dfb392434f"
    )
    assert identity["cipher_b_pine_sha256"] == (
        "0846dcabdd190b0d6880f13d58f955757720bf3777e77110bcb159c351c09bf3"
    )
    assert identity["cipher_dbsi_pine_sha256"] == (
        "1586777c02fb427c9809573992aefb59c24a402deb74bbe997c64de22948b860"
    )
    assert identity["krown_rsi_ema_pine_sha256"] == (
        "dd28f9cba352990dbe82d7b6189941cb2ef254fdc41bdf3f17a49c4d7d8668c0"
    )


@pytest.mark.skipif(not BACKTEST_LAB.is_dir(), reason="local backtest-lab unavailable")
def test_component_states_are_aligned_and_mutually_exclusive() -> None:
    """The corrected adapter must return one causal state per completed bar."""
    bars = _bars()

    states = compute_cipher_component_states(bars, BACKTEST_LAB, bar_minutes=5)

    assert states.index.equals(pd.DatetimeIndex(bars["bar_open_at"]))
    assert states.columns.tolist() == ["cipher_a", "cipher_b", "cipher_dbsi"]
    assert np.isin(states.to_numpy(), (-1, 0, 1)).all()
    assert states.iloc[240:].ne(0).any().all()


@pytest.mark.skipif(not BACKTEST_LAB.is_dir(), reason="local backtest-lab unavailable")
def test_gap_resets_components_and_requires_fresh_warmup() -> None:
    """Indicator state must not carry through missing market history."""
    bars = _bars()
    bars.loc[260:, "bar_open_at"] += pd.Timedelta(hours=1)

    states = compute_cipher_component_states(bars, BACKTEST_LAB, bar_minutes=5)

    assert states.iloc[:239].eq(0).all().all()
    assert states.iloc[260:].eq(0).all().all()


@pytest.mark.skipif(not BACKTEST_LAB.is_dir(), reason="local backtest-lab unavailable")
def test_bundle_uses_cipher_a_ribbon_as_persistent_trend() -> None:
    """Documented A context must follow its EMA 11/34 ribbon, not A symbols."""
    bars = _bars(360)
    bars["close"] = np.linspace(100.0, 200.0, len(bars))
    bars["open"] = bars["close"].shift(1, fill_value=100.0)
    bars["high"] = bars[["open", "close"]].max(axis=1) + 0.2
    bars["low"] = bars[["open", "close"]].min(axis=1) - 0.2

    components = compute_cipher_bundle_components(bars, BACKTEST_LAB, bar_minutes=5)

    assert components.columns.tolist() == [
        "cipher_a_trend",
        "cipher_b_trigger",
        "cipher_b_cross_trigger",
        "cipher_b_money_flow",
        "cipher_dbsi",
    ]
    assert components.iloc[:239].eq(0).all().all()
    assert components.loc[components.index[239] :, "cipher_a_trend"].eq(1).all()
    assert np.isin(components["cipher_b_trigger"], (-1, 0, 1)).all()


@pytest.mark.skipif(not BACKTEST_LAB.is_dir(), reason="local backtest-lab unavailable")
def test_signal_components_are_append_invariant() -> None:
    """Future bars must not revise any earlier Market Cipher component."""
    bars = _bars(360)

    prefix = compute_market_cipher_signal_components(
        bars.iloc[:320], BACKTEST_LAB, bar_minutes=5
    )
    full = compute_market_cipher_signal_components(
        bars, BACKTEST_LAB, bar_minutes=5
    ).loc[prefix.index]

    pd.testing.assert_frame_equal(prefix, full)
    assert {"krown_rsi", "krown_rsi_ema", "krown_direction"}.issubset(full.columns)
