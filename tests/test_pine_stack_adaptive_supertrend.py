"""Causal tests for the corrected CS adaptive-SuperTrend entry source."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hypervector.research.pine_stack_adaptive_supertrend import (
    AdaptiveSupertrendConfig,
    build_adaptive_supertrend,
    pine_rma,
)


def _bars(rows: int = 160) -> pd.DataFrame:
    """Return deterministic 15m bars with a trend reversal."""
    up = np.linspace(100.0, 125.0, rows // 2)
    down = np.linspace(125.0, 92.0, rows - rows // 2)
    close = np.concatenate((up, down))
    open_ = np.concatenate(([close[0]], close[:-1]))
    return pd.DataFrame(
        {
            "bar_open_at": pd.date_range(
                "2026-01-01", periods=rows, freq="15min", tz="UTC"
            ),
            "open": open_,
            "high": np.maximum(open_, close) + 0.6,
            "low": np.minimum(open_, close) - 0.6,
            "close": close,
            "volume": np.linspace(100.0, 300.0, rows),
        }
    )


def test_pine_rma_uses_sma_seed_then_wilder_recurrence() -> None:
    """Pine RMA parity requires an SMA seed, not an EWM first-value seed."""
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])

    result = pine_rma(values, length=3)

    assert np.isnan(result[:2]).all()
    assert result[2] == pytest.approx(2.0)
    assert result[3] == pytest.approx(8.0 / 3.0)
    assert result[4] == pytest.approx(31.0 / 9.0)


def test_adaptive_supertrend_emits_completed_bar_onsets_and_factor() -> None:
    """Entry state must be timestamped when its native bar becomes knowable."""
    result = build_adaptive_supertrend(_bars(), bar_minutes=15)
    ready = result.loc[result["selected_factor"].notna()]

    assert not ready.empty
    assert set(ready["trend_state"].unique()).issubset({-1, 1})
    assert ready["selected_factor"].between(1.0, 5.0).all()
    assert ready["trailing_stop"].notna().all()
    assert result["long_onset"].any()
    assert result["short_onset"].any()
    assert (
        result["decision_time_utc"] == result["bar_open_at"] + pd.Timedelta(minutes=15)
    ).all()


def test_adaptive_supertrend_is_append_invariant() -> None:
    """Future bars must not alter an earlier adaptive factor or signal."""
    bars = _bars()
    before = build_adaptive_supertrend(bars.iloc[:120], bar_minutes=15)
    after = build_adaptive_supertrend(bars, bar_minutes=15).iloc[:120]

    pd.testing.assert_frame_equal(before, after.reset_index(drop=True))


def test_adaptive_supertrend_rejects_invalid_native_timing() -> None:
    """The backend must fail closed on mismatched native bar timestamps."""
    bars = _bars(20)
    bars.loc[3, "bar_open_at"] += pd.Timedelta(minutes=1)

    with pytest.raises(ValueError, match="native 15-minute"):
        build_adaptive_supertrend(
            bars,
            bar_minutes=15,
            config=AdaptiveSupertrendConfig(atr_period=3),
        )
