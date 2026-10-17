"""Regression: SL/TP must trigger on bar extremes and stop fills pay slippage.

compute_trial_metrics used to call VectorBT with close only, so a stop pierced
by the bar low (but not the close) never fired, and StopLimit fills skipped the
configured slippage.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hypervector.sweep.costs import ZERO_COST, CostModel
from hypervector.sweep.exits import ExitConfig
from hypervector.sweep.metrics import compute_trial_metrics
from hypervector.sweep.sizing import RiskConfig


def _bars(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    o, h, lo, c = (np.asarray(col, dtype=float) for col in zip(*rows))
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-05-01", periods=len(rows), freq="1min", tz="UTC"),
            "open": o,
            "high": h,
            "low": lo,
            "close": c,
            "volume": 1.0,
        }
    )


def _signals(n: int, entry: int, exit_: int) -> tuple[pd.Series, pd.Series]:
    entries = pd.Series(False, index=pd.RangeIndex(n))
    exits = pd.Series(False, index=pd.RangeIndex(n))
    entries.iloc[entry] = True
    exits.iloc[exit_] = True
    return entries, exits


FLAT = (100.0, 100.0, 100.0, 100.0)
# 1% stop, 2% target; risk 1% / stop 1% = exactly 1x notional
FIXED = ExitConfig(mode="fixed_rr", sl_pct=0.01, rr=2.0)
ONE_X = RiskConfig(risk_pct_min=0.01, risk_pct_max=0.01)


def _run(df: pd.DataFrame, direction: str = "long", cost: CostModel = ZERO_COST, **kw: object) -> dict:
    entries, exits = _signals(len(df), 2, len(df) - 2)
    return compute_trial_metrics(
        df["close"],
        entries,
        exits,
        direction=direction,
        df=df,
        cost=cost,
        exit_cfg=kw.pop("exit_cfg", FIXED),
        risk_cfg=ONE_X,
        **kw,
    )


def test_long_stop_fires_when_the_low_pierces_it_but_the_close_does_not() -> None:
    df = _bars([FLAT, FLAT, FLAT, FLAT, (100.0, 100.2, 98.5, 100.0), FLAT, FLAT, FLAT])
    m = _run(df)

    assert m["trade_count"] == 1
    assert m["net_pnl"] == pytest.approx(10_000.0 * (99.0 / 100.0 - 1.0), rel=1e-9)
    assert m["stop_fill_model"] == "intrabar_ohlc_stopmarket"


def test_short_stop_fires_when_the_high_pierces_it() -> None:
    df = _bars([FLAT, FLAT, FLAT, (100.0, 101.6, 99.8, 100.0), FLAT, FLAT])
    m = _run(df, "short")

    assert m["net_pnl"] == pytest.approx(-10_000.0 * 0.01, rel=1e-9)


def test_stop_exit_pays_the_configured_slippage() -> None:
    df = _bars([FLAT, FLAT, FLAT, FLAT, (100.0, 100.2, 98.5, 100.0), FLAT, FLAT, FLAT])
    slip = CostModel(taker_fee=0.0, slippage_bps=10.0, funding_rate_1h=0.0)
    m = _run(df, cost=slip)

    entry_fill = 100.0 * 1.001
    units = 10_000.0 / 100.0  # VectorBT values the order at the bar price
    exit_fill = 99.0 * (1.0 - 0.001)  # stop-market: slippage applies
    assert m["net_pnl"] == pytest.approx(units * (exit_fill - entry_fill), rel=1e-9)


def test_take_profit_fills_at_the_target_inside_the_bar() -> None:
    df = _bars([FLAT, FLAT, FLAT, (100.0, 102.5, 99.9, 101.0), FLAT, FLAT])
    m = _run(df)

    assert m["net_pnl"] == pytest.approx(10_000.0 * 0.02, rel=1e-9)


def test_gap_through_the_stop_fills_at_the_open() -> None:
    df = _bars([FLAT, FLAT, FLAT, (97.0, 97.5, 96.5, 97.2), FLAT, FLAT])
    m = _run(df)

    assert m["net_pnl"] == pytest.approx(10_000.0 * (97.0 / 100.0 - 1.0), rel=1e-9)


def test_entry_bar_extremes_do_not_trigger_the_new_stop() -> None:
    rows = [FLAT, FLAT, (100.0, 100.1, 98.0, 100.0), FLAT, (100.0, 100.0, 100.0, 103.0), (103.0, 103.0, 103.0, 103.0)]
    df = _bars(rows)
    entries, exits = _signals(len(df), 2, len(df) - 1)
    m = compute_trial_metrics(
        df["close"], entries, exits, df=df, cost=ZERO_COST, exit_cfg=ExitConfig(mode="fixed_rr", sl_pct=0.01, rr=50.0), risk_cfg=ONE_X
    )

    assert m["net_pnl"] == pytest.approx(10_000.0 * 0.03, rel=1e-9)


def test_close_only_input_keeps_close_based_evaluation() -> None:
    close = pd.Series([100.0, 100.0, 100.0, 99.5, 100.0, 100.0, 100.0])
    entries, exits = _signals(len(close), 2, 5)
    m = compute_trial_metrics(close, entries, exits, cost=ZERO_COST, exit_cfg=FIXED, risk_cfg=ONE_X)

    assert m["trade_count"] == 1
    assert m["net_pnl"] == pytest.approx(0.0, abs=1e-9)


def test_intrabar_stops_can_be_disabled_for_legacy_close_only_results() -> None:
    df = _bars([FLAT, FLAT, FLAT, FLAT, (100.0, 100.2, 98.5, 100.0), FLAT, FLAT, FLAT])
    m = _run(df, intrabar_stops=False)

    assert m["net_pnl"] == pytest.approx(0.0, abs=1e-9)
    assert m["stop_fill_model"] == "close_only_stoplimit"
