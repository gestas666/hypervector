"""Tests for causal HIP-3 oil shock-reversion signals."""

from __future__ import annotations

from importlib import import_module, util

import pandas as pd
import pytest


_MODULE = "hypervector.research.hip3_oil_shock_reversion_signals"


def test_builds_fresh_symmetric_reversion_entries() -> None:
    """A continuing shock fires once, while a sign flip fires the other side."""
    spec = util.find_spec(_MODULE)
    assert spec is not None, "oil shock-reversion signal module is missing"
    module = import_module(_MODULE)
    config_type = getattr(module, "Hip3OilShockReversionConfig", None)
    builder = getattr(module, "build_hip3_oil_shock_reversion_signals", None)
    assert config_type is not None and callable(builder)
    index = pd.date_range("2026-06-01", periods=10, freq="5min", tz="UTC")
    bars = pd.DataFrame(
        {
            "close": [100.0] * 6 + [90.0, 90.0, 110.0, 110.0],
            "gap_before_bars": [0] * 10,
        },
        index=index,
    )
    config = config_type(
        return_lookback_bars=2,
        threshold_lookback_bars=4,
        minimum_history_bars=4,
        shock_quantile=0.75,
    )

    signals = builder(bars, config)

    assert signals.loc[index[6], "long_entry"]
    assert not signals.loc[index[7], "long_entry"]
    assert signals.loc[index[8], "short_entry"]
    assert signals.loc[index[8], "long_exit"]
    assert signals.loc[index[6], "signal_name"] == "hip3_oil_shock_reversion_long@5m"


def test_rejects_target_not_above_stop_distance() -> None:
    """The frozen positive-payoff barrier relationship is explicit."""
    module = import_module(_MODULE)

    with pytest.raises(ValueError, match="target must exceed stop"):
        module.Hip3OilShockReversionConfig(target_bps=20.0, stop_bps=30.0)
