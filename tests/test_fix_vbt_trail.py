"""Regression: trail mode applies one trailing stop that follows the position.

A second, hand-rolled trail (_trail_exits) was OR'd into the strategy exits. It
ignored strategy and VectorBT exits, so a re-entry inherited the stale stop of
the previous trade and was closed prematurely.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hypervector.sweep.costs import ZERO_COST
from hypervector.sweep.exits import ExitConfig, apply_exit_mode
from hypervector.sweep.metrics import compute_trial_metrics

WARMUP = 30
TRAIL = ExitConfig(mode="trail", trail_atr_mult=2.0)


def _bars(path: list[float]) -> pd.DataFrame:
    c = np.asarray([100.0] * WARMUP + path, dtype=float)
    o = np.concatenate([[c[0]], c[:-1]])
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-06-01", periods=len(c), freq="1min", tz="UTC"),
            "open": o,
            "high": np.maximum(o, c) + 1.25,
            "low": np.minimum(o, c) - 1.25,
            "close": c,
            "volume": 1.0,
        }
    )


def _flags(n: int, bars: list[int]) -> pd.Series:
    out = pd.Series(False, index=pd.RangeIndex(n))
    out.iloc[[WARMUP + b for b in bars]] = True
    return out


def test_trail_mode_does_not_add_a_second_stop_to_strategy_exits() -> None:
    df = _bars([100, 110, 120, 118, 113, 113, 116, 117, 118, 118])
    entries = _flags(len(df), [0, 3])
    exits = _flags(len(df), [2])

    out_entries, out_exits, stop, tp = apply_exit_mode(df, entries, exits, direction="long", cfg=TRAIL)

    assert out_entries.equals(entries)
    assert out_exits.equals(exits)
    assert stop.notna().all()
    assert tp.isna().all()


def test_reentry_does_not_inherit_the_previous_trades_stop() -> None:
    df = _bars([100, 110, 120, 118, 113, 113, 116, 117, 118, 118])
    entries = _flags(len(df), [0, 3])
    exits = _flags(len(df), [2])

    m = compute_trial_metrics(
        df["close"], entries, exits, df=df, cost=ZERO_COST, exit_cfg=TRAIL, fixed_notional_fraction=1.0
    )

    # trade 1: 100 -> 120 by the strategy exit; trade 2 (118) stays open to the
    # last bar (118) because its own trail (from 118, ATR at entry) is never hit.
    assert m["trade_count"] == 2
    assert m["net_pnl"] == pytest.approx(10_000.0 * 0.20, rel=1e-9)


def test_trailing_stop_ratchets_on_bar_highs_and_fills_intrabar() -> None:
    df = _bars([100, 105, 110, 110, 104, 104, 104])
    entries = _flags(len(df), [0])
    exits = _flags(len(df), [6])

    m = compute_trial_metrics(
        df["close"], entries, exits, df=df, cost=ZERO_COST, exit_cfg=TRAIL, fixed_notional_fraction=1.0
    )

    # stop distance at entry = 2 * ATR(2.5) / 100 = 5%; highest high = 111.25
    stop_price = 111.25 * (1.0 - 0.05)
    assert m["trade_count"] == 1
    assert m["net_pnl"] == pytest.approx(10_000.0 * (stop_price / 100.0 - 1.0), rel=1e-9)
