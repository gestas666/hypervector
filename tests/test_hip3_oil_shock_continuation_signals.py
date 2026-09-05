"""Tests for causal HIP-3 oil shock-continuation signals."""

from __future__ import annotations

from importlib import import_module, util

import pandas as pd

from hypervector.research.hip3_oil_shock_reversion_signals import (
    Hip3OilShockReversionConfig,
)


_MODULE = "hypervector.research.hip3_oil_shock_continuation_signals"


def test_continuation_signal_module_exists() -> None:
    """The distinct continuation hypothesis has an explicit module identity."""
    assert util.find_spec(_MODULE) is not None


def test_continuation_enters_in_the_shock_direction_once() -> None:
    """A negative shock shorts and a later positive shock reverses long."""
    module = import_module(_MODULE)
    builder = getattr(module, "build_hip3_oil_shock_continuation_signals", None)
    assert callable(builder)
    index = pd.date_range("2026-06-01", periods=10, freq="5min", tz="UTC")
    bars = pd.DataFrame(
        {
            "close": [100.0] * 6 + [90.0, 90.0, 110.0, 110.0],
            "gap_before_bars": [0] * 10,
        },
        index=index,
    )
    config = Hip3OilShockReversionConfig(
        return_lookback_bars=2,
        threshold_lookback_bars=4,
        minimum_history_bars=4,
        shock_quantile=0.75,
    )

    signals = builder(bars, config)

    assert signals.loc[index[6], "short_entry"]
    assert not signals.loc[index[7], "short_entry"]
    assert signals.loc[index[8], "long_entry"]
    assert signals.loc[index[8], "short_exit"]
    assert signals.loc[index[6], "signal_name"] == (
        "hip3_oil_shock_continuation_short@5m"
    )
    assert set(signals["execution_authority"]) == {"none"}
