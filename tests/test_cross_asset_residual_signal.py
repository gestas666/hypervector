"""Causality tests for cross-asset residual state construction."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pandas.testing as pdt
import pytest

from hypervector.research.cross_asset_residual_models import (
    CrossAssetResidualConfig,
)
from hypervector.research.cross_asset_residual_signal import (
    build_residual_signals,
    build_residual_states,
)


def _prices(rows: int = 140) -> tuple[pd.Series, pd.Series]:
    index = pd.date_range("2026-01-01", periods=rows, freq="5min", tz="UTC")
    base = 4.0 + np.linspace(0.0, 0.05, rows)
    residual = 0.004 * np.sin(np.arange(rows) / 3.0)
    residual[70] = -0.04
    residual[100] = 0.04
    right = pd.Series(np.exp(base), index=index)
    left = pd.Series(np.exp(base + residual), index=index)
    return left, right


def _config() -> CrossAssetResidualConfig:
    return CrossAssetResidualConfig(
        lookback_bars=30,
        zscore_window_bars=20,
        refit_interval_bars=10,
        entry_z=1.5,
        exit_z=0.5,
        stop_z=4.0,
        minimum_abs_error_correction_t=0.0,
    )


def test_state_fit_ends_before_the_completed_decision_bar() -> None:
    """Every fit and z-score reference window must exclude the current bar."""
    left, right = _prices()
    states = build_residual_states(left, right, "BTC", "ETH", _config())

    resolved = states.dropna(subset=["hedge_ratio"])
    assert not resolved.empty
    assert (
        pd.to_datetime(resolved["fit_end_utc"], utc=True) <= resolved["bar_open_at"]
    ).all()
    assert (
        pd.to_datetime(resolved["decision_time_utc"], utc=True)
        == resolved["bar_open_at"] + pd.Timedelta(minutes=5)
    ).all()


def test_future_append_cannot_change_prior_residual_states() -> None:
    """Appending unseen prices must preserve every prior state exactly."""
    left, right = _prices(160)
    before = build_residual_states(
        left.iloc[:120], right.iloc[:120], "BTC", "ETH", _config()
    )
    after = build_residual_states(left, right, "BTC", "ETH", _config()).iloc[:120]

    pdt.assert_frame_equal(before.reset_index(drop=True), after.reset_index(drop=True))


def test_signal_builder_emits_both_spread_directions_on_threshold_onsets() -> None:
    """Large negative and positive residual shocks map to opposite pair sides."""
    left, right = _prices()
    states = build_residual_states(left, right, "BTC", "ETH", _config())
    signals = build_residual_signals(states, _config())

    assert {signal.direction for signal in signals} == {
        "long_spread",
        "short_spread",
    }
    assert all(signal.execution_authority == "none" for signal in signals)


def test_state_builder_rejects_misaligned_or_nonfinite_inputs() -> None:
    """Pair evidence cannot silently align or impute malformed prices."""
    left, right = _prices()
    with pytest.raises(ValueError, match="aligned"):
        build_residual_states(left.iloc[:-1], right, "BTC", "ETH", _config())

    malformed = left.copy()
    malformed.iloc[4] = np.nan
    with pytest.raises(ValueError, match="positive and finite"):
        build_residual_states(malformed, right, "BTC", "ETH", _config())
