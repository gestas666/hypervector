"""Signal-adapter tests for four-Pine shared bar portfolio screening."""

from __future__ import annotations

import numpy as np
import pandas as pd

from hypervector.research.pine_stack_portfolio_adapter import (
    declared_pine_stack_exit_variants,
    pine_stack_portfolio_signals,
)


def _features() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=8, freq="15min", tz="UTC")
    return pd.DataFrame(
        {
            "bar_open_at": index,
            "cs_long_onset": [False, True, False, False, False, False, True, False],
            "cs_short_onset": [False, False, False, False, True, False, False, False],
            "trend_levels_state": [0, 1, 1, -1, -1, -1, 1, 1],
            "tp_density_80_onset": [
                False,
                False,
                True,
                False,
                False,
                False,
                False,
                False,
            ],
            "tp_density_100_onset": [
                False,
                False,
                False,
                False,
                False,
                True,
                False,
                False,
            ],
        }
    )


def _entries() -> pd.DataFrame:
    features = _features()
    return pd.DataFrame(
        {
            "candidate": ["cs_base", "cs_base", "cs_base"],
            "symbol": ["BTC"] * 3,
            "signal_bar_open_at": features["bar_open_at"].iloc[[1, 4, 6]].tolist(),
            "decision_time_utc": features["bar_open_at"].iloc[[2, 5, 7]].tolist(),
            "side": ["long", "short", "long"],
            "execution_authority": ["none"] * 3,
        }
    )


def test_portfolio_adapter_preserves_entry_timing_and_source_exit() -> None:
    """Signal-bar decisions must fill on the following native bar only."""
    signals = pine_stack_portfolio_signals(
        _features(), _entries(), candidate="cs_base", exit_variant="cs_flip"
    )

    assert signals.index.equals(pd.DatetimeIndex(_features()["bar_open_at"]))
    assert signals["long_entry"].tolist() == [
        False,
        True,
        False,
        False,
        False,
        False,
        True,
        False,
    ]
    assert signals["short_entry"].iloc[4]
    assert signals["long_exit"].iloc[4]
    assert signals["short_exit"].iloc[6]
    assert signals["execution_authority"].eq("none").all()


def test_portfolio_exit_ablations_add_only_declared_causal_events() -> None:
    """TP and structural challengers must retain the source CS flip exit."""
    base = pine_stack_portfolio_signals(
        _features(), _entries(), candidate="cs_base", exit_variant="cs_flip"
    )
    tp = pine_stack_portfolio_signals(
        _features(), _entries(), candidate="cs_base", exit_variant="tp80_or_cs"
    )
    trend = pine_stack_portfolio_signals(
        _features(), _entries(), candidate="cs_base", exit_variant="trend_or_cs"
    )

    assert set(declared_pine_stack_exit_variants()) == {
        "cs_flip",
        "trend_or_cs",
        "tp80_or_cs",
        "tp100_or_cs",
    }
    assert (tp["long_exit"] | ~base["long_exit"]).all()
    assert tp["long_exit"].iloc[2]
    assert trend["long_exit"].iloc[3]
    assert np.array_equal(base["long_entry"], tp["long_entry"])
